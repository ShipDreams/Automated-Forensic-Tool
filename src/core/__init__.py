"""
Core Layer - 核心层
包含 ADB 控制、UI 定位、录屏管理等基础能力
"""

from .adb_controller import ADBController
from .ui_locator import UILocator, UIElement
from .recorder import ScreenRecorder

__all__ = ['ADBController', 'UILocator', 'UIElement', 'ScreenRecorder']
