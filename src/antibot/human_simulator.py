#!/usr/bin/env python3
"""
Human Behavior Simulator
Simulates human operations through random delays, random scrolling, etc.
"""

import random
import time
import logging
from typing import Optional, Tuple

from locales import t

logger = logging.getLogger(__name__)


class HumanSimulator:
    """
    Human Behavior Simulator

    Core features:
    - Random delay (avoid fixed intervals)
    - Random scrolling (simulate browsing behavior)
    - Random click offset (avoid precise coordinate clicks)
    - Random browsing actions (occasionally perform unrelated operations)
    """

    def __init__(self, config: dict = None):
        """
        Initialize simulator.

        Args:
            config: Config dictionary, from config/antibot.json human_behavior section
        """
        self.config = config or {}
        self._load_config()

    def _load_config(self):
        """Load config parameters."""
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
        Random delay.

        Args:
            min_ms: Minimum delay milliseconds
            max_ms: Maximum delay milliseconds

        Returns:
            Actual delay in seconds
        """
        min_ms = min_ms or self.sleep_min_ms
        max_ms = max_ms or self.sleep_max_ms

        delay_ms = random.randint(min_ms, max_ms)
        delay_sec = delay_ms / 1000.0

        logger.debug(t('log.random_delay', ms=delay_ms))
        time.sleep(delay_sec)

        return delay_sec

    def sleep_after_click(self) -> float:
        """Random delay after click."""
        return self.random_sleep(self.after_click_min_ms, self.after_click_max_ms)

    def get_random_offset(self, max_offset: int = 10) -> Tuple[int, int]:
        """
        Get random offset (for click coordinate adjustment).

        Args:
            max_offset: Maximum offset pixels

        Returns:
            (x_offset, y_offset) tuple
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
        Add random offset to coordinate point.

        Args:
            x: Original x coordinate
            y: Original y coordinate
            max_offset: Maximum offset pixels

        Returns:
            (new_x, new_y) tuple
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
        Get random scroll parameters.

        Args:
            screen_width: Screen width
            screen_height: Screen height
            direction: Scroll direction ('up', 'down', 'left', 'right')

        Returns:
            (start_x, start_y, end_x, end_y, duration_ms) tuple
        """
        # Randomly select start point in center screen area
        center_x = screen_width // 2
        x_variance = screen_width // 6
        start_x = center_x + random.randint(-x_variance, x_variance)

        # Calculate scroll based on direction
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
            raise ValueError(t('log.unknown_scroll_direction', direction=direction))

        # Ensure coordinates within screen bounds
        end_x = max(0, min(end_x, screen_width - 1))
        end_y = max(0, min(end_y, screen_height - 1))

        return start_x, start_y, end_x, end_y, duration

    def should_do_random_action(self) -> bool:
        """
        Determine if should execute random browsing action.

        Returns:
            Whether should execute
        """
        if not self.random_browse_enabled:
            return False
        return random.random() < self.random_browse_probability

    def get_random_action(self) -> str:
        """
        Get a random action.

        Returns:
            Action name ('scroll_up', 'scroll_down', 'wait')
        """
        return random.choice(self.random_actions)

    def execute_random_action(self, adb_controller) -> bool:
        """
        Execute random browsing action.

        Args:
            adb_controller: ADBController instance

        Returns:
            Whether executed successfully
        """
        if not self.should_do_random_action():
            return False

        action = self.get_random_action()
        logger.info(t('log.execute_random_action', action=action))

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
            logger.warning(t('log.random_action_failed', error=e))
            return False

    def humanize_typing_delay(self, text: str) -> float:
        """
        Calculate human-like typing delay.

        Args:
            text: Text to input

        Returns:
            Total delay in seconds
        """
        # Average 100-300ms per character
        char_delay = len(text) * random.uniform(0.1, 0.3)
        # Add some random pauses
        pause_delay = random.uniform(0.2, 0.5)
        return char_delay + pause_delay
