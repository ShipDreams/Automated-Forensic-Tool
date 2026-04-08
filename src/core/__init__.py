"""
Core Layer
Contains ADB control, UI locator, screen recording and other base capabilities.
"""

from .adb_controller import ADBController
from .ui_locator import UILocator, UIElement
from .recorder import ScreenRecorder
try:
    from .image_locator import ImageLocator
except ImportError:
    ImageLocator = None
from .device_manager import DeviceManager, Device, DeviceStatus, get_device_manager
from .parallel_executor import ParallelExecutor, run_parallel_mode
from .notifier import CrossPlatformNotifier, get_notifier, notify_captcha

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
    'CrossPlatformNotifier',
    'get_notifier',
    'notify_captcha',
    'ImageLocator',
]
