#!/usr/bin/env python3
"""
AntiBot 主模块
整合人类行为模拟、风险检测、冷却管理
"""

import json
import logging
from pathlib import Path
from typing import Optional, List, Callable

from .human_simulator import HumanSimulator
from .risk_detector import RiskDetector, RiskSignal, RiskType
from .cooldown import CooldownManager

logger = logging.getLogger(__name__)


class AntiBot:
    """
    AntiBot 防风控管理器

    核心功能：
    - 统一管理人类行为模拟
    - 统一管理风险检测
    - 统一管理冷却机制
    - 提供便捷的装饰器和上下文管理器
    """

    def __init__(self, config_path: str = None):
        """
        初始化 AntiBot

        Args:
            config_path: 配置文件路径，默认使用 config/antibot.json
        """
        self.config = self._load_config(config_path)

        # 初始化子模块
        self.human = HumanSimulator(self.config.get('human_behavior', {}))
        self.detector = RiskDetector(self.config.get('risk_detection', {}))
        self.cooldown = CooldownManager(self.config.get('cooldown', {}))

        # 风险回调
        self._risk_callbacks: List[Callable[[RiskSignal], None]] = []

    def _load_config(self, config_path: str = None) -> dict:
        """加载配置文件"""
        if config_path:
            path = Path(config_path)
        else:
            path = Path(__file__).parent.parent.parent / 'config' / 'antibot.json'

        if not path.exists():
            logger.warning(f"配置文件不存在: {path}，使用默认配置")
            return {}

        try:
            with open(path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            logger.info(f"加载 AntiBot 配置: {path}")
            return config
        except Exception as e:
            logger.error(f"加载配置失败: {e}")
            return {}

    # ==================== 人类行为模拟 ====================

    def sleep(self, min_ms: int = None, max_ms: int = None) -> float:
        """随机延迟"""
        return self.human.random_sleep(min_ms, max_ms)

    def sleep_after_click(self) -> float:
        """点击后随机延迟"""
        return self.human.sleep_after_click()

    def random_offset(self, x: int, y: int, max_offset: int = 10):
        """给坐标添加随机偏移"""
        return self.human.apply_offset_to_point(x, y, max_offset)

    def maybe_random_action(self, adb_controller) -> bool:
        """可能执行随机浏览动作"""
        return self.human.execute_random_action(adb_controller)

    # ==================== 风险检测 ====================

    def check_risk(self, ui_root) -> List[RiskSignal]:
        """
        检测当前页面风险

        Args:
            ui_root: UI 层级树根节点

        Returns:
            风险信号列表
        """
        signals = self.detector.detect_from_ui_tree(ui_root)

        # 处理高风险信号
        for signal in signals:
            if signal.confidence >= 0.6:
                logger.warning(f"检测到风险: {signal.risk_type.value} "
                             f"(置信度: {signal.confidence:.2f}) - {signal.details}")

                # 触发回调
                for callback in self._risk_callbacks:
                    try:
                        callback(signal)
                    except Exception as e:
                        logger.error(f"风险回调执行失败: {e}")

                # 根据风险类型触发冷却
                if signal.risk_type in [RiskType.BLOCKED, RiskType.RATE_LIMIT]:
                    self.cooldown.trigger_risk_cooldown(signal.risk_type.value)

        return signals

    def is_safe(self, ui_root, threshold: float = 0.6) -> bool:
        """
        检查当前页面是否安全

        Args:
            ui_root: UI 层级树根节点
            threshold: 风险阈值

        Returns:
            是否安全
        """
        signals = self.check_risk(ui_root)
        return self.detector.is_safe(signals, threshold)

    def detect_captcha(self, ui_root) -> Optional[str]:
        """
        检测验证码类型

        Args:
            ui_root: UI 层级树根节点

        Returns:
            验证码类型或 None
        """
        return self.detector.detect_captcha_type(ui_root)

    def on_risk(self, callback: Callable[[RiskSignal], None]):
        """
        注册风险回调

        Args:
            callback: 回调函数，接收 RiskSignal 参数
        """
        self._risk_callbacks.append(callback)

    # ==================== 冷却管理 ====================

    def can_proceed(self) -> bool:
        """检查是否可以继续执行"""
        return self.cooldown.can_execute_task()

    def wait_if_cooling(self) -> bool:
        """如果在冷却中则等待"""
        return self.cooldown.wait_for_cooldown()

    def record_task_done(self, success: bool = True):
        """记录任务完成"""
        self.cooldown.record_task_complete(success)

    def trigger_pause(self, reason: str = "手动暂停", minutes: int = None):
        """触发暂停/冷却"""
        self.cooldown.trigger_cooldown(reason, minutes)

    def get_cooldown_status(self) -> dict:
        """获取冷却状态"""
        return self.cooldown.get_status()

    # ==================== 便捷方法 ====================

    def safe_click(self, adb_controller, x: int, y: int) -> bool:
        """
        安全点击（带随机偏移和延迟）

        Args:
            adb_controller: ADBController 实例
            x: 目标 x 坐标
            y: 目标 y 坐标

        Returns:
            是否成功
        """
        # 添加随机偏移
        new_x, new_y = self.random_offset(x, y)

        # 执行点击
        result = adb_controller.tap(new_x, new_y)

        # 点击后延迟
        self.sleep_after_click()

        return result

    def safe_input(self, adb_controller, text: str) -> bool:
        """
        安全输入文本（带人类化延迟）

        Args:
            adb_controller: ADBController 实例
            text: 要输入的文本

        Returns:
            是否成功
        """
        # 输入前短暂延迟
        self.sleep(300, 800)

        # 执行输入
        result = adb_controller.input_text(text)

        # 输入后延迟
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
        安全滚动（带随机参数）

        Args:
            adb_controller: ADBController 实例
            direction: 滚动方向

        Returns:
            是否成功
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
        操作前检查

        适合在每个关键操作前调用，检查风险和冷却状态。

        Args:
            ui_locator: UILocator 实例

        Returns:
            是否可以继续
        """
        # 检查冷却
        if not self.can_proceed():
            remaining = self.cooldown.get_remaining_cooldown()
            logger.warning(f"正在冷却中，剩余 {remaining}")
            return False

        # 检查风险
        root = ui_locator.dump_and_parse()
        if root and not self.is_safe(root):
            logger.warning("检测到风险，建议暂停")
            return False

        # 可能执行随机动作
        # self.maybe_random_action(ui_locator.adb)

        return True
