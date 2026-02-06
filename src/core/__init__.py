"""
Core Layer - 核心层
包含 ADB 控制、UI 定位、录屏管理等基础能力
"""

from .adb_controller import ADBController
from .ui_locator import UILocator, UIElement
from .recorder import ScreenRecorder
from .device_manager import DeviceManager, Device, DeviceStatus, get_device_manager
from .parallel_executor import ParallelExecutor, run_parallel_mode

__all__ = [
    'ADBController',
    'UILocator',
    'UIElement',
    'ScreenRecorder',
    'DeviceManager',
    'Device',
    'DeviceStatus',
    'get_device_manager',
    'ParallelExecutor',
    'run_parallel_mode',
]
