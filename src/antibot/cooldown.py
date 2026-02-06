#!/usr/bin/env python3
"""
Cooldown Manager
Controls task execution frequency to avoid triggering risk controls.
"""

import time
import logging
from typing import Optional
from datetime import datetime, timedelta
from pathlib import Path
import json

from locales import t

logger = logging.getLogger(__name__)


class CooldownManager:
    """
    Cooldown Manager

    Core features:
    - Continuous task counting
    - Auto cooldown after risk detection
    - Cooldown state persistence (supports per-device differentiation)
    """

    def __init__(self, config: dict = None, state_file: str = None, device_id: str = None):
        """
        Initialize cooldown manager.

        Args:
            config: Config dictionary, from config/antibot.json cooldown section
            state_file: State file path (for persistence)
            device_id: Device ID (for multi-device state differentiation)
        """
        self.config = config or {}
        self.device_id = device_id or "default"
        self._load_config()

        # State file (supports per-device differentiation)
        if state_file:
            self.state_file = Path(state_file)
        else:
            state_dir = Path(__file__).parent.parent.parent / 'logs'
            state_dir.mkdir(parents=True, exist_ok=True)
            # Use device ID as filename suffix
            safe_device_id = self.device_id.replace(':', '_').replace('/', '_')
            self.state_file = state_dir / f'cooldown_state_{safe_device_id}.json'

        # Runtime state
        self.continuous_tasks = 0
        self.cooldown_until: Optional[datetime] = None
        self.last_task_time: Optional[datetime] = None

        # Load persisted state
        self._load_state()

    def _load_config(self):
        """Load config parameters."""
        self.enabled = self.config.get('enabled', True)
        self.trigger_on_risk = self.config.get('trigger_on_risk', True)
        self.duration_minutes = self.config.get('duration_minutes', 15)
        self.max_continuous_tasks = self.config.get('max_continuous_tasks', 10)

    def _load_state(self):
        """Load state from file."""
        if not self.state_file.exists():
            return

        try:
            with open(self.state_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            self.continuous_tasks = data.get('continuous_tasks', 0)

            cooldown_str = data.get('cooldown_until')
            if cooldown_str:
                self.cooldown_until = datetime.fromisoformat(cooldown_str)
                # Check if expired
                if self.cooldown_until < datetime.now():
                    self.cooldown_until = None
                    self.continuous_tasks = 0

            last_task_str = data.get('last_task_time')
            if last_task_str:
                self.last_task_time = datetime.fromisoformat(last_task_str)

            logger.info(t('log.cooldown_state_loaded',
                         tasks=self.continuous_tasks,
                         cooling=self.is_cooling_down()))

        except Exception as e:
            logger.warning(t('log.cooldown_state_load_failed', error=e))

    def _save_state(self):
        """Save state to file."""
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)

            data = {
                'continuous_tasks': self.continuous_tasks,
                'cooldown_until': self.cooldown_until.isoformat() if self.cooldown_until else None,
                'last_task_time': self.last_task_time.isoformat() if self.last_task_time else None,
            }

            with open(self.state_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

        except Exception as e:
            logger.warning(t('log.cooldown_state_save_failed', error=e))

    def is_cooling_down(self) -> bool:
        """
        Check if in cooldown period.

        Returns:
            Whether in cooldown period
        """
        if not self.enabled:
            return False

        if self.cooldown_until is None:
            return False

        if datetime.now() >= self.cooldown_until:
            # Cooldown ended
            self.cooldown_until = None
            self.continuous_tasks = 0
            self._save_state()
            return False

        return True

    def get_remaining_cooldown(self) -> Optional[timedelta]:
        """
        Get remaining cooldown time.

        Returns:
            Remaining time, None if not cooling down
        """
        if not self.is_cooling_down():
            return None

        return self.cooldown_until - datetime.now()

    def can_execute_task(self) -> bool:
        """
        Check if task can be executed.

        Returns:
            Whether can execute
        """
        if not self.enabled:
            return True

        return not self.is_cooling_down()

    def record_task_start(self):
        """Record task start."""
        self.last_task_time = datetime.now()
        self._save_state()

    def record_task_complete(self, success: bool = True):
        """
        Record task completion.

        Args:
            success: Whether task succeeded
        """
        self.continuous_tasks += 1
        self.last_task_time = datetime.now()

        # Check if auto cooldown needed
        if self.continuous_tasks >= self.max_continuous_tasks:
            logger.info(t('log.max_continuous_reached', count=self.continuous_tasks))
            self.trigger_cooldown(reason=t('log.max_continuous_reason'))

        self._save_state()

    def trigger_cooldown(self, reason: str = "Manual trigger", duration_minutes: int = None):
        """
        Trigger cooldown.

        Args:
            reason: Trigger reason
            duration_minutes: Cooldown duration (minutes), defaults to config value
        """
        if not self.enabled:
            logger.info(t('log.cooldown_disabled_skip'))
            return

        duration = duration_minutes or self.duration_minutes
        self.cooldown_until = datetime.now() + timedelta(minutes=duration)

        logger.warning(t('log.cooldown_triggered',
                        reason=reason,
                        minutes=duration,
                        until=self.cooldown_until))
        self._save_state()

    def trigger_risk_cooldown(self, risk_type: str):
        """
        Trigger cooldown due to risk.

        Args:
            risk_type: Risk type
        """
        if not self.trigger_on_risk:
            logger.info(t('log.risk_cooldown_disabled'))
            return

        # Adjust cooldown duration based on risk type
        duration_map = {
            'blocked': self.duration_minutes * 2,  # Double cooldown for block
            'captcha': self.duration_minutes,
            'rate_limit': self.duration_minutes,
            'login_required': self.duration_minutes // 2,
        }

        duration = duration_map.get(risk_type, self.duration_minutes)
        self.trigger_cooldown(reason=t('log.risk_detected_cooldown', risk_type=risk_type), duration_minutes=duration)

    def reset(self):
        """Reset cooldown state."""
        self.continuous_tasks = 0
        self.cooldown_until = None
        self._save_state()
        logger.info(t('log.cooldown_state_reset'))

    def wait_for_cooldown(self) -> bool:
        """
        Wait for cooldown to end.

        Returns:
            Whether successfully waited (returns True immediately if not cooling down)
        """
        remaining = self.get_remaining_cooldown()
        if remaining is None:
            return True

        seconds = remaining.total_seconds()
        if seconds <= 0:
            return True

        logger.info(t('log.waiting_cooldown_end', seconds=int(seconds)))

        try:
            time.sleep(seconds)
            self.cooldown_until = None
            self.continuous_tasks = 0
            self._save_state()
            return True
        except KeyboardInterrupt:
            logger.warning(t('log.user_interrupted_wait'))
            return False

    def get_status(self) -> dict:
        """
        Get current status.

        Returns:
            Status dictionary
        """
        remaining = self.get_remaining_cooldown()
        return {
            'enabled': self.enabled,
            'is_cooling_down': self.is_cooling_down(),
            'continuous_tasks': self.continuous_tasks,
            'max_continuous_tasks': self.max_continuous_tasks,
            'remaining_seconds': remaining.total_seconds() if remaining else 0,
            'cooldown_until': self.cooldown_until.isoformat() if self.cooldown_until else None,
        }
