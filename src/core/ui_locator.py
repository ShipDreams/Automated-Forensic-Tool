#!/usr/bin/env python3
"""
UI element locator module.
Responsible for parsing UI hierarchy and locating target elements.
"""

import xml.etree.ElementTree as ET
import re
import logging
from typing import Optional, List, Tuple, Dict, Callable
from pathlib import Path

from locales import t

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class UIElement:
    """UI element object"""

    def __init__(self, node: ET.Element):
        """
        Initialize UI element.

        Args:
            node: XML node
        """
        self.node = node
        self.attrib = node.attrib

    def get_bounds(self) -> Optional[Tuple[int, int, int, int]]:
        """
        Get element boundary coordinates.

        Returns:
            (x1, y1, x2, y2) or None
        """
        bounds_str = self.attrib.get('bounds', '')
        # Format: [x1,y1][x2,y2]
        match = re.match(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', bounds_str)
        if match:
            return tuple(map(int, match.groups()))
        return None

    def get_center(self) -> Optional[Tuple[int, int]]:
        """Get element center point coordinates"""
        bounds = self.get_bounds()
        if bounds:
            x1, y1, x2, y2 = bounds
            center_x = (x1 + x2) // 2
            center_y = (y1 + y2) // 2
            return (center_x, center_y)
        return None

    @property
    def resource_id(self) -> str:
        """Get resource-id"""
        return self.attrib.get('resource-id', '')

    @property
    def class_name(self) -> str:
        """Get class"""
        return self.attrib.get('class', '')

    @property
    def text(self) -> str:
        """Get text"""
        return self.attrib.get('text', '')

    @property
    def content_desc(self) -> str:
        """Get content-desc"""
        return self.attrib.get('content-desc', '')

    @property
    def clickable(self) -> bool:
        """Whether clickable"""
        return self.attrib.get('clickable', 'false').lower() == 'true'

    def __repr__(self):
        bounds = self.get_bounds()
        return f"UIElement(id={self.resource_id}, class={self.class_name}, text={self.text}, bounds={bounds})"


class UILocator:
    """UI element locator"""

    def __init__(self, adb_controller):
        """
        Initialize UI locator.

        Args:
            adb_controller: ADBController instance
        """
        self.adb = adb_controller
        self.temp_dir = Path("./temp")
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.current_xml_path = None

    def dump_and_parse(self) -> Optional[ET.Element]:
        """
        Dump and parse UI hierarchy (enhanced version with file verification).

        Returns:
            XML root node or None
        """
        try:
            # Dump UI hierarchy to device
            device_path = "/sdcard/window_dump.xml"
            if not self.adb.dump_ui_hierarchy(device_path):
                logger.error(t('log.dump_ui_failed'))
                return None

            # Verify file exists
            if not self.adb.file_exists(device_path):
                logger.error(t('log.ui_file_not_exist', path=device_path))
                return None

            # Verify file size
            file_size = self.adb.get_file_size(device_path)
            if file_size is None or file_size == 0:
                logger.error(t('log.ui_file_empty'))
                return None

            logger.info(t('log.ui_file_size', size=file_size))

            # Pull to local
            local_path = self.temp_dir / "window_dump.xml"
            if not self.adb.pull_file(device_path, str(local_path)):
                logger.error(t('log.pull_ui_file_failed'))
                return None

            # Parse XML
            tree = ET.parse(str(local_path))
            self.current_xml_path = str(local_path)
            logger.info(t('log.ui_parse_success', path=local_path))
            return tree.getroot()

        except ET.ParseError as e:
            logger.error(t('log.xml_parse_failed', error=e))
            logger.error(t('log.xml_file_corrupted'))
            return None
        except Exception as e:
            logger.error(t('log.dump_and_parse_failed', error=e))
            return None

    def find_element_by_id(self, root: ET.Element, resource_id: str) -> Optional[UIElement]:
        """Find element by resource-id"""
        for node in root.iter():
            if node.attrib.get('resource-id', '') == resource_id:
                logger.info(t('log.found_by_resource_id', id=resource_id))
                return UIElement(node)
        return None

    def find_element_by_text(self, root: ET.Element, text: str, exact: bool = True) -> Optional[UIElement]:
        """Find element by text"""
        for node in root.iter():
            node_text = node.attrib.get('text', '')
            if exact:
                if node_text == text:
                    logger.info(t('log.found_by_text', text=text))
                    return UIElement(node)
            else:
                if text in node_text:
                    logger.info(t('log.found_by_text_contains', text=text))
                    return UIElement(node)
        return None

    def find_element_by_desc(self, root: ET.Element, desc: str, exact: bool = False) -> Optional[UIElement]:
        """Find element by content-desc"""
        for node in root.iter():
            node_desc = node.attrib.get('content-desc', '')
            if exact:
                if node_desc == desc:
                    logger.info(t('log.found_by_desc', desc=desc))
                    return UIElement(node)
            else:
                if desc in node_desc:
                    logger.info(t('log.found_by_desc_contains', desc=desc))
                    return UIElement(node)
        return None

    def find_elements_by_class(self, root: ET.Element, class_name: str) -> List[UIElement]:
        """Find all matching elements by class"""
        elements = []
        for node in root.iter():
            if node.attrib.get('class', '') == class_name:
                elements.append(UIElement(node))
        logger.info(t('log.found_by_class', count=len(elements), class_name=class_name))
        return elements

    def find_clickable_in_region(
        self,
        root: ET.Element,
        x1: int, y1: int, x2: int, y2: int
    ) -> List[UIElement]:
        """Find clickable elements in specified region"""
        elements = []
        for node in root.iter():
            if node.attrib.get('clickable', 'false').lower() == 'true':
                element = UIElement(node)
                bounds = element.get_bounds()
                if bounds:
                    ex1, ey1, ex2, ey2 = bounds
                    # Check if element is within specified region
                    if ex1 >= x1 and ey1 >= y1 and ex2 <= x2 and ey2 <= y2:
                        elements.append(element)

        logger.info(t('log.found_clickable_in_region', x1=x1, y1=y1, x2=x2, y2=y2, count=len(elements)))
        return elements

    def find_video_element(self, root: ET.Element, strategies: Optional[List[str]] = None) -> Optional[UIElement]:
        """
        Use multi-strategy to find video playback element (exact match version).

        Args:
            root: UI root node
            strategies: Strategy list, uses all strategies by default

        Returns:
            Found element or None
        """
        if strategies is None:
            strategies = ['resource_id', 'content_desc']

        logger.info(t('log.search_video_element'))

        # Strategy 1: Find by resource-id (contains match, as resource-id is usually unique)
        if 'resource_id' in strategies:
            logger.info(t('log.strategy_resource_id'))
            video_keywords = ['video', 'player', 'play', 'media']
            for node in root.iter():
                res_id = node.attrib.get('resource-id', '').lower()
                for keyword in video_keywords:
                    if keyword in res_id:
                        element = UIElement(node)
                        if element.clickable:
                            logger.info(t('log.strategy_success_resource_id', id=res_id))
                            return element

        # Strategy 2: Exact match by content-desc
        if 'content_desc' in strategies:
            logger.info(t('log.strategy_content_desc'))
            # Exact match keyword list
            exact_desc_keywords = ['播放', '视频', 'play', 'video', '主图', '播放视频', '点击播放']
            for node in root.iter():
                desc = node.attrib.get('content-desc', '')
                # Exact match (case insensitive)
                if desc.lower() in [k.lower() for k in exact_desc_keywords]:
                    element = UIElement(node)
                    if element.clickable:
                        logger.info(t('log.strategy_success_content_desc', desc=desc))
                        return element

        logger.warning(t('log.video_element_not_found'))
        return None

    def find_video_progress_bar(self, root: ET.Element) -> Optional[Tuple[int, int, int, int]]:
        """
        Find video progress bar position.

        Args:
            root: UI root node

        Returns:
            Progress bar boundary coordinates (x1, y1, x2, y2) or None
        """
        logger.info(t('log.search_video_progress'))

        # Strategy 0 (priority): Find touch area by exact Taobao resource-id
        # seek_touch_container is the touch area for progress bar (larger than progress bar itself)
        taobao_progress_ids = [
            "com.taobao.taobao:id/seek_touch_container",
            "com.taobao.taobao:id/pb_mini_progress",
        ]
        for res_id in taobao_progress_ids:
            element = self.find_element_by_id(root, res_id)
            if element:
                bounds = element.get_bounds()
                if bounds and bounds != (0, 0, 0, 0):
                    logger.info(t('log.strategy_0_success', id=res_id, bounds=bounds))
                    return bounds

        # Strategy 1: Find progress bar by fuzzy resource-id
        progress_ids = ['progress', 'seekbar', 'seek_bar', 'seek_touch', 'video_progress', 'player_progress']
        for node in root.iter():
            res_id = node.attrib.get('resource-id', '').lower()
            for keyword in progress_ids:
                if keyword in res_id:
                    element = UIElement(node)
                    bounds = element.get_bounds()
                    if bounds and bounds != (0, 0, 0, 0):
                        logger.info(t('log.strategy_1_success', id=res_id))
                        return bounds

        # Strategy 2: Find SeekBar or ProgressBar by class
        logger.info(t('log.strategy_2_seekbar'))
        for node in root.iter():
            class_name = node.attrib.get('class', '').lower()
            if 'seekbar' in class_name or 'progressbar' in class_name:
                element = UIElement(node)
                bounds = element.get_bounds()
                if bounds and bounds != (0, 0, 0, 0):
                    x1, y1, x2, y2 = bounds
                    # Progress bar is usually horizontal (width > 3x height)
                    width = x2 - x1
                    height = y2 - y1
                    if height > 0 and width > height * 3:
                        logger.info(t('log.strategy_2_success', bounds=bounds))
                        return bounds

        # Strategy 3: Find horizontal thin element at video area bottom
        logger.info(t('log.strategy_3_video_area'))
        screen_size = self.adb.get_screen_size()
        if screen_size:
            width, height = screen_size
            # Video area usually in top 2/3 of screen
            video_region_height = height * 2 // 3

            for node in root.iter():
                element = UIElement(node)
                bounds = element.get_bounds()
                if bounds and bounds != (0, 0, 0, 0):
                    x1, y1, x2, y2 = bounds
                    # Within video area
                    if y2 <= video_region_height:
                        elem_width = x2 - x1
                        elem_height = y2 - y1
                        # Progress bar features: width > 50% screen, small height
                        if elem_width > width * 0.5 and elem_height > 0 and elem_height < 120 and elem_width > elem_height * 3:
                            logger.info(t('log.strategy_3_success', bounds=bounds))
                            return bounds

        logger.warning(t('log.progress_bar_not_found'))
        return None

    def drag_video_progress_to_start(self, max_attempts: int = 2) -> bool:
        """
        Drag video progress bar to start position (0 seconds).

        Args:
            max_attempts: Maximum retry attempts

        Returns:
            Whether drag was successful
        """
        logger.info(t('log.drag_progress_to_start'))

        for attempt in range(1, max_attempts + 1):
            logger.info(t('log.attempt_n', attempt=attempt, max_attempts=max_attempts))

            root = self.dump_and_parse()
            if not root:
                logger.warning(t('log.cannot_get_ui_hierarchy'))
                continue

            progress_bounds = self.find_video_progress_bar(root)
            if progress_bounds:
                x1, y1, x2, y2 = progress_bounds
                # Drag from middle of progress bar to leftmost
                start_x = (x1 + x2) // 2
                start_y = (y1 + y2) // 2
                end_x = x1 + 10  # Leave small margin
                end_y = start_y

                logger.info(t('log.drag_progress_bar', x1=start_x, y1=start_y, x2=end_x, y2=end_y))
                if self.adb.swipe(start_x, start_y, end_x, end_y, duration_ms=300):
                    logger.info(t('log.progress_dragged_to_start'))
                    return True
                else:
                    logger.warning(t('log.drag_operation_failed'))
            else:
                # If progress bar not found, try dragging at video area bottom
                logger.info(t('log.progress_not_found_try_blind'))
                screen_size = self.adb.get_screen_size()
                if screen_size:
                    width, height = screen_size
                    # Video area usually in top 1/3, progress bar at video bottom
                    video_bottom_y = height // 3
                    start_x = width // 2
                    end_x = width // 10

                    logger.info(t('log.blind_drag_progress', x1=start_x, y1=video_bottom_y, x2=end_x, y2=video_bottom_y))
                    if self.adb.swipe(start_x, video_bottom_y, end_x, video_bottom_y, duration_ms=300):
                        logger.info(t('log.blind_drag_complete'))
                        return True

            if attempt < max_attempts:
                import time
                time.sleep(1)

        logger.warning(t('log.drag_progress_warning'))
        return False

    def find_app_store_open_button(self, root: ET.Element, prefer_first: bool = True) -> Optional[UIElement]:
        """
        Find app store "Open" button (cross-brand universal).
        Supports search results page (may have multiple "Open" buttons).

        Args:
            root: UI root node
            prefer_first: Whether to prefer first found (first one on search results is usually official Taobao)

        Returns:
            Found button element or None
        """
        logger.info(t('log.search_open_button'))

        # Strategy 1: Find by text (Chinese and English)
        open_keywords = ['打开', 'Open', 'OPEN', '启动', 'Launch', 'LAUNCH']

        # Collect all matching "Open" buttons
        all_open_buttons = []

        for keyword in open_keywords:
            # Find all elements containing this keyword
            for node in root.iter():
                text = node.attrib.get('text', '')
                if text == keyword:
                    element = UIElement(node)
                    # Don't check clickable, Xiaomi app store buttons may have clickable=false
                    all_open_buttons.append(element)
                    logger.info(t('log.found_open_button', text=keyword, clickable=element.clickable, bounds=element.get_bounds()))

        # If multiple found, prefer first one (usually official Taobao App)
        if all_open_buttons:
            if prefer_first:
                logger.info(t('log.found_n_open_buttons', count=len(all_open_buttons)))
                return all_open_buttons[0]
            else:
                logger.info(t('log.found_open_by_text'))
                return all_open_buttons[0]

        # Strategy 2: Find by content-desc (don't check clickable)
        for keyword in open_keywords:
            for node in root.iter():
                desc = node.attrib.get('content-desc', '')
                if keyword in desc:
                    element = UIElement(node)
                    logger.info(t('log.found_open_by_desc', desc=desc, clickable=element.clickable, bounds=element.get_bounds()))
                    return element

        # Strategy 3: Find by resource-id (some app stores have fixed ID)
        open_button_ids = [
            'btn_open',
            'button_open',
            'open_button',
            'app_open',
            'action_button',
            'open',  # Xiaomi app store
            'btn_action'  # Some brands
        ]
        for res_id in open_button_ids:
            # Try exact match
            element = self.find_element_by_id(root, res_id)
            if element:
                logger.info(t('log.found_open_by_id', id=res_id, clickable=element.clickable))
                return element

            # Try contains match
            for node in root.iter():
                rid = node.attrib.get('resource-id', '')
                if res_id in rid.lower():
                    element = UIElement(node)
                    if element.text in open_keywords:
                        logger.info(t('log.found_open_by_id_contains', id=rid, clickable=element.clickable))
                        return element

        logger.warning(t('log.open_button_not_found'))
        return None

    def find_and_click_app_store_open_button(self, max_attempts: int = 3) -> bool:
        """
        Find and click app store "Open" button.

        Args:
            max_attempts: Maximum retry attempts

        Returns:
            Whether click was successful
        """
        for attempt in range(1, max_attempts + 1):
            logger.info(t('log.attempt_find_open_button', attempt=attempt, max_attempts=max_attempts))

            root = self.dump_and_parse()
            if not root:
                logger.error(t('log.cannot_get_ui_hierarchy'))
                continue

            element = self.find_app_store_open_button(root)
            if element:
                if self.click_element(element):
                    logger.info(t('log.click_open_success'))
                    return True
                else:
                    logger.error(t('log.click_failed'))
            else:
                logger.warning(t('log.open_button_not_found'))

            if attempt < max_attempts:
                logger.info(t('log.wait_2s_retry'))
                import time
                time.sleep(2)

        logger.error(t('log.open_button_click_failed', max_attempts=max_attempts))
        return False

    def _get_element_area(self, element: UIElement) -> int:
        """Calculate element area"""
        bounds = element.get_bounds()
        if bounds:
            x1, y1, x2, y2 = bounds
            return (x2 - x1) * (y2 - y1)
        return 0

    def click_element(self, element: UIElement, apply_offset: bool = True, max_offset_px: int = 5) -> bool:
        """
        Click element (enhanced version with detailed logging, random offset and visualization).

        Args:
            element: UI element to click
            apply_offset: Whether to apply random offset (anti-detection)
            max_offset_px: Maximum offset pixels

        Returns:
            Whether click was successful
        """
        import random

        center = element.get_center()
        if not center:
            logger.error(t('log.cannot_get_element_center'))
            return False

        x, y = center
        bounds = element.get_bounds()

        # Apply random offset (anti-detection)
        original_x, original_y = x, y
        if apply_offset and bounds:
            x1, y1, x2, y2 = bounds
            # Calculate allowed offset range (don't exceed element boundary)
            max_offset_x = min(max_offset_px, (x2 - x1) // 4)
            max_offset_y = min(max_offset_px, (y2 - y1) // 4)

            if max_offset_x > 0:
                x += random.randint(-max_offset_x, max_offset_x)
            if max_offset_y > 0:
                y += random.randint(-max_offset_y, max_offset_y)

            # Ensure coordinates still within element boundary
            x = max(x1 + 1, min(x, x2 - 1))
            y = max(y1 + 1, min(y, y2 - 1))

        # Log detailed click info
        logger.info("=" * 50)
        logger.info(t('log.prepare_click_element'))
        if apply_offset and (x != original_x or y != original_y):
            logger.info(t('log.original_coordinate', x=original_x, y=original_y))
            logger.info(t('log.offset_coordinate', x=x, y=y))
        else:
            logger.info(t('log.coordinate', x=x, y=y))
        logger.info(t('log.bounds', bounds=bounds))
        logger.info(t('log.text', text=element.text))
        logger.info(t('log.desc', desc=element.content_desc))
        logger.info(t('log.class_name', class_name=element.class_name))
        logger.info(t('log.resource_id', id=element.resource_id))
        logger.info(t('log.clickable', clickable=element.clickable))
        logger.info("=" * 50)

        # Execute click
        success = self.adb.tap(x, y)

        if success:
            logger.info(t('log.click_success'))
            # Wait for touch animation to fully display
            import time
            time.sleep(1.5)

            # Log current focus after click
            current_focus = self.adb.get_current_focus()
            if current_focus:
                logger.info(t('log.focus_after_click', focus=current_focus))
        else:
            logger.error(t('log.click_execute_failed'))

        return success

    def find_and_click_video(self, max_attempts: int = 3) -> bool:
        """
        Find and click video element.

        Args:
            max_attempts: Maximum retry attempts

        Returns:
            Whether click was successful
        """
        for attempt in range(1, max_attempts + 1):
            logger.info(t('log.attempt_find_video', attempt=attempt, max_attempts=max_attempts))

            root = self.dump_and_parse()
            if not root:
                logger.error(t('log.cannot_get_ui_hierarchy'))
                continue

            element = self.find_video_element(root)
            if element:
                if self.click_element(element):
                    logger.info(t('log.click_video_success'))
                    return True
                else:
                    logger.error(t('log.click_failed'))
            else:
                logger.warning(t('log.video_not_found'))

            if attempt < max_attempts:
                logger.info(t('log.wait_2s_retry'))
                import time
                time.sleep(2)

        logger.error(t('log.video_click_failed', max_attempts=max_attempts))
        return False

    def find_browser_search_box(self, root: ET.Element) -> Optional[UIElement]:
        """
        Find browser search box (generic method, works with Baidu etc.).

        Args:
            root: UI root node

        Returns:
            Found search box element or None
        """
        logger.info(t('log.search_browser_searchbox'))

        # Strategy 1: Find by resource-id (common search box IDs)
        search_box_ids = [
            "kw",  # Baidu search box
            "index-kw",  # Baidu homepage search box
            "search_input",
            "searchInput",
            "query"
        ]

        for res_id in search_box_ids:
            for node in root.iter():
                rid = node.attrib.get('resource-id', '')
                if res_id in rid:
                    element = UIElement(node)
                    logger.info(t('log.strategy_1_searchbox_id', id=rid))
                    return element

        # Strategy 2: Find EditText (input box) by class
        logger.info(t('log.strategy_2_edittext'))
        edit_texts = self.find_elements_by_class(root, "android.widget.EditText")
        if edit_texts:
            # Prefer first one (usually main search box)
            logger.info(t('log.strategy_2_success_edittext'))
            return edit_texts[0]

        # Strategy 3: Find EditText in WebView
        logger.info(t('log.strategy_3_webview'))
        for node in root.iter():
            if 'webview' in node.attrib.get('class', '').lower():
                # Find EditText in WebView children
                for child in node.iter():
                    if 'edittext' in child.attrib.get('class', '').lower():
                        element = UIElement(child)
                        logger.info(t('log.strategy_3_success_webview'))
                        return element

        logger.warning(t('log.browser_searchbox_not_found'))
        return None

    def find_taobao_search_box(self, root: ET.Element) -> Optional[UIElement]:
        """
        Find Taobao homepage top search box.

        Args:
            root: UI root node

        Returns:
            Found search box element or None
        """
        logger.info(t('log.search_taobao_searchbox'))

        # Strategy 1: Find by resource-id (common Taobao search box IDs)
        search_box_ids = [
            "com.taobao.taobao:id/searchEdit",
            "com.taobao.taobao:id/search_edit",
            "com.taobao.taobao:id/home_searchbar",
            "com.taobao.taobao:id/searchbar",
            "com.taobao.taobao:id/search_input"
        ]

        for res_id in search_box_ids:
            element = self.find_element_by_id(root, res_id)
            if element:
                logger.info(t('log.strategy_1_taobao_id', id=res_id))
                return element

        # Strategy 2: Find by text (search box default hint text)
        search_hints = ['搜索', '搜索淘宝商品', '搜索宝贝', '请输入关键词', 'Search']
        for hint in search_hints:
            element = self.find_element_by_text(root, hint, exact=False)
            if element:
                logger.info(t('log.strategy_2_taobao_text', text=hint))
                return element

        # Strategy 3: Find by content-desc
        for hint in search_hints:
            element = self.find_element_by_desc(root, hint, exact=False)
            if element:
                logger.info(t('log.strategy_3_taobao_desc', desc=hint))
                return element

        # Strategy 4: Find by class and position (EditText in top area)
        logger.info(t('log.strategy_4_class_position'))
        screen_size = self.adb.get_screen_size()
        if screen_size:
            width, height = screen_size
            # Search box usually in top 1/5 area
            top_region_height = height // 5

            edit_texts = self.find_elements_by_class(root, "android.widget.EditText")
            for element in edit_texts:
                bounds = element.get_bounds()
                if bounds:
                    x1, y1, x2, y2 = bounds
                    # Check if in top area
                    if y1 < top_region_height:
                        logger.info(t('log.strategy_4_success', bounds=bounds))
                        return element

        logger.warning(t('log.taobao_searchbox_not_found'))
        return None

    def find_search_button(self, root: ET.Element) -> Optional[UIElement]:
        """
        Find search button (search icon or button to right of search box).

        Args:
            root: UI root node

        Returns:
            Found search button or None
        """
        logger.info(t('log.search_search_button'))

        # Strategy 1: Find by text
        search_keywords = ['搜索', 'Search', '确定', '确认']
        for keyword in search_keywords:
            element = self.find_element_by_text(root, keyword, exact=True)
            if element:
                logger.info(t('log.found_by_text', text=keyword))
                return element

        # Strategy 2: Find by content-desc
        for keyword in search_keywords:
            element = self.find_element_by_desc(root, keyword, exact=False)
            if element:
                logger.info(t('log.found_by_desc', desc=keyword))
                return element

        # Strategy 3: Find by resource-id
        search_button_ids = [
            "com.taobao.taobao:id/search_button",
            "com.taobao.taobao:id/searchbtn",
            "com.taobao.taobao:id/search_btn"
        ]
        for res_id in search_button_ids:
            element = self.find_element_by_id(root, res_id)
            if element:
                logger.info(t('log.found_by_resource_id', id=res_id))
                return element

        logger.warning(t('log.search_button_not_found'))
        return None

    def find_volume_button(self, root: ET.Element) -> Optional[UIElement]:
        """
        Find video bottom-right volume/mute button.

        Args:
            root: UI root node

        Returns:
            Found volume button or None
        """
        logger.info(t('log.search_volume_button'))

        # Strategy 0 (priority): Find by exact Taobao resource-id
        taobao_mute_ids = [
            "com.taobao.taobao:id/iv_mute_btn",
        ]
        for res_id in taobao_mute_ids:
            element = self.find_element_by_id(root, res_id)
            if element:
                logger.info(t('log.strategy_0_volume_id', id=res_id))
                return element

        # Strategy 1: Find by fuzzy resource-id
        volume_keywords = ['volume', 'mute', 'sound', 'audio', '音量', '静音']
        for node in root.iter():
            res_id = node.attrib.get('resource-id', '').lower()
            for keyword in volume_keywords:
                if keyword in res_id:
                    element = UIElement(node)
                    logger.info(t('log.strategy_1_volume_id', id=res_id))
                    return element

        # Strategy 2: Find by content-desc
        desc_keywords = ['音量', '静音', '声音', '开启声音', '关闭声音', 'volume', 'mute', 'sound']
        for keyword in desc_keywords:
            element = self.find_element_by_desc(root, keyword, exact=False)
            if element:
                logger.info(t('log.strategy_2_volume_desc', keyword=keyword))
                return element

        # Strategy 3: Find in bottom-right area (video controls usually in bottom-right)
        logger.info(t('log.strategy_3_bottom_right'))
        screen_size = self.adb.get_screen_size()
        if screen_size:
            width, height = screen_size
            # Bottom-right 1/4 area
            x1 = width // 2
            y1 = height // 2
            clickable_elements = self.find_clickable_in_region(root, x1, y1, width, height)

            # Filter elements with volume-related description
            for element in clickable_elements:
                desc = element.content_desc.lower()
                text = element.text.lower()
                for keyword in volume_keywords:
                    if keyword in desc or keyword in text:
                        logger.info(t('log.strategy_3_success_volume'))
                        return element

        logger.warning(t('log.volume_button_not_found'))
        return None

    def _find_clickable_parent(self, root: ET.Element, target_node: ET.Element, max_depth: int = 5) -> Optional[UIElement]:
        """
        Find clickable parent element containing target node.

        Args:
            root: UI root node
            target_node: Target child node (usually TextView)
            max_depth: Maximum search depth upward

        Returns:
            Found clickable parent element or None
        """
        # Build parent node map
        parent_map = {c: p for p in root.iter() for c in p}

        current = target_node
        depth = 0

        while depth < max_depth:
            if current not in parent_map:
                break

            parent = parent_map[current]
            parent_element = UIElement(parent)

            # Check if parent element is clickable and has valid bounds
            bounds = parent_element.get_bounds()
            if bounds and bounds != (0, 0, 0, 0):
                if parent_element.clickable:
                    logger.info(t('log.found_clickable_parent', depth=depth + 1, class_name=parent_element.class_name, bounds=bounds))
                    return parent_element
                # Even if clickable=false, may be target if has valid bounds
                elif depth < 3:  # Only accept clickable=false in shallow levels
                    logger.info(t('log.found_valid_bounds_parent', depth=depth + 1, class_name=parent_element.class_name, bounds=bounds))
                    return parent_element

            current = parent
            depth += 1

        return None

    def find_shop_button(self, root: ET.Element) -> Optional[UIElement]:
        """
        Find product page bottom-left "Shop" button (exact match version).

        Args:
            root: UI root node

        Returns:
            Found shop button or None
        """
        logger.info(t('log.search_shop_button'))

        # Strategy 1: Find by resource-id (priority)
        logger.info(t('log.strategy_1_shop_id'))
        shop_id_keywords = ['shop', 'store', 'seller', 'merchant', '店铺', 'goto_shop', 'shop_entrance']
        for node in root.iter():
            res_id = node.attrib.get('resource-id', '').lower()
            for keyword in shop_id_keywords:
                if keyword in res_id:
                    element = UIElement(node)
                    bounds = element.get_bounds()
                    if bounds and bounds != (0, 0, 0, 0):
                        logger.info(t('log.strategy_1_shop_success', id=res_id))
                        return element

        # Strategy 2: Exact match "店铺" by text
        logger.info(t('log.strategy_2_shop_text'))
        for node in root.iter():
            text = node.attrib.get('text', '')
            if text == "店铺":  # Exact match
                element = UIElement(node)
                bounds = element.get_bounds()

                # Check if element itself is valid
                if bounds and bounds != (0, 0, 0, 0):
                    logger.info(t('log.strategy_2_shop_success', bounds=bounds))
                    return element
                else:
                    # Element invalid, try finding clickable parent
                    logger.info(t('log.shop_text_invalid_bounds', bounds=bounds))
                    parent = self._find_clickable_parent(root, node)
                    if parent:
                        logger.info(t('log.strategy_2_shop_parent'))
                        return parent

        # Strategy 3: Exact match "店铺" or "店铺,按钮" by content-desc
        logger.info(t('log.strategy_3_shop_desc'))
        for node in root.iter():
            desc = node.attrib.get('content-desc', '')
            if desc == "店铺" or desc == "店铺,按钮":  # Exact match
                element = UIElement(node)
                bounds = element.get_bounds()

                if bounds and bounds != (0, 0, 0, 0):
                    logger.info(t('log.strategy_3_shop_success'))
                    return element
                else:
                    logger.info(t('log.shop_desc_invalid_bounds'))
                    parent = self._find_clickable_parent(root, node)
                    if parent:
                        logger.info(t('log.strategy_3_shop_parent'))
                        return parent

        logger.warning(t('log.shop_button_not_found'))
        return None

    def find_shop_name_or_avatar(self, root: ET.Element) -> Optional[UIElement]:
        """
        Find shop page shop name or avatar.

        Args:
            root: UI root node

        Returns:
            Found shop name or avatar element
        """
        logger.info(t('log.search_shop_name_avatar'))

        # Video control element keywords to exclude
        exclude_res_id_keywords = ['play', 'mute', 'video', 'sound', 'volume', 'seek', 'progress']
        exclude_desc_keywords = ['播放', 'play', '静音', '音量', '返回', 'back', '按钮']

        def _is_video_control(node) -> bool:
            """Check if node is video control element or navigation button (to exclude)"""
            rid = node.attrib.get('resource-id', '').lower()
            desc = node.attrib.get('content-desc', '').lower()
            for kw in exclude_res_id_keywords:
                if kw in rid:
                    return True
            for kw in exclude_desc_keywords:
                if kw in desc:
                    return True
            return False

        # Strategy 0 (priority): Find shop avatar by content-desc="logoCover"
        logger.info(t('log.strategy_0_logo_cover'))
        for node in root.iter():
            desc = node.attrib.get('content-desc', '')
            if desc == 'logoCover':
                element = UIElement(node)
                bounds = element.get_bounds()
                if bounds and bounds != (0, 0, 0, 0):
                    # Prefer finding clickable parent element
                    parent = self._find_clickable_parent(root, node)
                    if parent:
                        logger.info(t('log.strategy_0_logo_parent', bounds=parent.get_bounds()))
                        return parent
                    logger.info(t('log.strategy_0_logo_success', bounds=bounds))
                    return element

        # Strategy 1: Find by resource-id
        logger.info(t('log.strategy_1_shop_name'))
        shop_ids = ['shop_name', 'store_name', 'shop_title', 'seller_name', 'avatar', 'shop_avatar']
        for res_id in shop_ids:
            for node in root.iter():
                rid = node.attrib.get('resource-id', '').lower()
                if res_id in rid and not _is_video_control(node):
                    element = UIElement(node)
                    logger.info(t('log.strategy_1_shop_name_success', id=rid))
                    return element

        # Strategy 2: ImageView in top area (avatar usually at top)
        logger.info(t('log.strategy_2_avatar'))
        screen_size = self.adb.get_screen_size()
        if screen_size:
            width, height = screen_size
            top_region_height = height // 4

            # Find ImageView
            for node in root.iter():
                if 'imageview' in node.attrib.get('class', '').lower():
                    # Exclude video control elements
                    if _is_video_control(node):
                        continue

                    element = UIElement(node)
                    bounds = element.get_bounds()
                    if bounds:
                        x1, y1, x2, y2 = bounds
                        # In top area and square (avatar usually square)
                        if y1 < top_region_height:
                            width_e = x2 - x1
                            height_e = y2 - y1
                            if abs(width_e - height_e) < width_e * 0.2:  # Width-height ratio close to 1:1
                                logger.info(t('log.strategy_2_avatar_success', bounds=bounds))
                                return element

        logger.warning(t('log.shop_name_avatar_not_found'))
        return None

    def find_qualification_button(self, root: ET.Element) -> Optional[UIElement]:
        """
        Find shop homepage "Qualification" button (exact match version).

        Args:
            root: UI root node

        Returns:
            Found qualification button or None
        """
        logger.info(t('log.search_qualification_button'))

        # Strategy 1: Exact match "资质证照" by text
        logger.info(t('log.strategy_1_qualification_text'))
        element = self.find_element_by_text(root, "资质证照", exact=True)
        if element:
            logger.info(t('log.strategy_1_qualification_success'))
            return element

        # Strategy 2: Exact match "资质证照" by content-desc
        logger.info(t('log.strategy_2_qualification_desc'))
        element = self.find_element_by_desc(root, "资质证照", exact=True)
        if element:
            logger.info(t('log.strategy_2_qualification_success'))
            return element

        logger.warning(t('log.qualification_button_not_found'))
        return None

    def detect_captcha(self, root: ET.Element) -> bool:
        """
        Detect if captcha page appears.

        Args:
            root: UI root node

        Returns:
            True means captcha detected, needs manual intervention
        """
        logger.info(t('log.detect_captcha'))

        captcha_keywords = ['验证码', '滑动验证', '拼图', '点击验证', '安全验证', 'captcha', 'verify']

        # Iterate all nodes, check for captcha-related text
        for node in root.iter():
            text = node.attrib.get('text', '').lower()
            desc = node.attrib.get('content-desc', '').lower()

            for keyword in captcha_keywords:
                if keyword in text or keyword in desc:
                    logger.warning(t('log.captcha_detected', keyword=keyword))
                    return True

        logger.info(t('log.no_captcha'))
        return False


    # ========== Shishibao App UI locator methods ==========

    def find_shishibao_screen_record_button(self, root: ET.Element) -> Optional[UIElement]:
        """
        Find Shishibao App homepage "Screen Record" button.

        Args:
            root: UI root node

        Returns:
            Found button element or None
        """
        logger.info(t('log.search_screen_record_button'))

        # Strategy 1: Find by text
        keywords = ['屏幕录像', '录屏', '屏幕录制']
        for keyword in keywords:
            element = self.find_element_by_text(root, keyword, exact=False)
            if element:
                bounds = element.get_bounds()
                if bounds and bounds != (0, 0, 0, 0):
                    logger.info(t('log.found_by_text_keyword', keyword=keyword))
                    return element
                else:
                    # Find parent element
                    parent = self._find_clickable_parent(root, element.node)
                    if parent:
                        logger.info(t('log.found_parent_by_text'))
                        return parent

        # Strategy 2: Find by content-desc
        for keyword in keywords:
            element = self.find_element_by_desc(root, keyword, exact=False)
            if element:
                bounds = element.get_bounds()
                if bounds and bounds != (0, 0, 0, 0):
                    logger.info(t('log.found_by_desc_keyword', keyword=keyword))
                    return element

        logger.warning(t('log.screen_record_button_not_found'))
        return None

    def find_shishibao_start_now_button(self, root: ET.Element) -> Optional[UIElement]:
        """
        Find Shishibao popup "Start Now" button.

        Args:
            root: UI root node

        Returns:
            Found button element or None
        """
        logger.info(t('log.search_start_now_button'))

        # Strategy 1: Find by text
        keywords = ['立即开始', '开始', '确定', '允许']
        for keyword in keywords:
            element = self.find_element_by_text(root, keyword, exact=False)
            if element:
                bounds = element.get_bounds()
                if bounds and bounds != (0, 0, 0, 0):
                    logger.info(t('log.found_text_keyword', keyword=keyword))
                    return element
                else:
                    parent = self._find_clickable_parent(root, element.node)
                    if parent:
                        logger.info(t('log.found_text_parent'))
                        return parent

        # Strategy 2: Find button in popup bottom area
        logger.info(t('log.strategy_2_bottom_area'))
        screen_size = self.adb.get_screen_size()
        if screen_size:
            width, height = screen_size
            # Bottom 1/3 area
            y1 = height * 2 // 3
            clickable_elements = self.find_clickable_in_region(root, 0, y1, width, height)
            if clickable_elements:
                logger.info(t('log.strategy_2_bottom_success'))
                return clickable_elements[0]

        logger.warning(t('log.start_now_button_not_found'))
        return None

    def find_shishibao_start_record_button(self, root: ET.Element) -> Optional[UIElement]:
        """
        Find Shishibao "Start Recording" button.

        Args:
            root: UI root node

        Returns:
            Found button element or None
        """
        logger.info(t('log.search_start_record_button'))

        # Strategy 1: Find by text
        keywords = ['开始录屏', '开始录制', '开始', '录屏', '录制']
        for keyword in keywords:
            element = self.find_element_by_text(root, keyword, exact=False)
            if element:
                bounds = element.get_bounds()
                if bounds and bounds != (0, 0, 0, 0):
                    logger.info(t('log.found_text_keyword', keyword=keyword))
                    return element
                else:
                    parent = self._find_clickable_parent(root, element.node)
                    if parent:
                        logger.info(t('log.found_text_parent'))
                        return parent

        # Strategy 2: Find by content-desc
        for keyword in keywords:
            element = self.find_element_by_desc(root, keyword, exact=False)
            if element:
                bounds = element.get_bounds()
                if bounds and bounds != (0, 0, 0, 0):
                    logger.info(t('log.found_desc_keyword', keyword=keyword))
                    return element

        logger.warning(t('log.start_record_button_not_found'))
        return None

    def find_shishibao_stop_record_button(self, root: ET.Element) -> Optional[UIElement]:
        """
        Find Shishibao "Stop Recording" button.

        Note: During recording, UI dump may be inaccurate, button shows "Stop Recording"
        but dumped text may be "Start Recording".
        Therefore, prioritize locating by resource-id.

        Args:
            root: UI root node

        Returns:
            Found button element or None
        """
        logger.info(t('log.search_stop_record_button'))

        # Strategy 1 (priority): Find recording button by resource-id
        # During recording, text may be inaccurate, but resource-id is stable
        logger.info(t('log.strategy_1_resource_id'))
        target_id = "com.a1010bao.web.rdbao:id/tv_screen_record"
        element = self.find_element_by_id(root, target_id)
        if element:
            bounds = element.get_bounds()
            if bounds and bounds != (0, 0, 0, 0):
                logger.info(t('log.found_record_button_by_id', id=target_id))
                return element

        # Strategy 2: Find by exact text
        logger.info(t('log.strategy_2_text'))
        keywords = ['结束录屏', '停止录屏', '结束录制', '停止录制', '开始录屏', '开始录制']
        for keyword in keywords:
            element = self.find_element_by_text(root, keyword, exact=True)
            if element:
                bounds = element.get_bounds()
                if bounds and bounds != (0, 0, 0, 0):
                    logger.info(t('log.found_text_keyword', keyword=keyword))
                    return element

        # Strategy 3: Find element containing "录屏" by text
        logger.info(t('log.strategy_3_contains_record'))
        for node in root.iter():
            text = node.attrib.get('text', '')
            if '录屏' in text or '录制' in text:
                element = UIElement(node)
                bounds = element.get_bounds()
                if bounds and bounds != (0, 0, 0, 0):
                    logger.info(t('log.found_record_text', text=text))
                    return element

        logger.warning(t('log.stop_record_button_not_found'))
        return None

    def find_shishibao_save_button(self, root: ET.Element) -> Optional[UIElement]:
        """
        Find Shishibao "Save" button.

        Args:
            root: UI root node

        Returns:
            Found button element or None
        """
        logger.info(t('log.search_save_button'))

        # Strategy 1: Find by text
        keywords = ['保存', '确定', '完成']
        for keyword in keywords:
            element = self.find_element_by_text(root, keyword, exact=False)
            if element:
                bounds = element.get_bounds()
                if bounds and bounds != (0, 0, 0, 0):
                    logger.info(t('log.found_text_keyword', keyword=keyword))
                    return element
                else:
                    parent = self._find_clickable_parent(root, element.node)
                    if parent:
                        logger.info(t('log.found_text_parent'))
                        return parent

        # Strategy 2: Find by content-desc
        for keyword in keywords:
            element = self.find_element_by_desc(root, keyword, exact=False)
            if element:
                bounds = element.get_bounds()
                if bounds and bounds != (0, 0, 0, 0):
                    logger.info(t('log.found_desc_keyword', keyword=keyword))
                    return element

        logger.warning(t('log.save_button_not_found'))
        return None

    def find_shishibao_cancel_button(self, root: ET.Element) -> Optional[UIElement]:
        """
        Find Shishibao "Cancel" button.

        Args:
            root: UI root node

        Returns:
            Found button element or None
        """
        logger.info(t('log.search_cancel_button'))

        # Find "Cancel" by exact text
        element = self.find_element_by_text(root, '取消', exact=True)
        if element:
            bounds = element.get_bounds()
            if bounds and bounds != (0, 0, 0, 0):
                logger.info(t('log.found_cancel_text'))
                return element
            else:
                parent = self._find_clickable_parent(root, element.node)
                if parent:
                    logger.info(t('log.found_cancel_parent'))
                    return parent

        # Find by content-desc
        element = self.find_element_by_desc(root, '取消', exact=True)
        if element:
            bounds = element.get_bounds()
            if bounds and bounds != (0, 0, 0, 0):
                logger.info(t('log.found_cancel_desc'))
                return element

        logger.warning(t('log.cancel_button_not_found'))
        return None


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

    locator = UILocator(controller)

    # Test dump and parse
    root = locator.dump_and_parse()
    if root:
        logger.info(t('log.ui_parse_success', path='test'))

        # Test find clickable elements
        screen_size = controller.get_screen_size()
        if screen_size:
            width, height = screen_size
            clickable = locator.find_clickable_in_region(root, 0, 0, width, height // 3)
            logger.info(f"Found {len(clickable)} clickable elements in top 1/3 area")
