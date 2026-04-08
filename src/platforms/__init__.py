"""
Platform Handler Layer
Implements forensic workflows for various e-commerce platforms.
"""

from .router import PlatformRouter
from .base_handler import BasePlatformHandler
from .taobao_handler import TaobaoHandler
from .taobao_favorites import TaobaoFavorites

__all__ = [
    'PlatformRouter',
    'BasePlatformHandler',
    'TaobaoHandler',
    'TaobaoFavorites',
]
