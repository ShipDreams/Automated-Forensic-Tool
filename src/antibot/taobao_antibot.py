#!/usr/bin/env python3
"""
Taobao-specific Anti-bot Module
Implements Taobao platform-specific human behavior simulation and cycle management.
"""

import random
import time
import logging
import json
from pathlib import Path
from typing import Optional, Tuple
from datetime import datetime, timedelta

from locales import t

logger = logging.getLogger(__name__)


class TaobaoAntiBot:
    """
    Taobao-specific Anti-bot Manager

    Core features:
    - Simulate human browsing behavior (2-5 minutes)
    - Cycle management (3-5 tasks per cycle)
    - Cooldown management (enter 15-minute cooldown after 3-5 cycles)
    - Device state persistence
    """

    TAOBAO_PACKAGE = "com.taobao.taobao"

    def __init__(self, adb_controller, ui_locator, config: dict = None, device_id: str = None):
        """
        Initialize Taobao anti-bot.

        Args:
            adb_controller: ADBController instance
            ui_locator: UILocator instance
            config: Config dictionary (Taobao-specific section)
            device_id: Device ID (for state persistence)
        """
        self.adb = adb_controller
        self.locator = ui_locator
        self.config = config or {}
        self.device_id = device_id or adb_controller.device_id or "default"

        self._load_config()
        self._load_state()

    def _load_config(self):
        """Load config parameters."""
        # Tasks per cycle range
        tasks_range = self.config.get('tasks_per_cycle', [3, 5])
        self.tasks_per_cycle_min = tasks_range[0] if isinstance(tasks_range, list) else 3
        self.tasks_per_cycle_max = tasks_range[1] if isinstance(tasks_range, list) else 5

        # Cycles before cooldown range
        cycles_range = self.config.get('cycles_before_cooldown', [3, 5])
        self.cycles_before_cooldown_min = cycles_range[0] if isinstance(cycles_range, list) else 3
        self.cycles_before_cooldown_max = cycles_range[1] if isinstance(cycles_range, list) else 5

        # Browse simulation duration range (minutes)
        browse_range = self.config.get('browse_duration_minutes', [2, 5])
        self.browse_duration_min = browse_range[0] if isinstance(browse_range, list) else 2
        self.browse_duration_max = browse_range[1] if isinstance(browse_range, list) else 5

        # Cooldown duration (minutes)
        self.cooldown_duration_minutes = self.config.get('cooldown_duration_minutes', 15)

        # Click offset
        self.click_offset_max_px = self.config.get('click_offset_max_px', 5)

        # Current cycle target task count (randomly determined)
        self._current_cycle_target = random.randint(self.tasks_per_cycle_min, self.tasks_per_cycle_max)
        # Current cooldown period target cycle count (randomly determined)
        self._current_cooldown_target = random.randint(self.cycles_before_cooldown_min, self.cycles_before_cooldown_max)

    def _get_state_file_path(self) -> Path:
        """Get device-specific state file path."""
        state_dir = Path(__file__).parent.parent.parent / 'logs'
        state_dir.mkdir(parents=True, exist_ok=True)
        # Use device ID as filename suffix
        safe_device_id = self.device_id.replace(':', '_').replace('/', '_')
        return state_dir / f'taobao_antibot_state_{safe_device_id}.json'

    def _load_state(self):
        """Load device state."""
        state_file = self._get_state_file_path()

        # Default state
        self.tasks_in_cycle = 0  # Tasks completed in current cycle
        self.completed_cycles = 0  # Completed cycles count
        self.cooldown_until: Optional[datetime] = None  # Cooldown end time
        self.last_task_time: Optional[datetime] = None  # Last task time

        if not state_file.exists():
            logger.info(t('log.taobao_state_file_not_exist', path=state_file))
            return

        try:
            with open(state_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            self.tasks_in_cycle = data.get('tasks_in_cycle', 0)
            self.completed_cycles = data.get('completed_cycles', 0)

            cooldown_str = data.get('cooldown_until')
            if cooldown_str:
                self.cooldown_until = datetime.fromisoformat(cooldown_str)
                # Check if expired
                if self.cooldown_until < datetime.now():
                    logger.info(t('log.taobao_cooldown_expired_reset'))
                    self.cooldown_until = None
                    self.completed_cycles = 0
                    self.tasks_in_cycle = 0

            last_task_str = data.get('last_task_time')
            if last_task_str:
                self.last_task_time = datetime.fromisoformat(last_task_str)

            # Restore target values
            self._current_cycle_target = data.get('current_cycle_target',
                random.randint(self.tasks_per_cycle_min, self.tasks_per_cycle_max))
            self._current_cooldown_target = data.get('current_cooldown_target',
                random.randint(self.cycles_before_cooldown_min, self.cycles_before_cooldown_max))

            logger.info(t('log.taobao_state_loaded',
                         tasks_in_cycle=self.tasks_in_cycle,
                         cycle_target=self._current_cycle_target,
                         completed_cycles=self.completed_cycles,
                         cooldown_target=self._current_cooldown_target,
                         cooling=self.is_cooling_down()))

        except Exception as e:
            logger.warning(t('log.taobao_state_load_failed', error=e))

    def _save_state(self):
        """Save device state."""
        state_file = self._get_state_file_path()

        try:
            data = {
                'device_id': self.device_id,
                'tasks_in_cycle': self.tasks_in_cycle,
                'completed_cycles': self.completed_cycles,
                'cooldown_until': self.cooldown_until.isoformat() if self.cooldown_until else None,
                'last_task_time': self.last_task_time.isoformat() if self.last_task_time else None,
                'current_cycle_target': self._current_cycle_target,
                'current_cooldown_target': self._current_cooldown_target,
                'updated_at': datetime.now().isoformat()
            }

            with open(state_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            logger.debug(t('log.taobao_state_saved', path=state_file))

        except Exception as e:
            logger.error(t('log.taobao_state_save_failed', error=e))

    # ==================== State Queries ====================

    def is_cooling_down(self) -> bool:
        """Check if in cooldown period."""
        if self.cooldown_until is None:
            return False

        if datetime.now() >= self.cooldown_until:
            # Cooldown ended
            self.cooldown_until = None
            self.completed_cycles = 0
            self.tasks_in_cycle = 0
            self._current_cooldown_target = random.randint(
                self.cycles_before_cooldown_min, self.cycles_before_cooldown_max)
            self._save_state()
            return False

        return True

    def get_remaining_cooldown(self) -> Optional[timedelta]:
        """Get remaining cooldown time."""
        if not self.is_cooling_down():
            return None
        return self.cooldown_until - datetime.now()

    def can_proceed(self) -> bool:
        """Check if task can be executed."""
        return not self.is_cooling_down()

    def get_status(self) -> dict:
        """Get current status."""
        remaining = self.get_remaining_cooldown()
        return {
            'device_id': self.device_id,
            'tasks_in_cycle': self.tasks_in_cycle,
            'tasks_per_cycle_target': self._current_cycle_target,
            'completed_cycles': self.completed_cycles,
            'cycles_before_cooldown_target': self._current_cooldown_target,
            'is_cooling_down': self.is_cooling_down(),
            'remaining_seconds': remaining.total_seconds() if remaining else 0,
            'cooldown_until': self.cooldown_until.isoformat() if self.cooldown_until else None,
        }

    # ==================== Task Cycle Management ====================

    def record_task_complete(self) -> Tuple[bool, bool]:
        """
        Record task completion.

        Returns:
            (should_browse, should_cooldown) tuple
            - should_browse: Whether to execute human browse simulation
            - should_cooldown: Whether to enter cooldown period
        """
        self.tasks_in_cycle += 1
        self.last_task_time = datetime.now()

        should_browse = False
        should_cooldown = False

        # Check if current cycle is complete
        if self.tasks_in_cycle >= self._current_cycle_target:
            should_browse = True
            self.completed_cycles += 1
            self.tasks_in_cycle = 0
            # Generate new random target for next cycle
            self._current_cycle_target = random.randint(
                self.tasks_per_cycle_min, self.tasks_per_cycle_max)

            logger.info(t('log.taobao_cycle_complete', cycle=self.completed_cycles))

            # Check if cooldown needed
            if self.completed_cycles >= self._current_cooldown_target:
                should_cooldown = True
                logger.info(t('log.taobao_need_cooldown', cycles=self.completed_cycles))

        self._save_state()
        return should_browse, should_cooldown

    def trigger_cooldown(self, reason: str = "cycle_complete"):
        """
        Trigger cooldown period.

        Args:
            reason: Trigger reason
        """
        self.cooldown_until = datetime.now() + timedelta(minutes=self.cooldown_duration_minutes)
        self.completed_cycles = 0
        self.tasks_in_cycle = 0
        # Generate new random target for next cooldown period
        self._current_cooldown_target = random.randint(
            self.cycles_before_cooldown_min, self.cycles_before_cooldown_max)

        self._save_state()
        logger.warning(t('log.taobao_enter_cooldown',
                        reason=reason,
                        minutes=self.cooldown_duration_minutes,
                        until=self.cooldown_until))

    def reset_state(self):
        """Reset state."""
        self.tasks_in_cycle = 0
        self.completed_cycles = 0
        self.cooldown_until = None
        self._current_cycle_target = random.randint(
            self.tasks_per_cycle_min, self.tasks_per_cycle_max)
        self._current_cooldown_target = random.randint(
            self.cycles_before_cooldown_min, self.cycles_before_cooldown_max)
        self._save_state()
        logger.info(t('log.taobao_state_reset'))

    # ==================== Human Behavior Simulation ====================

    def _is_in_taobao(self) -> bool:
        """Check if currently in Taobao App."""
        current_focus = self.adb.get_current_focus()
        if current_focus and 'taobao' in current_focus.lower():
            return True
        return False

    def _random_sleep(self, min_sec: float, max_sec: float):
        """Random delay."""
        delay = random.uniform(min_sec, max_sec)
        time.sleep(delay)
        return delay

    def _random_scroll(self, direction: str = 'up') -> bool:
        """
        Random scroll.

        Args:
            direction: Direction ('up', 'down')

        Returns:
            Whether successful
        """
        screen_size = self.adb.get_screen_size()
        if not screen_size:
            return False

        width, height = screen_size

        # Calculate random scroll parameters
        center_x = width // 2 + random.randint(-width // 6, width // 6)
        distance = random.randint(200, 500)
        duration = random.randint(300, 600)

        if direction == 'up':
            start_y = height * 2 // 3 + random.randint(-50, 50)
            end_y = start_y - distance
        else:
            start_y = height // 3 + random.randint(-50, 50)
            end_y = start_y + distance

        end_x = center_x + random.randint(-20, 20)

        # Ensure coordinates within screen bounds
        end_y = max(0, min(end_y, height - 1))
        end_x = max(0, min(end_x, width - 1))

        return self.adb.swipe(center_x, start_y, end_x, end_y, duration)

    def _find_and_click_random_product(self) -> bool:
        """
        Randomly click a product link.

        Returns:
            Whether click succeeded
        """
        root = self.locator.dump_and_parse()
        if not root:
            return False

        screen_size = self.adb.get_screen_size()
        if not screen_size:
            return False

        width, height = screen_size

        # Find clickable elements in middle region (exclude top and bottom nav bars)
        clickable_elements = self.locator.find_clickable_in_region(
            root, 0, height // 6, width, height * 5 // 6
        )

        if not clickable_elements:
            logger.debug(t('log.taobao_no_clickable_products'))
            return False

        # Randomly select an element to click
        element = random.choice(clickable_elements)
        center = element.get_center()
        if not center:
            return False

        x, y = center
        # Add random offset
        x += random.randint(-self.click_offset_max_px, self.click_offset_max_px)
        y += random.randint(-self.click_offset_max_px, self.click_offset_max_px)

        logger.debug(t('log.taobao_click_random_product', x=x, y=y))
        return self.adb.tap(x, y)

    def _go_back_safely(self) -> bool:
        """
        Safe back navigation (check if still in Taobao).

        Returns:
            Whether still in Taobao
        """
        self.adb.press_back()
        self._random_sleep(1.0, 2.0)

        # Check if still in Taobao
        if not self._is_in_taobao():
            logger.warning(t('log.taobao_left_after_back'))
            # Try to reopen Taobao
            self.adb.run_command(f"am start -n {self.TAOBAO_PACKAGE}/.MainTabActivity")
            self._random_sleep(2.0, 3.0)
            return self._is_in_taobao()

        return True

    def _go_to_home_tab(self) -> bool:
        """
        Try to go back to Taobao home tab.

        Returns:
            Whether successful
        """
        # Click "Home" button in bottom navigation bar
        root = self.locator.dump_and_parse()
        if not root:
            return False

        screen_size = self.adb.get_screen_size()
        if not screen_size:
            return False

        width, height = screen_size

        # Find home button in bottom navigation bar
        home_keywords = ['首页', '淘宝', 'Home']

        for node in root.iter():
            text = node.attrib.get('text', '')
            desc = node.attrib.get('content-desc', '')

            for keyword in home_keywords:
                if keyword in text or keyword in desc:
                    from .human_simulator import HumanSimulator
                    element = self.locator.find_element_by_text(root, keyword, exact=False)
                    if element:
                        center = element.get_center()
                        if center:
                            x, y = center
                            # Ensure in bottom region
                            if y > height * 4 // 5:
                                logger.info(t('log.taobao_click_home_tab'))
                                self.adb.tap(x, y)
                                self._random_sleep(1.5, 2.5)
                                return True

        return False

    def simulate_human_browse(self) -> bool:
        """
        Simulate human browsing behavior.

        The entire process lasts 2-5 minutes, including:
        - Random up/down scrolling
        - Random product clicks
        - Occasionally return to home

        Returns:
            Whether completed successfully
        """
        if not self._is_in_taobao():
            logger.info(t('log.taobao_not_in_app_opening'))
            self.adb.run_command(f"am start -n {self.TAOBAO_PACKAGE}/.MainTabActivity")
            self._random_sleep(3.0, 5.0)  # Wait for Taobao to start
            if not self._is_in_taobao():
                logger.warning(t('log.taobao_cannot_open_skip_browse'))
                return False
            logger.info(t('log.taobao_opened'))

        # Randomly decide browse duration
        browse_duration = random.uniform(
            self.browse_duration_min * 60,  # Convert to seconds
            self.browse_duration_max * 60
        )

        logger.info(t('log.taobao_start_browse_simulation', minutes=browse_duration / 60))

        start_time = time.time()
        action_count = 0
        back_to_home_count = 0
        max_back_to_home = 2  # Max times to go home

        while time.time() - start_time < browse_duration:
            # Check if still in Taobao
            if not self._is_in_taobao():
                logger.warning(t('log.taobao_left_trying_return'))
                self.adb.run_command(f"am start -n {self.TAOBAO_PACKAGE}/.MainTabActivity")
                self._random_sleep(2.0, 3.0)
                if not self._is_in_taobao():
                    logger.error(t('log.taobao_cannot_return_abort'))
                    return False

            # Randomly select action
            action = random.choices(
                ['scroll_up', 'scroll_down', 'click_product', 'wait', 'go_home'],
                weights=[30, 25, 25, 15, 5],  # Action weights
                k=1
            )[0]

            action_count += 1
            logger.debug(t('log.taobao_execute_action', count=action_count, action=action))

            if action == 'scroll_up':
                self._random_scroll('up')
                self._random_sleep(1.0, 2.5)

            elif action == 'scroll_down':
                self._random_scroll('down')
                self._random_sleep(1.0, 2.5)

            elif action == 'click_product':
                if self._find_and_click_random_product():
                    # View product for 2-5 seconds
                    self._random_sleep(2.0, 5.0)
                    # Maybe scroll to view details
                    if random.random() < 0.5:
                        self._random_scroll('up')
                        self._random_sleep(1.0, 2.0)
                    # Go back
                    self._go_back_safely()
                else:
                    # Click failed, scroll and retry
                    self._random_scroll('up')
                    self._random_sleep(1.0, 2.0)

            elif action == 'wait':
                self._random_sleep(2.0, 4.0)

            elif action == 'go_home':
                if back_to_home_count < max_back_to_home:
                    self._go_to_home_tab()
                    back_to_home_count += 1
                    self._random_sleep(1.5, 3.0)

        elapsed = time.time() - start_time
        logger.info(t('log.taobao_browse_complete', minutes=elapsed / 60, actions=action_count))

        return True

    def close_taobao(self) -> bool:
        """
        Close Taobao process.

        Returns:
            Whether successful
        """
        logger.info(t('log.taobao_closing_process'))
        result = self.adb.force_stop_app(self.TAOBAO_PACKAGE)
        if result:
            logger.info(t('log.taobao_process_closed'))
        else:
            logger.warning(t('log.taobao_close_may_failed'))
        return result

    def execute_cycle_end_actions(self) -> bool:
        """
        Execute actions after cycle ends.

        Including:
        1. Simulate human browsing
        2. Close Taobao process

        Returns:
            Whether successful
        """
        logger.info("=" * 60)
        logger.info(t('log.taobao_execute_cycle_end_actions'))
        logger.info("=" * 60)

        # Simulate human browsing
        browse_success = self.simulate_human_browse()

        # Close Taobao regardless of browse success
        self.close_taobao()

        return browse_success

    # ==================== Click Offset ====================

    def apply_click_offset(self, x: int, y: int) -> Tuple[int, int]:
        """
        Add random offset to click coordinates.

        Args:
            x: Original x coordinate
            y: Original y coordinate

        Returns:
            (new_x, new_y) coordinates with offset applied
        """
        offset_x = random.randint(-self.click_offset_max_px, self.click_offset_max_px)
        offset_y = random.randint(-self.click_offset_max_px, self.click_offset_max_px)
        return x + offset_x, y + offset_y
