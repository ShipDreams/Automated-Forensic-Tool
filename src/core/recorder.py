#!/usr/bin/env python3
"""
Screen recording management module - Shishibao App version.
Responsible for screen recording via "Shishibao" App (forensic-dedicated).
"""

import time
import logging
from typing import Optional

from locales import t

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class ScreenRecorder:
    """Screen recording manager (Shishibao App version)"""

    def __init__(self, adb_controller):
        """
        Initialize recording manager.

        Args:
            adb_controller: ADBController instance
        """
        self.adb = adb_controller
        self.locator = None  # Will be injected in start_recording
        self.is_recording = False

    def start_recording(self) -> bool:
        """
        Start recording via "Shishibao" App (smart page state detection).

        Flow:
        1. Open "Shishibao" App
        2. Detect current page state:
           - If "Start Recording" button exists, click directly (skip Screen Record step)
           - If "Screen Record" button exists, execute full flow
        3. Click popup "Start Now" (if needed)
        4. Click "Start Recording"
        5. Wait 4 seconds to ensure recording starts

        Returns:
            Whether recording started successfully
        """
        try:
            try:
                from .ui_locator import UILocator
            except ImportError:
                from ui_locator import UILocator
            if not self.locator:
                self.locator = UILocator(self.adb)

            logger.info("=" * 60)
            logger.info(t('log.shishibao_start_recording'))
            logger.info("=" * 60)

            # Step 1: Open Shishibao App
            logger.info(t('log.step_1_open_shishibao'))
            if not self.adb.open_shishibao_app():
                logger.error(t('log.open_shishibao_failed'))
                return False

            # Step 2: Detect current page state
            logger.info(t('log.step_2_detect_page'))
            time.sleep(2)  # Wait for page to load
            root = self.locator.dump_and_parse()
            if not root:
                logger.error(t('log.cannot_get_shishibao_ui'))
                return False

            # First check if already on recording ready page (has "Start Recording" button)
            start_record_btn = self.locator.find_shishibao_start_record_button(root)
            if start_record_btn:
                logger.info(t('log.detected_start_record_button'))
                # Click "Start Recording" directly
                if not self.locator.click_element(start_record_btn):
                    logger.error(t('log.click_start_record_failed'))
                    return False
            else:
                # Need to click "Screen Record" first
                logger.info(t('log.need_click_screen_record'))
                screen_record_btn = self.locator.find_shishibao_screen_record_button(root)
                if not screen_record_btn:
                    logger.error(t('log.screen_record_not_found'))
                    return False

                if not self.locator.click_element(screen_record_btn):
                    logger.error(t('log.click_screen_record_failed'))
                    return False

                # Step 3: Click popup "Start Now"
                logger.info(t('log.step_3_click_start_now'))
                time.sleep(2)  # Wait for popup
                root = self.locator.dump_and_parse()
                if not root:
                    logger.error(t('log.cannot_get_dialog_ui'))
                    return False

                start_now_btn = self.locator.find_shishibao_start_now_button(root)
                if not start_now_btn:
                    logger.error(t('log.start_now_not_found'))
                    return False

                if not self.locator.click_element(start_now_btn):
                    logger.error(t('log.click_start_now_failed'))
                    return False

                # Step 3.5: Uncheck microphone if checked
                logger.info("检查麦克风勾选状态...")
                time.sleep(2)  # Wait for page response
                root = self.locator.dump_and_parse()
                if root:
                    mic_checkbox = self.locator.find_shishibao_microphone_checkbox(root)
                    if mic_checkbox and mic_checkbox.node.attrib.get('checked', 'false') == 'true':
                        logger.info("麦克风已勾选，正在取消...")
                        self.locator.click_element(mic_checkbox)
                        time.sleep(1)
                        # Re-dump after clicking
                        root = self.locator.dump_and_parse()

                # Step 4: Click "Start Recording"
                logger.info(t('log.step_4_click_start_record'))
                if not root:
                    time.sleep(2)
                    root = self.locator.dump_and_parse()
                if not root:
                    logger.error(t('log.cannot_get_shishibao_ui'))
                    return False

                start_record_btn = self.locator.find_shishibao_start_record_button(root)
                if not start_record_btn:
                    logger.error(t('log.start_record_not_found'))
                    return False

                if not self.locator.click_element(start_record_btn):
                    logger.error(t('log.click_start_record_failed'))
                    return False

            # Step 5: Wait for recording to stabilize
            logger.info(t('log.step_5_wait_recording'))
            time.sleep(4)

            self.is_recording = True
            logger.info("=" * 60)
            logger.info(t('log.shishibao_recording_started'))
            logger.info("=" * 60)
            return True

        except Exception as e:
            logger.error(t('log.start_shishibao_recording_failed', error=e), exc_info=True)
            return False

    def stop_recording(self, wait_time: int = 3, max_retries: int = 3, evidence_name: str = "") -> bool:
        """
        Stop recording and save via "Shishibao" App.

        Flow:
        1. Open "Shishibao" App
        2. Click "Stop Recording" (with retry)
        3. If evidence_name provided, find the filename input field and append evidence_name
        4. Click "Save"
        5. Wait for save to complete

        Args:
            wait_time: Wait time after save (seconds)
            max_retries: Maximum retry attempts for finding button
            evidence_name: Evidence name to append to default filename (e.g. "xxx店_淘宝")

        Returns:
            Whether stop and save was successful
        """
        try:
            try:
                from .ui_locator import UILocator
            except ImportError:
                from ui_locator import UILocator
            if not self.locator:
                self.locator = UILocator(self.adb)

            logger.info("=" * 60)
            logger.info(t('log.shishibao_stop_recording'))
            logger.info("=" * 60)

            # Step 1: Open Shishibao App
            logger.info(t('log.step_1_open_shishibao'))
            if not self.adb.open_shishibao_app():
                logger.error(t('log.open_shishibao_failed'))
                return False

            # Press back to close Taobao page and ensure Shishibao is in foreground
            logger.info(t('log.press_back_close_taobao'))
            time.sleep(2)
            self.adb.press_back()  # Close Taobao license page
            time.sleep(2)

            # Verify current focus is Shishibao
            current_focus = self.adb.get_current_focus()
            if current_focus and 'rdbao' not in current_focus:
                logger.warning(t('log.shishibao_not_foreground'))
                self.adb.press_back()
                time.sleep(1)
            else:
                logger.info(t('log.shishibao_in_foreground'))

            # Step 2: Click "Stop Recording" (with retry mechanism)
            logger.info(t('log.step_2_click_stop_record'))
            stop_btn = None
            for attempt in range(1, max_retries + 1):
                logger.info(t('log.attempt_find_stop_button', attempt=attempt, max_retries=max_retries))
                time.sleep(3)  # Wait for Shishibao UI to fully load
                root = self.locator.dump_and_parse()
                if not root:
                    logger.warning(t('log.attempt_cannot_get_ui', attempt=attempt))
                    continue

                stop_btn = self.locator.find_shishibao_stop_record_button(root)
                if stop_btn:
                    logger.info(t('log.attempt_found_stop_button', attempt=attempt))
                    break
                else:
                    logger.warning(t('log.attempt_stop_button_not_found', attempt=attempt))
                    if attempt < max_retries:
                        # Try pressing back to refresh UI
                        self.adb.press_back()
                        time.sleep(1)
                        self.adb.open_shishibao_app()
                        time.sleep(2)

            if not stop_btn:
                logger.error(t('log.stop_button_not_found_after_retries', max_retries=max_retries))
                return False

            if not self.locator.click_element(stop_btn):
                logger.error(t('log.click_stop_record_failed'))
                return False

            # Step 3: Input evidence name into filename field (if provided)
            if evidence_name:
                logger.info(f"准备在文件名输入框追加证据名称: {evidence_name}")
                time.sleep(2)  # Wait for save page to load
                root = self.locator.dump_and_parse()
                if root:
                    # Find filename input by exact resource-id
                    filename_input = self.locator.find_element_by_id(
                        root, "com.a1010bao.web.rdbao:id/tv_modify_name"
                    )
                    if filename_input:
                        bounds = filename_input.get_bounds()
                        if bounds:
                            x1, y1, x2, y2 = bounds
                            # Click the right edge of the input field to position cursor at end of timestamp
                            right_x = x2 - 10
                            center_y = (y1 + y2) // 2
                            logger.info(f"点击文件名输入框右侧 ({right_x}, {center_y})")
                            self.adb.tap(right_x, center_y)
                            time.sleep(1)
                            # Input evidence name (appended after default timestamp)
                            logger.info(f"输入证据名称: {evidence_name}")
                            self.adb.input_text(evidence_name)
                            time.sleep(1)
                        else:
                            logger.warning("无法获取文件名输入框坐标")
                    else:
                        logger.warning("未找到文件名输入框 (tv_modify_name)")
                else:
                    logger.warning("无法获取保存页面UI，跳过证据名称输入")

            # Step 4: Click "Save"
            logger.info(t('log.step_3_click_save'))
            time.sleep(2)  # Wait for response
            root = self.locator.dump_and_parse()
            if not root:
                logger.error(t('log.cannot_get_shishibao_ui'))
                return False

            save_btn = self.locator.find_shishibao_save_button(root)
            if not save_btn:
                logger.error(t('log.save_not_found'))
                return False

            if not self.locator.click_element(save_btn):
                logger.error(t('log.click_save_failed'))
                return False

            # Step 5: Wait for save to complete
            logger.info(t('log.step_4_wait_save', wait_time=wait_time))
            time.sleep(wait_time)

            self.is_recording = False
            logger.info("=" * 60)
            logger.info(t('log.shishibao_recording_stopped'))
            logger.info(t('log.recording_saved_in_app'))
            logger.info("=" * 60)
            return True

        except Exception as e:
            logger.error(t('log.stop_shishibao_recording_failed', error=e), exc_info=True)
            return False

    def cancel_recording(self, max_retries: int = 3) -> bool:
        """
        Stop recording via "Shishibao" App but don't save (cancel).

        Used to clean up recording state when task fails, without saving current recording.

        Flow:
        1. Open "Shishibao" App
        2. Click "Stop Recording" (with retry)
        3. Click "Cancel"
        4. Wait for interface to restore

        Args:
            max_retries: Maximum retry attempts for finding button

        Returns:
            Whether cancel was successful
        """
        try:
            try:
                from .ui_locator import UILocator
            except ImportError:
                from ui_locator import UILocator
            if not self.locator:
                self.locator = UILocator(self.adb)

            logger.info("=" * 60)
            logger.info(t('log.shishibao_cancel_recording'))
            logger.info("=" * 60)

            # Step 1: Open Shishibao App
            logger.info(t('log.step_1_open_shishibao'))
            if not self.adb.open_shishibao_app():
                logger.error(t('log.open_shishibao_failed'))
                return False

            # Press back to ensure Shishibao is in foreground
            logger.info(t('log.press_back_ensure_foreground'))
            time.sleep(2)
            self.adb.press_back()
            time.sleep(2)

            # Verify current focus is Shishibao
            current_focus = self.adb.get_current_focus()
            if current_focus and 'rdbao' not in current_focus:
                logger.warning(t('log.shishibao_not_foreground'))
                self.adb.press_back()
                time.sleep(1)
            else:
                logger.info(t('log.shishibao_in_foreground'))

            # Step 2: Click "Stop Recording" (with retry mechanism)
            logger.info(t('log.step_2_click_stop_record'))
            stop_btn = None
            for attempt in range(1, max_retries + 1):
                logger.info(t('log.attempt_find_stop_button', attempt=attempt, max_retries=max_retries))
                time.sleep(3)
                root = self.locator.dump_and_parse()
                if not root:
                    logger.warning(t('log.attempt_cannot_get_ui', attempt=attempt))
                    continue

                stop_btn = self.locator.find_shishibao_stop_record_button(root)
                if stop_btn:
                    logger.info(t('log.attempt_found_stop_button', attempt=attempt))
                    break
                else:
                    logger.warning(t('log.attempt_stop_button_not_found', attempt=attempt))
                    if attempt < max_retries:
                        self.adb.press_back()
                        time.sleep(1)
                        self.adb.open_shishibao_app()
                        time.sleep(2)

            if not stop_btn:
                logger.error(t('log.stop_button_not_found_after_retries', max_retries=max_retries))
                return False

            if not self.locator.click_element(stop_btn):
                logger.error(t('log.click_stop_record_failed'))
                return False

            # Step 3: Click "Cancel"
            logger.info(t('log.step_3_click_cancel'))
            time.sleep(2)
            root = self.locator.dump_and_parse()
            if not root:
                logger.warning(t('log.cannot_get_shishibao_ui'))
                # Fallback: press back key to exit without saving
                logger.info("Fallback: pressing back key to exit without saving")
                self.adb.press_back()
                time.sleep(1)
                self.adb.press_back()
                self.is_recording = False
                return True

            cancel_btn = self.locator.find_shishibao_cancel_button(root)
            if not cancel_btn:
                logger.warning(t('log.cancel_not_found'))
                # Fallback: press back key to exit without saving
                logger.info("Fallback: cancel button not found, pressing back key to exit")
                self.adb.press_back()
                time.sleep(1)
                self.adb.press_back()
                self.is_recording = False
                return True

            if not self.locator.click_element(cancel_btn):
                logger.warning(t('log.click_cancel_failed'))
                # Fallback: press back key to exit without saving
                logger.info("Fallback: click cancel failed, pressing back key to exit")
                self.adb.press_back()
                time.sleep(1)
                self.is_recording = False
                return True

            # Step 4: Wait for interface to restore
            logger.info(t('log.step_4_wait_restore'))
            time.sleep(2)

            self.is_recording = False
            logger.info("=" * 60)
            logger.info(t('log.shishibao_recording_cancelled'))
            logger.info("=" * 60)
            return True

        except Exception as e:
            logger.error(t('log.cancel_shishibao_recording_failed', error=e), exc_info=True)
            return False

    def export_recording(self, output_dir: str = "./output") -> Optional[str]:
        """
        Export recording file (Shishibao version doesn't need export, file saved in App).

        Args:
            output_dir: Output directory (unused)

        Returns:
            None (file already saved in Shishibao backend)
        """
        logger.info(t('log.recording_auto_saved'))
        logger.info(t('log.export_recording_hint'))
        return None

    def cleanup_device_files(self) -> bool:
        """Clean up device files (Shishibao version doesn't need cleanup)"""
        logger.info(t('log.no_cleanup_needed'))
        return True


if __name__ == "__main__":
    # Test code
    try:
        from .adb_controller import ADBController
    except ImportError:
        from adb_controller import ADBController

    controller = ADBController()
    if not controller.device_id:
        logger.error(t('log.no_device_detected'))
        exit(1)

    recorder = ScreenRecorder(controller)

    # Test start recording
    logger.info(t('log.test_shishibao_recording'))
    if recorder.start_recording():
        logger.info(t('log.recording_started_waiting'))
        time.sleep(10)

        if recorder.stop_recording():
            logger.info(t('log.test_success'))
        else:
            logger.error(t('log.stop_recording_failed_test'))
    else:
        logger.error(t('log.start_recording_failed_test'))
