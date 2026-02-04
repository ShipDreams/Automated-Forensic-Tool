"""
Platform Handler Layer - 平台处理器层
负责各平台的取证流程实现
"""

from .router import PlatformRouter
from .base_handler import BasePlatformHandler
from .taobao_handler import TaobaoHandler

__all__ = [
    'PlatformRouter',
    'BasePlatformHandler',
    'TaobaoHandler',
]
