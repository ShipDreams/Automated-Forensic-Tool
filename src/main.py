#!/usr/bin/env python3
"""
Android Automated Forensic Main Process
Universal forensic framework supporting multiple platforms.
"""

import sys
import time
import logging
import argparse
from pathlib import Path

# Ensure logs directory exists
log_dir = Path(__file__).parent.parent / 'logs'
log_dir.mkdir(exist_ok=True)

# Import i18n module first
from locales import t, set_language

# Import custom modules
try:
    from core.adb_controller import ADBController
    from core.recorder import ScreenRecorder
    from core.ui_locator import UILocator
    from platforms import PlatformRouter
    from antibot import AntiBot, TaobaoAntiBot
    from task import TaskManager, Task, TaskResult
except ImportError as e:
    print(f"Module import failed: {e}")
    print("Trying compatibility mode...")
    # Compatibility with old approach
    from adb_controller import ADBController
    from recorder import ScreenRecorder
    from ui_locator import UILocator
    PlatformRouter = None
    AntiBot = None
    TaobaoAntiBot = None
    TaskManager = None

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(log_dir / 'evidence.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)


class EvidenceCollector:
    """
    Evidence Collection Manager

    Responsible for common processes (environment check, screen recording, time anchor),
    platform-specific processes are delegated to PlatformHandler.
    """

    def __init__(self, device_id: str = None, enable_antibot: bool = True):
        """
        Initialize evidence collector.

        Args:
            device_id: Device ID (optional)
            enable_antibot: Whether to enable anti-detection features
        """
        self.adb = ADBController(device_id)
        self.recorder = ScreenRecorder(self.adb)
        self.locator = UILocator(self.adb)

        # AntiBot anti-detection
        self.antibot = None
        if enable_antibot and AntiBot:
            try:
                self.antibot = AntiBot()
                logger.info(t('log.antibot_module_enabled'))
            except Exception as e:
                logger.warning(t('log.antibot_init_failed', error=e))

        # Platform router
        if PlatformRouter:
            self.router = PlatformRouter(self.adb, self.locator, self.antibot)
        else:
            self.router = None

        # Shishibao floating screenshot button position cache
        self._screenshot_button_pos = None

    # ==================== Screenshot Feature ====================

    def click_screenshot_button(self) -> bool:
        """
        Click Shishibao floating screenshot button.

        First call gets and caches button position, subsequent calls use cached coordinates.

        Returns:
            Whether click was successful
        """
        try:
            # Get button position on first call
            if self._screenshot_button_pos is None:
                pos = self.adb.get_overlay_button_position()
                if not pos:
                    logger.warning(t('log.screenshot_button_not_found'))
                    return False
                self._screenshot_button_pos = pos
                logger.info(t('log.screenshot_button_cached', pos=pos))

            # Click floating button
            x, y = self._screenshot_button_pos
            logger.info(t('log.click_screenshot_button', x=x, y=y))
            if self.adb.tap(x, y):
                logger.info(t('log.screenshot_button_clicked'))
                time.sleep(1)  # Wait for screenshot to complete
                return True
            else:
                logger.warning(t('log.click_screenshot_failed'))
                return False

        except Exception as e:
            logger.error(t('log.click_screenshot_exception', error=e))
            return False

    # ==================== Common Processes ====================

    def stage_1_check_environment(self) -> bool:
        """Stage 1: Environment check and connection verification"""
        logger.info("=" * 60)
        logger.info(t('log.stage_env_check'))
        logger.info("=" * 60)

        if not self.adb.device_id:
            logger.error(t('log.device_not_connected'))
            return False
        logger.info(t('log.device_connected', device_id=self.adb.device_id))

        screen_size = self.adb.get_screen_size()
        if not screen_size:
            logger.error(t('log.cannot_get_screen_resolution'))
            return False
        logger.info(t('log.screen_resolution_info', width=screen_size[0], height=screen_size[1]))

        if not self.adb.check_connection():
            logger.error(t('log.device_connection_abnormal'))
            return False
        logger.info(t('log.device_connection_normal'))

        self.adb.wake_screen()
        logger.info(t('log.screen_awakened'))

        # Check cooldown status
        if self.antibot and not self.antibot.can_proceed():
            status = self.antibot.get_cooldown_status()
            remaining = status.get('remaining_seconds', 0)
            logger.warning(t('log.in_cooldown_period', seconds=int(remaining)))
            logger.info(t('log.use_no_antibot_to_skip'))
            return False

        return True

    def stage_2_start_recording(self) -> bool:
        """Stage 2: Start Shishibao App recording"""
        logger.info("=" * 60)
        logger.info(t('log.stage_start_recording'))
        logger.info("=" * 60)

        logger.info(t('log.enabling_touch_visualization'))
        self.adb.enable_visual_feedback()
        time.sleep(1)

        if not self.recorder.start_recording():
            logger.error(t('log.start_recording_failed'))
            return False

        logger.info(t('log.recording_started'))
        return True

    def stage_3_show_beijing_time(self) -> bool:
        """Stage 3: Open Beijing time as time anchor"""
        logger.info("=" * 60)
        logger.info(t('log.stage_show_beijing_time'))
        logger.info("=" * 60)

        try:
            url = "https://www.beijing-time.org/"
            logger.info(t('log.opening_beijing_time', url=url))

            if not self.adb.open_url(url):
                logger.error(t('log.cannot_open_beijing_time'))
                return False

            logger.info(t('log.waiting_page_load', seconds=5))
            time.sleep(5)

            # Screenshot 1: Beijing time page
            logger.info(t('log.screenshot_beijing_time'))
            self.click_screenshot_button()

            logger.info(t('log.staying_beijing_time', seconds=5))
            time.sleep(5)

            logger.info(t('log.beijing_time_complete'))
            return True

        except Exception as e:
            logger.error(t('log.show_beijing_time_failed', error=e))
            return False

    def stage_9_export_evidence(self) -> bool:
        """Stage 9: Stop Shishibao recording and save"""
        logger.info("=" * 60)
        logger.info(t('log.stage_export_evidence'))
        logger.info("=" * 60)

        if not self.recorder.stop_recording():
            logger.error(t('log.stop_recording_failed'))
            return False

        logger.info(t('log.recording_stopped_saved'))
        self.adb.disable_visual_feedback()

        # Record task completion
        if self.antibot:
            self.antibot.record_task_done(success=True)

        return True

    # ==================== Main Process ====================

    def run_full_process(
        self,
        product_url: str,
        video_play_duration: int = 30
    ) -> tuple:
        """
        Execute full forensic process.

        Args:
            product_url: Product link (supports Taobao/Tmall/JD/Douyin etc.)
            video_play_duration: Video recording duration (seconds)

        Returns:
            (success: bool, error: str or None) - Whether successful, error reason on failure
        """
        logger.info("*" * 60)
        logger.info(t('log.start_full_process'))
        logger.info(t('log.product_link', url=product_url))
        logger.info("*" * 60)

        recording_started = False  # Flag whether recording has started

        try:
            # Stage 1: Environment check
            if not self.stage_1_check_environment():
                error = t('log.env_check_failed')
                logger.error(error)
                return False, error

            # Stage 2: Start Shishibao recording
            if not self.stage_2_start_recording():
                error = t('log.start_recording_failed_terminate')
                logger.error(error)
                return False, error
            recording_started = True

            # Stage 3: Display Beijing time
            if not self.stage_3_show_beijing_time():
                error = t('log.show_beijing_time_failed_terminate')
                logger.error(error)
                self._cleanup_on_failure(recording_started)
                return False, error

            # Stage 4-8: Platform-specific process
            if self.router:
                # Use platform router
                try:
                    handler = self.router.get_handler(product_url)
                    logger.info(t('log.using_platform_handler', platform=handler.get_platform_display_name()))

                    # Set screenshot callback
                    handler.set_screenshot_callback(self.click_screenshot_button)

                    success, platform_error = handler.execute(product_url, video_play_duration)
                    if not success:
                        error = platform_error or t('log.platform_forensic_failed')
                        logger.error(error)
                        if self.antibot:
                            self.antibot.record_task_done(success=False)
                        self._cleanup_on_failure(recording_started)
                        return False, error

                except NotImplementedError as e:
                    error = t('log.platform_not_implemented', error=e)
                    logger.error(error)
                    self._cleanup_on_failure(recording_started)
                    return False, error

                except ValueError as e:
                    error = t('log.platform_not_recognized', error=e)
                    logger.error(error)
                    self._cleanup_on_failure(recording_started)
                    return False, error
            else:
                # Compatibility mode: use old Taobao process directly
                logger.warning(t('log.platform_router_unavailable'))
                success, legacy_error = self._run_legacy_taobao_process(product_url, video_play_duration)
                if not success:
                    self._cleanup_on_failure(recording_started)
                    return False, legacy_error

            # Stage 9: Stop and export (save on success)
            if not self.stage_9_export_evidence():
                error = t('log.export_evidence_failed')
                logger.error(error)
                return False, error

            logger.info("*" * 60)
            logger.info(t('log.forensic_complete'))
            logger.info("*" * 60)
            return True, None

        except KeyboardInterrupt:
            logger.warning(t('log.user_interrupted'))
            self.recorder.stop_recording()
            return False, "User interrupted"

        except Exception as e:
            error = t('log.forensic_exception', error=e)
            logger.error(error, exc_info=True)
            if self.antibot:
                self.antibot.record_task_done(success=False)
            self._cleanup_on_failure(recording_started)
            return False, error

    def _cleanup_on_failure(self, recording_started: bool):
        """
        Cleanup recording state on task failure.

        Args:
            recording_started: Whether recording has started
        """
        if recording_started:
            logger.info(t('log.task_failed_cancel_recording'))
            try:
                self.recorder.cancel_recording()
            except Exception as e:
                logger.error(t('log.cancel_recording_failed', error=e))

    def _run_legacy_taobao_process(
        self,
        product_url: str,
        video_play_duration: int
    ) -> tuple:
        """
        Compatibility mode: old Taobao process (when PlatformRouter unavailable).

        This is logic preserved from original main.py for backward compatibility.
        New code should use PlatformRouter.

        Returns:
            (success: bool, error: str or None)
        """
        logger.warning(t('log.using_legacy_taobao'))

        # Stage 4: Open app store
        if not self.adb.open_app_store_and_search_taobao():
            error = "Failed to open app store"
            logger.error(error)
            return False, error
        time.sleep(6)

        # Stage 5: Open Taobao from app store
        if not self.locator.find_and_click_app_store_open_button(max_attempts=3):
            error = "Failed to click 'Open' button"
            logger.error(error)
            return False, error
        time.sleep(10)

        # Stage 6: Open product in Taobao
        time.sleep(3)
        self.adb.press_back()
        time.sleep(1)

        root = self.locator.dump_and_parse()
        if not root:
            error = t('log.cannot_get_ui_hierarchy')
            logger.error(error)
            return False, error

        search_box = self.locator.find_taobao_search_box(root)
        if not search_box:
            error = "Taobao search box not found"
            logger.error(error)
            return False, error

        if not self.locator.click_element(search_box):
            error = "Failed to click search box"
            logger.error(error)
            return False, error
        time.sleep(1)

        if not self.adb.input_text(product_url):
            error = "Failed to input product link"
            logger.error(error)
            return False, error
        time.sleep(1)

        self.adb.press_enter()
        time.sleep(8)

        # Stage 7: Play video
        self.locator.find_and_click_video(max_attempts=3)
        time.sleep(3)

        # Stage 8: Continue recording
        time.sleep(video_play_duration)

        # Stage 8.5: View shop qualification (simplified)
        root = self.locator.dump_and_parse()
        if root:
            shop_btn = self.locator.find_shop_button(root)
            if shop_btn:
                self.locator.click_element(shop_btn)
                time.sleep(3)

        return True, None


def _load_taobao_antibot_config() -> dict:
    """Load Taobao anti-detection config"""
    config_path = Path(__file__).parent.parent / 'config' / 'antibot.json'
    if config_path.exists():
        try:
            import json
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            return config.get('taobao', {})
        except Exception as e:
            logger.warning(t('log.taobao_antibot_init_failed', error=e))
    return {}


def run_batch_mode(task_file: str, device_id: str = None, video_duration: int = 30, enable_antibot: bool = True):
    """
    Batch mode: Load tasks from file and execute sequentially.

    Supports Taobao-specific anti-detection strategy:
    - Execute human browsing simulation every 3-5 tasks
    - Enter 15-minute cooldown after 3-5 cycles

    Args:
        task_file: Task file path (JSON/CSV/TXT)
        device_id: Device ID
        video_duration: Video recording duration
        enable_antibot: Whether to enable anti-detection
    """
    if not TaskManager:
        logger.error(t('log.task_manager_unavailable'))
        return False

    logger.info("=" * 60)
    logger.info(t('log.batch_mode'))
    logger.info(t('log.task_file', file=task_file))
    logger.info("=" * 60)

    # Initialize
    collector = EvidenceCollector(device_id=device_id, enable_antibot=enable_antibot)
    task_manager = TaskManager()

    # Initialize Taobao anti-detection (if enabled)
    taobao_antibot = None
    if enable_antibot and TaobaoAntiBot:
        try:
            taobao_config = _load_taobao_antibot_config()
            taobao_antibot = TaobaoAntiBot(
                adb_controller=collector.adb,
                ui_locator=collector.locator,
                config=taobao_config,
                device_id=collector.adb.device_id
            )
            logger.info(t('log.taobao_antibot_enabled'))
            status = taobao_antibot.get_status()
            logger.info(t('log.antibot_status', current=status['tasks_in_cycle'],
                         target=status['tasks_per_cycle_target'],
                         cycles=status['completed_cycles'],
                         cycles_target=status['cycles_before_cooldown_target']))

            # Check if in cooldown period
            if taobao_antibot.is_cooling_down():
                remaining = taobao_antibot.get_remaining_cooldown()
                logger.warning(t('log.device_in_cooldown', seconds=int(remaining.total_seconds())))
                logger.info(t('log.waiting_cooldown'))
                time.sleep(remaining.total_seconds())
                logger.info(t('log.cooldown_ended'))

        except Exception as e:
            logger.warning(t('log.taobao_antibot_init_failed', error=e))
            taobao_antibot = None

    # Load tasks
    count = task_manager.load_tasks_from_file(task_file)
    if count == 0:
        logger.error(t('log.no_tasks_loaded'))
        return False

    logger.info(t('log.tasks_loaded', count=count))

    # Set executor
    def execute_task(task: Task) -> TaskResult:
        """Task execution function"""
        logger.info(t('log.executing_task', id=task.id, url=task.product_url[:50]))

        # Check cooldown status
        if taobao_antibot and taobao_antibot.is_cooling_down():
            remaining = taobao_antibot.get_remaining_cooldown()
            logger.warning(t('log.in_cooldown_waiting', seconds=int(remaining.total_seconds())))
            logger.info(t('log.waiting_cooldown'))
            time.sleep(remaining.total_seconds())
            logger.info(t('log.cooldown_ended'))

        # #5: Check time-based cooldown
        if taobao_antibot:
            taobao_antibot.check_time_based_cooldown()

        success, error = collector.run_full_process(
            product_url=task.product_url,
            video_play_duration=task.video_duration or video_duration
        )

        # #2: Record task completion (count both success and failure)
        try:
            if taobao_antibot:
                # Detect if Taobao link
                is_taobao = 'taobao' in task.product_url.lower() or 'tmall' in task.product_url.lower() or 'tb.cn' in task.product_url.lower()
                logger.info(t('log.antibot_check', is_taobao=is_taobao, url=task.product_url[:50]))
                if is_taobao:
                    should_browse, should_cooldown = taobao_antibot.record_task_done(success=success)
                    status = taobao_antibot.get_status()
                    logger.info(t('log.antibot_status_detail',
                                 current=status['tasks_in_cycle'],
                                 target=status['tasks_per_cycle_target'],
                                 cycles=status['completed_cycles'],
                                 cycles_target=status['cycles_before_cooldown_target'],
                                 browse=should_browse, cooldown=should_cooldown))

                    if should_browse and success:
                        logger.info("=" * 60)
                        logger.info(t('log.trigger_cycle_end'))
                        logger.info("=" * 60)
                        taobao_antibot.execute_cycle_end_actions()

                    if should_cooldown:
                        taobao_antibot.trigger_cooldown("Completed multiple cycles")
                        # Close Taobao process
                        taobao_antibot.close_taobao()

                    # #3: Check if failure is risk-related
                    if not success and error:
                        error_lower = str(error).lower()
                        risk_type = None
                        if 'risk_detected' in error_lower or 'captcha' in error_lower:
                            risk_type = 'captcha'
                        elif 'login' in error_lower:
                            risk_type = 'login_required'
                        elif 'blocked' in error_lower:
                            risk_type = 'blocked'

                        if risk_type:
                            duration = taobao_antibot.trigger_risk_cooldown(risk_type)
                            logger.warning(f"Risk detected ({risk_type}), entering {duration} min cooldown")
                            # Send notification
                            try:
                                from core.notifier import notify_captcha
                                notify_captcha(device_id=collector.adb.device_id or "unknown", sound=True)
                            except Exception as ne:
                                logger.warning(f"Failed to send notification: {ne}")
            else:
                logger.warning(t('log.antibot_not_enabled'))
        except Exception as e:
            logger.error(t('log.antibot_processing_exception', error=e), exc_info=True)

        # Close both apps after each task to ensure initial state for next task
        logger.info(t('log.closing_apps_for_next_task'))
        collector.adb.force_stop_app("com.taobao.taobao")
        collector.adb.force_stop_app("com.a1010bao.web.rdbao")

        return TaskResult(
            success=success,
            message="Forensic complete" if success else "Forensic failed",
            error=error
        )

    task_manager.set_executor(execute_task)

    # Execute all tasks
    try:
        stats = task_manager.run_all(delay_between_tasks=10)
    except KeyboardInterrupt:
        logger.warning(t('log.user_interrupted_batch'))
        # Set end time for report generation
        from datetime import datetime
        task_manager.stats['end_time'] = datetime.now().isoformat()
    finally:
        # Generate summary report regardless of success, failure, or interruption
        task_manager.generate_report()

    # Close Taobao after all tasks complete
    if taobao_antibot:
        logger.info(t('log.all_tasks_complete_closing'))
        taobao_antibot.close_taobao()

    return task_manager.stats.get('failed', 0) == 0


def main():
    """Main function"""
    parser = argparse.ArgumentParser(
        description='Android Automated Forensic Tool',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Single link forensic
  python main.py "https://item.taobao.com/item.htm?id=xxx"

  # Batch forensic (single device sequential)
  python main.py --batch tasks.json

  # Batch forensic (multi-device parallel)
  python main.py --batch tasks.csv --parallel

  # Specify devices for parallel execution
  python main.py --batch tasks.csv --parallel --devices "device1,device2"

  # Disable anti-detection (skip cooldown check)
  python main.py --no-antibot "https://item.taobao.com/item.htm?id=xxx"

  # Set language
  python main.py --lang zh_CN "https://item.taobao.com/item.htm?id=xxx"
        """
    )

    # Mutual exclusion group: single link mode vs batch mode
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        'product_url',
        nargs='?',
        help='Product link (supports Taobao/Tmall/JD/Douyin etc.)'
    )
    mode_group.add_argument(
        '--batch', '-b',
        metavar='FILE',
        help='Batch mode: load tasks from file (supports JSON/CSV/TXT)'
    )

    parser.add_argument(
        '-d', '--device',
        help='Device ID (optional, auto-detect by default)',
        default=None
    )
    parser.add_argument(
        '-p', '--play-duration',
        help='Video playback recording duration (seconds), default 30',
        type=int,
        default=30
    )
    parser.add_argument(
        '--no-antibot',
        action='store_true',
        help='Disable anti-detection (skip cooldown check and human behavior simulation)'
    )
    parser.add_argument(
        '--parallel',
        action='store_true',
        help='Enable multi-device parallel mode (use with --batch)'
    )
    parser.add_argument(
        '--devices',
        help='Specify device ID list (comma-separated), only valid in parallel mode',
        default=None
    )
    parser.add_argument(
        '--strategy',
        choices=['round_robin', 'load_balance', 'random'],
        default='round_robin',
        help='Task dispatch strategy (default: round_robin)'
    )
    parser.add_argument(
        '--lang',
        choices=['en_US', 'zh_CN'],
        default=None,
        help='Language setting (default: auto-detect from environment)'
    )

    args = parser.parse_args()

    # Set language if specified
    if args.lang:
        set_language(args.lang)

    # Batch mode
    if args.batch:
        # Parallel mode
        if args.parallel:
            from core.parallel_executor import run_parallel_mode

            # Parse device list
            device_ids = None
            if args.devices:
                device_ids = [d.strip() for d in args.devices.split(',')]

            success = run_parallel_mode(
                task_file=args.batch,
                device_ids=device_ids,
                video_duration=args.play_duration,
                enable_antibot=not args.no_antibot,
                strategy=args.strategy
            )
            sys.exit(0 if success else 1)

        # Single device sequential mode
        success = run_batch_mode(
            task_file=args.batch,
            device_id=args.device,
            video_duration=args.play_duration,
            enable_antibot=not args.no_antibot
        )
        sys.exit(0 if success else 1)

    # Single link mode
    collector = EvidenceCollector(
        device_id=args.device,
        enable_antibot=not args.no_antibot
    )

    success, error = collector.run_full_process(
        product_url=args.product_url,
        video_play_duration=args.play_duration
    )

    if not success and error:
        logger.error(f"Forensic failed: {error}")

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
