#!/usr/bin/env python3
"""
AntiBot Main Module
Integrates human behavior simulation, risk detection, and cooldown management.
"""

import json
import logging
from pathlib import Path
from typing import Optional, List, Callable

from locales import t
from .human_simulator import HumanSimulator
from .risk_detector import RiskDetector, RiskSignal, RiskType
from .cooldown import CooldownManager

logger = logging.getLogger(__name__)


class AntiBot:
    """
    AntiBot Risk Control Manager

    Core features:
    - Unified human behavior simulation management
    - Unified risk detection management
    - Unified cooldown mechanism management
    - Convenient decorators and context managers
    """

    def __init__(self, config_path: str = None):
        """
        Initialize AntiBot.

        Args:
            config_path: Config file path, defaults to config/antibot.json
        """
        self.config = self._load_config(config_path)

        # Initialize submodules
        self.human = HumanSimulator(self.config.get('human_behavior', {}))
        self.detector = RiskDetector(self.config.get('risk_detection', {}))
        self.cooldown = CooldownManager(self.config.get('cooldown', {}))

        # Risk callbacks
        self._risk_callbacks: List[Callable[[RiskSignal], None]] = []

    def _load_config(self, config_path: str = None) -> dict:
        """Load configuration file."""
        if config_path:
            path = Path(config_path)
        else:
            path = Path(__file__).parent.parent.parent / 'config' / 'antibot.json'

        if not path.exists():
            logger.warning(t('log.antibot_config_not_found', path=path))
            return {}

        try:
            with open(path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            logger.info(t('log.antibot_config_loaded', path=path))
            return config
        except Exception as e:
            logger.error(t('log.antibot_config_load_failed', error=e))
            return {}

    # ==================== Human Behavior Simulation ====================

    def sleep(self, min_ms: int = None, max_ms: int = None) -> float:
        """Random delay."""
        return self.human.random_sleep(min_ms, max_ms)

    def sleep_after_click(self) -> float:
        """Random delay after click."""
        return self.human.sleep_after_click()

    def random_offset(self, x: int, y: int, max_offset: int = 10):
        """Add random offset to coordinates."""
        return self.human.apply_offset_to_point(x, y, max_offset)

    def maybe_random_action(self, adb_controller) -> bool:
        """Possibly execute random browsing action."""
        return self.human.execute_random_action(adb_controller)

    # ==================== Risk Detection ====================

    def check_risk(self, ui_root) -> List[RiskSignal]:
        """
        Detect risks on current page.

        Args:
            ui_root: UI hierarchy tree root node

        Returns:
            List of risk signals
        """
        signals = self.detector.detect_from_ui_tree(ui_root)

        # Handle high risk signals
        for signal in signals:
            if signal.confidence >= 0.6:
                logger.warning(t('log.risk_detected_detail',
                              risk_type=signal.risk_type.value,
                              confidence=signal.confidence,
                              details=signal.details))

                # Trigger callbacks
                for callback in self._risk_callbacks:
                    try:
                        callback(signal)
                    except Exception as e:
                        logger.error(t('log.risk_callback_failed', error=e))

                # Trigger cooldown based on risk type
                if signal.risk_type in [RiskType.BLOCKED, RiskType.RATE_LIMIT]:
                    self.cooldown.trigger_risk_cooldown(signal.risk_type.value)

        return signals

    def is_safe(self, ui_root, threshold: float = 0.6) -> bool:
        """
        Check if current page is safe.

        Args:
            ui_root: UI hierarchy tree root node
            threshold: Risk threshold

        Returns:
            Whether safe
        """
        signals = self.check_risk(ui_root)
        return self.detector.is_safe(signals, threshold)

    def detect_captcha(self, ui_root) -> Optional[str]:
        """
        Detect captcha type.

        Args:
            ui_root: UI hierarchy tree root node

        Returns:
            Captcha type or None
        """
        return self.detector.detect_captcha_type(ui_root)

    def on_risk(self, callback: Callable[[RiskSignal], None]):
        """
        Register risk callback.

        Args:
            callback: Callback function, accepts RiskSignal parameter
        """
        self._risk_callbacks.append(callback)

    # ==================== Cooldown Management ====================

    def can_proceed(self) -> bool:
        """Check if execution can proceed."""
        return self.cooldown.can_execute_task()

    def wait_if_cooling(self) -> bool:
        """Wait if in cooldown period."""
        return self.cooldown.wait_for_cooldown()

    def record_task_done(self, success: bool = True):
        """Record task completion."""
        self.cooldown.record_task_complete(success)

    def trigger_pause(self, reason: str = "Manual pause", minutes: int = None):
        """Trigger pause/cooldown."""
        self.cooldown.trigger_cooldown(reason, minutes)

    def get_cooldown_status(self) -> dict:
        """Get cooldown status."""
        return self.cooldown.get_status()

    # ==================== Convenience Methods ====================

    def safe_click(self, adb_controller, x: int, y: int) -> bool:
        """
        Safe click (with random offset and delay).

        Args:
            adb_controller: ADBController instance
            x: Target x coordinate
            y: Target y coordinate

        Returns:
            Whether successful
        """
        # Add random offset
        new_x, new_y = self.random_offset(x, y)

        # Execute click
        result = adb_controller.tap(new_x, new_y)

        # Delay after click
        self.sleep_after_click()

        return result

    def safe_input(self, adb_controller, text: str) -> bool:
        """
        Safe text input (with human-like delay).

        Args:
            adb_controller: ADBController instance
            text: Text to input

        Returns:
            Whether successful
        """
        # Brief delay before input
        self.sleep(300, 800)

        # Execute input
        result = adb_controller.input_text(text)

        # Delay after input
        delay = self.human.humanize_typing_delay(text)
        import time
        time.sleep(delay)

        return result

    def safe_scroll(
        self,
        adb_controller,
        direction: str = 'up'
    ) -> bool:
        """
        Safe scroll (with random parameters).

        Args:
            adb_controller: ADBController instance
            direction: Scroll direction

        Returns:
            Whether successful
        """
        screen_size = adb_controller.get_screen_size()
        if not screen_size:
            return False

        params = self.human.get_random_scroll_params(
            screen_size[0], screen_size[1], direction
        )

        result = adb_controller.swipe(*params)
        self.sleep_after_click()

        return result

    def pre_action_check(self, ui_locator) -> bool:
        """
        Pre-action check.

        Suitable for calling before each critical operation to check risk and cooldown status.

        Args:
            ui_locator: UILocator instance

        Returns:
            Whether can proceed
        """
        # Check cooldown
        if not self.can_proceed():
            remaining = self.cooldown.get_remaining_cooldown()
            logger.warning(t('log.in_cooldown_remaining', remaining=remaining))
            return False

        # Check risk
        root = ui_locator.dump_and_parse()
        if root and not self.is_safe(root):
            logger.warning(t('log.risk_detected_suggest_pause'))
            return False

        # Possibly execute random action
        # self.maybe_random_action(ui_locator.adb)

        return True
