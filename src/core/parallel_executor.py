#!/usr/bin/env python3
"""
Parallel Executor
Responsible for executing forensic tasks in parallel on multiple devices.
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

from locales import t
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
    """Device worker thread context"""
    device_id: str
    adb: ADBController
    recorder: ScreenRecorder
    locator: UILocator
    base_antibot: Any = None  # AntiBot instance (for human behavior simulation in handlers)
    antibot: Any = None  # TaobaoAntiBot instance (for cycle cooldown strategy)
    platform_router: Any = None  # PlatformRouter instance


class ParallelExecutor:
    """
    Parallel Executor

    Features:
    - Multi-device parallel task execution
    - Independent worker thread per device
    - Device-level state isolation
    - Real-time progress tracking
    - Summary report generation
    """

    def __init__(
        self,
        device_ids: List[str] = None,
        max_workers: int = None,
        enable_antibot: bool = True,
        dispatch_strategy: DispatchStrategy = DispatchStrategy.ROUND_ROBIN
    ):
        """
        Initialize parallel executor.

        Args:
            device_ids: Specified device ID list, auto-discover if None
            max_workers: Maximum worker threads, defaults to device count
            enable_antibot: Whether to enable anti-detection
            dispatch_strategy: Task dispatch strategy
        """
        self.device_manager = DeviceManager()
        self.dispatcher = TaskDispatcher(strategy=dispatch_strategy)
        self.enable_antibot = enable_antibot

        # Get device list
        if device_ids:
            self._device_ids = device_ids
        else:
            available_devices = self.device_manager.get_available_devices()
            self._device_ids = [d.device_id for d in available_devices]

        if not self._device_ids:
            raise RuntimeError(t('log.no_available_devices'))

        self.max_workers = max_workers or len(self._device_ids)
        logger.info(t('log.parallel_executor_init', device_count=len(self._device_ids), worker_count=self.max_workers))

        # Device contexts (independent controller per device)
        self._device_contexts: Dict[str, DeviceWorkerContext] = {}

        # Thread synchronization
        self._lock = Lock()
        self._stop_event = Event()

        # Statistics
        self.stats = {
            'start_time': None,
            'end_time': None,
            'total_tasks': 0,
            'completed': 0,
            'failed': 0,
            'devices': {}
        }

        # Task source file
        self._source_file: Optional[str] = None

    def _init_device_context(self, device_id: str) -> DeviceWorkerContext:
        """
        Initialize device context.

        Args:
            device_id: Device ID

        Returns:
            Device work context
        """
        logger.info(t('log.init_device_context', device_id=device_id))

        adb = ADBController(device_id)
        recorder = ScreenRecorder(adb)
        locator = UILocator(adb)

        # Initialize AntiBot (for human behavior simulation in handlers)
        base_antibot = None
        if self.enable_antibot:
            try:
                from antibot import AntiBot
                base_antibot = AntiBot()
                logger.info(t('log.device_antibot_initialized', device_id=device_id))
            except Exception as e:
                logger.warning(t('log.device_antibot_init_failed', device_id=device_id, error=e))

        # Initialize TaobaoAntiBot (for cycle cooldown strategy)
        antibot = None
        if self.enable_antibot:
            try:
                from antibot import TaobaoAntiBot
                config = self._load_antibot_config()
                antibot = TaobaoAntiBot(
                    adb_controller=adb,
                    ui_locator=locator,
                    config=config,
                    device_id=device_id  # Key: use device ID to isolate state
                )
                logger.info(t('log.device_taobao_antibot_initialized', device_id=device_id))
            except Exception as e:
                logger.warning(t('log.device_antibot_init_failed', device_id=device_id, error=e))

        # Initialize platform router (pass base_antibot for handler sleep/simulation)
        platform_router = None
        try:
            from platforms import PlatformRouter
            platform_router = PlatformRouter(adb, locator, base_antibot)
        except Exception as e:
            logger.warning(t('log.device_router_init_failed', device_id=device_id, error=e))

        context = DeviceWorkerContext(
            device_id=device_id,
            adb=adb,
            recorder=recorder,
            locator=locator,
            base_antibot=base_antibot,
            antibot=antibot,
            platform_router=platform_router
        )

        self._device_contexts[device_id] = context
        return context

    def _load_antibot_config(self) -> dict:
        """Load anti-detection config"""
        config_path = Path(__file__).parent.parent / 'config' / 'antibot.json'
        if config_path.exists():
            try:
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                return config.get('taobao', {})
            except Exception as e:
                logger.warning(t('log.load_antibot_config_failed', error=e))
        return {}

    def run(
        self,
        tasks: List[Task],
        delay_between_tasks: int = 10,
        video_duration: int = 30
    ) -> Dict[str, Any]:
        """
        Execute tasks in parallel.

        Args:
            tasks: Task list
            delay_between_tasks: Delay between tasks (seconds)
            video_duration: Video recording duration

        Returns:
            Execution statistics
        """
        if not tasks:
            logger.warning(t('log.no_tasks_to_execute'))
            return self.stats

        self.stats['start_time'] = datetime.now().isoformat()
        self.stats['total_tasks'] = len(tasks)

        # Dispatch tasks
        task_distribution = self.dispatcher.dispatch(tasks, self._device_ids)

        logger.info("=" * 60)
        logger.info(t('log.parallel_execution_start', task_count=len(tasks), device_count=len(self._device_ids)))
        logger.info("=" * 60)

        # Initialize device statistics
        for device_id in self._device_ids:
            self.stats['devices'][device_id] = {
                'total': len(task_distribution.get(device_id, [])),
                'completed': 0,
                'failed': 0
            }

        # Create thread pool
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures: Dict[Future, str] = {}

            # Start worker thread for each device
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

            # Wait for all tasks to complete
            try:
                for future in as_completed(futures):
                    device_id = futures[future]
                    try:
                        result = future.result()
                        logger.info(t('log.device_task_execution_complete', device_id=device_id, result=result))
                    except Exception as e:
                        logger.error(t('log.device_execution_exception', device_id=device_id, error=e))

            except KeyboardInterrupt:
                logger.warning(t('log.user_interrupt_stopping'))
                self._stop_event.set()
                # Wait for threads to exit gracefully
                executor.shutdown(wait=True, cancel_futures=True)

        self.stats['end_time'] = datetime.now().isoformat()

        # Finalize statistics
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
        Device worker thread.

        Args:
            device_id: Device ID
            tasks: Task list for this device
            delay_between_tasks: Delay between tasks
            video_duration: Video recording duration

        Returns:
            Execution statistics {completed, failed}
        """
        logger.info(t('log.worker_thread_started', device_id=device_id, task_count=len(tasks)))

        # Initialize device context
        context = self._init_device_context(device_id)
        self.device_manager.mark_device_busy(device_id, "batch_tasks")

        completed = 0
        failed = 0

        for i, task in enumerate(tasks):
            # Check stop signal
            if self._stop_event.is_set():
                logger.info(t('log.stop_signal_received', device_id=device_id))
                break

            logger.info(t('log.executing_task_n', device_id=device_id, current=i+1, total=len(tasks), url=task.product_url[:50]))

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
                logger.error(t('log.task_execution_exception', device_id=device_id, error=e))
                with self._lock:
                    failed += 1
                    self.stats['failed'] += 1
                    self.stats['devices'][device_id]['failed'] += 1

            # Delay between tasks (not needed for last task)
            if i < len(tasks) - 1 and not self._stop_event.is_set():
                logger.info(t('log.waiting_between_tasks', device_id=device_id, seconds=delay_between_tasks))
                time.sleep(delay_between_tasks)

        # Cleanup
        self.device_manager.mark_device_available(device_id, success=(failed == 0))
        logger.info(t('log.worker_thread_ended', device_id=device_id, completed=completed, failed=failed))

        return {'completed': completed, 'failed': failed}

    def _execute_task(
        self,
        context: DeviceWorkerContext,
        task: Task,
        video_duration: int
    ) -> bool:
        """
        Execute single task.

        Args:
            context: Device context
            task: Task
            video_duration: Video recording duration

        Returns:
            Whether successful
        """
        device_id = context.device_id
        adb = context.adb
        recorder = context.recorder
        locator = context.locator
        antibot = context.antibot
        router = context.platform_router

        # Floating button position cache
        screenshot_button_pos = None

        def click_screenshot_button() -> bool:
            """Click screenshot button"""
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
                logger.error(t('log.device_click_screenshot_exception', device_id=device_id, error=e))
                return False

        recording_started = False
        task_success = False

        try:
            # Check cooldown status
            if antibot and antibot.is_cooling_down():
                remaining = antibot.get_remaining_cooldown()
                logger.warning(t('log.device_in_cooldown_waiting', device_id=device_id, seconds=int(remaining.total_seconds())))
                time.sleep(remaining.total_seconds())

            # Environment check
            if not adb.check_connection():
                logger.error(t('log.device_connection_error', device_id=device_id))
                return False

            adb.wake_screen()

            # Start recording
            adb.enable_visual_feedback()
            time.sleep(1)

            if not recorder.start_recording():
                logger.error(t('log.device_start_recording_failed', device_id=device_id))
                return False
            recording_started = True

            # Display Beijing time
            if not adb.open_url("https://www.beijing-time.org/"):
                self._cancel_recording(recorder, recording_started)
                return False
            time.sleep(5)
            click_screenshot_button()
            time.sleep(5)

            # Platform forensic
            if router:
                try:
                    handler = router.get_handler(task.product_url)
                    handler.set_screenshot_callback(click_screenshot_button)
                    success, error = handler.execute(
                        task.product_url,
                        task.video_duration or video_duration
                    )
                    if not success:
                        logger.error(t('log.device_platform_failed', device_id=device_id, error=error))
                        if antibot:
                            antibot.record_task_done(success=False)
                        self._cancel_recording(recorder, recording_started)
                        return False
                except Exception as e:
                    logger.error(t('log.device_platform_exception', device_id=device_id, error=e))
                    self._cancel_recording(recorder, recording_started)
                    return False

            # Stop recording
            if not recorder.stop_recording():
                logger.error(t('log.device_stop_recording_failed', device_id=device_id))
                return False

            adb.disable_visual_feedback()

            # Anti-detection handling
            if antibot:
                is_taobao = any(k in task.product_url.lower() for k in ['taobao', 'tmall', 'tb.cn'])
                if is_taobao:
                    should_browse, should_cooldown = antibot.record_task_complete()
                    if should_browse:
                        antibot.execute_cycle_end_actions()
                    if should_cooldown:
                        antibot.trigger_cooldown("Completed multiple cycles")
                        antibot.close_taobao()

            task_success = True
            return True

        except Exception as e:
            logger.error(t('log.device_task_exception', device_id=device_id, error=e))
            self._cancel_recording(recorder, recording_started)
            return False

        finally:
            # Always close apps to ensure clean state for next task
            adb.force_stop_app("com.taobao.taobao")
            adb.force_stop_app("com.a1010bao.web.rdbao")

    def _cancel_recording(self, recorder: ScreenRecorder, recording_started: bool):
        """Cancel recording"""
        if recording_started:
            try:
                recorder.cancel_recording()
            except Exception:
                pass

    def _finalize_stats(self):
        """Finalize statistics"""
        logger.info("=" * 60)
        logger.info(t('log.parallel_execution_complete'))
        logger.info("=" * 60)
        logger.info(t('log.total_tasks', count=self.stats['total_tasks']))
        logger.info(t('log.success_count', count=self.stats['completed']))
        logger.info(t('log.failed_count', count=self.stats['failed']))

        if self.stats['start_time'] and self.stats['end_time']:
            start = datetime.fromisoformat(self.stats['start_time'])
            end = datetime.fromisoformat(self.stats['end_time'])
            duration = end - start
            logger.info(t('log.total_duration', duration=duration))

        logger.info("-" * 40)
        logger.info(t('log.device_statistics'))
        for device_id, device_stats in self.stats['devices'].items():
            logger.info(t('log.device_stat_line', device_id=device_id, total=device_stats['total'],
                         completed=device_stats['completed'], failed=device_stats['failed']))
        logger.info("=" * 60)

    def generate_report(self, output_dir: str = None) -> str:
        """
        Generate execution report.

        Args:
            output_dir: Output directory

        Returns:
            Report file path
        """
        if output_dir:
            reports_dir = Path(output_dir)
        else:
            reports_dir = Path(__file__).parent.parent / 'reports'

        reports_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        report_file = reports_dir / f'parallel_report_{timestamp}.json'

        # Calculate duration
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

        logger.info(t('log.parallel_report_generated', path=report_file))
        return str(report_file)

    def load_tasks_from_file(self, file_path: str) -> List[Task]:
        """
        Load tasks from file.

        Args:
            file_path: Task file path

        Returns:
            Task list
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
            logger.error(t('log.unsupported_file_format', suffix=path.suffix))
            return []

        logger.info(t('log.tasks_loaded_from_file', count=len(tasks), file=file_path))
        return tasks


def run_parallel_mode(
    task_file: str,
    device_ids: List[str] = None,
    video_duration: int = 30,
    enable_antibot: bool = True,
    strategy: str = "round_robin"
) -> bool:
    """
    Run parallel mode.

    Args:
        task_file: Task file path
        device_ids: Device ID list (optional)
        video_duration: Video recording duration
        enable_antibot: Whether to enable anti-detection
        strategy: Dispatch strategy

    Returns:
        Whether successful
    """
    # Parse dispatch strategy
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

        # Load tasks
        tasks = executor.load_tasks_from_file(task_file)
        if not tasks:
            logger.error(t('log.no_tasks_loaded_from_file'))
            return False

        # Execute
        stats = executor.run(
            tasks=tasks,
            delay_between_tasks=10,
            video_duration=video_duration
        )

        # Generate report
        executor.generate_report()

        return stats.get('failed', 0) == 0

    except Exception as e:
        logger.error(t('log.parallel_execution_failed', error=e))
        return False


if __name__ == "__main__":
    # Test code
    logging.basicConfig(level=logging.INFO)

    manager = DeviceManager()
    devices = manager.get_available_devices()
    print(f"Available devices: {[d.device_id for d in devices]}")
