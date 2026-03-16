#!/usr/bin/env python3
"""
Taobao Platform Handler
Implements complete forensic workflow for Taobao/Tmall products.
"""

import time
import logging
from typing import Optional

from locales import t
from .base_handler import BasePlatformHandler

logger = logging.getLogger(__name__)


class TaobaoHandler(BasePlatformHandler):
    """
    Taobao Platform Handler

    Handles Taobao/Tmall product forensics, including:
    - Opening Taobao from app store
    - Inputting product link in search box
    - Playing product video
    - Viewing shop qualification certificates
    """

    def get_platform_name(self) -> str:
        return "taobao"

    def get_platform_display_name(self) -> str:
        return "Taobao"

    def get_app_package(self) -> str:
        return "com.taobao.taobao"

    def get_app_store_search_keyword(self) -> str:
        # Chinese keyword for app store search (matches actual app name)
        return "淘宝"

    def open_app_from_store(self, wait_time: int = 6) -> bool:
        """Search Taobao in app store."""
        logger.info("=" * 60)
        logger.info(t('log.taobao_open_app_store'))
        logger.info("=" * 60)

        # Use brand-adaptive search protocol to open app store
        if not self.adb.open_app_store_and_search_taobao():
            logger.error(t('log.taobao_app_store_search_failed'))
            return False

        # Wait for search results (with human-like delay)
        logger.info(t('log.waiting_search_results', seconds=wait_time))
        self._sleep(wait_time * 1000 - 500, wait_time * 1000 + 500)

        logger.info(t('log.app_store_results_loaded'))
        return True

    def launch_app(self, wait_time: int = 10) -> bool:
        """
        Launch Taobao directly via ADB command.

        Instead of clicking 'Open' button in app store (which may redirect to
        marketing/promotional tabs like Flash Sale), use ADB monkey command to
        launch Taobao's main activity, ensuring it opens to the default home page.
        """
        logger.info("=" * 60)
        logger.info(t('log.taobao_launch_from_store'))
        logger.info("=" * 60)

        # Screenshot app store search results as proof of legitimate source
        self.take_screenshot(t('log.screenshot_app_store_proof'))

        # Launch Taobao directly via ADB (avoid marketing page from app store)
        logger.info(t('log.launch_taobao_direct'))
        if not self.adb.launch_app(self.get_app_package()):
            logger.error(t('log.click_open_button_failed'))
            return False

        self._sleep_after_click()

        # Wait for Taobao app to fully launch
        logger.info(t('log.waiting_app_launch', seconds=wait_time))
        self._sleep(wait_time * 1000 - 1000, wait_time * 1000 + 1000)

        # Confirm Taobao is opened
        current_focus = self.adb.get_current_focus()
        if current_focus:
            logger.info(t('log.current_app', app=current_focus))
            if 'taobao' in current_focus.lower():
                logger.info(t('log.taobao_app_launched'))
                return True

        logger.warning(t('log.cannot_confirm_app_launch'))
        return True

    def navigate_to_product(self, product_url: str, wait_time: int = 8) -> bool:
        """Open product link via Taobao search box."""
        logger.info("=" * 60)
        logger.info(t('log.taobao_navigate_to_product'))
        logger.info("=" * 60)

        try:
            # Extra wait to ensure Taobao home is fully loaded
            logger.info(t('log.waiting_home_load'))
            self._sleep(2500, 3500)

            # Try to close possible popups
            logger.info(t('log.closing_popups'))
            self.adb.press_back()
            self._sleep(800, 1200)

            # Dump UI hierarchy and find search box (with retry)
            max_dump_attempts = 2
            root = None

            for attempt in range(1, max_dump_attempts + 1):
                logger.info(t('log.finding_search_box', attempt=attempt, max=max_dump_attempts))
                root = self.locator.dump_and_parse()
                if root:
                    break

                if attempt < max_dump_attempts:
                    logger.warning(t('log.ui_dump_failed_retry'))
                    self.adb.press_back()
                    self._sleep(1500, 2500)

            if not root:
                logger.error(t('log.cannot_get_ui_hierarchy'))
                return False

            search_box = self.locator.find_taobao_search_box(root)
            if not search_box:
                logger.error(t('log.search_box_not_found'))
                return False

            # Click search box to activate input
            logger.info(t('log.clicking_search_box'))
            if not self.locator.click_element(search_box):
                logger.error(t('log.click_search_box_failed'))
                return False

            self._sleep_after_click()

            # Input product link
            logger.info(t('log.inputting_product_url', url=product_url))
            if not self.adb.input_text(product_url):
                logger.error(t('log.input_url_failed'))
                return False

            self._sleep(800, 1200)

            # Press Enter to trigger search
            logger.info(t('log.pressing_enter'))
            if not self.adb.press_enter():
                logger.error(t('log.press_enter_failed'))

                # Try to find and click search button
                logger.info(t('log.trying_search_button'))
                root = self.locator.dump_and_parse()
                if root:
                    search_button = self.locator.find_search_button(root)
                    if search_button:
                        if not self.locator.click_element(search_button):
                            logger.error(t('log.click_search_button_failed'))
                            return False
                        self._sleep_after_click()
                    else:
                        logger.error(t('log.search_button_not_found'))
                        return False
                else:
                    return False

            # Wait for product page to load
            logger.info(t('log.waiting_product_load', seconds=wait_time))
            self._sleep(wait_time * 1000 - 1000, wait_time * 1000 + 1000)

            # Screenshot 2: Taobao product page
            self.take_screenshot(t('log.screenshot_product_page'))

            logger.info(t('log.product_page_opened'))
            return True

        except Exception as e:
            logger.error(t('log.open_product_failed_error', error=e))
            return False

    def play_video(self, max_attempts: int = 3) -> bool:
        """
        Play product video.

        Note: Taobao product videos usually auto-play, this method is now a fallback.
        Main flow should use replay_video_from_start() for replay from beginning.
        """
        logger.info("=" * 60)
        logger.info(t('log.play_video_fallback'))
        logger.info("=" * 60)

        # Use UI locator to find and click video
        success = self.locator.find_and_click_video(max_attempts=max_attempts)

        if success:
            logger.info(t('log.video_triggered'))
            self._sleep(2500, 3500)
        else:
            logger.warning(t('log.video_trigger_failed'))

        return success

    def replay_video_from_start(self) -> bool:
        """
        Replay video from start (drag progress bar to 0 seconds).

        Taobao product videos usually auto-play, this method:
        1. If video is paused, click play first
        2. Unmute audio
        3. Drag progress bar to start position

        Returns:
            Whether successful
        """
        logger.info("=" * 60)
        logger.info(t('log.replay_video_from_start'))
        logger.info("=" * 60)

        # Check if video is paused (play button iv_play_btn visible means paused)
        root = self.locator.dump_and_parse()
        if root:
            play_btn = self.locator.find_element_by_id(root, "com.taobao.taobao:id/iv_play_btn")
            if play_btn:
                logger.info(t('log.video_paused_clicking_play'))
                self.locator.click_element(play_btn, apply_offset=False)
                self._sleep(1500, 2500)

        # Unmute audio
        self.unmute_video(max_attempts=2)

        # Drag progress bar to start
        logger.info(t('log.dragging_progress_bar'))
        success = self.locator.drag_video_progress_to_start(max_attempts=2)

        if success:
            logger.info(t('log.video_replay_started'))
        else:
            logger.warning(t('log.progress_bar_drag_failed'))

        # After dragging, check if video ended (play button visible means paused/ended)
        self._sleep(500, 1000)
        root = self.locator.dump_and_parse()
        if root:
            play_btn = self.locator.find_element_by_id(root, "com.taobao.taobao:id/iv_play_btn")
            if play_btn:
                logger.info(t('log.play_button_detected_clicking'))
                self.locator.click_element(play_btn, apply_offset=False)
                self._sleep(1000, 1500)

        return True  # Continue flow even if drag failed

    def unmute_video(self, max_attempts: int = 2) -> bool:
        """Unmute video audio."""
        logger.info("=" * 60)
        logger.info(t('log.unmute_video'))
        logger.info("=" * 60)

        for attempt in range(1, max_attempts + 1):
            logger.info(t('log.finding_volume_button', attempt=attempt, max=max_attempts))

            root = self.locator.dump_and_parse()
            if not root:
                logger.warning(t('log.cannot_get_ui_hierarchy'))
                if attempt < max_attempts:
                    self._sleep(1500, 2500)
                continue

            volume_btn = self.locator.find_volume_button(root)
            if volume_btn:
                # Volume button icon is small, don't apply coordinate offset
                if self.locator.click_element(volume_btn, apply_offset=False):
                    logger.info(t('log.video_unmuted'))
                    self._sleep(1500, 2500)
                    return True
                else:
                    logger.warning(t('log.click_volume_button_failed'))
            else:
                logger.warning(t('log.volume_button_not_found'))

            if attempt < max_attempts:
                self._sleep(1500, 2500)

        logger.warning(t('log.unmute_failed_continue'))
        return False

    def view_shop_info(self) -> bool:
        """View shop info (click shop button to enter shop page)."""
        logger.info(t('log.clicking_shop_button'))

        root = self.locator.dump_and_parse()
        if not root:
            logger.error(t('log.cannot_get_ui_hierarchy'))
            return False

        shop_btn = self.locator.find_shop_button(root)
        if not shop_btn:
            logger.error(t('log.shop_button_not_found'))
            return False

        if not self.locator.click_element(shop_btn):
            logger.error(t('log.click_shop_button_failed'))
            return False

        self._sleep_after_click()

        logger.info(t('log.waiting_shop_page'))
        self._sleep(2500, 3500)

        # 点击店铺名称文本进入店铺主页（带重试机制，复杂页面可能加载较慢）
        logger.info(t('log.clicking_shop_name'))
        max_retries = 5
        shop_name = None
        for attempt in range(1, max_retries + 1):
            root = self.locator.dump_and_parse()
            if not root:
                logger.warning(f"[重试 {attempt}/{max_retries}] 无法获取UI层次结构，等待后重试...")
                self._sleep(1500 + attempt * 500, 2000 + attempt * 500)
                continue

            shop_name = self.locator.find_shop_name_or_avatar(root)
            if shop_name:
                logger.info(f"[重试 {attempt}/{max_retries}] 成功找到店铺名称元素")
                break
            else:
                logger.warning(f"[重试 {attempt}/{max_retries}] 未找到店铺名称，等待页面加载后重试...")
                self._sleep(1500 + attempt * 500, 2000 + attempt * 500)

        if not shop_name:
            logger.error(t('log.shop_name_not_found'))
            return False

        if not self.locator.click_element(shop_name):
            logger.error(t('log.click_shop_name_failed'))
            return False

        self._sleep_after_click()

        logger.info(t('log.waiting_shop_home'))
        self._sleep(3500, 4500)

        # Screenshot 3: Shop home page
        self.take_screenshot(t('log.screenshot_shop_home'))

        logger.info(t('log.entered_shop_home'))
        return True

    def view_qualification(self) -> bool:
        """View shop qualification certificates."""
        logger.info("=" * 60)
        logger.info(t('log.view_qualification'))
        logger.info("=" * 60)

        try:
            # First enter shop page
            if not self.view_shop_info():
                return False

            # 点击"资质证照"按钮（带重试机制，店铺主页可能加载较慢）
            logger.info(t('log.finding_qualification_button'))
            max_retries = 3
            qualification_btn = None
            for attempt in range(1, max_retries + 1):
                root = self.locator.dump_and_parse()
                if not root:
                    logger.warning(f"[重试 {attempt}/{max_retries}] 无法获取店铺主页UI，等待后重试...")
                    self._sleep(1500 + attempt * 500, 2000 + attempt * 500)
                    continue

                qualification_btn = self.locator.find_qualification_button(root)
                if qualification_btn:
                    logger.info(f"[重试 {attempt}/{max_retries}] 成功找到资质证照按钮")
                    break
                else:
                    logger.warning(f"[重试 {attempt}/{max_retries}] 未找到资质证照按钮，等待页面加载后重试...")
                    self._sleep(1500 + attempt * 500, 2000 + attempt * 500)

            if not qualification_btn:
                logger.warning(t('log.qualification_button_not_found'))
                logger.warning(t('log.qualification_not_found_reason'))
                return False

            if not self.locator.click_element(qualification_btn):
                logger.error(t('log.click_qualification_failed'))
                return False

            self._sleep_after_click()

            logger.info(t('log.waiting_qualification_load'))
            self._sleep(2500, 3500)

            # Detect captcha after qualification page load
            if not self._handle_captcha_if_detected():
                return False

            # Stay to record qualification info
            logger.info(t('log.recording_qualification'))
            time.sleep(10)

            # Screenshot 4: Qualification page
            self.take_screenshot(t('log.screenshot_qualification'))

            logger.info(t('log.qualification_view_complete'))
            return True

        except Exception as e:
            logger.error(t('log.view_qualification_failed', error=e))
            return False
