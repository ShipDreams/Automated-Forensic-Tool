"""
Platform Handler Layer
Implements forensic workflows for various e-commerce platforms.
"""

from .router import PlatformRouter
from .base_handler import BasePlatformHandler
from .taobao_handler import TaobaoHandler

__all__ = [
    'PlatformRouter',
    'BasePlatformHandler',
    'TaobaoHandler',
]
