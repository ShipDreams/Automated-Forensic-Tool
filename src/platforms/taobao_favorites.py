#!/usr/bin/env python3
"""
Taobao Favorites Operations Module.
Handles adding/removing favorites, navigating favorites list, and clicking items.

Note: Favorites pages in Taobao are WebView-rendered, so XML dump is mostly useless.
Image recognition (ImageLocator) is the primary method for in-list operations.
"""

import time
import logging
from typing import Optional

from locales import t

logger = logging.getLogger(__name__)


class TaobaoFavorites:
    """Taobao favorites operations for pre-screening flow."""

    def __init__(self, adb_controller, ui_locator, antibot=None, stop_checker=None, captcha_handler=None):
        """
        Initialize favorites operator.

        Args:
            adb_controller: ADBController instance
            ui_locator: UILocator instance
            antibot: Optional AntiBot instance for human-like delays
        """
        self.adb = adb_controller
        self.locator = ui_locator
        self.antibot = antibot
        self._stop_checker = stop_checker
        self._img_locator = None
        self._favorite_scroll_index = 0
        self._captcha_handler = captcha_handler
        self._last_action_failure_reason: Optional[str] = None

    def set_stop_checker(self, stop_checker):
        """Set a callback returning True when execution should stop."""
        self._stop_checker = stop_checker

    def set_captcha_handler(self, captcha_handler):
        """Set a callback used when an element-finding step is about to fail."""
        self._captcha_handler = captcha_handler

    def _handle_captcha_before_failure(self, step_name: str) -> str:
        """Check captcha only when a step is about to fail after retries are exhausted."""
        if not self._captcha_handler:
            return "not_detected"
        return self._captcha_handler(step_name)

    def consume_last_action_failure_reason(self) -> Optional[str]:
        """Return and clear the last favorites-action failure reason."""
        reason = self._last_action_failure_reason
        self._last_action_failure_reason = None
        return reason

    def _check_stop(self):
        """Raise when execution has been asked to stop."""
        if self._stop_checker and self._stop_checker():
            raise InterruptedError("Execution stopped")

    def _get_image_locator(self):
        """Get image locator instance."""
        if self._img_locator is None:
            self._img_locator = self.locator._get_image_locator()
        return self._img_locator

    def _click_by_template_first(self, template_name: str, threshold: float = 0.7,
                                 max_attempts: int = 3) -> bool:
        """
        Click by OpenCV template first.

        When a template exists, do not dump XML before trying image matching.
        """
        img = self._get_image_locator()
        if not img or not img.template_exists(template_name):
            return False
        return img.find_and_click(template_name, threshold=threshold, max_attempts=max_attempts)

    def _dismiss_ad_popup_once(self, context: str) -> bool:
        """
        Best-effort single attempt to close Taobao ad popup via template matching.

        Returns:
            True if ad close button matched and clicked, False otherwise.
        """
        logger.warning(f"{context}: target element not found, trying ad popup close once...")
        if not self._click_by_template_first("del_ads", threshold=0.85, max_attempts=1):
            logger.warning(f"{context}: ad popup close template not matched")
            return False

        logger.info(f"{context}: ad popup close button clicked")
        self._sleep(1200, 1800)
        return True

    def _sleep(self, min_ms: int = 800, max_ms: int = 1500):
        """Human-like random delay."""
        import random
        delay = random.uniform(min_ms / 1000, max_ms / 1000)
        if not self._stop_checker:
            time.sleep(delay)
            return

        remaining = delay
        while remaining > 0:
            self._check_stop()
            chunk = min(0.2, remaining)
            time.sleep(chunk)
            remaining -= chunk

    def _reset_list_navigation_state(self):
        """Reset favorites list cursor."""
        self._favorite_scroll_index = 0

    def _is_on_favorites_page(self) -> bool:
        """Fast check for the favorites list page without dumping XML."""
        img = self._get_image_locator()
        if img and img.find_template("manage_btn", threshold=0.6):
            return True
        return False

    def _get_primary_item_tap_point(self, width: int, height: int) -> tuple:
        """
        Return the fixed tap point for the first fully visible favorite item.

        The list layout is more stable than the nth-row y-coordinate. We scroll the
        next target item into this slot, then always tap the same position.
        """
        tap_x = int(width * 0.28)
        tap_y = int(height * 0.24)
        return tap_x, tap_y

    def _scroll_to_next_visible_item(self, width: int, height: int, fine_tune: bool = False) -> bool:
        """
        Scroll the favorites list so the next item moves into the primary tap slot.

        `fine_tune=True` uses a shorter swipe to correct slight row misalignment
        without skipping an item.
        """
        start_x = int(width * 0.30)
        if fine_tune:
            start_y = int(height * 0.36)
            end_y = int(height * 0.24)
            duration_ms = 230
        else:
            start_y = int(height * 0.42)
            end_y = int(height * 0.20)
            duration_ms = 340

        self._check_stop()
        logger.info(f"Scrolling favorites list (fine_tune={fine_tune})")
        if not self.adb.swipe(start_x, start_y, start_x, end_y, duration_ms=duration_ms):
            logger.warning("Favorites list swipe failed")
            return False

        self._sleep(1000, 1600)
        return True

    def navigate_to_favorites(self, _captcha_retry_allowed: bool = True) -> bool:
        """
        Navigate to My Favorites page from Taobao home.

        Steps:
        1. Click "我的淘宝" bottom tab
        2. Click "收藏" entry

        Returns:
            Whether navigation was successful
        """
        logger.info("Navigating to favorites page...")
        self._reset_list_navigation_state()
        self._check_stop()

        # Step 1: Click "我的淘宝" tab
        if not self._click_by_template_first("my_taobao_tab", threshold=0.7):
            root = self.locator.dump_and_parse()
            if not root:
                logger.error("Cannot get UI hierarchy")
                return False

            my_taobao_tab = self.locator.find_my_taobao_tab(root)
            if not my_taobao_tab:
                captcha_status = self._handle_captcha_before_failure("navigate_to_favorites_find_my_taobao_tab")
                if captcha_status == "resolved" and _captcha_retry_allowed:
                    logger.info("Captcha resolved, retrying navigate_to_favorites once")
                    return self.navigate_to_favorites(_captcha_retry_allowed=False)
                logger.error("'我的淘宝' tab not found")
                return False
            if not self.locator.click_element(my_taobao_tab):
                captcha_status = self._handle_captcha_before_failure("navigate_to_favorites_click_my_taobao_tab")
                if captcha_status == "resolved" and _captcha_retry_allowed:
                    logger.info("Captcha resolved, retrying navigate_to_favorites once")
                    return self.navigate_to_favorites(_captcha_retry_allowed=False)
                logger.error("Failed to click '我的淘宝' tab")
                return False

        self._sleep(2000, 3000)
        self._check_stop()

        # Step 2: Click "收藏" entry
        if self._click_by_template_first("favorites_entry", threshold=0.75):
            logger.info("Clicked favorites entry via image recognition")
            self._sleep(2000, 3000)
            return True

        root = self.locator.dump_and_parse()
        if root:
            fav_entry = self.locator.find_favorites_entry(root)
            if fav_entry and self.locator.click_element(fav_entry):
                logger.info("Clicked favorites entry via XML")
                self._sleep(2000, 3000)
                return True

        captcha_status = self._handle_captcha_before_failure("navigate_to_favorites_find_entry")
        if captcha_status == "resolved" and _captcha_retry_allowed:
            logger.info("Captcha resolved, retrying navigate_to_favorites once")
            return self.navigate_to_favorites(_captcha_retry_allowed=False)
        logger.error("Failed to find favorites entry")
        return False

    def clear_favorites(self) -> bool:
        """
        Clear all items from favorites.

        Steps:
        1. Navigate to favorites list
        2. Click "管理" button
        3. Click "全选"
        4. Click "删除"
        5. Confirm deletion

        Returns:
            Whether clearing was successful
        """
        logger.info("Clearing favorites...")
        self._check_stop()

        # Navigate to favorites
        if not self.navigate_to_favorites():
            logger.error("Failed to navigate to favorites for clearing")
            return False

        self._sleep(1500, 2500)
        self._check_stop()

        img = self._get_image_locator()
        if not img:
            logger.error("Image locator not available, cannot operate on WebView favorites page")
            return False

        # Click "管理" button (WebView page, must use image recognition)
        logger.info("Clicking manage button...")
        if not img.find_and_click("manage_btn", threshold=0.7, max_attempts=3):
            # Favorites might be empty — no manage button visible
            logger.info("Manage button not found, favorites may be empty")
            return True

        self._sleep(1000, 2000)
        self._check_stop()

        # Click "全选" button
        logger.info("Clicking select all...")
        if not img.find_and_click("select_all_btn", threshold=0.7, max_attempts=3):
            logger.warning("Select all button not found")
            # Try to exit manage mode
            img.find_and_click("exit_manage_btn", threshold=0.7)
            return False

        self._sleep(800, 1200)
        self._check_stop()

        # Click "删除" button
        logger.info("Clicking delete...")
        if not img.find_and_click("delete_btn", threshold=0.7, max_attempts=3):
            logger.warning("Delete button not found")
            img.find_and_click("exit_manage_btn", threshold=0.7)
            return False

        self._sleep(1500, 2200)
        self._check_stop()
        logger.info("Delete button clicked; assuming favorites clear completed without confirmation dialog")

        self._sleep(1500, 2500)
        self._check_stop()

        logger.info("Favorites cleared")
        return True

    def add_to_favorites(self, _captcha_retry_allowed: bool = True) -> bool:
        """
        Add current product to favorites (click favorite button on product detail page).

        Returns:
            Whether adding was successful
        """
        logger.info("Adding product to favorites...")
        self._check_stop()
        self._last_action_failure_reason = None

        if self._click_by_template_first("favorite_btn", threshold=0.7):
            if self._confirm_favorite_success():
                logger.info("Product added to favorites via image recognition")
                self._sleep(1000, 1500)
                return True
            captcha_status = self._handle_captcha_before_failure("confirm_favorite_success")
            if captcha_status == "resolved" and _captcha_retry_allowed:
                logger.info("Captcha resolved, retrying add_to_favorites once")
                return self.add_to_favorites(_captcha_retry_allowed=False)
            self._last_action_failure_reason = "收藏失败"
            logger.warning("Favorite button clicked but success popup was not detected")
            return False

        if self._dismiss_ad_popup_once("Product detail favorite button"):
            if self._click_by_template_first("favorite_btn", threshold=0.7):
                if self._confirm_favorite_success():
                    logger.info("Product added to favorites via image recognition after closing ad popup")
                    self._sleep(1000, 1500)
                    return True
                captcha_status = self._handle_captcha_before_failure("confirm_favorite_success")
                if captcha_status == "resolved" and _captcha_retry_allowed:
                    logger.info("Captcha resolved, retrying add_to_favorites once")
                    return self.add_to_favorites(_captcha_retry_allowed=False)
                self._last_action_failure_reason = "收藏失败"
                logger.warning("Favorite button clicked after closing ad popup but success popup was not detected")
                return False

        captcha_status = self._handle_captcha_before_failure("add_to_favorites")
        if captcha_status == "resolved" and _captcha_retry_allowed:
            logger.info("Captcha resolved, retrying add_to_favorites once")
            return self.add_to_favorites(_captcha_retry_allowed=False)
        self._last_action_failure_reason = "收藏失败"
        logger.warning("Failed to find favorite button")
        return False

    def _confirm_favorite_success(self) -> bool:
        """Verify that the favorite success popup appeared after clicking favorite."""
        img = self._get_image_locator()
        if not img or not img.template_exists("favorite_success_popup"):
            logger.warning("Favorite success popup template not available")
            return False

        # Taobao first shows a transient toast for a few seconds after tapping
        # favorite; wait for it to disappear before matching the wishlist popup.
        logger.info("Waiting 5 seconds before checking favorite success popup...")
        self._sleep(4800, 5400)

        for attempt in range(1, 3):
            self._check_stop()
            logger.info(f"Checking favorite success popup, attempt {attempt}/2")
            if img.find_template("favorite_success_popup", threshold=0.75):
                logger.info("Favorite success popup detected")
                return True
            if attempt < 2:
                self._sleep(600, 900)
        logger.warning("Favorite success popup not detected after retries")
        return False

    def click_favorite_item(self, index: int = 0, _captcha_retry_allowed: bool = True) -> bool:
        """
        Click the nth item in favorites list.

        WebView page, XML dump is unreliable. Instead of tapping the nth y-position,
        keep scrolling the next item into one stable "first visible item" slot and
        tap that fixed point every time.

        Args:
            index: 0-based index of the item to click

        Returns:
            Whether click was successful
        """
        logger.info(f"Clicking favorite item at index {index}...")
        self._check_stop()

        screen_size = self.adb.get_screen_size()
        if not screen_size:
            logger.error("Cannot get screen size")
            return False

        width, height = screen_size
        if index < 0:
            logger.error("Favorite item index must be >= 0")
            return False

        if index < self._favorite_scroll_index:
            logger.warning("Favorite list index moved backwards, resetting cursor")
            self._favorite_scroll_index = 0

        while self._favorite_scroll_index < index:
            if not self._scroll_to_next_visible_item(width, height):
                return False
            self._favorite_scroll_index += 1

        tap_x, tap_y = self._get_primary_item_tap_point(width, height)

        for attempt in range(1, 4):
            self._check_stop()
            logger.info(f"Tapping favorite item {index} at ({tap_x}, {tap_y}), attempt={attempt}")
            if not self.adb.tap(tap_x, tap_y):
                logger.warning("Tap failed, retrying...")
                continue

            self._sleep(2500, 3500)
            self._check_stop()
            if not self._is_on_favorites_page():
                return True

            logger.warning("Still on favorites page after tap, adjusting list position...")
            self._scroll_to_next_visible_item(width, height, fine_tune=True)

        captcha_status = self._handle_captcha_before_failure("click_favorite_item")
        if captcha_status == "resolved" and _captcha_retry_allowed:
            logger.info("Captcha resolved, retrying click_favorite_item once")
            return self.click_favorite_item(index=index, _captcha_retry_allowed=False)
        logger.error("Failed to open favorite item after retries")
        return False

    def go_back_to_favorites_list(self, _captcha_retry_allowed: bool = True) -> bool:
        """
        Go back from product detail page to favorites list.

        Returns:
            Whether navigation back was successful
        """
        logger.info("Going back to favorites list...")
        self._check_stop()
        self.adb.press_back()
        self._sleep(1500, 2500)

        img = self._get_image_locator()
        for attempt in range(1, 3):
            if img and img.find_template("manage_btn", threshold=0.6):
                logger.info("Successfully returned to favorites list")
                return True
            if attempt < 2:
                logger.warning("Favorites page not confirmed yet, retrying image check...")
                self._sleep(1200, 1800)

        captcha_status = self._handle_captcha_before_failure("go_back_to_favorites_list")
        if captcha_status == "resolved" and _captcha_retry_allowed:
            logger.info("Captcha resolved, retrying go_back_to_favorites_list once")
            return self.go_back_to_favorites_list(_captcha_retry_allowed=False)
        logger.error("Failed to confirm return to favorites list")
        return False
