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

        # Retry config
        self.max_retries = 3
        self.retry_delay = 60  # seconds

        # Keywords that should not auto-retry (risk-related or environment issues)
        self._risk_keywords = ['risk_detected', 'captcha', 'login', 'blocked', 'failed to start recording']

        # Statistics
        self.stats = {
            'start_time': None,
            'end_time': None,
            'total_tasks': 0,
            'completed': 0,
            'failed': 0,
            'retried': 0,
            'devices': {}
        }

        # Per-task result records
        self._task_results: List[Dict[str, Any]] = []

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

        # Finalize statistics (always runs, even after interruption)
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
                # Record remaining tasks as cancelled
                for remaining_task in tasks[i:]:
                    self._record_task_result(device_id, remaining_task, 'cancelled', None, 0)
                break

            logger.info(t('log.executing_task_n', device_id=device_id, current=i+1, total=len(tasks), url=task.product_url[:50]))

            # Execute with retry
            task_success = False
            task_error = None
            retry_count = 0

            for attempt in range(1 + self.max_retries):
                if self._stop_event.is_set():
                    break

                try:
                    success, error = self._execute_task_with_error(context, task, video_duration)

                    if success:
                        task_success = True
                        task_error = None
                        break

                    task_error = error or "Unknown error"

                    # Check if this is a risk-related failure (don't auto-retry)
                    if error:
                        error_lower = str(error).lower()
                        is_risk = any(k in error_lower for k in self._risk_keywords)
                        if is_risk:
                            logger.warning(f"[{device_id}] Risk-related failure, skipping retry: {error}")
                            break

                    # Check if we have retries left
                    if attempt < self.max_retries:
                        retry_count += 1
                        with self._lock:
                            self.stats['retried'] += 1
                        logger.warning(f"[{device_id}] Task failed, retrying ({retry_count}/{self.max_retries}) after {self.retry_delay}s: {error}")
                        time.sleep(self.retry_delay)
                    else:
                        logger.error(f"[{device_id}] Task failed after {self.max_retries} retries: {error}")

                except Exception as e:
                    task_error = str(e)
                    logger.error(t('log.task_execution_exception', device_id=device_id, error=e))
                    if attempt < self.max_retries:
                        retry_count += 1
                        with self._lock:
                            self.stats['retried'] += 1
                        logger.warning(f"[{device_id}] Task exception, retrying ({retry_count}/{self.max_retries}) after {self.retry_delay}s")
                        time.sleep(self.retry_delay)

            # Record result
            status = 'completed' if task_success else 'failed'
            self._record_task_result(device_id, task, status, task_error, retry_count)

            with self._lock:
                if task_success:
                    completed += 1
                    self.stats['completed'] += 1
                    self.stats['devices'][device_id]['completed'] += 1
                else:
                    failed += 1
                    self.stats['failed'] += 1
                    self.stats['devices'][device_id]['failed'] += 1

            self.dispatcher.record_task_complete(device_id, task_success)

            # Save realtime report after each task
            self._save_realtime_report()

            # Delay between tasks (not needed for last task)
            if i < len(tasks) - 1 and not self._stop_event.is_set():
                logger.info(t('log.waiting_between_tasks', device_id=device_id, seconds=delay_between_tasks))
                time.sleep(delay_between_tasks)

        # Cleanup
        self.device_manager.mark_device_available(device_id, success=(failed == 0))
        logger.info(t('log.worker_thread_ended', device_id=device_id, completed=completed, failed=failed))

        return {'completed': completed, 'failed': failed}

    def _execute_task_with_error(
        self,
        context: DeviceWorkerContext,
        task: Task,
        video_duration: int
    ) -> tuple:
        """
        Execute single task.

        Args:
            context: Device context
            task: Task
            video_duration: Video recording duration

        Returns:
            (success: bool, error: str or None)
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
                if remaining and remaining.total_seconds() > 0:
                    logger.warning(t('log.device_in_cooldown_waiting', device_id=device_id, seconds=int(remaining.total_seconds())))
                    time.sleep(remaining.total_seconds())

            # Environment check
            if not adb.check_connection():
                logger.error(t('log.device_connection_error', device_id=device_id))
                return False, "Device connection error"

            adb.wake_screen()

            # Start recording
            adb.enable_visual_feedback()
            time.sleep(1)

            if not recorder.start_recording():
                logger.error(t('log.device_start_recording_failed', device_id=device_id))
                return False, "Failed to start recording"
            recording_started = True

            # Display Beijing time
            if not adb.open_url("https://www.beijing-time.org/"):
                self._cancel_recording(recorder, recording_started)
                return False, "Failed to open Beijing time page"
            time.sleep(5)
            click_screenshot_button()
            time.sleep(5)

            # Platform forensic (with captcha retry support)
            if router:
                try:
                    handler = router.get_handler(task.product_url)
                    handler.set_screenshot_callback(click_screenshot_button)

                    max_captcha_retries = 1  # Allow 1 retry after human captcha handling
                    for captcha_attempt in range(1 + max_captcha_retries):
                        success, error = handler.execute(
                            task.product_url,
                            task.video_duration or video_duration
                        )

                        if success:
                            break  # Task succeeded

                        logger.error(t('log.device_platform_failed', device_id=device_id, error=error))

                        # Check if failure is risk-related
                        if not (antibot and error):
                            break  # Non-risk failure, no retry

                        error_lower = str(error).lower()
                        is_risk = any(k in error_lower for k in ['risk_detected', 'captcha', 'login', 'blocked'])

                        if not is_risk:
                            break  # Non-risk failure, no retry

                        # Send blocking notification (waits up to 3 min for human)
                        human_confirmed = False
                        try:
                            from core.notifier import notify_captcha
                            human_confirmed = notify_captcha(device_id=device_id, sound=True)
                        except Exception as ne:
                            logger.warning(f"[{device_id}] Failed to send notification: {ne}")

                        if not human_confirmed:
                            # Timeout or cancelled - enter protection mode, fail task
                            logger.warning(f"[{device_id}] No human response, entering protection mode")
                            antibot.enter_protection_mode(reason="captcha_timeout")
                            break

                        # Human confirmed - retry the task
                        if captcha_attempt < max_captcha_retries:
                            logger.info(f"[{device_id}] Human confirmed captcha handled, retrying task...")
                            time.sleep(3)  # Brief wait for page to stabilize after captcha
                        else:
                            # Already used up captcha retry, captcha still present = not actually handled
                            logger.warning(f"[{device_id}] Captcha still detected after human confirmation, entering protection mode")
                            antibot.enter_protection_mode(reason="captcha_unresolved")
                            break

                    if not success:
                        self._cancel_recording(recorder, recording_started)
                        return False, error
                except Exception as e:
                    logger.error(t('log.device_platform_exception', device_id=device_id, error=e))
                    self._cancel_recording(recorder, recording_started)
                    return False, str(e)

            # Stop recording
            if not recorder.stop_recording():
                logger.error(t('log.device_stop_recording_failed', device_id=device_id))
                return False, "Failed to stop recording"

            adb.disable_visual_feedback()

            task_success = True
            return True, None

        except Exception as e:
            logger.error(t('log.device_task_exception', device_id=device_id, error=e))
            self._cancel_recording(recorder, recording_started)
            return False, str(e)

        finally:
            # Record task completion and check if protection mode needed
            if antibot:
                is_taobao = any(k in task.product_url.lower() for k in ['taobao', 'tmall', 'tb.cn'])
                if is_taobao:
                    try:
                        should_protect = antibot.record_task_done(success=task_success)
                        if should_protect:
                            antibot.enter_protection_mode(reason="cycle_complete")
                    except Exception as e:
                        logger.error(f"[{device_id}] AntiBot recording exception: {e}")

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

    def _record_task_result(
        self,
        device_id: str,
        task: Task,
        status: str,
        error: Optional[str],
        retry_count: int
    ):
        """
        Record per-task execution result.

        Args:
            device_id: Device ID
            task: Task object
            status: Result status ('completed', 'failed', 'cancelled')
            error: Error message (if failed)
            retry_count: Number of retries attempted
        """
        record = {
            'task_id': task.id,
            'url': task.product_url,
            'device_id': device_id,
            'status': status,
            'retry_count': retry_count,
            'timestamp': datetime.now().isoformat(),
        }
        if error:
            record['error'] = error

        with self._lock:
            self._task_results.append(record)

    def _save_realtime_report(self):
        """
        Save realtime report to a fixed file after each task completion.

        This file is overwritten each time so that even if the process is
        force-killed, completed task records are preserved on disk.
        """
        try:
            reports_dir = Path(__file__).parent.parent / 'reports'
            reports_dir.mkdir(parents=True, exist_ok=True)
            report_file = reports_dir / 'parallel_report_latest.json'

            with self._lock:
                report = {
                    'report_time': datetime.now().isoformat(),
                    'source_file': self._source_file,
                    'execution_mode': 'parallel',
                    'status': 'in_progress',
                    'summary': {
                        'total_devices': len(self._device_ids),
                        'total_tasks': self.stats['total_tasks'],
                        'completed': self.stats['completed'],
                        'failed': self.stats['failed'],
                        'retried': self.stats.get('retried', 0),
                    },
                    'devices': dict(self.stats['devices']),
                    'tasks': list(self._task_results),
                }

            with open(report_file, 'w', encoding='utf-8') as f:
                json.dump(report, f, ensure_ascii=False, indent=2)

        except Exception as e:
            logger.warning(f"Failed to save realtime report: {e}")

    def _finalize_stats(self):
        """Finalize statistics"""
        logger.info("=" * 60)
        logger.info(t('log.parallel_execution_complete'))
        logger.info("=" * 60)
        logger.info(t('log.total_tasks', count=self.stats['total_tasks']))
        logger.info(t('log.success_count', count=self.stats['completed']))
        logger.info(t('log.failed_count', count=self.stats['failed']))
        logger.info(f"  Retried: {self.stats.get('retried', 0)}")

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

        # Log failed tasks summary
        failed_tasks = [r for r in self._task_results if r['status'] == 'failed']
        if failed_tasks:
            logger.info("-" * 40)
            logger.info(f"Failed tasks ({len(failed_tasks)}):")
            for r in failed_tasks:
                logger.info(f"  [{r['device_id']}] {r['url'][:60]} | retries={r['retry_count']} | {r.get('error', 'N/A')}")

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
                'retried': self.stats.get('retried', 0),
                'duration_seconds': duration_seconds,
            },
            'devices': self.stats['devices'],
            'tasks': self._task_results,
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

    executor = None
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

        return stats.get('failed', 0) == 0

    except KeyboardInterrupt:
        logger.warning(t('log.user_interrupt_stopping'))
        if executor:
            executor._stop_event.set()
        return False

    except Exception as e:
        logger.error(t('log.parallel_execution_failed', error=e))
        return False

    finally:
        # #4: Always generate report, even on early exit
        if executor:
            try:
                if not executor.stats.get('end_time'):
                    executor.stats['end_time'] = datetime.now().isoformat()
                    executor._finalize_stats()
                executor.generate_report()
            except Exception as e:
                logger.error(f"Failed to generate report: {e}")


if __name__ == "__main__":
    # Test code
    logging.basicConfig(level=logging.INFO)

    manager = DeviceManager()
    devices = manager.get_available_devices()
    print(f"Available devices: {[d.device_id for d in devices]}")
