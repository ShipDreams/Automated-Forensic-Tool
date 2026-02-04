#!/usr/bin/env python3
"""
冷却管理器
控制任务执行频率，避免触发风控
"""

import time
import logging
from typing import Optional
from datetime import datetime, timedelta
from pathlib import Path
import json

logger = logging.getLogger(__name__)


class CooldownManager:
    """
    冷却管理器

    核心功能：
    - 连续任务计数
    - 风险触发后自动冷却
    - 冷却状态持久化
    """

    def __init__(self, config: dict = None, state_file: str = None):
        """
        初始化冷却管理器

        Args:
            config: 配置字典，来自 config/antibot.json 的 cooldown 部分
            state_file: 状态文件路径（用于持久化）
        """
        self.config = config or {}
        self._load_config()

        # 状态文件
        if state_file:
            self.state_file = Path(state_file)
        else:
            self.state_file = Path(__file__).parent.parent.parent / 'logs' / 'cooldown_state.json'

        # 运行时状态
        self.continuous_tasks = 0
        self.cooldown_until: Optional[datetime] = None
        self.last_task_time: Optional[datetime] = None

        # 加载持久化状态
        self._load_state()

    def _load_config(self):
        """加载配置参数"""
        self.enabled = self.config.get('enabled', True)
        self.trigger_on_risk = self.config.get('trigger_on_risk', True)
        self.duration_minutes = self.config.get('duration_minutes', 15)
        self.max_continuous_tasks = self.config.get('max_continuous_tasks', 10)

    def _load_state(self):
        """从文件加载状态"""
        if not self.state_file.exists():
            return

        try:
            with open(self.state_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            self.continuous_tasks = data.get('continuous_tasks', 0)

            cooldown_str = data.get('cooldown_until')
            if cooldown_str:
                self.cooldown_until = datetime.fromisoformat(cooldown_str)
                # 检查是否已过期
                if self.cooldown_until < datetime.now():
                    self.cooldown_until = None
                    self.continuous_tasks = 0

            last_task_str = data.get('last_task_time')
            if last_task_str:
                self.last_task_time = datetime.fromisoformat(last_task_str)

            logger.info(f"加载冷却状态: 连续任务={self.continuous_tasks}, 冷却中={self.is_cooling_down()}")

        except Exception as e:
            logger.warning(f"加载冷却状态失败: {e}")

    def _save_state(self):
        """保存状态到文件"""
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
            logger.warning(f"保存冷却状态失败: {e}")

    def is_cooling_down(self) -> bool:
        """
        检查是否正在冷却中

        Returns:
            是否在冷却期
        """
        if not self.enabled:
            return False

        if self.cooldown_until is None:
            return False

        if datetime.now() >= self.cooldown_until:
            # 冷却结束
            self.cooldown_until = None
            self.continuous_tasks = 0
            self._save_state()
            return False

        return True

    def get_remaining_cooldown(self) -> Optional[timedelta]:
        """
        获取剩余冷却时间

        Returns:
            剩余时间，如果没有在冷却则返回 None
        """
        if not self.is_cooling_down():
            return None

        return self.cooldown_until - datetime.now()

    def can_execute_task(self) -> bool:
        """
        检查是否可以执行任务

        Returns:
            是否可以执行
        """
        if not self.enabled:
            return True

        return not self.is_cooling_down()

    def record_task_start(self):
        """记录任务开始"""
        self.last_task_time = datetime.now()
        self._save_state()

    def record_task_complete(self, success: bool = True):
        """
        记录任务完成

        Args:
            success: 任务是否成功
        """
        self.continuous_tasks += 1
        self.last_task_time = datetime.now()

        # 检查是否需要自动冷却
        if self.continuous_tasks >= self.max_continuous_tasks:
            logger.info(f"连续执行 {self.continuous_tasks} 个任务，触发自动冷却")
            self.trigger_cooldown(reason="达到最大连续任务数")

        self._save_state()

    def trigger_cooldown(self, reason: str = "手动触发", duration_minutes: int = None):
        """
        触发冷却

        Args:
            reason: 触发原因
            duration_minutes: 冷却时长（分钟），默认使用配置值
        """
        if not self.enabled:
            logger.info("冷却功能已禁用，跳过")
            return

        duration = duration_minutes or self.duration_minutes
        self.cooldown_until = datetime.now() + timedelta(minutes=duration)

        logger.warning(f"触发冷却: {reason}，冷却 {duration} 分钟，直到 {self.cooldown_until}")
        self._save_state()

    def trigger_risk_cooldown(self, risk_type: str):
        """
        因风险触发冷却

        Args:
            risk_type: 风险类型
        """
        if not self.trigger_on_risk:
            logger.info("风险触发冷却已禁用")
            return

        # 根据风险类型调整冷却时长
        duration_map = {
            'blocked': self.duration_minutes * 2,  # 封禁加倍冷却
            'captcha': self.duration_minutes,
            'rate_limit': self.duration_minutes,
            'login_required': self.duration_minutes // 2,
        }

        duration = duration_map.get(risk_type, self.duration_minutes)
        self.trigger_cooldown(reason=f"检测到风险: {risk_type}", duration_minutes=duration)

    def reset(self):
        """重置冷却状态"""
        self.continuous_tasks = 0
        self.cooldown_until = None
        self._save_state()
        logger.info("冷却状态已重置")

    def wait_for_cooldown(self) -> bool:
        """
        等待冷却结束

        Returns:
            是否成功等待（如果没有在冷却则立即返回 True）
        """
        remaining = self.get_remaining_cooldown()
        if remaining is None:
            return True

        seconds = remaining.total_seconds()
        if seconds <= 0:
            return True

        logger.info(f"等待冷却结束，剩余 {int(seconds)} 秒...")

        try:
            time.sleep(seconds)
            self.cooldown_until = None
            self.continuous_tasks = 0
            self._save_state()
            return True
        except KeyboardInterrupt:
            logger.warning("用户中断等待")
            return False

    def get_status(self) -> dict:
        """
        获取当前状态

        Returns:
            状态字典
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
