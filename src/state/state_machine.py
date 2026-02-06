#!/usr/bin/env python3
"""
State Machine
Manages page state transitions and flow control.
"""

import logging
from typing import Optional, List, Dict, Callable, Any
from dataclasses import dataclass, field
from enum import Enum

from locales import t
from .states import PageState
from .state_detector import StateDetector, StateMatch

logger = logging.getLogger(__name__)


class TransitionResult(Enum):
    """Transition result."""
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    BLOCKED = "blocked"
    RETRY = "retry"


@dataclass
class Transition:
    """
    State transition definition.
    """
    from_state: PageState
    to_state: PageState
    action: str  # Action name
    handler: Optional[Callable] = None  # Transition handler function
    max_attempts: int = 3
    timeout: int = 30


@dataclass
class StateContext:
    """
    State Context

    Context information passed during state transitions.
    """
    current_state: PageState = PageState.UNKNOWN
    previous_state: Optional[PageState] = None
    target_state: Optional[PageState] = None
    attempts: int = 0
    data: Dict[str, Any] = field(default_factory=dict)
    history: List[PageState] = field(default_factory=list)


class StateMachine:
    """
    State Machine

    Core features:
    - Manage page states
    - Define state transition rules
    - Auto-detect current state
    - Drive state transitions
    - Handle exception states (captcha, popups, etc.)
    """

    def __init__(self, ui_locator, platform: str = None):
        """
        Initialize state machine.

        Args:
            ui_locator: UILocator instance
            platform: Platform name
        """
        self.locator = ui_locator
        self.adb = ui_locator.adb
        self.platform = platform

        # State detector
        self.detector = StateDetector(platform)

        # Current context
        self.context = StateContext()

        # State transition definitions
        self._transitions: Dict[tuple, Transition] = {}

        # State handlers
        self._state_handlers: Dict[PageState, Callable] = {}

        # Global exception state handlers
        self._exception_handlers: Dict[PageState, Callable] = {}

        # Callbacks
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
        Register state transition.

        Args:
            from_state: Starting state
            to_state: Target state
            action: Action description
            handler: Transition handler function
            max_attempts: Max attempt count
            timeout: Timeout in seconds
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
        logger.debug(t('log.register_transition',
                      from_state=from_state.name,
                      to_state=to_state.name,
                      action=action))

    def register_state_handler(self, state: PageState, handler: Callable):
        """
        Register state handler.

        Called when entering this state.

        Args:
            state: Page state
            handler: Handler function
        """
        self._state_handlers[state] = handler

    def register_exception_handler(self, state: PageState, handler: Callable):
        """
        Register exception state handler.

        Used to handle captcha, popups, and other exception states.

        Args:
            state: Exception state
            handler: Handler function, returns True if handled successfully
        """
        self._exception_handlers[state] = handler
        logger.debug(t('log.register_exception_handler', state=state.name))

    def on_state_change(self, callback: Callable[[PageState, PageState], None]):
        """Register state change callback."""
        self._on_state_change.append(callback)

    def detect_current_state(self) -> StateMatch:
        """
        Detect current page state.

        Returns:
            State match result
        """
        # Get UI hierarchy
        root = self.locator.dump_and_parse()

        # Get current package name and Activity
        package_name = None
        activity_name = None
        focus_info = self.adb.get_current_focus()
        if focus_info:
            parts = focus_info.split('/')
            if len(parts) >= 2:
                package_name = parts[0]
                activity_name = parts[1] if len(parts) > 1 else None

        # Detect state
        match = self.detector.detect(root, package_name, activity_name)

        # Update context
        if match.state != self.context.current_state:
            self._update_state(match.state)

        return match

    def _update_state(self, new_state: PageState):
        """Update current state."""
        old_state = self.context.current_state

        self.context.previous_state = old_state
        self.context.current_state = new_state
        self.context.history.append(new_state)

        # Limit history length
        if len(self.context.history) > 100:
            self.context.history = self.context.history[-50:]

        logger.info(t('log.state_changed',
                     old_state=old_state.name,
                     new_state=new_state.name))

        # Trigger callbacks
        for callback in self._on_state_change:
            try:
                callback(old_state, new_state)
            except Exception as e:
                logger.error(t('log.state_change_callback_failed', error=e))

        # Call state handler
        if new_state in self._state_handlers:
            try:
                self._state_handlers[new_state]()
            except Exception as e:
                logger.error(t('log.state_handler_failed', error=e))

    def get_current_state(self) -> PageState:
        """Get current state."""
        return self.context.current_state

    def is_in_state(self, state: PageState) -> bool:
        """Check if in specified state."""
        match = self.detect_current_state()
        return match.state == state

    def wait_for_state(
        self,
        target_state: PageState,
        timeout: int = 30,
        poll_interval: float = 1.0
    ) -> bool:
        """
        Wait for target state.

        Args:
            target_state: Target state
            timeout: Timeout in seconds
            poll_interval: Poll interval in seconds

        Returns:
            Whether successfully entered target state
        """
        import time
        start_time = time.time()

        while time.time() - start_time < timeout:
            match = self.detect_current_state()

            if match.state == target_state:
                logger.info(t('log.entered_target_state', state=target_state.name))
                return True

            # Check if encountered exception state
            if self._handle_exception_state(match.state):
                continue  # Handled successfully, continue waiting

            time.sleep(poll_interval)

        logger.warning(t('log.wait_state_timeout', state=target_state.name))
        return False

    def _handle_exception_state(self, state: PageState) -> bool:
        """
        Handle exception state.

        Returns:
            Whether handled successfully
        """
        if state not in self._exception_handlers:
            return False

        handler = self._exception_handlers[state]
        try:
            result = handler()
            if result:
                logger.info(t('log.exception_state_handled', state=state.name))
            return result
        except Exception as e:
            logger.error(t('log.handle_exception_state_failed',
                          state=state.name, error=e))
            return False

    def transition_to(self, target_state: PageState) -> TransitionResult:
        """
        Try to transition to target state.

        Args:
            target_state: Target state

        Returns:
            Transition result
        """
        current = self.context.current_state
        key = (current, target_state)

        if key not in self._transitions:
            logger.error(t('log.undefined_transition',
                          from_state=current.name,
                          to_state=target_state.name))
            return TransitionResult.FAILED

        transition = self._transitions[key]
        self.context.target_state = target_state
        self.context.attempts = 0

        for attempt in range(1, transition.max_attempts + 1):
            self.context.attempts = attempt
            logger.info(t('log.execute_transition',
                         action=transition.action,
                         attempt=attempt,
                         max_attempts=transition.max_attempts))

            try:
                # Execute transition handler
                if transition.handler:
                    transition.handler()

                # Wait for target state
                if self.wait_for_state(target_state, transition.timeout):
                    return TransitionResult.SUCCESS

                # Check if blocked
                current_match = self.detect_current_state()
                if self.detector.is_risk_state(current_match.state):
                    logger.warning(t('log.transition_blocked',
                                    state=current_match.state.name))
                    return TransitionResult.BLOCKED

            except Exception as e:
                logger.error(t('log.transition_execution_failed', error=e))

        return TransitionResult.TIMEOUT

    def execute_flow(
        self,
        flow: List[PageState],
        handlers: Dict[PageState, Callable] = None
    ) -> bool:
        """
        Execute state flow.

        Args:
            flow: State flow list
            handlers: Handlers for each state

        Returns:
            Whether flow completed successfully
        """
        handlers = handlers or {}

        for i, target_state in enumerate(flow):
            logger.info(t('log.flow_step',
                         step=i + 1,
                         total=len(flow),
                         state=target_state.name))

            # Try transition
            result = self.transition_to(target_state)

            if result == TransitionResult.SUCCESS:
                # Execute state handler
                if target_state in handlers:
                    try:
                        handlers[target_state]()
                    except Exception as e:
                        logger.error(t('log.state_handler_failed', error=e))
                        return False
            elif result == TransitionResult.BLOCKED:
                logger.error(t('log.flow_blocked_at_step', step=i + 1))
                return False
            else:
                logger.error(t('log.flow_failed_at_step',
                              step=i + 1, result=result.value))
                return False

        logger.info(t('log.flow_complete'))
        return True

    def handle_popup(self) -> bool:
        """
        Handle current popup.

        Returns:
            Whether handled successfully
        """
        match = self.detect_current_state()

        if not self.detector.is_popup_state(match.state):
            return True  # No popup

        # Try to close popup
        root = self.locator.dump_and_parse()
        if not root:
            return False

        # Find close button
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
                        logger.info(t('log.popup_closed'))
                        import time
                        time.sleep(1)
                        return True

        # Try pressing back
        self.adb.press_back()
        import time
        time.sleep(1)

        return True

    def get_context(self) -> StateContext:
        """Get current context."""
        return self.context

    def reset(self):
        """Reset state machine."""
        self.context = StateContext()
        logger.info(t('log.state_machine_reset'))
