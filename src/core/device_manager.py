#!/usr/bin/env python3
"""
设备管理器
负责多设备发现、状态跟踪、健康检查
"""

import subprocess
import logging
import time
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime

logger = logging.getLogger(__name__)


class DeviceStatus(Enum):
    """设备状态"""
    ONLINE = "online"           # 在线可用
    OFFLINE = "offline"         # 离线
    BUSY = "busy"              # 忙碌（正在执行任务）
    ERROR = "error"            # 错误状态
    UNAUTHORIZED = "unauthorized"  # 未授权


@dataclass
class Device:
    """设备信息"""
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
        """转换为字典"""
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
    设备管理器

    功能：
    - 自动发现所有已连接设备
    - 设备健康检查
    - 设备状态跟踪
    - 设备池管理
    """

    def __init__(self):
        """初始化设备管理器"""
        self._devices: Dict[str, Device] = {}
        self._refresh_interval = 30  # 刷新间隔（秒）
        self._last_refresh: Optional[datetime] = None

    def discover_devices(self) -> List[Device]:
        """
        发现所有已连接设备

        Returns:
            设备列表
        """
        logger.info("正在发现设备...")

        try:
            result = subprocess.run(
                ["adb", "devices", "-l"],
                capture_output=True,
                text=True,
                timeout=10
            )

            devices = []
            for line in result.stdout.split('\n')[1:]:  # 跳过标题行
                line = line.strip()
                if not line or 'List of devices' in line:
                    continue

                parts = line.split()
                if len(parts) >= 2:
                    device_id = parts[0]
                    status_str = parts[1]

                    # 解析状态
                    if status_str == 'device':
                        status = DeviceStatus.ONLINE
                    elif status_str == 'offline':
                        status = DeviceStatus.OFFLINE
                    elif status_str == 'unauthorized':
                        status = DeviceStatus.UNAUTHORIZED
                    else:
                        status = DeviceStatus.ERROR

                    # 解析额外信息
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

            logger.info(f"发现 {len(devices)} 台设备")
            self._last_refresh = datetime.now()

            # 更新内部设备列表
            for device in devices:
                if device.device_id in self._devices:
                    # 保留已有的统计信息
                    existing = self._devices[device.device_id]
                    device.tasks_completed = existing.tasks_completed
                    device.tasks_failed = existing.tasks_failed
                    device.current_task_id = existing.current_task_id
                    # 如果正在执行任务，保持 BUSY 状态
                    if existing.status == DeviceStatus.BUSY:
                        device.status = DeviceStatus.BUSY
                self._devices[device.device_id] = device

            return devices

        except subprocess.TimeoutExpired:
            logger.error("发现设备超时")
            return []
        except Exception as e:
            logger.error(f"发现设备失败: {e}")
            return []

    def get_device_info(self, device_id: str) -> Optional[Device]:
        """
        获取设备详细信息

        Args:
            device_id: 设备 ID

        Returns:
            设备信息
        """
        if device_id not in self._devices:
            self.discover_devices()

        device = self._devices.get(device_id)
        if not device:
            return None

        # 获取更多信息
        if not device.brand:
            device.brand = self._get_device_property(device_id, "ro.product.brand")
        if not device.model:
            device.model = self._get_device_property(device_id, "ro.product.model")
        if device.screen_size == (0, 0):
            device.screen_size = self._get_screen_size(device_id)

        return device

    def _get_device_property(self, device_id: str, prop: str) -> str:
        """获取设备属性"""
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
        """获取屏幕尺寸"""
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
        检查设备健康状态

        Args:
            device_id: 设备 ID

        Returns:
            设备是否健康可用
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
            logger.warning(f"设备 {device_id} 健康检查超时")
            if device_id in self._devices:
                self._devices[device_id].status = DeviceStatus.ERROR
            return False
        except Exception as e:
            logger.error(f"设备 {device_id} 健康检查失败: {e}")
            return False

    def get_available_devices(self) -> List[Device]:
        """
        获取所有可用设备

        Returns:
            可用设备列表
        """
        # 刷新设备列表
        self.discover_devices()

        available = []
        for device in self._devices.values():
            if device.status == DeviceStatus.ONLINE:
                # 健康检查
                if self.check_device_health(device.device_id):
                    available.append(device)

        logger.info(f"可用设备: {len(available)} 台")
        return available

    def mark_device_busy(self, device_id: str, task_id: str):
        """
        标记设备为忙碌

        Args:
            device_id: 设备 ID
            task_id: 当前任务 ID
        """
        if device_id in self._devices:
            self._devices[device_id].status = DeviceStatus.BUSY
            self._devices[device_id].current_task_id = task_id
            self._devices[device_id].last_active = datetime.now().isoformat()
            logger.debug(f"设备 {device_id} 开始执行任务 {task_id}")

    def mark_device_available(self, device_id: str, success: bool = True):
        """
        标记设备为可用

        Args:
            device_id: 设备 ID
            success: 上一个任务是否成功
        """
        if device_id in self._devices:
            self._devices[device_id].status = DeviceStatus.ONLINE
            self._devices[device_id].current_task_id = None
            self._devices[device_id].last_active = datetime.now().isoformat()

            if success:
                self._devices[device_id].tasks_completed += 1
            else:
                self._devices[device_id].tasks_failed += 1

            logger.debug(f"设备 {device_id} 任务完成，成功={success}")

    def mark_device_error(self, device_id: str, error: str):
        """
        标记设备为错误状态

        Args:
            device_id: 设备 ID
            error: 错误信息
        """
        if device_id in self._devices:
            self._devices[device_id].status = DeviceStatus.ERROR
            self._devices[device_id].error_message = error
            logger.warning(f"设备 {device_id} 进入错误状态: {error}")

    def get_device(self, device_id: str) -> Optional[Device]:
        """获取设备"""
        return self._devices.get(device_id)

    def get_all_devices(self) -> List[Device]:
        """获取所有设备"""
        return list(self._devices.values())

    def get_statistics(self) -> Dict[str, Any]:
        """
        获取设备统计信息

        Returns:
            统计信息字典
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


# 单例模式
_device_manager_instance: Optional[DeviceManager] = None


def get_device_manager() -> DeviceManager:
    """获取设备管理器单例"""
    global _device_manager_instance
    if _device_manager_instance is None:
        _device_manager_instance = DeviceManager()
    return _device_manager_instance


if __name__ == "__main__":
    # 测试代码
    logging.basicConfig(level=logging.INFO)

    manager = DeviceManager()
    devices = manager.get_available_devices()

    for device in devices:
        print(f"设备: {device.device_id}")
        info = manager.get_device_info(device.device_id)
        if info:
            print(f"  品牌: {info.brand}")
            print(f"  型号: {info.model}")
            print(f"  分辨率: {info.screen_size}")
