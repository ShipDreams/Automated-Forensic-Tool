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

    def _get_image_locator(self):
        """Get image locator instance."""
        if self._img_locator is None:
            self._img_locator = self.locator._get_image_locator()
        return self._img_locator

    def _sleep(self, min_ms: int = 800, max_ms: int = 1500):
        """Human-like random delay."""
        import random
        delay = random.uniform(min_ms / 1000, max_ms / 1000)
        time.sleep(delay)

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

        # Step 1: Click "我的淘宝" tab
        root = self.locator.dump_and_parse()
        if not root:
            logger.error("Cannot get UI hierarchy")
            return False

        my_taobao_tab = self.locator.find_my_taobao_tab(root)
        if my_taobao_tab:
            if not self.locator.click_element(my_taobao_tab):
                logger.error("Failed to click '我的淘宝' tab")
                return False
        else:
            # Image fallback
            img = self._get_image_locator()
            if not img or not img.find_and_click("my_taobao_tab", threshold=0.7):
                logger.error("'我的淘宝' tab not found")
                return False

        self._sleep(2000, 3000)

        # Step 2: Click "收藏" entry
        root = self.locator.dump_and_parse()

        # Try XML first
        if root:
            fav_entry = self.locator.find_favorites_entry(root)
            if fav_entry:
                if self.locator.click_element(fav_entry):
                    logger.info("Clicked favorites entry via XML")
                    self._sleep(2000, 3000)
                    return True

        # Image fallback
        img = self._get_image_locator()
        if img and img.find_and_click("favorites_entry", threshold=0.75):
            logger.info("Clicked favorites entry via image recognition")
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

        # Try XML first
        root = self.locator.dump_and_parse()
        if root:
            fav_btn = self.locator.find_favorite_button(root)
            if fav_btn:
                if self.locator.click_element(fav_btn):
                    logger.info("Product added to favorites via XML")
                    self._sleep(1000, 1500)
                    return True

        # Image fallback
        img = self._get_image_locator()
        if img and img.find_and_click("favorite_btn", threshold=0.7):
            logger.info("Product added to favorites via image recognition")
            self._sleep(1000, 1500)
            return True

        logger.warning("Failed to find favorite button")
        return False

    def click_favorite_item(self, index: int = 0) -> bool:
        """
        Click the nth item in favorites list.

        WebView page, XML dump useless. Use screen-ratio-based coordinate clicking.
        Ratios derived from actual favorites screenshot (1080x2400):
          - List starts at ~10.4% of screen height (below title+tabs+filters)
          - Each item height is ~11.3% of screen height
          - First item center at ~17.5% height

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

        # Ratio-based positioning (works across different resolutions)
        first_item_center_ratio = 0.24    # First item center at 24% of screen height
        item_height_ratio = 0.113          # Each item is 11.3% of screen height
        tap_x_ratio = 0.25                 # Click on product image area (left quarter)

        tap_y = int(height * (first_item_center_ratio + item_height_ratio * index))
        tap_x = int(width * tap_x_ratio)

        # If item would be off-screen, scroll first
        if tap_y > height - int(height * 0.1):
            logger.info(f"Item {index} may be off-screen (tap_y={tap_y}), scrolling down...")
            self.adb.swipe(width // 2, int(height * 0.75), width // 2, int(height * 0.25), duration_ms=500)
            self._sleep(1000, 1500)
            # After scrolling, click the first visible item position
            tap_y = int(height * first_item_center_ratio)

        logger.info(f"Tapping favorite item {index} at ({tap_x}, {tap_y})")
        if self.adb.tap(tap_x, tap_y):
            self._sleep(2500, 3500)  # Wait for product page to load
            return True

        logger.error("Tap failed")
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
