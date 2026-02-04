#!/usr/bin/env python3
"""
状态机
管理页面状态转换和流程控制
"""

import logging
from typing import Optional, List, Dict, Callable, Any
from dataclasses import dataclass, field
from enum import Enum

from .states import PageState
from .state_detector import StateDetector, StateMatch

logger = logging.getLogger(__name__)


class TransitionResult(Enum):
    """转换结果"""
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    BLOCKED = "blocked"
    RETRY = "retry"


@dataclass
class Transition:
    """
    状态转换定义
    """
    from_state: PageState
    to_state: PageState
    action: str  # 动作名称
    handler: Optional[Callable] = None  # 转换处理函数
    max_attempts: int = 3
    timeout: int = 30


@dataclass
class StateContext:
    """
    状态上下文

    在状态转换过程中传递的上下文信息。
    """
    current_state: PageState = PageState.UNKNOWN
    previous_state: Optional[PageState] = None
    target_state: Optional[PageState] = None
    attempts: int = 0
    data: Dict[str, Any] = field(default_factory=dict)
    history: List[PageState] = field(default_factory=list)


class StateMachine:
    """
    状态机

    核心功能：
    - 管理页面状态
    - 定义状态转换规则
    - 自动检测当前状态
    - 驱动状态转换
    - 处理异常状态（验证码、弹窗等）
    """

    def __init__(self, ui_locator, platform: str = None):
        """
        初始化状态机

        Args:
            ui_locator: UILocator 实例
            platform: 平台名称
        """
        self.locator = ui_locator
        self.adb = ui_locator.adb
        self.platform = platform

        # 状态检测器
        self.detector = StateDetector(platform)

        # 当前上下文
        self.context = StateContext()

        # 状态转换定义
        self._transitions: Dict[tuple, Transition] = {}

        # 状态处理器
        self._state_handlers: Dict[PageState, Callable] = {}

        # 全局异常状态处理器
        self._exception_handlers: Dict[PageState, Callable] = {}

        # 回调
        self._on_state_change: List[Callable[[PageState, PageState], None]] = []

    def register_transition(
        self,
        from_state: PageState,
        to_state: PageState,
        action: str,
        handler: Callable = None,
        max_attempts: int = 3,
        timeout: int = 30
    ):
        """
        注册状态转换

        Args:
            from_state: 起始状态
            to_state: 目标状态
            action: 动作描述
            handler: 转换处理函数
            max_attempts: 最大尝试次数
            timeout: 超时时间（秒）
        """
        key = (from_state, to_state)
        self._transitions[key] = Transition(
            from_state=from_state,
            to_state=to_state,
            action=action,
            handler=handler,
            max_attempts=max_attempts,
            timeout=timeout
        )
        logger.debug(f"注册转换: {from_state.name} -> {to_state.name} ({action})")

    def register_state_handler(self, state: PageState, handler: Callable):
        """
        注册状态处理器

        当进入该状态时会调用此处理器。

        Args:
            state: 页面状态
            handler: 处理函数
        """
        self._state_handlers[state] = handler

    def register_exception_handler(self, state: PageState, handler: Callable):
        """
        注册异常状态处理器

        用于处理验证码、弹窗等异常状态。

        Args:
            state: 异常状态
            handler: 处理函数，返回 True 表示处理成功
        """
        self._exception_handlers[state] = handler
        logger.debug(f"注册异常处理器: {state.name}")

    def on_state_change(self, callback: Callable[[PageState, PageState], None]):
        """注册状态变化回调"""
        self._on_state_change.append(callback)

    def detect_current_state(self) -> StateMatch:
        """
        检测当前页面状态

        Returns:
            状态匹配结果
        """
        # 获取 UI 层级
        root = self.locator.dump_and_parse()

        # 获取当前包名和 Activity
        package_name = None
        activity_name = None
        focus_info = self.adb.get_current_focus()
        if focus_info:
            parts = focus_info.split('/')
            if len(parts) >= 2:
                package_name = parts[0]
                activity_name = parts[1] if len(parts) > 1 else None

        # 检测状态
        match = self.detector.detect(root, package_name, activity_name)

        # 更新上下文
        if match.state != self.context.current_state:
            self._update_state(match.state)

        return match

    def _update_state(self, new_state: PageState):
        """更新当前状态"""
        old_state = self.context.current_state

        self.context.previous_state = old_state
        self.context.current_state = new_state
        self.context.history.append(new_state)

        # 限制历史记录长度
        if len(self.context.history) > 100:
            self.context.history = self.context.history[-50:]

        logger.info(f"状态变化: {old_state.name} -> {new_state.name}")

        # 触发回调
        for callback in self._on_state_change:
            try:
                callback(old_state, new_state)
            except Exception as e:
                logger.error(f"状态变化回调失败: {e}")

        # 调用状态处理器
        if new_state in self._state_handlers:
            try:
                self._state_handlers[new_state]()
            except Exception as e:
                logger.error(f"状态处理器失败: {e}")

    def get_current_state(self) -> PageState:
        """获取当前状态"""
        return self.context.current_state

    def is_in_state(self, state: PageState) -> bool:
        """检查是否在指定状态"""
        match = self.detect_current_state()
        return match.state == state

    def wait_for_state(
        self,
        target_state: PageState,
        timeout: int = 30,
        poll_interval: float = 1.0
    ) -> bool:
        """
        等待进入目标状态

        Args:
            target_state: 目标状态
            timeout: 超时时间（秒）
            poll_interval: 轮询间隔（秒）

        Returns:
            是否成功进入目标状态
        """
        import time
        start_time = time.time()

        while time.time() - start_time < timeout:
            match = self.detect_current_state()

            if match.state == target_state:
                logger.info(f"已进入目标状态: {target_state.name}")
                return True

            # 检查是否遇到异常状态
            if self._handle_exception_state(match.state):
                continue  # 处理成功，继续等待

            time.sleep(poll_interval)

        logger.warning(f"等待状态 {target_state.name} 超时")
        return False

    def _handle_exception_state(self, state: PageState) -> bool:
        """
        处理异常状态

        Returns:
            是否处理成功
        """
        if state not in self._exception_handlers:
            return False

        handler = self._exception_handlers[state]
        try:
            result = handler()
            if result:
                logger.info(f"异常状态 {state.name} 处理成功")
            return result
        except Exception as e:
            logger.error(f"处理异常状态 {state.name} 失败: {e}")
            return False

    def transition_to(self, target_state: PageState) -> TransitionResult:
        """
        尝试转换到目标状态

        Args:
            target_state: 目标状态

        Returns:
            转换结果
        """
        current = self.context.current_state
        key = (current, target_state)

        if key not in self._transitions:
            logger.error(f"未定义的转换: {current.name} -> {target_state.name}")
            return TransitionResult.FAILED

        transition = self._transitions[key]
        self.context.target_state = target_state
        self.context.attempts = 0

        for attempt in range(1, transition.max_attempts + 1):
            self.context.attempts = attempt
            logger.info(f"执行转换: {transition.action} "
                       f"(第 {attempt}/{transition.max_attempts} 次)")

            try:
                # 执行转换处理器
                if transition.handler:
                    transition.handler()

                # 等待进入目标状态
                if self.wait_for_state(target_state, transition.timeout):
                    return TransitionResult.SUCCESS

                # 检查是否被阻断
                current_match = self.detect_current_state()
                if self.detector.is_risk_state(current_match.state):
                    logger.warning(f"转换被阻断，当前状态: {current_match.state.name}")
                    return TransitionResult.BLOCKED

            except Exception as e:
                logger.error(f"转换执行失败: {e}")

        return TransitionResult.TIMEOUT

    def execute_flow(
        self,
        flow: List[PageState],
        handlers: Dict[PageState, Callable] = None
    ) -> bool:
        """
        执行状态流程

        Args:
            flow: 状态流程列表
            handlers: 各状态的处理器

        Returns:
            是否成功完成流程
        """
        handlers = handlers or {}

        for i, target_state in enumerate(flow):
            logger.info(f"流程步骤 {i + 1}/{len(flow)}: 进入 {target_state.name}")

            # 尝试转换
            result = self.transition_to(target_state)

            if result == TransitionResult.SUCCESS:
                # 执行该状态的处理器
                if target_state in handlers:
                    try:
                        handlers[target_state]()
                    except Exception as e:
                        logger.error(f"状态处理器失败: {e}")
                        return False
            elif result == TransitionResult.BLOCKED:
                logger.error(f"流程在步骤 {i + 1} 被阻断")
                return False
            else:
                logger.error(f"流程在步骤 {i + 1} 失败: {result.value}")
                return False

        logger.info("流程执行完成")
        return True

    def handle_popup(self) -> bool:
        """
        处理当前弹窗

        Returns:
            是否处理成功
        """
        match = self.detect_current_state()

        if not self.detector.is_popup_state(match.state):
            return True  # 没有弹窗

        # 尝试关闭弹窗
        root = self.locator.dump_and_parse()
        if not root:
            return False

        # 查找关闭按钮
        close_patterns = ['关闭', '×', 'X', 'close', '取消', '跳过', 'skip']

        for elem in root.iter():
            text = elem.attrib.get('text', '').lower()
            content_desc = elem.attrib.get('content-desc', '').lower()
            clickable = elem.attrib.get('clickable') == 'true'

            if not clickable:
                continue

            for pattern in close_patterns:
                if pattern.lower() in text or pattern.lower() in content_desc:
                    if self.locator.click_element(elem):
                        logger.info("关闭弹窗成功")
                        import time
                        time.sleep(1)
                        return True

        # 尝试按返回键
        self.adb.press_back()
        import time
        time.sleep(1)

        return True

    def get_context(self) -> StateContext:
        """获取当前上下文"""
        return self.context

    def reset(self):
        """重置状态机"""
        self.context = StateContext()
        logger.info("状态机已重置")
