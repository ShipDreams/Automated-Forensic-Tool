#!/usr/bin/env python3
"""
任务管理器
负责任务队列管理、调度、执行、重试
"""

import logging
import time
from typing import Optional, List, Callable, Dict, Any
from pathlib import Path
from datetime import datetime
from queue import PriorityQueue
from dataclasses import dataclass, field

from .task_model import Task, TaskStatus, TaskResult, TaskPriority
from .task_loader import TaskLoader

logger = logging.getLogger(__name__)


@dataclass(order=True)
class PrioritizedTask:
    """带优先级的任务（用于优先队列）"""
    priority: int
    task: Task = field(compare=False)


class TaskManager:
    """
    任务管理器

    核心功能：
    - 任务队列管理（支持优先级）
    - 任务调度与执行
    - 失败重试（最多 3 次）
    - 任务状态持久化
    - 执行统计
    """

    def __init__(
        self,
        tasks_dir: str = None,
        max_retries: int = 3,
        retry_delay: int = 60
    ):
        """
        初始化任务管理器

        Args:
            tasks_dir: 任务目录路径
            max_retries: 最大重试次数
            retry_delay: 重试延迟（秒）
        """
        self.loader = TaskLoader(tasks_dir)
        self.tasks_dir = self.loader.tasks_dir
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        # 任务队列
        self._queue: PriorityQueue = PriorityQueue()
        self._all_tasks: Dict[str, Task] = {}

        # 执行器（由外部注入）
        self._executor: Optional[Callable[[Task], TaskResult]] = None

        # 回调
        self._on_task_start: List[Callable[[Task], None]] = []
        self._on_task_complete: List[Callable[[Task, TaskResult], None]] = []
        self._on_task_failed: List[Callable[[Task, str], None]] = []

        # 统计
        self.stats = {
            'total': 0,
            'completed': 0,
            'failed': 0,
            'retried': 0,
            'start_time': None,
            'end_time': None,
        }

    def set_executor(self, executor: Callable[[Task], TaskResult]):
        """
        设置任务执行器

        Args:
            executor: 执行函数，接收 Task，返回 TaskResult
        """
        self._executor = executor

    def add_task(self, task: Task) -> str:
        """
        添加任务到队列

        Args:
            task: 任务对象

        Returns:
            任务 ID
        """
        # 设置默认重试次数
        task.max_retries = self.max_retries

        # 添加到队列（优先级取负数，因为 PriorityQueue 是小顶堆）
        priority = -task.priority.value
        self._queue.put(PrioritizedTask(priority=priority, task=task))

        # 保存引用
        self._all_tasks[task.id] = task

        logger.info(f"添加任务: {task.id} ({task.product_url[:50]}...)")
        return task.id

    def add_tasks(self, tasks: List[Task]) -> List[str]:
        """批量添加任务"""
        return [self.add_task(task) for task in tasks]

    def add_url(self, url: str, **params) -> str:
        """
        通过 URL 添加任务

        Args:
            url: 商品链接
            **params: 其他任务参数

        Returns:
            任务 ID
        """
        task = Task.from_url(url, **params)
        return self.add_task(task)

    def add_urls(self, urls: List[str], **params) -> List[str]:
        """批量添加 URL"""
        return [self.add_url(url, **params) for url in urls]

    def load_tasks_from_file(self, file_path: str) -> int:
        """
        从文件加载任务

        Args:
            file_path: 文件路径

        Returns:
            加载的任务数量
        """
        path = Path(file_path)

        if path.suffix == '.json':
            tasks = self.loader.load_from_json(file_path)
        elif path.suffix == '.csv':
            tasks = self.loader.load_from_csv(file_path)
        elif path.suffix == '.txt':
            tasks = self.loader.load_from_text(file_path)
        else:
            logger.error(f"不支持的文件格式: {path.suffix}")
            return 0

        self.add_tasks(tasks)
        return len(tasks)

    def load_pending_tasks(self) -> int:
        """
        加载所有待处理任务

        Returns:
            加载的任务数量
        """
        tasks = self.loader.load_pending_tasks()
        self.add_tasks(tasks)
        return len(tasks)

    def get_next_task(self) -> Optional[Task]:
        """
        获取下一个待执行的任务

        Returns:
            任务对象，如果队列为空返回 None
        """
        if self._queue.empty():
            return None

        prioritized = self._queue.get()
        return prioritized.task

    def peek_next_task(self) -> Optional[Task]:
        """查看下一个任务（不移出队列）"""
        if self._queue.empty():
            return None
        # PriorityQueue 不支持 peek，这里简单实现
        prioritized = self._queue.get()
        self._queue.put(prioritized)
        return prioritized.task

    def execute_task(self, task: Task) -> TaskResult:
        """
        执行单个任务

        Args:
            task: 任务对象

        Returns:
            执行结果
        """
        if not self._executor:
            raise RuntimeError("未设置任务执行器，请先调用 set_executor()")

        # 标记运行中
        task.mark_running()
        self._save_task(task)

        # 触发回调
        for callback in self._on_task_start:
            try:
                callback(task)
            except Exception as e:
                logger.error(f"任务开始回调失败: {e}")

        try:
            # 执行任务
            logger.info(f"开始执行任务: {task.id}")
            result = self._executor(task)

            if result.success:
                task.mark_completed(result)
                self.stats['completed'] += 1
                logger.info(f"任务完成: {task.id}")

                # 触发完成回调
                for callback in self._on_task_complete:
                    try:
                        callback(task, result)
                    except Exception as e:
                        logger.error(f"任务完成回调失败: {e}")
            else:
                self._handle_task_failure(task, result.error or "未知错误")

        except Exception as e:
            logger.error(f"任务执行异常: {e}", exc_info=True)
            self._handle_task_failure(task, str(e))
            result = TaskResult(success=False, error=str(e))

        # 保存最终状态
        self._save_task(task)
        return result

    def _handle_task_failure(self, task: Task, error: str):
        """处理任务失败"""
        # 判断是否可重试
        can_retry = task.retry_count < self.max_retries

        task.mark_failed(error, can_retry=can_retry)

        if task.status == TaskStatus.RETRY:
            # 加回队列等待重试
            self.stats['retried'] += 1
            logger.warning(f"任务 {task.id} 将在 {self.retry_delay} 秒后重试 "
                          f"(第 {task.retry_count}/{self.max_retries} 次)")

            # 降低优先级（重试任务优先级降低）
            task.priority = TaskPriority.LOW
            self._queue.put(PrioritizedTask(
                priority=-task.priority.value + task.retry_count,
                task=task
            ))
        else:
            self.stats['failed'] += 1

            # 触发失败回调
            for callback in self._on_task_failed:
                try:
                    callback(task, error)
                except Exception as e:
                    logger.error(f"任务失败回调失败: {e}")

    def run_all(self, delay_between_tasks: int = 5) -> Dict[str, Any]:
        """
        执行所有队列中的任务

        Args:
            delay_between_tasks: 任务间延迟（秒）

        Returns:
            执行统计
        """
        self.stats['start_time'] = datetime.now().isoformat()
        self.stats['total'] = self._queue.qsize()

        logger.info(f"开始批量执行，共 {self.stats['total']} 个任务")

        while not self._queue.empty():
            task = self.get_next_task()
            if not task:
                break

            try:
                self.execute_task(task)
            except Exception as e:
                logger.error(f"执行任务 {task.id} 时发生错误: {e}")

            # 任务间延迟
            if not self._queue.empty():
                logger.info(f"等待 {delay_between_tasks} 秒后执行下一个任务...")
                time.sleep(delay_between_tasks)

        self.stats['end_time'] = datetime.now().isoformat()

        # 打印统计
        self._print_stats()

        return self.stats

    def run_single(self) -> Optional[TaskResult]:
        """
        执行单个任务

        Returns:
            执行结果，如果队列为空返回 None
        """
        task = self.get_next_task()
        if not task:
            return None

        return self.execute_task(task)

    def _save_task(self, task: Task):
        """保存任务状态"""
        try:
            task.save_to_file(self.tasks_dir)
        except Exception as e:
            logger.error(f"保存任务状态失败: {e}")

    def _print_stats(self):
        """打印执行统计"""
        logger.info("=" * 50)
        logger.info("任务执行统计")
        logger.info("=" * 50)
        logger.info(f"总任务数: {self.stats['total']}")
        logger.info(f"成功: {self.stats['completed']}")
        logger.info(f"失败: {self.stats['failed']}")
        logger.info(f"重试次数: {self.stats['retried']}")
        if self.stats['start_time'] and self.stats['end_time']:
            start = datetime.fromisoformat(self.stats['start_time'])
            end = datetime.fromisoformat(self.stats['end_time'])
            duration = end - start
            logger.info(f"总耗时: {duration}")
        logger.info("=" * 50)

    # ==================== 回调注册 ====================

    def on_task_start(self, callback: Callable[[Task], None]):
        """注册任务开始回调"""
        self._on_task_start.append(callback)

    def on_task_complete(self, callback: Callable[[Task, TaskResult], None]):
        """注册任务完成回调"""
        self._on_task_complete.append(callback)

    def on_task_failed(self, callback: Callable[[Task, str], None]):
        """注册任务失败回调"""
        self._on_task_failed.append(callback)

    # ==================== 状态查询 ====================

    def get_task(self, task_id: str) -> Optional[Task]:
        """获取任务"""
        return self._all_tasks.get(task_id)

    def get_queue_size(self) -> int:
        """获取队列大小"""
        return self._queue.qsize()

    def is_empty(self) -> bool:
        """队列是否为空"""
        return self._queue.empty()

    def get_all_tasks(self) -> List[Task]:
        """获取所有任务"""
        return list(self._all_tasks.values())

    def get_tasks_by_status(self, status: TaskStatus) -> List[Task]:
        """按状态获取任务"""
        return [t for t in self._all_tasks.values() if t.status == status]

    def cancel_task(self, task_id: str) -> bool:
        """取消任务"""
        task = self._all_tasks.get(task_id)
        if not task:
            return False

        if task.status == TaskStatus.RUNNING:
            logger.warning("无法取消正在运行的任务")
            return False

        task.mark_cancelled()
        self._save_task(task)
        return True

    def clear_queue(self):
        """清空队列"""
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except:
                break
        logger.info("任务队列已清空")

    def reset_stats(self):
        """重置统计"""
        self.stats = {
            'total': 0,
            'completed': 0,
            'failed': 0,
            'retried': 0,
            'start_time': None,
            'end_time': None,
        }
