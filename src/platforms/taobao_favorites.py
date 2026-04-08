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

    def __init__(self, adb_controller, ui_locator, antibot=None):
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
        self._img_locator = None
        self._favorite_scroll_index = 0

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
        time.sleep(delay)

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

        logger.info(f"Scrolling favorites list (fine_tune={fine_tune})")
        if not self.adb.swipe(start_x, start_y, start_x, end_y, duration_ms=duration_ms):
            logger.warning("Favorites list swipe failed")
            return False

        self._sleep(1000, 1600)
        return True

    def navigate_to_favorites(self) -> bool:
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

        # Step 1: Click "我的淘宝" tab
        if not self._click_by_template_first("my_taobao_tab", threshold=0.7):
            root = self.locator.dump_and_parse()
            if not root:
                logger.error("Cannot get UI hierarchy")
                return False

            my_taobao_tab = self.locator.find_my_taobao_tab(root)
            if not my_taobao_tab:
                logger.error("'我的淘宝' tab not found")
                return False
            if not self.locator.click_element(my_taobao_tab):
                logger.error("Failed to click '我的淘宝' tab")
                return False

        self._sleep(2000, 3000)

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

        # Navigate to favorites
        if not self.navigate_to_favorites():
            logger.error("Failed to navigate to favorites for clearing")
            return False

        self._sleep(1500, 2500)

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

        # Click "全选" button
        logger.info("Clicking select all...")
        if not img.find_and_click("select_all_btn", threshold=0.7, max_attempts=3):
            logger.warning("Select all button not found")
            # Try to exit manage mode
            img.find_and_click("exit_manage_btn", threshold=0.7)
            return False

        self._sleep(800, 1200)

        # Click "删除" button
        logger.info("Clicking delete...")
        if not img.find_and_click("delete_btn", threshold=0.7, max_attempts=3):
            logger.warning("Delete button not found")
            img.find_and_click("exit_manage_btn", threshold=0.7)
            return False

        self._sleep(1000, 1500)

        # Confirm deletion dialog (try XML for dialog buttons)
        root = self.locator.dump_and_parse()
        confirmed = False
        if root:
            for keyword in ['确定', '确认', '删除', 'OK']:
                btn = self.locator.find_element_by_text(root, keyword, exact=True)
                if btn:
                    if self.locator.click_element(btn):
                        logger.info(f"Confirmed deletion with '{keyword}' button")
                        confirmed = True
                        break

        if not confirmed:
            # Try tapping common confirmation button positions
            screen_size = self.adb.get_screen_size()
            if screen_size:
                w, h = screen_size
                # Confirmation button typically in center-right of dialog
                self.adb.tap(w * 3 // 4, h // 2)
                logger.info("Tapped confirmation area")

        self._sleep(1500, 2500)

        logger.info("Favorites cleared")
        return True

    def add_to_favorites(self) -> bool:
        """
        Add current product to favorites (click favorite button on product detail page).

        Returns:
            Whether adding was successful
        """
        logger.info("Adding product to favorites...")

        if self._click_by_template_first("favorite_btn", threshold=0.7):
            logger.info("Product added to favorites via image recognition")
            self._sleep(1000, 1500)
            return True

        if self._dismiss_ad_popup_once("Product detail favorite button"):
            if self._click_by_template_first("favorite_btn", threshold=0.7):
                logger.info("Product added to favorites via image recognition after closing ad popup")
                self._sleep(1000, 1500)
                return True

        logger.warning("Failed to find favorite button")
        return False

    def click_favorite_item(self, index: int = 0) -> bool:
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
            logger.info(f"Tapping favorite item {index} at ({tap_x}, {tap_y}), attempt={attempt}")
            if not self.adb.tap(tap_x, tap_y):
                logger.warning("Tap failed, retrying...")
                continue

            self._sleep(2500, 3500)
            if not self._is_on_favorites_page():
                return True

            logger.warning("Still on favorites page after tap, adjusting list position...")
            self._scroll_to_next_visible_item(width, height, fine_tune=True)

        logger.error("Failed to open favorite item after retries")
        return False

    def go_back_to_favorites_list(self) -> bool:
        """
        Go back from product detail page to favorites list.

        Returns:
            Whether navigation back was successful
        """
        logger.info("Going back to favorites list...")
        self.adb.press_back()
        self._sleep(1500, 2500)

        # Verify we're back on favorites page by checking for manage button
        img = self._get_image_locator()
        if img:
            match = img.find_template("manage_btn", threshold=0.6)
            if match:
                logger.info("Successfully returned to favorites list")
                return True

        # Secondary check via XML
        root = self.locator.dump_and_parse()
        if root:
            for node in root.iter():
                text = node.attrib.get('text', '')
                desc = node.attrib.get('content-desc', '')
                if '收藏' in text or '收藏' in desc:
                    logger.info("Detected favorites page indicator")
                    return True

        # Press back once more if needed
        logger.info("First back may not have returned to favorites, trying again...")
        self.adb.press_back()
        self._sleep(1500, 2000)

        return True  # Assume success to continue flow
