#!/usr/bin/env python3
"""
并行执行器
负责在多台设备上并行执行取证任务
"""

import logging
import time
import json
from typing import List, Dict, Any, Optional, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed, Future
from threading import Lock, Event
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass

from core.device_manager import DeviceManager, Device, DeviceStatus
from core.adb_controller import ADBController
from core.recorder import ScreenRecorder
from core.ui_locator import UILocator
from task.task_dispatcher import TaskDispatcher, DispatchStrategy
from task.task_model import Task, TaskResult, TaskStatus
from task.task_loader import TaskLoader

logger = logging.getLogger(__name__)


@dataclass
class DeviceWorkerContext:
    """设备工作线程上下文"""
    device_id: str
    adb: ADBController
    recorder: ScreenRecorder
    locator: UILocator
    antibot: Any = None  # TaobaoAntiBot 实例
    platform_router: Any = None  # PlatformRouter 实例


class ParallelExecutor:
    """
    并行执行器

    功能：
    - 多设备并行执行任务
    - 每台设备独立的工作线程
    - 设备级别的状态隔离
    - 实时进度跟踪
    - 汇总报告生成
    """

    def __init__(
        self,
        device_ids: List[str] = None,
        max_workers: int = None,
        enable_antibot: bool = True,
        dispatch_strategy: DispatchStrategy = DispatchStrategy.ROUND_ROBIN
    ):
        """
        初始化并行执行器

        Args:
            device_ids: 指定的设备 ID 列表，None 则自动发现
            max_workers: 最大工作线程数，默认为设备数量
            enable_antibot: 是否启用防封控
            dispatch_strategy: 任务分配策略
        """
        self.device_manager = DeviceManager()
        self.dispatcher = TaskDispatcher(strategy=dispatch_strategy)
        self.enable_antibot = enable_antibot

        # 获取设备列表
        if device_ids:
            self._device_ids = device_ids
        else:
            available_devices = self.device_manager.get_available_devices()
            self._device_ids = [d.device_id for d in available_devices]

        if not self._device_ids:
            raise RuntimeError("没有可用的设备")

        self.max_workers = max_workers or len(self._device_ids)
        logger.info(f"并行执行器初始化: {len(self._device_ids)} 台设备, {self.max_workers} 个工作线程")

        # 设备上下文（每个设备独立的控制器）
        self._device_contexts: Dict[str, DeviceWorkerContext] = {}

        # 线程同步
        self._lock = Lock()
        self._stop_event = Event()

        # 统计
        self.stats = {
            'start_time': None,
            'end_time': None,
            'total_tasks': 0,
            'completed': 0,
            'failed': 0,
            'devices': {}
        }

        # 任务源文件
        self._source_file: Optional[str] = None

    def _init_device_context(self, device_id: str) -> DeviceWorkerContext:
        """
        初始化设备上下文

        Args:
            device_id: 设备 ID

        Returns:
            设备工作上下文
        """
        logger.info(f"初始化设备 {device_id} 的工作上下文...")

        adb = ADBController(device_id)
        recorder = ScreenRecorder(adb)
        locator = UILocator(adb)

        # 初始化防封控（如果启用）
        antibot = None
        if self.enable_antibot:
            try:
                from antibot import TaobaoAntiBot
                config = self._load_antibot_config()
                antibot = TaobaoAntiBot(
                    adb_controller=adb,
                    ui_locator=locator,
                    config=config,
                    device_id=device_id  # 关键：使用设备 ID 隔离状态
                )
                logger.info(f"设备 {device_id}: TaobaoAntiBot 已初始化")
            except Exception as e:
                logger.warning(f"设备 {device_id}: TaobaoAntiBot 初始化失败: {e}")

        # 初始化平台路由器
        platform_router = None
        try:
            from platforms import PlatformRouter
            platform_router = PlatformRouter(adb, locator, antibot)
        except Exception as e:
            logger.warning(f"设备 {device_id}: PlatformRouter 初始化失败: {e}")

        context = DeviceWorkerContext(
            device_id=device_id,
            adb=adb,
            recorder=recorder,
            locator=locator,
            antibot=antibot,
            platform_router=platform_router
        )

        self._device_contexts[device_id] = context
        return context

    def _load_antibot_config(self) -> dict:
        """加载防封控配置"""
        config_path = Path(__file__).parent.parent / 'config' / 'antibot.json'
        if config_path.exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                return config.get('taobao', {})
            except Exception as e:
                logger.warning(f"加载防封控配置失败: {e}")
        return {}

    def run(
        self,
        tasks: List[Task],
        delay_between_tasks: int = 10,
        video_duration: int = 30
    ) -> Dict[str, Any]:
        """
        并行执行任务

        Args:
            tasks: 任务列表
            delay_between_tasks: 任务间延迟（秒）
            video_duration: 视频录制时长

        Returns:
            执行统计
        """
        if not tasks:
            logger.warning("没有任务需要执行")
            return self.stats

        self.stats['start_time'] = datetime.now().isoformat()
        self.stats['total_tasks'] = len(tasks)

        # 分配任务
        task_distribution = self.dispatcher.dispatch(tasks, self._device_ids)

        logger.info("=" * 60)
        logger.info(f"开始并行执行: {len(tasks)} 个任务, {len(self._device_ids)} 台设备")
        logger.info("=" * 60)

        # 初始化设备统计
        for device_id in self._device_ids:
            self.stats['devices'][device_id] = {
                'total': len(task_distribution.get(device_id, [])),
                'completed': 0,
                'failed': 0
            }

        # 创建线程池
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures: Dict[Future, str] = {}

            # 为每台设备启动工作线程
            for device_id in self._device_ids:
                device_tasks = task_distribution.get(device_id, [])
                if not device_tasks:
                    continue

                future = executor.submit(
                    self._device_worker,
                    device_id,
                    device_tasks,
                    delay_between_tasks,
                    video_duration
                )
                futures[future] = device_id

            # 等待所有任务完成
            try:
                for future in as_completed(futures):
                    device_id = futures[future]
                    try:
                        result = future.result()
                        logger.info(f"设备 {device_id} 任务执行完成: {result}")
                    except Exception as e:
                        logger.error(f"设备 {device_id} 执行异常: {e}")

            except KeyboardInterrupt:
                logger.warning("用户中断，正在停止所有任务...")
                self._stop_event.set()
                # 等待线程优雅退出
                executor.shutdown(wait=True, cancel_futures=True)

        self.stats['end_time'] = datetime.now().isoformat()

        # 汇总统计
        self._finalize_stats()

        return self.stats

    def _device_worker(
        self,
        device_id: str,
        tasks: List[Task],
        delay_between_tasks: int,
        video_duration: int
    ) -> Dict[str, int]:
        """
        设备工作线程

        Args:
            device_id: 设备 ID
            tasks: 该设备的任务列表
            delay_between_tasks: 任务间延迟
            video_duration: 视频录制时长

        Returns:
            执行统计 {completed, failed}
        """
        logger.info(f"[{device_id}] 工作线程启动，共 {len(tasks)} 个任务")

        # 初始化设备上下文
        context = self._init_device_context(device_id)
        self.device_manager.mark_device_busy(device_id, "batch_tasks")

        completed = 0
        failed = 0

        for i, task in enumerate(tasks):
            # 检查停止信号
            if self._stop_event.is_set():
                logger.info(f"[{device_id}] 收到停止信号，终止执行")
                break

            logger.info(f"[{device_id}] 执行任务 {i+1}/{len(tasks)}: {task.product_url[:50]}...")

            try:
                success = self._execute_task(context, task, video_duration)

                with self._lock:
                    if success:
                        completed += 1
                        self.stats['completed'] += 1
                        self.stats['devices'][device_id]['completed'] += 1
                    else:
                        failed += 1
                        self.stats['failed'] += 1
                        self.stats['devices'][device_id]['failed'] += 1

                self.dispatcher.record_task_complete(device_id, success)

            except Exception as e:
                logger.error(f"[{device_id}] 任务执行异常: {e}")
                with self._lock:
                    failed += 1
                    self.stats['failed'] += 1
                    self.stats['devices'][device_id]['failed'] += 1

            # 任务间延迟（最后一个任务不需要）
            if i < len(tasks) - 1 and not self._stop_event.is_set():
                logger.info(f"[{device_id}] 等待 {delay_between_tasks} 秒...")
                time.sleep(delay_between_tasks)

        # 清理
        self.device_manager.mark_device_available(device_id, success=(failed == 0))
        logger.info(f"[{device_id}] 工作线程结束: 成功 {completed}, 失败 {failed}")

        return {'completed': completed, 'failed': failed}

    def _execute_task(
        self,
        context: DeviceWorkerContext,
        task: Task,
        video_duration: int
    ) -> bool:
        """
        执行单个任务

        Args:
            context: 设备上下文
            task: 任务
            video_duration: 视频录制时长

        Returns:
            是否成功
        """
        device_id = context.device_id
        adb = context.adb
        recorder = context.recorder
        locator = context.locator
        antibot = context.antibot
        router = context.platform_router

        # 悬浮按钮位置缓存
        screenshot_button_pos = None

        def click_screenshot_button() -> bool:
            """点击截屏按钮"""
            nonlocal screenshot_button_pos
            try:
                if screenshot_button_pos is None:
                    pos = adb.get_overlay_button_position()
                    if not pos:
                        return False
                    screenshot_button_pos = pos

                x, y = screenshot_button_pos
                if adb.tap(x, y):
                    time.sleep(1)
                    return True
                return False
            except Exception as e:
                logger.error(f"[{device_id}] 点击截屏按钮异常: {e}")
                return False

        recording_started = False

        try:
            # 检查冷却状态
            if antibot and antibot.is_cooling_down():
                remaining = antibot.get_remaining_cooldown()
                logger.warning(f"[{device_id}] 处于冷却期，等待 {int(remaining.total_seconds())} 秒")
                time.sleep(remaining.total_seconds())

            # 环境检查
            if not adb.check_connection():
                logger.error(f"[{device_id}] 设备连接异常")
                return False

            adb.wake_screen()

            # 启动录屏
            adb.enable_visual_feedback()
            time.sleep(1)

            if not recorder.start_recording():
                logger.error(f"[{device_id}] 启动录屏失败")
                return False
            recording_started = True

            # 展示北京时间
            if not adb.open_url("https://www.beijing-time.org/"):
                self._cancel_recording(recorder, recording_started)
                return False
            time.sleep(5)
            click_screenshot_button()
            time.sleep(5)

            # 平台取证
            if router:
                try:
                    handler = router.get_handler(task.product_url)
                    handler.set_screenshot_callback(click_screenshot_button)
                    success, error = handler.execute(
                        task.product_url,
                        task.video_duration or video_duration
                    )
                    if not success:
                        logger.error(f"[{device_id}] 平台取证失败: {error}")
                        if antibot:
                            antibot.record_task_done(success=False)
                        self._cancel_recording(recorder, recording_started)
                        return False
                except Exception as e:
                    logger.error(f"[{device_id}] 平台取证异常: {e}")
                    self._cancel_recording(recorder, recording_started)
                    return False

            # 停止录屏
            if not recorder.stop_recording():
                logger.error(f"[{device_id}] 停止录屏失败")
                return False

            adb.disable_visual_feedback()

            # 防封控处理
            if antibot:
                is_taobao = any(k in task.product_url.lower() for k in ['taobao', 'tmall', 'tb.cn'])
                if is_taobao:
                    should_browse, should_cooldown = antibot.record_task_complete()
                    if should_browse:
                        antibot.execute_cycle_end_actions()
                    if should_cooldown:
                        antibot.trigger_cooldown("完成多个周期")
                        antibot.close_taobao()

            # 关闭应用，保证下次初始状态
            adb.force_stop_app("com.taobao.taobao")
            adb.force_stop_app("com.a1010bao.web.rdbao")

            return True

        except Exception as e:
            logger.error(f"[{device_id}] 任务执行异常: {e}")
            self._cancel_recording(recorder, recording_started)
            return False

    def _cancel_recording(self, recorder: ScreenRecorder, recording_started: bool):
        """取消录屏"""
        if recording_started:
            try:
                recorder.cancel_recording()
            except Exception:
                pass

    def _finalize_stats(self):
        """最终统计"""
        logger.info("=" * 60)
        logger.info("并行执行完成 - 统计汇总")
        logger.info("=" * 60)
        logger.info(f"总任务数: {self.stats['total_tasks']}")
        logger.info(f"成功: {self.stats['completed']}")
        logger.info(f"失败: {self.stats['failed']}")

        if self.stats['start_time'] and self.stats['end_time']:
            start = datetime.fromisoformat(self.stats['start_time'])
            end = datetime.fromisoformat(self.stats['end_time'])
            duration = end - start
            logger.info(f"总耗时: {duration}")

        logger.info("-" * 40)
        logger.info("各设备统计:")
        for device_id, device_stats in self.stats['devices'].items():
            logger.info(f"  {device_id}: 总计 {device_stats['total']}, "
                       f"成功 {device_stats['completed']}, 失败 {device_stats['failed']}")
        logger.info("=" * 60)

    def generate_report(self, output_dir: str = None) -> str:
        """
        生成执行报告

        Args:
            output_dir: 输出目录

        Returns:
            报告文件路径
        """
        if output_dir:
            reports_dir = Path(output_dir)
        else:
            reports_dir = Path(__file__).parent.parent / 'reports'

        reports_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        report_file = reports_dir / f'parallel_report_{timestamp}.json'

        # 计算耗时
        duration_seconds = 0
        if self.stats['start_time'] and self.stats['end_time']:
            start = datetime.fromisoformat(self.stats['start_time'])
            end = datetime.fromisoformat(self.stats['end_time'])
            duration_seconds = int((end - start).total_seconds())

        report = {
            'report_time': datetime.now().isoformat(),
            'source_file': self._source_file,
            'execution_mode': 'parallel',
            'summary': {
                'total_devices': len(self._device_ids),
                'total_tasks': self.stats['total_tasks'],
                'completed': self.stats['completed'],
                'failed': self.stats['failed'],
                'duration_seconds': duration_seconds,
            },
            'devices': self.stats['devices'],
            'dispatcher': self.dispatcher.get_statistics()
        }

        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        logger.info(f"✓ 并行执行报告已生成: {report_file}")
        return str(report_file)

    def load_tasks_from_file(self, file_path: str) -> List[Task]:
        """
        从文件加载任务

        Args:
            file_path: 任务文件路径

        Returns:
            任务列表
        """
        self._source_file = str(Path(file_path).resolve())
        loader = TaskLoader()

        path = Path(file_path)
        if path.suffix == '.json':
            tasks = loader.load_from_json(file_path)
        elif path.suffix == '.csv':
            tasks = loader.load_from_csv(file_path)
        elif path.suffix == '.txt':
            tasks = loader.load_from_text(file_path)
        else:
            logger.error(f"不支持的文件格式: {path.suffix}")
            return []

        logger.info(f"从 {file_path} 加载了 {len(tasks)} 个任务")
        return tasks


def run_parallel_mode(
    task_file: str,
    device_ids: List[str] = None,
    video_duration: int = 30,
    enable_antibot: bool = True,
    strategy: str = "round_robin"
) -> bool:
    """
    运行并行模式

    Args:
        task_file: 任务文件路径
        device_ids: 设备 ID 列表（可选）
        video_duration: 视频录制时长
        enable_antibot: 是否启用防封控
        strategy: 分配策略

    Returns:
        是否成功
    """
    # 解析分配策略
    strategy_map = {
        'round_robin': DispatchStrategy.ROUND_ROBIN,
        'load_balance': DispatchStrategy.LOAD_BALANCE,
        'random': DispatchStrategy.RANDOM
    }
    dispatch_strategy = strategy_map.get(strategy, DispatchStrategy.ROUND_ROBIN)

    try:
        executor = ParallelExecutor(
            device_ids=device_ids,
            enable_antibot=enable_antibot,
            dispatch_strategy=dispatch_strategy
        )

        # 加载任务
        tasks = executor.load_tasks_from_file(task_file)
        if not tasks:
            logger.error("没有加载到任务")
            return False

        # 执行
        stats = executor.run(
            tasks=tasks,
            delay_between_tasks=10,
            video_duration=video_duration
        )

        # 生成报告
        executor.generate_report()

        return stats.get('failed', 0) == 0

    except Exception as e:
        logger.error(f"并行执行失败: {e}")
        return False


if __name__ == "__main__":
    # 测试代码
    logging.basicConfig(level=logging.INFO)

    manager = DeviceManager()
    devices = manager.get_available_devices()
    print(f"可用设备: {[d.device_id for d in devices]}")
