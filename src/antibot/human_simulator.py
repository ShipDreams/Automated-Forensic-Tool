#!/usr/bin/env python3
"""
人类行为模拟器
通过随机延迟、随机滚动等方式模拟真人操作
"""

import random
import time
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)


class HumanSimulator:
    """
    人类行为模拟器

    核心功能：
    - 随机延迟（避免固定间隔）
    - 随机滚动（模拟浏览行为）
    - 随机点击偏移（避免精确坐标点击）
    - 随机浏览动作（偶尔做一些无关操作）
    """

    def __init__(self, config: dict = None):
        """
        初始化模拟器

        Args:
            config: 配置字典，来自 config/antibot.json 的 human_behavior 部分
        """
        self.config = config or {}
        self._load_config()

    def _load_config(self):
        """加载配置参数"""
        sleep_config = self.config.get('sleep', {})
        self.sleep_min_ms = sleep_config.get('min_ms', 500)
        self.sleep_max_ms = sleep_config.get('max_ms', 2000)
        self.after_click_min_ms = sleep_config.get('after_click_min_ms', 800)
        self.after_click_max_ms = sleep_config.get('after_click_max_ms', 1500)

        scroll_config = self.config.get('scroll', {})
        self.scroll_min_distance = scroll_config.get('min_distance', 200)
        self.scroll_max_distance = scroll_config.get('max_distance', 600)
        self.scroll_min_duration = scroll_config.get('min_duration_ms', 300)
        self.scroll_max_duration = scroll_config.get('max_duration_ms', 800)

        browse_config = self.config.get('random_browse', {})
        self.random_browse_enabled = browse_config.get('enabled', True)
        self.random_browse_probability = browse_config.get('probability', 0.1)
        self.random_actions = browse_config.get('actions', ['scroll_up', 'scroll_down', 'wait'])

    def random_sleep(self, min_ms: int = None, max_ms: int = None) -> float:
        """
        随机延迟

        Args:
            min_ms: 最小延迟毫秒数
            max_ms: 最大延迟毫秒数

        Returns:
            实际延迟的秒数
        """
        min_ms = min_ms or self.sleep_min_ms
        max_ms = max_ms or self.sleep_max_ms

        delay_ms = random.randint(min_ms, max_ms)
        delay_sec = delay_ms / 1000.0

        logger.debug(f"随机延迟: {delay_ms}ms")
        time.sleep(delay_sec)

        return delay_sec

    def sleep_after_click(self) -> float:
        """点击后的随机延迟"""
        return self.random_sleep(self.after_click_min_ms, self.after_click_max_ms)

    def get_random_offset(self, max_offset: int = 10) -> Tuple[int, int]:
        """
        获取随机偏移量（用于点击坐标微调）

        Args:
            max_offset: 最大偏移像素

        Returns:
            (x_offset, y_offset) 元组
        """
        x_offset = random.randint(-max_offset, max_offset)
        y_offset = random.randint(-max_offset, max_offset)
        return x_offset, y_offset

    def apply_offset_to_point(
        self,
        x: int,
        y: int,
        max_offset: int = 10
    ) -> Tuple[int, int]:
        """
        给坐标点添加随机偏移

        Args:
            x: 原始 x 坐标
            y: 原始 y 坐标
            max_offset: 最大偏移像素

        Returns:
            (new_x, new_y) 元组
        """
        offset_x, offset_y = self.get_random_offset(max_offset)
        return x + offset_x, y + offset_y

    def get_random_scroll_params(
        self,
        screen_width: int,
        screen_height: int,
        direction: str = 'up'
    ) -> Tuple[int, int, int, int, int]:
        """
        获取随机滚动参数

        Args:
            screen_width: 屏幕宽度
            screen_height: 屏幕高度
            direction: 滚动方向 ('up', 'down', 'left', 'right')

        Returns:
            (start_x, start_y, end_x, end_y, duration_ms) 元组
        """
        # 在屏幕中间区域随机选择起点
        center_x = screen_width // 2
        x_variance = screen_width // 6
        start_x = center_x + random.randint(-x_variance, x_variance)

        # 根据方向计算滚动
        distance = random.randint(self.scroll_min_distance, self.scroll_max_distance)
        duration = random.randint(self.scroll_min_duration, self.scroll_max_duration)

        if direction == 'up':
            start_y = screen_height * 2 // 3 + random.randint(-50, 50)
            end_x = start_x + random.randint(-20, 20)
            end_y = start_y - distance
        elif direction == 'down':
            start_y = screen_height // 3 + random.randint(-50, 50)
            end_x = start_x + random.randint(-20, 20)
            end_y = start_y + distance
        elif direction == 'left':
            start_y = screen_height // 2 + random.randint(-50, 50)
            start_x = screen_width * 2 // 3
            end_x = start_x - distance
            end_y = start_y + random.randint(-20, 20)
        elif direction == 'right':
            start_y = screen_height // 2 + random.randint(-50, 50)
            start_x = screen_width // 3
            end_x = start_x + distance
            end_y = start_y + random.randint(-20, 20)
        else:
            raise ValueError(f"未知的滚动方向: {direction}")

        # 确保坐标在屏幕范围内
        end_x = max(0, min(end_x, screen_width - 1))
        end_y = max(0, min(end_y, screen_height - 1))

        return start_x, start_y, end_x, end_y, duration

    def should_do_random_action(self) -> bool:
        """
        判断是否应该执行随机浏览动作

        Returns:
            是否应该执行
        """
        if not self.random_browse_enabled:
            return False
        return random.random() < self.random_browse_probability

    def get_random_action(self) -> str:
        """
        获取一个随机动作

        Returns:
            动作名称 ('scroll_up', 'scroll_down', 'wait')
        """
        return random.choice(self.random_actions)

    def execute_random_action(self, adb_controller) -> bool:
        """
        执行随机浏览动作

        Args:
            adb_controller: ADBController 实例

        Returns:
            是否执行成功
        """
        if not self.should_do_random_action():
            return False

        action = self.get_random_action()
        logger.info(f"执行随机浏览动作: {action}")

        try:
            screen_size = adb_controller.get_screen_size()
            if not screen_size:
                return False

            width, height = screen_size

            if action == 'scroll_up':
                params = self.get_random_scroll_params(width, height, 'up')
                adb_controller.swipe(*params)
            elif action == 'scroll_down':
                params = self.get_random_scroll_params(width, height, 'down')
                adb_controller.swipe(*params)
            elif action == 'wait':
                self.random_sleep(1000, 3000)

            self.sleep_after_click()
            return True

        except Exception as e:
            logger.warning(f"随机动作执行失败: {e}")
            return False

    def humanize_typing_delay(self, text: str) -> float:
        """
        计算人类化的打字延迟

        Args:
            text: 要输入的文本

        Returns:
            总延迟秒数
        """
        # 平均每个字符 100-300ms
        char_delay = len(text) * random.uniform(0.1, 0.3)
        # 加上一些随机停顿
        pause_delay = random.uniform(0.2, 0.5)
        return char_delay + pause_delay
