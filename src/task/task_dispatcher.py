#!/usr/bin/env python3
"""
任务分配器
负责将任务分配到多台设备
"""

import logging
from typing import List, Dict, Optional
from enum import Enum
from dataclasses import dataclass
from queue import Queue
from threading import Lock

from .task_model import Task

logger = logging.getLogger(__name__)


class DispatchStrategy(Enum):
    """任务分配策略"""
    ROUND_ROBIN = "round_robin"     # 轮询分配
    LOAD_BALANCE = "load_balance"   # 负载均衡（基于已完成任务数）
    RANDOM = "random"               # 随机分配


@dataclass
class DeviceTaskQueue:
    """设备任务队列"""
    device_id: str
    tasks: List[Task]
    completed_count: int = 0
    failed_count: int = 0

    @property
    def pending_count(self) -> int:
        """待处理任务数"""
        return len(self.tasks) - self.completed_count - self.failed_count


class TaskDispatcher:
    """
    任务分配器

    功能：
    - 将任务列表分配到多台设备
    - 支持多种分配策略
    - 线程安全的任务获取
    """

    def __init__(self, strategy: DispatchStrategy = DispatchStrategy.ROUND_ROBIN):
        """
        初始化任务分配器

        Args:
            strategy: 分配策略
        """
        self.strategy = strategy
        self._device_queues: Dict[str, Queue] = {}
        self._device_stats: Dict[str, DeviceTaskQueue] = {}
        self._lock = Lock()
        self._all_tasks: List[Task] = []

    def dispatch(self, tasks: List[Task], device_ids: List[str]) -> Dict[str, List[Task]]:
        """
        将任务分配到设备

        Args:
            tasks: 任务列表
            device_ids: 设备 ID 列表

        Returns:
            设备任务分配字典 {device_id: [tasks]}
        """
        if not tasks:
            logger.warning("没有任务需要分配")
            return {}

        if not device_ids:
            logger.error("没有可用设备")
            return {}

        self._all_tasks = tasks
        num_devices = len(device_ids)
        num_tasks = len(tasks)

        logger.info(f"开始分配任务: {num_tasks} 个任务 -> {num_devices} 台设备")
        logger.info(f"分配策略: {self.strategy.value}")

        # 初始化设备队列
        for device_id in device_ids:
            self._device_queues[device_id] = Queue()
            self._device_stats[device_id] = DeviceTaskQueue(device_id=device_id, tasks=[])

        # 根据策略分配
        if self.strategy == DispatchStrategy.ROUND_ROBIN:
            self._dispatch_round_robin(tasks, device_ids)
        elif self.strategy == DispatchStrategy.LOAD_BALANCE:
            self._dispatch_load_balance(tasks, device_ids)
        elif self.strategy == DispatchStrategy.RANDOM:
            self._dispatch_random(tasks, device_ids)

        # 构建返回结果
        result = {}
        for device_id in device_ids:
            result[device_id] = self._device_stats[device_id].tasks
            logger.info(f"  设备 {device_id}: 分配 {len(result[device_id])} 个任务")

        return result

    def _dispatch_round_robin(self, tasks: List[Task], device_ids: List[str]):
        """轮询分配"""
        for i, task in enumerate(tasks):
            device_id = device_ids[i % len(device_ids)]
            self._assign_task(device_id, task)

    def _dispatch_load_balance(self, tasks: List[Task], device_ids: List[str]):
        """
        负载均衡分配
        优先分配给任务数最少的设备
        """
        for task in tasks:
            # 找到任务数最少的设备
            min_device = min(
                device_ids,
                key=lambda d: len(self._device_stats[d].tasks)
            )
            self._assign_task(min_device, task)

    def _dispatch_random(self, tasks: List[Task], device_ids: List[str]):
        """随机分配"""
        import random
        for task in tasks:
            device_id = random.choice(device_ids)
            self._assign_task(device_id, task)

    def _assign_task(self, device_id: str, task: Task):
        """将任务分配给设备"""
        with self._lock:
            self._device_queues[device_id].put(task)
            self._device_stats[device_id].tasks.append(task)

    def get_next_task(self, device_id: str) -> Optional[Task]:
        """
        获取设备的下一个任务

        Args:
            device_id: 设备 ID

        Returns:
            任务对象，如果队列为空返回 None
        """
        queue = self._device_queues.get(device_id)
        if not queue or queue.empty():
            return None

        with self._lock:
            try:
                return queue.get_nowait()
            except:
                return None

    def get_device_tasks(self, device_id: str) -> List[Task]:
        """获取设备的所有任务"""
        stats = self._device_stats.get(device_id)
        return stats.tasks if stats else []

    def get_device_queue_size(self, device_id: str) -> int:
        """获取设备队列剩余任务数"""
        queue = self._device_queues.get(device_id)
        return queue.qsize() if queue else 0

    def record_task_complete(self, device_id: str, success: bool):
        """
        记录任务完成

        Args:
            device_id: 设备 ID
            success: 是否成功
        """
        with self._lock:
            if device_id in self._device_stats:
                if success:
                    self._device_stats[device_id].completed_count += 1
                else:
                    self._device_stats[device_id].failed_count += 1

    def get_progress(self) -> Dict[str, any]:
        """
        获取整体进度

        Returns:
            进度信息字典
        """
        total = len(self._all_tasks)
        completed = sum(s.completed_count for s in self._device_stats.values())
        failed = sum(s.failed_count for s in self._device_stats.values())
        pending = total - completed - failed

        device_progress = {}
        for device_id, stats in self._device_stats.items():
            device_progress[device_id] = {
                'total': len(stats.tasks),
                'completed': stats.completed_count,
                'failed': stats.failed_count,
                'pending': stats.pending_count,
            }

        return {
            'total': total,
            'completed': completed,
            'failed': failed,
            'pending': pending,
            'progress_percent': round(completed / total * 100, 1) if total > 0 else 0,
            'devices': device_progress
        }

    def is_all_done(self) -> bool:
        """检查是否所有任务已完成"""
        for queue in self._device_queues.values():
            if not queue.empty():
                return False
        return True

    def get_statistics(self) -> Dict[str, any]:
        """获取统计信息"""
        return {
            'strategy': self.strategy.value,
            'total_tasks': len(self._all_tasks),
            'devices': len(self._device_queues),
            'progress': self.get_progress()
        }


if __name__ == "__main__":
    # 测试代码
    logging.basicConfig(level=logging.INFO)

    from .task_model import Task

    # 创建测试任务
    tasks = [Task.from_url(f"https://item.taobao.com/item.htm?id={i}") for i in range(10)]
    devices = ["device1", "device2", "device3"]

    # 测试轮询分配
    dispatcher = TaskDispatcher(strategy=DispatchStrategy.ROUND_ROBIN)
    result = dispatcher.dispatch(tasks, devices)

    for device_id, device_tasks in result.items():
        print(f"{device_id}: {len(device_tasks)} 任务")
