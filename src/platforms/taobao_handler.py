#!/usr/bin/env python3
"""
Taobao Platform Handler
Implements complete forensic workflow for Taobao/Tmall products.
"""

import time
import json
import logging
from pathlib import Path
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

    def _dismiss_ad_popup_once(self, context: str) -> bool:
        """
        Best-effort single attempt to close a Taobao ad popup via template matching.

        Returns:
            True if ad close button matched and clicked, False otherwise.
        """
        logger.warning(f"{context}: target element not found, trying ad popup close once...")
        img_locator = self.locator._get_image_locator()
        if not img_locator or not img_locator.template_exists("del_ads"):
            logger.warning(f"{context}: ad popup close template not available")
            return False

        if not img_locator.find_and_click("del_ads", threshold=0.85, max_attempts=1):
            logger.warning(f"{context}: ad popup close template not matched")
            return False

        logger.info(f"{context}: ad popup close button clicked")
        self._sleep(1200, 1800)
        return True

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

            root = self.locator.dump_and_parse()
            if not root:
                logger.error(t('log.cannot_get_ui_hierarchy'))
                return False

            search_box = self.locator.find_taobao_search_box(root)
            if not search_box:
                if not self._dismiss_ad_popup_once("Taobao home search box"):
                    logger.error(t('log.search_box_not_found'))
                    return False

                root = self.locator.dump_and_parse()
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
        Prepare product video for recording.

        Current Taobao phase-2 flow only needs to ensure audio is enabled.
        Do not click play or drag the progress bar; after unmuting, the caller
        immediately enters the configured recording wait duration.
        """
        logger.info("=" * 60)
        logger.info(t('log.replay_video_from_start'))
        logger.info("=" * 60)

        success = self.unmute_video(max_attempts=3, image_only=True)
        if success:
            logger.info(t('log.video_replay_started'))
            return True

        logger.warning(t('log.unmute_failed_continue'))
        return False

    def unmute_video(self, max_attempts: int = 3, image_only: bool = True) -> bool:
        """Unmute video audio. Prefer direct image recognition when templates exist."""
        logger.info("=" * 60)
        logger.info(t('log.unmute_video'))
        logger.info("=" * 60)

        img_locator = self.locator._get_image_locator()
        if img_locator and img_locator.template_exists("mute_btn"):
            logger.info("Trying image recognition for mute button...")
            if img_locator.find_and_click("mute_btn", threshold=0.70, max_attempts=max_attempts):
                logger.info(t('log.video_unmuted'))
                self._sleep(1000, 1500)
                return True
            if image_only:
                logger.warning("Image recognition did not find mute button, skipping XML fallback")
                return False
            logger.info("Image recognition failed, falling back to XML dump...")
        elif image_only:
            logger.warning("Mute button template not available, skipping XML fallback")
            return False

        # Fallback: XML dump approach (only when explicitly allowed)
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

        img_locator = self.locator._get_image_locator()
        if img_locator and img_locator.template_exists("shop_btn"):
            logger.info("Trying image recognition for shop button...")
            if img_locator.find_and_click("shop_btn", threshold=0.75):
                logger.info("Shop button clicked via image recognition")
                self._sleep_after_click()
                self._sleep(2500, 3500)
                return self._navigate_to_shop_home(root=None)

            if self._dismiss_ad_popup_once("Product detail shop button"):
                if img_locator.find_and_click("shop_btn", threshold=0.75, max_attempts=1):
                    logger.info("Shop button clicked via image recognition after closing ad popup")
                    self._sleep_after_click()
                    self._sleep(2500, 3500)
                    return self._navigate_to_shop_home(root=None)

            logger.error(t('log.shop_button_not_found'))
            return False

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

        return self._navigate_to_shop_home(root=None)

    def _navigate_to_shop_home(self, root=None) -> bool:
        """Click shop name to enter shop home page (extracted from view_shop_info)."""
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
        self.reset_qualification_context(cleanup_file=True)

        try:
            # First enter shop page
            if not self.view_shop_info():
                self.set_qualification_issue("资质查看失败")
                return False

            # 点击"资质证照"按钮（如果首次未找到，只尝试一次广告弹窗关闭）
            logger.info(t('log.finding_qualification_button'))
            qualification_btn = None
            root = self.locator.dump_and_parse()
            if root:
                qualification_btn = self.locator.find_qualification_button(root)

            if not qualification_btn:
                if not self._dismiss_ad_popup_once("Shop home qualification button"):
                    logger.warning(t('log.qualification_button_not_found'))
                    logger.warning(t('log.qualification_not_found_reason'))
                    self.set_qualification_issue("资质查看失败")
                    return False

                root = self.locator.dump_and_parse()
                if root:
                    qualification_btn = self.locator.find_qualification_button(root)

            if not qualification_btn:
                logger.warning(t('log.qualification_button_not_found'))
                logger.warning(t('log.qualification_not_found_reason'))
                self.set_qualification_issue("资质查看失败")
                return False

            if not self.locator.click_element(qualification_btn):
                logger.error(t('log.click_qualification_failed'))
                self.set_qualification_issue("资质查看失败")
                return False

            self._sleep_after_click()

            logger.info(t('log.waiting_qualification_load'))
            self._sleep(2500, 3500)

            # Detect captcha after qualification page load
            if not self._handle_captcha_if_detected():
                self.set_qualification_issue("资质查看失败")
                return False

            # Stay to record qualification info
            logger.info(t('log.recording_qualification'))
            time.sleep(10)

            # Screenshot 4: Qualification page
            self.take_screenshot(t('log.screenshot_qualification'))
            logger.info(t('log.ocr_capture_start'))
            local_capture = self.adb.take_screenshot_to_file()
            if local_capture:
                self.set_pending_qualification_capture(local_capture)
                logger.info("OCR task deferred until post-export drain")
            else:
                logger.warning(t('log.ocr_capture_save_failed'))

            logger.info(t('log.qualification_view_complete'))
            return True

        except Exception as e:
            self.set_qualification_issue("资质查看失败")
            logger.error(t('log.view_qualification_failed', error=e))
            return False

    def check_product_validity(self) -> bool:
        """
        Check if current product page shows a valid (non-expired) product.

        Dumps UI hierarchy and checks for invalid product keywords.

        Returns:
            True if product is valid, False if expired/removed/invalid
        """
        root = self.locator.dump_and_parse()
        if not root:
            logger.warning("Cannot get UI hierarchy for validity check, assuming invalid")
            return False

        # Load keywords from config
        invalid_keywords = self._get_invalid_product_keywords()

        for node in root.iter():
            text = node.attrib.get('text', '')
            desc = node.attrib.get('content-desc', '')
            for keyword in invalid_keywords:
                if keyword in text or keyword in desc:
                    logger.info(f"Product invalid: found keyword '{keyword}' in text='{text}' desc='{desc}'")
                    return False

        logger.info("Product validity check passed")
        return True

    def _get_invalid_product_keywords(self) -> list:
        """Load invalid product keywords from config."""
        try:
            config_path = Path(__file__).parent.parent.parent / "config" / "platform_rules" / "taobao.json"
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            keywords = config.get('invalid_product_keywords', [])
            if keywords:
                return keywords
        except Exception as e:
            logger.debug(f"Failed to load config keywords: {e}")

        # Default fallback
        return [
            "商品已下架", "宝贝已下架", "该商品已下架",
            "商品过期", "宝贝已过期", "已失效",
            "没有找到相应的商品", "该宝贝已不存在",
            "商品不存在", "页面不存在", "抱歉，没有找到",
            "该链接已失效", "商品已被删除",
            "卖家已关闭交易", "该交易已关闭",
            "宝贝不存在", "商品信息已过期",
            "宝贝不在了", "商品过期不存在"
        ]
