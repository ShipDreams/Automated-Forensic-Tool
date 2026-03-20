#!/usr/bin/env python3
"""
Task Model
Defines task data structure and status.
"""

import json
import logging
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field, asdict
from pathlib import Path
import uuid

from locales import t

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    """Task status enumeration"""
    PENDING = "pending"      # Pending
    RUNNING = "running"      # Running
    COMPLETED = "completed"  # Completed
    FAILED = "failed"        # Failed
    RETRY = "retry"          # Waiting for retry
    CANCELLED = "cancelled"  # Cancelled


class TaskPriority(Enum):
    """Task priority"""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    URGENT = 4


@dataclass
class TaskResult:
    """Task execution result"""
    success: bool
    message: str = ""
    error: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class Task:
    """
    Task Data Model

    Represents a forensic task, containing product link, platform, status, retry count, etc.
    """
    # Basic info
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    product_url: str = ""
    platform: str = ""  # taobao, jd, douyin, etc.

    # Execution parameters
    video_duration: int = 30
    priority: TaskPriority = TaskPriority.NORMAL

    # Status info
    status: TaskStatus = TaskStatus.PENDING
    retry_count: int = 0
    max_retries: int = 3

    # Time records
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    # Result
    result: Optional[TaskResult] = None
    error_history: List[str] = field(default_factory=list)

    # Evidence name (appended to default timestamp filename when saving recording)
    evidence_name: str = ""

    # Metadata
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary"""
        data = asdict(self)
        data['status'] = self.status.value
        data['priority'] = self.priority.value
        if self.result:
            data['result'] = asdict(self.result)
        return data

    @classmethod
    def from_dict(cls, data: dict) -> 'Task':
        """Create task from dictionary"""
        # Convert enum types
        if 'status' in data and isinstance(data['status'], str):
            data['status'] = TaskStatus(data['status'])
        if 'priority' in data and isinstance(data['priority'], (int, str)):
            if isinstance(data['priority'], str):
                data['priority'] = TaskPriority[data['priority'].upper()]
            else:
                data['priority'] = TaskPriority(data['priority'])

        # Convert TaskResult
        if 'result' in data and isinstance(data['result'], dict):
            data['result'] = TaskResult(**data['result'])

        return cls(**data)

    @classmethod
    def from_url(cls, url: str, **kwargs) -> 'Task':
        """Create task from URL"""
        return cls(product_url=url, **kwargs)

    def mark_running(self):
        """Mark as running"""
        self.status = TaskStatus.RUNNING
        self.started_at = datetime.now().isoformat()

    def mark_completed(self, result: TaskResult = None):
        """Mark as completed"""
        self.status = TaskStatus.COMPLETED
        self.completed_at = datetime.now().isoformat()
        if result:
            self.result = result

    def mark_failed(self, error: str, can_retry: bool = True):
        """Mark as failed"""
        self.error_history.append(f"{datetime.now().isoformat()}: {error}")

        if can_retry and self.retry_count < self.max_retries:
            self.status = TaskStatus.RETRY
            self.retry_count += 1
            logger.info(t('log.task_marked_retry', id=self.id, count=self.retry_count))
        else:
            self.status = TaskStatus.FAILED
            self.completed_at = datetime.now().isoformat()
            self.result = TaskResult(success=False, error=error)
            logger.error(t('log.task_final_failed', id=self.id, error=error))

    def mark_cancelled(self):
        """Mark as cancelled"""
        self.status = TaskStatus.CANCELLED
        self.completed_at = datetime.now().isoformat()

    def can_retry(self) -> bool:
        """Check if can retry"""
        return (
            self.status in [TaskStatus.FAILED, TaskStatus.RETRY] and
            self.retry_count < self.max_retries
        )

    def is_finished(self) -> bool:
        """Check if finished"""
        return self.status in [
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED
        ]

    def save_to_file(self, directory: Path):
        """Save to file"""
        # Choose directory based on status
        if self.status == TaskStatus.PENDING:
            target_dir = directory / 'pending'
        elif self.status == TaskStatus.COMPLETED:
            target_dir = directory / 'completed'
        elif self.status == TaskStatus.FAILED:
            target_dir = directory / 'failed'
        else:
            target_dir = directory / 'pending'

        target_dir.mkdir(parents=True, exist_ok=True)
        file_path = target_dir / f"{self.id}.json"

        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=2)

        logger.debug(t('log.task_saved_to', path=file_path))
        return file_path

    def __str__(self):
        return f"Task({self.id}, {self.platform}, {self.status.value})"
