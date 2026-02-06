#!/usr/bin/env python3
"""
Device Manager
Responsible for multi-device discovery, status tracking, and health checks.
"""

import subprocess
import logging
import time
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime

from locales import t

logger = logging.getLogger(__name__)


class DeviceStatus(Enum):
    """Device status"""
    ONLINE = "online"           # Online and available
    OFFLINE = "offline"         # Offline
    BUSY = "busy"              # Busy (executing task)
    ERROR = "error"            # Error state
    UNAUTHORIZED = "unauthorized"  # Unauthorized


@dataclass
class Device:
    """Device information"""
    device_id: str
    status: DeviceStatus = DeviceStatus.ONLINE
    brand: str = ""
    model: str = ""
    screen_size: tuple = (0, 0)
    current_task_id: Optional[str] = None
    tasks_completed: int = 0
    tasks_failed: int = 0
    last_active: Optional[str] = None
    error_message: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'device_id': self.device_id,
            'status': self.status.value,
            'brand': self.brand,
            'model': self.model,
            'screen_size': self.screen_size,
            'current_task_id': self.current_task_id,
            'tasks_completed': self.tasks_completed,
            'tasks_failed': self.tasks_failed,
            'last_active': self.last_active,
        }


class DeviceManager:
    """
    Device Manager

    Features:
    - Auto-discover all connected devices
    - Device health check
    - Device status tracking
    - Device pool management
    """

    def __init__(self):
        """Initialize device manager"""
        self._devices: Dict[str, Device] = {}
        self._refresh_interval = 30  # Refresh interval (seconds)
        self._last_refresh: Optional[datetime] = None

    def discover_devices(self) -> List[Device]:
        """
        Discover all connected devices.

        Returns:
            List of devices
        """
        logger.info(t('log.discovering_devices'))

        try:
            result = subprocess.run(
                ["adb", "devices", "-l"],
                capture_output=True,
                text=True,
                timeout=10
            )

            devices = []
            for line in result.stdout.split('\n')[1:]:  # Skip header line
                line = line.strip()
                if not line or 'List of devices' in line:
                    continue

                parts = line.split()
                if len(parts) >= 2:
                    device_id = parts[0]
                    status_str = parts[1]

                    # Parse status
                    if status_str == 'device':
                        status = DeviceStatus.ONLINE
                    elif status_str == 'offline':
                        status = DeviceStatus.OFFLINE
                    elif status_str == 'unauthorized':
                        status = DeviceStatus.UNAUTHORIZED
                    else:
                        status = DeviceStatus.ERROR

                    # Parse extra info
                    model = ""
                    for part in parts[2:]:
                        if part.startswith('model:'):
                            model = part.split(':')[1]

                    device = Device(
                        device_id=device_id,
                        status=status,
                        model=model
                    )
                    devices.append(device)

            logger.info(t('log.devices_discovered', count=len(devices)))
            self._last_refresh = datetime.now()

            # Update internal device list
            for device in devices:
                if device.device_id in self._devices:
                    # Preserve existing statistics
                    existing = self._devices[device.device_id]
                    device.tasks_completed = existing.tasks_completed
                    device.tasks_failed = existing.tasks_failed
                    device.current_task_id = existing.current_task_id
                    # Keep BUSY status if executing task
                    if existing.status == DeviceStatus.BUSY:
                        device.status = DeviceStatus.BUSY
                self._devices[device.device_id] = device

            return devices

        except subprocess.TimeoutExpired:
            logger.error(t('log.discover_devices_timeout'))
            return []
        except Exception as e:
            logger.error(t('log.discover_devices_failed', error=e))
            return []

    def get_device_info(self, device_id: str) -> Optional[Device]:
        """
        Get device detailed information.

        Args:
            device_id: Device ID

        Returns:
            Device information
        """
        if device_id not in self._devices:
            self.discover_devices()

        device = self._devices.get(device_id)
        if not device:
            return None

        # Get more info
        if not device.brand:
            device.brand = self._get_device_property(device_id, "ro.product.brand")
        if not device.model:
            device.model = self._get_device_property(device_id, "ro.product.model")
        if device.screen_size == (0, 0):
            device.screen_size = self._get_screen_size(device_id)

        return device

    def _get_device_property(self, device_id: str, prop: str) -> str:
        """Get device property"""
        try:
            result = subprocess.run(
                ["adb", "-s", device_id, "shell", "getprop", prop],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return ""

    def _get_screen_size(self, device_id: str) -> tuple:
        """Get screen size"""
        try:
            result = subprocess.run(
                ["adb", "-s", device_id, "shell", "wm", "size"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                # Physical size: 1080x2400
                output = result.stdout.strip()
                if ':' in output:
                    size_str = output.split(':')[-1].strip()
                    width, height = map(int, size_str.split('x'))
                    return (width, height)
        except Exception:
            pass
        return (0, 0)

    def check_device_health(self, device_id: str) -> bool:
        """
        Check device health status.

        Args:
            device_id: Device ID

        Returns:
            Whether device is healthy and available
        """
        try:
            result = subprocess.run(
                ["adb", "-s", device_id, "shell", "echo", "health_check"],
                capture_output=True,
                text=True,
                timeout=5
            )

            is_healthy = result.returncode == 0 and "health_check" in result.stdout

            if device_id in self._devices:
                if is_healthy:
                    if self._devices[device_id].status not in [DeviceStatus.BUSY]:
                        self._devices[device_id].status = DeviceStatus.ONLINE
                else:
                    self._devices[device_id].status = DeviceStatus.ERROR

            return is_healthy

        except subprocess.TimeoutExpired:
            logger.warning(t('log.device_health_check_timeout', device_id=device_id))
            if device_id in self._devices:
                self._devices[device_id].status = DeviceStatus.ERROR
            return False
        except Exception as e:
            logger.error(t('log.device_health_check_failed', device_id=device_id, error=e))
            return False

    def get_available_devices(self) -> List[Device]:
        """
        Get all available devices.

        Returns:
            List of available devices
        """
        # Refresh device list
        self.discover_devices()

        available = []
        for device in self._devices.values():
            if device.status == DeviceStatus.ONLINE:
                # Health check
                if self.check_device_health(device.device_id):
                    available.append(device)

        logger.info(t('log.available_devices', count=len(available)))
        return available

    def mark_device_busy(self, device_id: str, task_id: str):
        """
        Mark device as busy.

        Args:
            device_id: Device ID
            task_id: Current task ID
        """
        if device_id in self._devices:
            self._devices[device_id].status = DeviceStatus.BUSY
            self._devices[device_id].current_task_id = task_id
            self._devices[device_id].last_active = datetime.now().isoformat()
            logger.debug(t('log.device_start_task', device_id=device_id, task_id=task_id))

    def mark_device_available(self, device_id: str, success: bool = True):
        """
        Mark device as available.

        Args:
            device_id: Device ID
            success: Whether previous task succeeded
        """
        if device_id in self._devices:
            self._devices[device_id].status = DeviceStatus.ONLINE
            self._devices[device_id].current_task_id = None
            self._devices[device_id].last_active = datetime.now().isoformat()

            if success:
                self._devices[device_id].tasks_completed += 1
            else:
                self._devices[device_id].tasks_failed += 1

            logger.debug(t('log.device_task_complete', device_id=device_id, success=success))

    def mark_device_error(self, device_id: str, error: str):
        """
        Mark device as error state.

        Args:
            device_id: Device ID
            error: Error message
        """
        if device_id in self._devices:
            self._devices[device_id].status = DeviceStatus.ERROR
            self._devices[device_id].error_message = error
            logger.warning(t('log.device_error_state', device_id=device_id, error=error))

    def get_device(self, device_id: str) -> Optional[Device]:
        """Get device"""
        return self._devices.get(device_id)

    def get_all_devices(self) -> List[Device]:
        """Get all devices"""
        return list(self._devices.values())

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get device statistics.

        Returns:
            Statistics dictionary
        """
        total = len(self._devices)
        online = sum(1 for d in self._devices.values() if d.status == DeviceStatus.ONLINE)
        busy = sum(1 for d in self._devices.values() if d.status == DeviceStatus.BUSY)
        error = sum(1 for d in self._devices.values() if d.status == DeviceStatus.ERROR)

        total_completed = sum(d.tasks_completed for d in self._devices.values())
        total_failed = sum(d.tasks_failed for d in self._devices.values())

        return {
            'total_devices': total,
            'online': online,
            'busy': busy,
            'error': error,
            'total_tasks_completed': total_completed,
            'total_tasks_failed': total_failed,
            'devices': [d.to_dict() for d in self._devices.values()]
        }


# Singleton pattern
_device_manager_instance: Optional[DeviceManager] = None


def get_device_manager() -> DeviceManager:
    """Get device manager singleton"""
    global _device_manager_instance
    if _device_manager_instance is None:
        _device_manager_instance = DeviceManager()
    return _device_manager_instance


if __name__ == "__main__":
    # Test code
    logging.basicConfig(level=logging.INFO)

    manager = DeviceManager()
    devices = manager.get_available_devices()

    for device in devices:
        print(f"Device: {device.device_id}")
        info = manager.get_device_info(device.device_id)
        if info:
            print(f"  Brand: {info.brand}")
            print(f"  Model: {info.model}")
            print(f"  Resolution: {info.screen_size}")
