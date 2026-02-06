"""
State Machine Layer
Responsible for page state recognition and flow control.
"""

from .state_machine import StateMachine, StateContext, TransitionResult, Transition
from .state_detector import StateDetector, StateMatch
from .states import (
    PageState,
    StateFeature,
    StateDefinition,
    get_all_states_for_platform,
    COMMON_STATES,
    TAOBAO_STATES,
    JD_STATES,
    DOUYIN_STATES,
)

__all__ = [
    # State Machine
    'StateMachine',
    'StateContext',
    'TransitionResult',
    'Transition',

    # State Detection
    'StateDetector',
    'StateMatch',

    # State Definitions
    'PageState',
    'StateFeature',
    'StateDefinition',
    'get_all_states_for_platform',
    'COMMON_STATES',
    'TAOBAO_STATES',
    'JD_STATES',
    'DOUYIN_STATES',
]
