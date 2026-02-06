#!/usr/bin/env python3
"""
UI 元素定位模块
负责解析 UI 层级结构并定位目标元素
"""

import xml.etree.ElementTree as ET
import re
import logging
from typing import Optional, List, Tuple, Dict, Callable
from pathlib import Path

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class UIElement:
    """UI 元素对象"""

    def __init__(self, node: ET.Element):
        """
        初始化 UI 元素

        Args:
            node: XML 节点
        """
        self.node = node
        self.attrib = node.attrib

    def get_bounds(self) -> Optional[Tuple[int, int, int, int]]:
        """
        获取元素边界坐标

        Returns:
            (x1, y1, x2, y2) 或 None
        """
        bounds_str = self.attrib.get('bounds', '')
        # 格式: [x1,y1][x2,y2]
        match = re.match(r'\[(\d+),(\d+)\]\[(\d+),(\d+)\]', bounds_str)
        if match:
            return tuple(map(int, match.groups()))
        return None

    def get_center(self) -> Optional[Tuple[int, int]]:
        """获取元素中心点坐标"""
        bounds = self.get_bounds()
        if bounds:
            x1, y1, x2, y2 = bounds
            center_x = (x1 + x2) // 2
            center_y = (y1 + y2) // 2
            return (center_x, center_y)
        return None

    @property
    def resource_id(self) -> str:
        """获取 resource-id"""
        return self.attrib.get('resource-id', '')

    @property
    def class_name(self) -> str:
        """获取 class"""
        return self.attrib.get('class', '')

    @property
    def text(self) -> str:
        """获取 text"""
        return self.attrib.get('text', '')

    @property
    def content_desc(self) -> str:
        """获取 content-desc"""
        return self.attrib.get('content-desc', '')

    @property
    def clickable(self) -> bool:
        """是否可点击"""
        return self.attrib.get('clickable', 'false').lower() == 'true'

    def __repr__(self):
        bounds = self.get_bounds()
        return f"UIElement(id={self.resource_id}, class={self.class_name}, text={self.text}, bounds={bounds})"


class UILocator:
    """UI 元素定位器"""

    def __init__(self, adb_controller):
        """
        初始化 UI 定位器

        Args:
            adb_controller: ADBController 实例
        """
        self.adb = adb_controller
        self.temp_dir = Path("./temp")
        self.temp_dir.mkdir(parents=True, exist_ok=True)
        self.current_xml_path = None

    def dump_and_parse(self) -> Optional[ET.Element]:
        """
        导出并解析 UI 层级结构（增强版，带文件验证）

        Returns:
            XML 根节点或 None
        """
        try:
            # 导出 UI 层级到设备
            device_path = "/sdcard/window_dump.xml"
            if not self.adb.dump_ui_hierarchy(device_path):
                logger.error("导出 UI 层级失败")
                return None

            # 验证文件是否存在
            if not self.adb.file_exists(device_path):
                logger.error(f"UI 文件不存在: {device_path}")
                return None

            # 验证文件大小
            file_size = self.adb.get_file_size(device_path)
            if file_size is None or file_size == 0:
                logger.error(f"UI 文件大小为 0 或无法获取，可能导出失败")
                return None

            logger.info(f"UI 文件大小: {file_size} bytes")

            # 拉取到本地
            local_path = self.temp_dir / "window_dump.xml"
            if not self.adb.pull_file(device_path, str(local_path)):
                logger.error("拉取 UI 文件失败")
                return None

            # 解析 XML
            tree = ET.parse(str(local_path))
            self.current_xml_path = str(local_path)
            logger.info(f"✓ UI 层级解析成功: {local_path}")
            return tree.getroot()

        except ET.ParseError as e:
            logger.error(f"XML 解析失败: {e}")
            logger.error("XML 文件可能损坏，请检查设备上的 UI dump 功能")
            return None
        except Exception as e:
            logger.error(f"导出并解析 UI 失败: {e}")
            return None

    def find_element_by_id(self, root: ET.Element, resource_id: str) -> Optional[UIElement]:
        """通过 resource-id 查找元素"""
        for node in root.iter():
            if node.attrib.get('resource-id', '') == resource_id:
                logger.info(f"✓ 通过 resource-id 找到元素: {resource_id}")
                return UIElement(node)
        return None

    def find_element_by_text(self, root: ET.Element, text: str, exact: bool = True) -> Optional[UIElement]:
        """通过 text 查找元素"""
        for node in root.iter():
            node_text = node.attrib.get('text', '')
            if exact:
                if node_text == text:
                    logger.info(f"✓ 通过 text 找到元素: {text}")
                    return UIElement(node)
            else:
                if text in node_text:
                    logger.info(f"✓ 通过 text 包含找到元素: {text}")
                    return UIElement(node)
        return None

    def find_element_by_desc(self, root: ET.Element, desc: str, exact: bool = False) -> Optional[UIElement]:
        """通过 content-desc 查找元素"""
        for node in root.iter():
            node_desc = node.attrib.get('content-desc', '')
            if exact:
                if node_desc == desc:
                    logger.info(f"✓ 通过 content-desc 找到元素: {desc}")
                    return UIElement(node)
            else:
                if desc in node_desc:
                    logger.info(f"✓ 通过 content-desc 包含找到元素: {desc}")
                    return UIElement(node)
        return None

    def find_elements_by_class(self, root: ET.Element, class_name: str) -> List[UIElement]:
        """通过 class 查找所有匹配的元素"""
        elements = []
        for node in root.iter():
            if node.attrib.get('class', '') == class_name:
                elements.append(UIElement(node))
        logger.info(f"✓ 通过 class 找到 {len(elements)} 个元素: {class_name}")
        return elements

    def find_clickable_in_region(
        self,
        root: ET.Element,
        x1: int, y1: int, x2: int, y2: int
    ) -> List[UIElement]:
        """查找指定区域内的可点击元素"""
        elements = []
        for node in root.iter():
            if node.attrib.get('clickable', 'false').lower() == 'true':
                element = UIElement(node)
                bounds = element.get_bounds()
                if bounds:
                    ex1, ey1, ex2, ey2 = bounds
                    # 检查元素是否在指定区域内
                    if ex1 >= x1 and ey1 >= y1 and ex2 <= x2 and ey2 <= y2:
                        elements.append(element)

        logger.info(f"✓ 在区域 ({x1},{y1})-({x2},{y2}) 找到 {len(elements)} 个可点击元素")
        return elements

    def find_video_element(self, root: ET.Element, strategies: Optional[List[str]] = None) -> Optional[UIElement]:
        """
        使用多策略查找视频播放元素（精确匹配版）

        Args:
            root: UI 根节点
            strategies: 策略列表，默认使用全部策略

        Returns:
            找到的元素或 None
        """
        if strategies is None:
            strategies = ['resource_id', 'content_desc']

        logger.info("开始查找视频播放元素...")

        # 策略 1: 通过 resource-id 查找（包含匹配，因为 resource-id 通常是唯一标识）
        if 'resource_id' in strategies:
            logger.info("策略 1: 通过 resource-id 查找...")
            video_keywords = ['video', 'player', 'play', 'media']
            for node in root.iter():
                res_id = node.attrib.get('resource-id', '').lower()
                for keyword in video_keywords:
                    if keyword in res_id:
                        element = UIElement(node)
                        if element.clickable:
                            logger.info(f"✓ 策略 1 成功: resource-id={res_id}")
                            return element

        # 策略 2: 通过 content-desc 精确匹配
        if 'content_desc' in strategies:
            logger.info("策略 2: 通过 content-desc 精确匹配...")
            # 精确匹配的关键词列表
            exact_desc_keywords = ['播放', '视频', 'play', 'video', '主图', '播放视频', '点击播放']
            for node in root.iter():
                desc = node.attrib.get('content-desc', '')
                # 精确匹配（忽略大小写）
                if desc.lower() in [k.lower() for k in exact_desc_keywords]:
                    element = UIElement(node)
                    if element.clickable:
                        logger.info(f"✓ 策略 2 成功: content-desc={desc}")
                        return element

        logger.warning("未找到视频元素（商品可能无视频）")
        return None

    def find_video_progress_bar(self, root: ET.Element) -> Optional[Tuple[int, int, int, int]]:
        """
        查找视频进度条的位置

        Args:
            root: UI 根节点

        Returns:
            进度条的边界坐标 (x1, y1, x2, y2) 或 None
        """
        logger.info("开始查找视频进度条...")

        # 策略 0（优先）: 通过淘宝精确 resource-id 查找触控区域
        # seek_touch_container 是进度条的触控区域（比进度条本身更大更容易拖动）
        taobao_progress_ids = [
            "com.taobao.taobao:id/seek_touch_container",
            "com.taobao.taobao:id/pb_mini_progress",
        ]
        for res_id in taobao_progress_ids:
            element = self.find_element_by_id(root, res_id)
            if element:
                bounds = element.get_bounds()
                if bounds and bounds != (0, 0, 0, 0):
                    logger.info(f"✓ 策略 0 成功: 通过精确 resource-id 找到进度条: {res_id}, bounds={bounds}")
                    return bounds

        # 策略 1: 通过 resource-id 模糊查找进度条
        progress_ids = ['progress', 'seekbar', 'seek_bar', 'seek_touch', 'video_progress', 'player_progress']
        for node in root.iter():
            res_id = node.attrib.get('resource-id', '').lower()
            for keyword in progress_ids:
                if keyword in res_id:
                    element = UIElement(node)
                    bounds = element.get_bounds()
                    if bounds and bounds != (0, 0, 0, 0):
                        logger.info(f"✓ 策略 1 成功: 通过 resource-id 找到进度条: {res_id}")
                        return bounds

        # 策略 2: 通过 class 查找 SeekBar 或 ProgressBar
        logger.info("策略 2: 查找 SeekBar/ProgressBar...")
        for node in root.iter():
            class_name = node.attrib.get('class', '').lower()
            if 'seekbar' in class_name or 'progressbar' in class_name:
                element = UIElement(node)
                bounds = element.get_bounds()
                if bounds and bounds != (0, 0, 0, 0):
                    x1, y1, x2, y2 = bounds
                    # 进度条通常是横向的（宽度 > 高度的3倍）
                    width = x2 - x1
                    height = y2 - y1
                    if height > 0 and width > height * 3:
                        logger.info(f"✓ 策略 2 成功: 找到 SeekBar, bounds={bounds}")
                        return bounds

        # 策略 3: 在视频区域底部查找横向细长元素
        logger.info("策略 3: 在视频区域查找进度条形状的元素...")
        screen_size = self.adb.get_screen_size()
        if screen_size:
            width, height = screen_size
            # 视频区域通常在屏幕上半部分
            video_region_height = height * 2 // 3

            for node in root.iter():
                element = UIElement(node)
                bounds = element.get_bounds()
                if bounds and bounds != (0, 0, 0, 0):
                    x1, y1, x2, y2 = bounds
                    # 在视频区域内
                    if y2 <= video_region_height:
                        elem_width = x2 - x1
                        elem_height = y2 - y1
                        # 进度条特征：宽度占屏幕50%以上、高度小
                        if elem_width > width * 0.5 and elem_height > 0 and elem_height < 120 and elem_width > elem_height * 3:
                            logger.info(f"✓ 策略 3 成功: 找到可能的进度条, bounds={bounds}")
                            return bounds

        logger.warning("未找到视频进度条")
        return None

    def drag_video_progress_to_start(self, max_attempts: int = 2) -> bool:
        """
        将视频进度条拖动到开始位置（0秒）

        Args:
            max_attempts: 最大尝试次数

        Returns:
            是否成功拖动
        """
        logger.info("尝试将视频进度条拖到开始位置...")

        for attempt in range(1, max_attempts + 1):
            logger.info(f"第 {attempt}/{max_attempts} 次尝试...")

            root = self.dump_and_parse()
            if not root:
                logger.warning("无法获取 UI 层级")
                continue

            progress_bounds = self.find_video_progress_bar(root)
            if progress_bounds:
                x1, y1, x2, y2 = progress_bounds
                # 从进度条中间位置拖到最左边
                start_x = (x1 + x2) // 2
                start_y = (y1 + y2) // 2
                end_x = x1 + 10  # 留一点边距
                end_y = start_y

                logger.info(f"拖动进度条: ({start_x}, {start_y}) -> ({end_x}, {end_y})")
                if self.adb.swipe(start_x, start_y, end_x, end_y, duration_ms=300):
                    logger.info("✓ 视频进度条已拖到开始位置")
                    return True
                else:
                    logger.warning("拖动操作失败")
            else:
                # 如果找不到进度条，尝试在视频区域底部进行拖动
                logger.info("未找到进度条元素，尝试在视频区域底部拖动...")
                screen_size = self.adb.get_screen_size()
                if screen_size:
                    width, height = screen_size
                    # 视频区域通常在顶部1/3，进度条在视频底部
                    video_bottom_y = height // 3
                    start_x = width // 2
                    end_x = width // 10

                    logger.info(f"盲拖进度条: ({start_x}, {video_bottom_y}) -> ({end_x}, {video_bottom_y})")
                    if self.adb.swipe(start_x, video_bottom_y, end_x, video_bottom_y, duration_ms=300):
                        logger.info("✓ 盲拖完成")
                        return True

            if attempt < max_attempts:
                import time
                time.sleep(1)

        logger.warning("⚠ 未能拖动视频进度条（继续流程）")
        return False

    def find_app_store_open_button(self, root: ET.Element, prefer_first: bool = True) -> Optional[UIElement]:
        """
        查找应用商店的"打开"按钮（跨品牌通用）
        支持搜索结果页（可能有多个"打开"按钮）

        Args:
            root: UI 根节点
            prefer_first: 是否优先选择第一个找到的（搜索结果页通常第一个是淘宝官方）

        Returns:
            找到的按钮元素或 None
        """
        logger.info("开始查找应用商店'打开'按钮...")

        # 策略 1: 通过 text 查找（中英文）
        open_keywords = ['打开', 'Open', 'OPEN', '启动', 'Launch', 'LAUNCH']

        # 收集所有匹配的"打开"按钮
        all_open_buttons = []

        for keyword in open_keywords:
            # 查找所有包含该关键词的元素
            for node in root.iter():
                text = node.attrib.get('text', '')
                if text == keyword:
                    element = UIElement(node)
                    # 不检查 clickable，小米应用商店的按钮可能 clickable=false
                    all_open_buttons.append(element)
                    logger.info(f"找到'打开'按钮: text={keyword}, clickable={element.clickable}, bounds={element.get_bounds()}")

        # 如果找到多个，优先选择第一个（通常是淘宝官方App）
        if all_open_buttons:
            if prefer_first:
                logger.info(f"✓ 找到 {len(all_open_buttons)} 个'打开'按钮，选择第一个")
                return all_open_buttons[0]
            else:
                logger.info(f"✓ 通过 text 找到'打开'按钮")
                return all_open_buttons[0]

        # 策略 2: 通过 content-desc 查找（不检查 clickable）
        for keyword in open_keywords:
            for node in root.iter():
                desc = node.attrib.get('content-desc', '')
                if keyword in desc:
                    element = UIElement(node)
                    logger.info(f"✓ 通过 content-desc 找到'打开'元素: desc={desc}, clickable={element.clickable}, bounds={element.get_bounds()}")
                    return element

        # 策略 3: 通过 resource-id 查找（部分应用商店有固定ID）
        open_button_ids = [
            'btn_open',
            'button_open',
            'open_button',
            'app_open',
            'action_button',
            'open',  # 小米应用商店
            'btn_action'  # 部分品牌
        ]
        for res_id in open_button_ids:
            # 尝试完整匹配
            element = self.find_element_by_id(root, res_id)
            if element:
                logger.info(f"✓ 通过 resource-id 找到'打开'按钮: {res_id}, clickable={element.clickable}")
                return element

            # 尝试包含匹配
            for node in root.iter():
                rid = node.attrib.get('resource-id', '')
                if res_id in rid.lower():
                    element = UIElement(node)
                    if element.text in open_keywords:
                        logger.info(f"✓ 通过 resource-id 包含匹配找到'打开'按钮: {rid}, clickable={element.clickable}")
                        return element

        logger.warning("未找到应用商店'打开'按钮")
        return None

    def find_and_click_app_store_open_button(self, max_attempts: int = 3) -> bool:
        """
        查找并点击应用商店的"打开"按钮

        Args:
            max_attempts: 最大尝试次数

        Returns:
            是否成功点击
        """
        for attempt in range(1, max_attempts + 1):
            logger.info(f"第 {attempt}/{max_attempts} 次尝试查找'打开'按钮...")

            root = self.dump_and_parse()
            if not root:
                logger.error("无法获取 UI 层级")
                continue

            element = self.find_app_store_open_button(root)
            if element:
                if self.click_element(element):
                    logger.info("✓ 成功点击'打开'按钮")
                    return True
                else:
                    logger.error("点击失败")
            else:
                logger.warning("未找到'打开'按钮")

            if attempt < max_attempts:
                logger.info("等待 2 秒后重试...")
                import time
                time.sleep(2)

        logger.error(f"经过 {max_attempts} 次尝试仍未成功点击'打开'按钮")
        return False

    def _get_element_area(self, element: UIElement) -> int:
        """计算元素面积"""
        bounds = element.get_bounds()
        if bounds:
            x1, y1, x2, y2 = bounds
            return (x2 - x1) * (y2 - y1)
        return 0

    def click_element(self, element: UIElement, apply_offset: bool = True, max_offset_px: int = 5) -> bool:
        """
        点击元素（增强版，包含详细日志、随机偏移和可视化）

        Args:
            element: 要点击的 UI 元素
            apply_offset: 是否应用随机偏移（防封控）
            max_offset_px: 最大偏移像素

        Returns:
            是否成功点击
        """
        import random

        center = element.get_center()
        if not center:
            logger.error("无法获取元素中心点")
            return False

        x, y = center
        bounds = element.get_bounds()

        # 应用随机偏移（防封控）
        original_x, original_y = x, y
        if apply_offset and bounds:
            x1, y1, x2, y2 = bounds
            # 计算允许的偏移范围（不超出元素边界）
            max_offset_x = min(max_offset_px, (x2 - x1) // 4)
            max_offset_y = min(max_offset_px, (y2 - y1) // 4)

            if max_offset_x > 0:
                x += random.randint(-max_offset_x, max_offset_x)
            if max_offset_y > 0:
                y += random.randint(-max_offset_y, max_offset_y)

            # 确保坐标仍在元素边界内
            x = max(x1 + 1, min(x, x2 - 1))
            y = max(y1 + 1, min(y, y2 - 1))

        # 详细记录点击信息
        logger.info("=" * 50)
        logger.info("准备点击元素:")
        if apply_offset and (x != original_x or y != original_y):
            logger.info(f"  - 原始坐标: ({original_x}, {original_y})")
            logger.info(f"  - 偏移后坐标: ({x}, {y})")
        else:
            logger.info(f"  - 坐标: ({x}, {y})")
        logger.info(f"  - 边界: {bounds}")
        logger.info(f"  - 文本: {element.text}")
        logger.info(f"  - 描述: {element.content_desc}")
        logger.info(f"  - 类名: {element.class_name}")
        logger.info(f"  - Resource ID: {element.resource_id}")
        logger.info(f"  - 可点击: {element.clickable}")
        logger.info("=" * 50)

        # 执行点击
        success = self.adb.tap(x, y)

        if success:
            logger.info("✓ 点击执行成功")
            # 增加等待时间让触摸动画完全显示
            import time
            time.sleep(1.5)

            # 记录点击后的当前焦点
            current_focus = self.adb.get_current_focus()
            if current_focus:
                logger.info(f"点击后当前焦点: {current_focus}")
        else:
            logger.error("✗ 点击执行失败")

        return success

    def find_and_click_video(self, max_attempts: int = 3) -> bool:
        """
        查找并点击视频元素

        Args:
            max_attempts: 最大尝试次数

        Returns:
            是否成功点击
        """
        for attempt in range(1, max_attempts + 1):
            logger.info(f"第 {attempt}/{max_attempts} 次尝试查找视频元素...")

            root = self.dump_and_parse()
            if not root:
                logger.error("无法获取 UI 层级")
                continue

            element = self.find_video_element(root)
            if element:
                if self.click_element(element):
                    logger.info("✓ 成功点击视频元素")
                    return True
                else:
                    logger.error("点击失败")
            else:
                logger.warning("未找到视频元素")

            if attempt < max_attempts:
                logger.info("等待 2 秒后重试...")
                import time
                time.sleep(2)

        logger.error(f"经过 {max_attempts} 次尝试仍未成功点击视频")
        return False

    def find_browser_search_box(self, root: ET.Element) -> Optional[UIElement]:
        """
        查找浏览器搜索框（通用方法，适用于百度等网页）

        Args:
            root: UI 根节点

        Returns:
            找到的搜索框元素或 None
        """
        logger.info("开始查找浏览器搜索框...")

        # 策略 1: 通过 resource-id 查找（常见搜索框ID）
        search_box_ids = [
            "kw",  # 百度搜索框
            "index-kw",  # 百度首页搜索框
            "search_input",
            "searchInput",
            "query"
        ]

        for res_id in search_box_ids:
            for node in root.iter():
                rid = node.attrib.get('resource-id', '')
                if res_id in rid:
                    element = UIElement(node)
                    logger.info(f"✓ 策略 1 成功: 通过 resource-id 找到搜索框: {rid}")
                    return element

        # 策略 2: 通过 class 查找 EditText（输入框）
        logger.info("策略 2: 查找网页中的 EditText...")
        edit_texts = self.find_elements_by_class(root, "android.widget.EditText")
        if edit_texts:
            # 优先选择第一个（通常是主搜索框）
            logger.info(f"✓ 策略 2 成功: 找到 EditText 搜索框")
            return edit_texts[0]

        # 策略 3: 在 WebView 中查找 EditText
        logger.info("策略 3: 在 WebView 中查找搜索框...")
        for node in root.iter():
            if 'webview' in node.attrib.get('class', '').lower():
                # 在 WebView 子节点中查找 EditText
                for child in node.iter():
                    if 'edittext' in child.attrib.get('class', '').lower():
                        element = UIElement(child)
                        logger.info(f"✓ 策略 3 成功: 在 WebView 中找到搜索框")
                        return element

        logger.warning("未找到浏览器搜索框")
        return None

    def find_taobao_search_box(self, root: ET.Element) -> Optional[UIElement]:
        """
        查找淘宝首页顶部搜索框

        Args:
            root: UI 根节点

        Returns:
            找到的搜索框元素或 None
        """
        logger.info("开始查找淘宝搜索框...")

        # 策略 1: 通过 resource-id 查找（淘宝搜索框常见 ID）
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
                logger.info(f"✓ 策略 1 成功: 通过 resource-id 找到搜索框: {res_id}")
                return element

        # 策略 2: 通过 text 查找（搜索框默认提示文字）
        search_hints = ['搜索', '搜索淘宝商品', '搜索宝贝', '请输入关键词', 'Search']
        for hint in search_hints:
            element = self.find_element_by_text(root, hint, exact=False)
            if element:
                logger.info(f"✓ 策略 2 成功: 通过 text 找到搜索框: {hint}")
                return element

        # 策略 3: 通过 content-desc 查找
        for hint in search_hints:
            element = self.find_element_by_desc(root, hint, exact=False)
            if element:
                logger.info(f"✓ 策略 3 成功: 通过 content-desc 找到搜索框: {hint}")
                return element

        # 策略 4: 通过 class 和位置查找（EditText 且在顶部区域）
        logger.info("策略 4: 通过 class 和位置查找...")
        screen_size = self.adb.get_screen_size()
        if screen_size:
            width, height = screen_size
            # 搜索框通常在顶部 1/5 区域
            top_region_height = height // 5

            edit_texts = self.find_elements_by_class(root, "android.widget.EditText")
            for element in edit_texts:
                bounds = element.get_bounds()
                if bounds:
                    x1, y1, x2, y2 = bounds
                    # 检查是否在顶部区域
                    if y1 < top_region_height:
                        logger.info(f"✓ 策略 4 成功: 顶部区域 EditText, bounds={bounds}")
                        return element

        logger.warning("未找到淘宝搜索框")
        return None

    def find_search_button(self, root: ET.Element) -> Optional[UIElement]:
        """
        查找搜索按钮（搜索框右侧的搜索图标或按钮）

        Args:
            root: UI 根节点

        Returns:
            找到的搜索按钮或 None
        """
        logger.info("开始查找搜索按钮...")

        # 策略 1: 通过 text 查找
        search_keywords = ['搜索', 'Search', '确定', '确认']
        for keyword in search_keywords:
            element = self.find_element_by_text(root, keyword, exact=True)
            if element:
                logger.info(f"✓ 策略 1 成功: 通过 text 找到搜索按钮: {keyword}")
                return element

        # 策略 2: 通过 content-desc 查找
        for keyword in search_keywords:
            element = self.find_element_by_desc(root, keyword, exact=False)
            if element:
                logger.info(f"✓ 策略 2 成功: 通过 content-desc 找到搜索按钮: {keyword}")
                return element

        # 策略 3: 通过 resource-id 查找
        search_button_ids = [
            "com.taobao.taobao:id/search_button",
            "com.taobao.taobao:id/searchbtn",
            "com.taobao.taobao:id/search_btn"
        ]
        for res_id in search_button_ids:
            element = self.find_element_by_id(root, res_id)
            if element:
                logger.info(f"✓ 策略 3 成功: 通过 resource-id 找到搜索按钮: {res_id}")
                return element

        logger.warning("未找到搜索按钮（可使用回车键代替）")
        return None

    def find_volume_button(self, root: ET.Element) -> Optional[UIElement]:
        """
        查找视频右下角的音量/静音按钮

        Args:
            root: UI 根节点

        Returns:
            找到的音量按钮或 None
        """
        logger.info("开始查找音量/静音按钮...")

        # 策略 0（优先）: 通过淘宝精确 resource-id 查找
        taobao_mute_ids = [
            "com.taobao.taobao:id/iv_mute_btn",
        ]
        for res_id in taobao_mute_ids:
            element = self.find_element_by_id(root, res_id)
            if element:
                logger.info(f"✓ 策略 0 成功: 通过精确 resource-id 找到音量按钮: {res_id}")
                return element

        # 策略 1: 通过 resource-id 模糊查找
        volume_keywords = ['volume', 'mute', 'sound', 'audio', '音量', '静音']
        for node in root.iter():
            res_id = node.attrib.get('resource-id', '').lower()
            for keyword in volume_keywords:
                if keyword in res_id:
                    element = UIElement(node)
                    logger.info(f"✓ 策略 1 成功: 通过 resource-id 找到音量按钮: {res_id}")
                    return element

        # 策略 2: 通过 content-desc 查找
        desc_keywords = ['音量', '静音', '声音', '开启声音', '关闭声音', 'volume', 'mute', 'sound']
        for keyword in desc_keywords:
            element = self.find_element_by_desc(root, keyword, exact=False)
            if element:
                logger.info(f"✓ 策略 2 成功: 通过 content-desc 找到音量按钮: {keyword}")
                return element

        # 策略 3: 右下角区域查找（视频控制按钮通常在右下角）
        logger.info("策略 3: 在右下角区域查找...")
        screen_size = self.adb.get_screen_size()
        if screen_size:
            width, height = screen_size
            # 右下角 1/4 区域
            x1 = width // 2
            y1 = height // 2
            clickable_elements = self.find_clickable_in_region(root, x1, y1, width, height)

            # 过滤包含音量相关描述的元素
            for element in clickable_elements:
                desc = element.content_desc.lower()
                text = element.text.lower()
                for keyword in volume_keywords:
                    if keyword in desc or keyword in text:
                        logger.info(f"✓ 策略 3 成功: 右下角区域找到音量按钮")
                        return element

        logger.warning("未找到音量/静音按钮")
        return None

    def _find_clickable_parent(self, root: ET.Element, target_node: ET.Element, max_depth: int = 5) -> Optional[UIElement]:
        """
        查找包含目标节点的可点击父元素

        Args:
            root: UI 根节点
            target_node: 目标子节点（通常是 TextView）
            max_depth: 最大向上查找深度

        Returns:
            找到的可点击父元素或 None
        """
        # 构建父节点映射
        parent_map = {c: p for p in root.iter() for c in p}

        current = target_node
        depth = 0

        while depth < max_depth:
            if current not in parent_map:
                break

            parent = parent_map[current]
            parent_element = UIElement(parent)

            # 检查父元素是否可点击且有有效边界
            bounds = parent_element.get_bounds()
            if bounds and bounds != (0, 0, 0, 0):
                if parent_element.clickable:
                    logger.info(f"找到可点击父元素（深度 {depth + 1}）: class={parent_element.class_name}, bounds={bounds}")
                    return parent_element
                # 即使 clickable=false，如果有有效边界也可能是目标
                elif depth < 3:  # 只在浅层接受 clickable=false
                    logger.info(f"找到有效边界父元素（深度 {depth + 1}，clickable=false）: class={parent_element.class_name}, bounds={bounds}")
                    return parent_element

            current = parent
            depth += 1

        return None

    def find_shop_button(self, root: ET.Element) -> Optional[UIElement]:
        """
        查找商品页左下角的"店铺"按钮（精确匹配版）

        Args:
            root: UI 根节点

        Returns:
            找到的店铺按钮或 None
        """
        logger.info("开始查找'店铺'按钮...")

        # 策略 1: 通过 resource-id 查找（优先）
        logger.info("策略 1: 通过 resource-id 查找...")
        shop_id_keywords = ['shop', 'store', 'seller', 'merchant', '店铺', 'goto_shop', 'shop_entrance']
        for node in root.iter():
            res_id = node.attrib.get('resource-id', '').lower()
            for keyword in shop_id_keywords:
                if keyword in res_id:
                    element = UIElement(node)
                    bounds = element.get_bounds()
                    if bounds and bounds != (0, 0, 0, 0):
                        logger.info(f"✓ 策略 1 成功: 通过 resource-id 找到店铺按钮: {res_id}")
                        return element

        # 策略 2: 通过 text 精确匹配"店铺"
        logger.info("策略 2: 通过 text 精确匹配'店铺'...")
        for node in root.iter():
            text = node.attrib.get('text', '')
            if text == "店铺":  # 精确匹配
                element = UIElement(node)
                bounds = element.get_bounds()

                # 检查元素本身是否有效
                if bounds and bounds != (0, 0, 0, 0):
                    logger.info(f"✓ 策略 2 成功: 通过 text 精确匹配找到店铺按钮, bounds={bounds}")
                    return element
                else:
                    # 元素无效，尝试查找可点击父元素
                    logger.info(f"text='店铺' 元素边界无效 {bounds}，查找可点击父元素...")
                    parent = self._find_clickable_parent(root, node)
                    if parent:
                        logger.info(f"✓ 策略 2 成功: 通过 text 找到父元素")
                        return parent

        # 策略 3: 通过 content-desc 精确匹配"店铺"或"店铺,按钮"
        logger.info("策略 3: 通过 content-desc 精确匹配'店铺'或'店铺,按钮'...")
        for node in root.iter():
            desc = node.attrib.get('content-desc', '')
            if desc == "店铺" or desc == "店铺,按钮":  # 精确匹配
                element = UIElement(node)
                bounds = element.get_bounds()

                if bounds and bounds != (0, 0, 0, 0):
                    logger.info(f"✓ 策略 3 成功: 通过 content-desc 精确匹配找到店铺按钮")
                    return element
                else:
                    logger.info(f"content-desc='店铺' 元素边界无效，查找可点击父元素...")
                    parent = self._find_clickable_parent(root, node)
                    if parent:
                        logger.info(f"✓ 策略 3 成功: 通过 content-desc 找到父元素")
                        return parent

        logger.warning("未找到'店铺'按钮")
        return None

    def find_shop_name_or_avatar(self, root: ET.Element) -> Optional[UIElement]:
        """
        查找店铺页面的店铺名称或头像

        Args:
            root: UI 根节点

        Returns:
            找到的店铺名称或头像元素
        """
        logger.info("开始查找店铺名称或头像...")

        # 需要排除的视频控制元素关键词
        exclude_res_id_keywords = ['play', 'mute', 'video', 'sound', 'volume', 'seek', 'progress']
        exclude_desc_keywords = ['播放', 'play', '静音', '音量', '返回', 'back', '按钮']

        def _is_video_control(node) -> bool:
            """判断节点是否为视频控制元素或导航按钮（需要排除的元素）"""
            rid = node.attrib.get('resource-id', '').lower()
            desc = node.attrib.get('content-desc', '').lower()
            for kw in exclude_res_id_keywords:
                if kw in rid:
                    return True
            for kw in exclude_desc_keywords:
                if kw in desc:
                    return True
            return False

        # 策略 0（优先）: 通过 content-desc="logoCover" 查找店铺头像
        logger.info("策略 0: 通过 content-desc='logoCover' 查找店铺头像...")
        for node in root.iter():
            desc = node.attrib.get('content-desc', '')
            if desc == 'logoCover':
                element = UIElement(node)
                bounds = element.get_bounds()
                if bounds and bounds != (0, 0, 0, 0):
                    # 优先查找可点击的父元素
                    parent = self._find_clickable_parent(root, node)
                    if parent:
                        logger.info(f"✓ 策略 0 成功: 通过 logoCover 找到店铺头像（可点击父元素）, bounds={parent.get_bounds()}")
                        return parent
                    logger.info(f"✓ 策略 0 成功: 通过 logoCover 找到店铺头像, bounds={bounds}")
                    return element

        # 策略 1: 通过 resource-id 查找
        logger.info("策略 1: 通过 resource-id 查找店铺元素...")
        shop_ids = ['shop_name', 'store_name', 'shop_title', 'seller_name', 'avatar', 'shop_avatar']
        for res_id in shop_ids:
            for node in root.iter():
                rid = node.attrib.get('resource-id', '').lower()
                if res_id in rid and not _is_video_control(node):
                    element = UIElement(node)
                    logger.info(f"✓ 策略 1 成功: 通过 resource-id 找到店铺元素: {rid}")
                    return element

        # 策略 2: 顶部区域的 ImageView（头像通常在顶部）
        logger.info("策略 2: 在顶部区域查找头像...")
        screen_size = self.adb.get_screen_size()
        if screen_size:
            width, height = screen_size
            top_region_height = height // 4

            # 查找 ImageView
            for node in root.iter():
                if 'imageview' in node.attrib.get('class', '').lower():
                    # 排除视频控制元素
                    if _is_video_control(node):
                        continue

                    element = UIElement(node)
                    bounds = element.get_bounds()
                    if bounds:
                        x1, y1, x2, y2 = bounds
                        # 在顶部区域且是正方形（头像通常是正方形）
                        if y1 < top_region_height:
                            width_e = x2 - x1
                            height_e = y2 - y1
                            if abs(width_e - height_e) < width_e * 0.2:  # 宽高比接近1:1
                                logger.info(f"✓ 策略 2 成功: 找到顶部头像, bounds={bounds}")
                                return element

        logger.warning("未找到店铺名称或头像")
        return None

    def find_qualification_button(self, root: ET.Element) -> Optional[UIElement]:
        """
        查找店铺主页的"资质证照"按钮（精确匹配版）

        Args:
            root: UI 根节点

        Returns:
            找到的资质证照按钮或 None
        """
        logger.info("开始查找'资质证照'按钮...")

        # 策略 1: 通过 text 精确匹配"资质证照"
        logger.info("策略 1: 通过 text 精确匹配'资质证照'...")
        element = self.find_element_by_text(root, "资质证照", exact=True)
        if element:
            logger.info(f"✓ 策略 1 成功: 通过 text 精确匹配找到资质证照按钮")
            return element

        # 策略 2: 通过 content-desc 精确匹配"资质证照"
        logger.info("策略 2: 通过 content-desc 精确匹配'资质证照'...")
        element = self.find_element_by_desc(root, "资质证照", exact=True)
        if element:
            logger.info(f"✓ 策略 2 成功: 通过 content-desc 精确匹配找到资质证照按钮")
            return element

        logger.warning("未找到'资质证照'按钮")
        return None

    def detect_captcha(self, root: ET.Element) -> bool:
        """
        检测是否出现验证码页面

        Args:
            root: UI 根节点

        Returns:
            True 表示检测到验证码，需要人工干预
        """
        logger.info("检测验证码...")

        captcha_keywords = ['验证码', '滑动验证', '拼图', '点击验证', '安全验证', 'captcha', 'verify']

        # 遍历所有节点，检查是否包含验证码相关文字
        for node in root.iter():
            text = node.attrib.get('text', '').lower()
            desc = node.attrib.get('content-desc', '').lower()

            for keyword in captcha_keywords:
                if keyword in text or keyword in desc:
                    logger.warning(f"✓ 检测到验证码：关键词={keyword}")
                    return True

        logger.info("未检测到验证码")
        return False


    # ========== 实时保 App UI 定位方法 ==========

    def find_shishibao_screen_record_button(self, root: ET.Element) -> Optional[UIElement]:
        """
        查找实时保App主页的"屏幕录像"按钮

        Args:
            root: UI 根节点

        Returns:
            找到的按钮元素或 None
        """
        logger.info("开始查找实时保'屏幕录像'按钮...")

        # 策略 1: 通过 text 查找
        keywords = ['屏幕录像', '录屏', '屏幕录制']
        for keyword in keywords:
            element = self.find_element_by_text(root, keyword, exact=False)
            if element:
                bounds = element.get_bounds()
                if bounds and bounds != (0, 0, 0, 0):
                    logger.info(f"✓ 策略 1 成功: 通过 text 找到'{keyword}'")
                    return element
                else:
                    # 查找父元素
                    parent = self._find_clickable_parent(root, element.node)
                    if parent:
                        logger.info(f"✓ 策略 1 成功: 通过 text 找到父元素")
                        return parent

        # 策略 2: 通过 content-desc 查找
        for keyword in keywords:
            element = self.find_element_by_desc(root, keyword, exact=False)
            if element:
                bounds = element.get_bounds()
                if bounds and bounds != (0, 0, 0, 0):
                    logger.info(f"✓ 策略 2 成功: 通过 content-desc 找到'{keyword}'")
                    return element

        logger.warning("未找到实时保'屏幕录像'按钮")
        return None

    def find_shishibao_start_now_button(self, root: ET.Element) -> Optional[UIElement]:
        """
        查找实时保弹窗的"立即开始"按钮

        Args:
            root: UI 根节点

        Returns:
            找到的按钮元素或 None
        """
        logger.info("开始查找实时保'立即开始'按钮...")

        # 策略 1: 通过 text 查找
        keywords = ['立即开始', '开始', '确定', '允许']
        for keyword in keywords:
            element = self.find_element_by_text(root, keyword, exact=False)
            if element:
                bounds = element.get_bounds()
                if bounds and bounds != (0, 0, 0, 0):
                    logger.info(f"✓ 通过 text 找到'{keyword}'")
                    return element
                else:
                    parent = self._find_clickable_parent(root, element.node)
                    if parent:
                        logger.info(f"✓ 通过 text 找到父元素")
                        return parent

        # 策略 2: 查找弹窗底部区域的按钮
        logger.info("策略 2: 在底部区域查找按钮...")
        screen_size = self.adb.get_screen_size()
        if screen_size:
            width, height = screen_size
            # 底部 1/3 区域
            y1 = height * 2 // 3
            clickable_elements = self.find_clickable_in_region(root, 0, y1, width, height)
            if clickable_elements:
                logger.info(f"✓ 策略 2 成功: 底部区域找到可点击元素")
                return clickable_elements[0]

        logger.warning("未找到实时保'立即开始'按钮")
        return None

    def find_shishibao_start_record_button(self, root: ET.Element) -> Optional[UIElement]:
        """
        查找实时保的"开始录制"按钮

        Args:
            root: UI 根节点

        Returns:
            找到的按钮元素或 None
        """
        logger.info("开始查找实时保'开始录制'按钮...")

        # 策略 1: 通过 text 查找
        keywords = ['开始录屏', '开始录制', '开始', '录屏', '录制']
        for keyword in keywords:
            element = self.find_element_by_text(root, keyword, exact=False)
            if element:
                bounds = element.get_bounds()
                if bounds and bounds != (0, 0, 0, 0):
                    logger.info(f"✓ 通过 text 找到'{keyword}'")
                    return element
                else:
                    parent = self._find_clickable_parent(root, element.node)
                    if parent:
                        logger.info(f"✓ 通过 text 找到父元素")
                        return parent

        # 策略 2: 通过 content-desc 查找
        for keyword in keywords:
            element = self.find_element_by_desc(root, keyword, exact=False)
            if element:
                bounds = element.get_bounds()
                if bounds and bounds != (0, 0, 0, 0):
                    logger.info(f"✓ 通过 content-desc 找到'{keyword}'")
                    return element

        logger.warning("未找到实时保'开始录制'按钮")
        return None

    def find_shishibao_stop_record_button(self, root: ET.Element) -> Optional[UIElement]:
        """
        查找实时保的"结束录屏"按钮

        注意：录屏期间 UI dump 可能不准确，按钮显示"结束录屏"但 dump 出来的 text 可能是"开始录屏"。
        因此优先通过 resource-id 定位。

        Args:
            root: UI 根节点

        Returns:
            找到的按钮元素或 None
        """
        logger.info("开始查找实时保'结束录屏'按钮...")

        # 策略 1（优先）: 通过 resource-id 查找录屏按钮
        # 录屏期间 text 可能不准确，但 resource-id 是稳定的
        logger.info("策略 1: 通过 resource-id 查找...")
        target_id = "com.a1010bao.web.rdbao:id/tv_screen_record"
        element = self.find_element_by_id(root, target_id)
        if element:
            bounds = element.get_bounds()
            if bounds and bounds != (0, 0, 0, 0):
                logger.info(f"✓ 通过 resource-id 找到录屏按钮: {target_id}")
                return element

        # 策略 2: 通过 text 精确查找
        logger.info("策略 2: 通过 text 查找...")
        keywords = ['结束录屏', '停止录屏', '结束录制', '停止录制', '开始录屏', '开始录制']
        for keyword in keywords:
            element = self.find_element_by_text(root, keyword, exact=True)
            if element:
                bounds = element.get_bounds()
                if bounds and bounds != (0, 0, 0, 0):
                    logger.info(f"✓ 通过 text 找到'{keyword}'")
                    return element

        # 策略 3: 通过 text 包含"录屏"查找
        logger.info("策略 3: 查找包含'录屏'的元素...")
        for node in root.iter():
            text = node.attrib.get('text', '')
            if '录屏' in text or '录制' in text:
                element = UIElement(node)
                bounds = element.get_bounds()
                if bounds and bounds != (0, 0, 0, 0):
                    logger.info(f"✓ 找到包含'录屏'的按钮: text='{text}'")
                    return element

        logger.warning("未找到实时保'结束录屏'按钮")
        return None

    def find_shishibao_save_button(self, root: ET.Element) -> Optional[UIElement]:
        """
        查找实时保的"保存"按钮

        Args:
            root: UI 根节点

        Returns:
            找到的按钮元素或 None
        """
        logger.info("开始查找实时保'保存'按钮...")

        # 策略 1: 通过 text 查找
        keywords = ['保存', '确定', '完成']
        for keyword in keywords:
            element = self.find_element_by_text(root, keyword, exact=False)
            if element:
                bounds = element.get_bounds()
                if bounds and bounds != (0, 0, 0, 0):
                    logger.info(f"✓ 通过 text 找到'{keyword}'")
                    return element
                else:
                    parent = self._find_clickable_parent(root, element.node)
                    if parent:
                        logger.info(f"✓ 通过 text 找到父元素")
                        return parent

        # 策略 2: 通过 content-desc 查找
        for keyword in keywords:
            element = self.find_element_by_desc(root, keyword, exact=False)
            if element:
                bounds = element.get_bounds()
                if bounds and bounds != (0, 0, 0, 0):
                    logger.info(f"✓ 通过 content-desc 找到'{keyword}'")
                    return element

        logger.warning("未找到实时保'保存'按钮")
        return None

    def find_shishibao_cancel_button(self, root: ET.Element) -> Optional[UIElement]:
        """
        查找实时保的"取消"按钮

        Args:
            root: UI 根节点

        Returns:
            找到的按钮元素或 None
        """
        logger.info("开始查找实时保'取消'按钮...")

        # 通过 text 精确查找"取消"
        element = self.find_element_by_text(root, '取消', exact=True)
        if element:
            bounds = element.get_bounds()
            if bounds and bounds != (0, 0, 0, 0):
                logger.info("✓ 通过 text 找到'取消'")
                return element
            else:
                parent = self._find_clickable_parent(root, element.node)
                if parent:
                    logger.info("✓ 通过 text 找到'取消'父元素")
                    return parent

        # 通过 content-desc 查找
        element = self.find_element_by_desc(root, '取消', exact=True)
        if element:
            bounds = element.get_bounds()
            if bounds and bounds != (0, 0, 0, 0):
                logger.info("✓ 通过 content-desc 找到'取消'")
                return element

        logger.warning("未找到实时保'取消'按钮")
        return None


if __name__ == "__main__":
    # 测试代码
    try:
        from .adb_controller import ADBController
    except ImportError:
        from adb_controller import ADBController

    controller = ADBController()
    if not controller.device_id:
        logger.error("未检测到设备")
        exit(1)

    locator = UILocator(controller)

    # 测试导出和解析
    root = locator.dump_and_parse()
    if root:
        logger.info("✓ UI 导出和解析成功")

        # 测试查找可点击元素
        screen_size = controller.get_screen_size()
        if screen_size:
            width, height = screen_size
            clickable = locator.find_clickable_in_region(root, 0, 0, width, height // 3)
            logger.info(f"顶部 1/3 区域找到 {len(clickable)} 个可点击元素")
