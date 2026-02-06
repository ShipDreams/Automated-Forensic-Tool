#!/usr/bin/env python3
"""
Task Dispatcher
Responsible for dispatching tasks to multiple devices.
"""

import logging
from typing import List, Dict, Optional
from enum import Enum
from dataclasses import dataclass
from queue import Queue
from threading import Lock

from locales import t
from .task_model import Task

logger = logging.getLogger(__name__)


class DispatchStrategy(Enum):
    """Task dispatch strategy"""
    ROUND_ROBIN = "round_robin"     # Round-robin dispatch
    LOAD_BALANCE = "load_balance"   # Load balance (based on completed tasks)
    RANDOM = "random"               # Random dispatch


@dataclass
class DeviceTaskQueue:
    """Device task queue"""
    device_id: str
    tasks: List[Task]
    completed_count: int = 0
    failed_count: int = 0

    @property
    def pending_count(self) -> int:
        """Pending task count"""
        return len(self.tasks) - self.completed_count - self.failed_count


class TaskDispatcher:
    """
    Task Dispatcher

    Features:
    - Dispatch task list to multiple devices
    - Support multiple dispatch strategies
    - Thread-safe task retrieval
    """

    def __init__(self, strategy: DispatchStrategy = DispatchStrategy.ROUND_ROBIN):
        """
        Initialize task dispatcher.

        Args:
            strategy: Dispatch strategy
        """
        self.strategy = strategy
        self._device_queues: Dict[str, Queue] = {}
        self._device_stats: Dict[str, DeviceTaskQueue] = {}
        self._lock = Lock()
        self._all_tasks: List[Task] = []

    def dispatch(self, tasks: List[Task], device_ids: List[str]) -> Dict[str, List[Task]]:
        """
        Dispatch tasks to devices.

        Args:
            tasks: Task list
            device_ids: Device ID list

        Returns:
            Device task distribution dict {device_id: [tasks]}
        """
        if not tasks:
            logger.warning(t('log.no_tasks_to_dispatch'))
            return {}

        if not device_ids:
            logger.error(t('log.no_devices_available'))
            return {}

        self._all_tasks = tasks
        num_devices = len(device_ids)
        num_tasks = len(tasks)

        logger.info(t('log.dispatch_start', task_count=num_tasks, device_count=num_devices))
        logger.info(t('log.dispatch_strategy', strategy=self.strategy.value))

        # Initialize device queues
        for device_id in device_ids:
            self._device_queues[device_id] = Queue()
            self._device_stats[device_id] = DeviceTaskQueue(device_id=device_id, tasks=[])

        # Dispatch based on strategy
        if self.strategy == DispatchStrategy.ROUND_ROBIN:
            self._dispatch_round_robin(tasks, device_ids)
        elif self.strategy == DispatchStrategy.LOAD_BALANCE:
            self._dispatch_load_balance(tasks, device_ids)
        elif self.strategy == DispatchStrategy.RANDOM:
            self._dispatch_random(tasks, device_ids)

        # Build return result
        result = {}
        for device_id in device_ids:
            result[device_id] = self._device_stats[device_id].tasks
            logger.info(t('log.device_assigned_tasks', device_id=device_id, count=len(result[device_id])))

        return result

    def _dispatch_round_robin(self, tasks: List[Task], device_ids: List[str]):
        """Round-robin dispatch"""
        for i, task in enumerate(tasks):
            device_id = device_ids[i % len(device_ids)]
            self._assign_task(device_id, task)

    def _dispatch_load_balance(self, tasks: List[Task], device_ids: List[str]):
        """
        Load balance dispatch.
        Prioritize devices with fewest tasks.
        """
        for task in tasks:
            # Find device with fewest tasks
            min_device = min(
                device_ids,
                key=lambda d: len(self._device_stats[d].tasks)
            )
            self._assign_task(min_device, task)

    def _dispatch_random(self, tasks: List[Task], device_ids: List[str]):
        """Random dispatch"""
        import random
        for task in tasks:
            device_id = random.choice(device_ids)
            self._assign_task(device_id, task)

    def _assign_task(self, device_id: str, task: Task):
        """Assign task to device"""
        with self._lock:
            self._device_queues[device_id].put(task)
            self._device_stats[device_id].tasks.append(task)

    def get_next_task(self, device_id: str) -> Optional[Task]:
        """
        Get next task for device.

        Args:
            device_id: Device ID

        Returns:
            Task object, None if queue is empty
        """
        queue = self._device_queues.get(device_id)
        if not queue or queue.empty():
            return None

        with self._lock:
            try:
                return queue.get_nowait()
            except:
                return None

    def get_device_tasks(self, device_id: str) -> List[Task]:
        """Get all tasks for device"""
        stats = self._device_stats.get(device_id)
        return stats.tasks if stats else []

    def get_device_queue_size(self, device_id: str) -> int:
        """Get remaining task count in device queue"""
        queue = self._device_queues.get(device_id)
        return queue.qsize() if queue else 0

    def record_task_complete(self, device_id: str, success: bool):
        """
        Record task completion.

        Args:
            device_id: Device ID
            success: Whether successful
        """
        with self._lock:
            if device_id in self._device_stats:
                if success:
                    self._device_stats[device_id].completed_count += 1
                else:
                    self._device_stats[device_id].failed_count += 1

    def get_progress(self) -> Dict[str, any]:
        """
        Get overall progress.

        Returns:
            Progress info dict
        """
        total = len(self._all_tasks)
        completed = sum(s.completed_count for s in self._device_stats.values())
        failed = sum(s.failed_count for s in self._device_stats.values())
        pending = total - completed - failed

        device_progress = {}
        for device_id, stats in self._device_stats.items():
            device_progress[device_id] = {
                'total': len(stats.tasks),
                'completed': stats.completed_count,
                'failed': stats.failed_count,
                'pending': stats.pending_count,
            }

        return {
            'total': total,
            'completed': completed,
            'failed': failed,
            'pending': pending,
            'progress_percent': round(completed / total * 100, 1) if total > 0 else 0,
            'devices': device_progress
        }

    def is_all_done(self) -> bool:
        """Check if all tasks are done"""
        for queue in self._device_queues.values():
            if not queue.empty():
                return False
        return True

    def get_statistics(self) -> Dict[str, any]:
        """Get statistics"""
        return {
            'strategy': self.strategy.value,
            'total_tasks': len(self._all_tasks),
            'devices': len(self._device_queues),
            'progress': self.get_progress()
        }


if __name__ == "__main__":
    # Test code
    logging.basicConfig(level=logging.INFO)

    from .task_model import Task

    # Create test tasks
    tasks = [Task.from_url(f"https://item.taobao.com/item.htm?id={i}") for i in range(10)]
    devices = ["device1", "device2", "device3"]

    # Test round-robin dispatch
    dispatcher = TaskDispatcher(strategy=DispatchStrategy.ROUND_ROBIN)
    result = dispatcher.dispatch(tasks, devices)

    for device_id, device_tasks in result.items():
        print(f"{device_id}: {len(device_tasks)} tasks")
