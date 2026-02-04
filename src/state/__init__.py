"""
State Machine Layer - 状态机层
负责页面状态识别和流程驱动
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
    # 状态机
    'StateMachine',
    'StateContext',
    'TransitionResult',
    'Transition',

    # 状态检测
    'StateDetector',
    'StateMatch',

    # 状态定义
    'PageState',
    'StateFeature',
    'StateDefinition',
    'get_all_states_for_platform',
    'COMMON_STATES',
    'TAOBAO_STATES',
    'JD_STATES',
    'DOUYIN_STATES',
]
