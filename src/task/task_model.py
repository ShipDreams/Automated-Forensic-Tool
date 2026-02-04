#!/usr/bin/env python3
"""
任务模型
定义任务数据结构和状态
"""

import json
import logging
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, field, asdict
from pathlib import Path
import uuid

logger = logging.getLogger(__name__)


class TaskStatus(Enum):
    """任务状态枚举"""
    PENDING = "pending"      # 待执行
    RUNNING = "running"      # 执行中
    COMPLETED = "completed"  # 已完成
    FAILED = "failed"        # 失败
    RETRY = "retry"          # 等待重试
    CANCELLED = "cancelled"  # 已取消


class TaskPriority(Enum):
    """任务优先级"""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    URGENT = 4


@dataclass
class TaskResult:
    """任务执行结果"""
    success: bool
    message: str = ""
    error: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class Task:
    """
    任务数据模型

    表示一个取证任务，包含商品链接、平台、状态、重试次数等信息。
    """
    # 基本信息
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    product_url: str = ""
    platform: str = ""  # taobao, jd, douyin, etc.

    # 执行参数
    video_duration: int = 30
    priority: TaskPriority = TaskPriority.NORMAL

    # 状态信息
    status: TaskStatus = TaskStatus.PENDING
    retry_count: int = 0
    max_retries: int = 3

    # 时间记录
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    # 结果
    result: Optional[TaskResult] = None
    error_history: List[str] = field(default_factory=list)

    # 元数据
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """转换为字典"""
        data = asdict(self)
        data['status'] = self.status.value
        data['priority'] = self.priority.value
        if self.result:
            data['result'] = asdict(self.result)
        return data

    @classmethod
    def from_dict(cls, data: dict) -> 'Task':
        """从字典创建任务"""
        # 转换枚举类型
        if 'status' in data and isinstance(data['status'], str):
            data['status'] = TaskStatus(data['status'])
        if 'priority' in data and isinstance(data['priority'], (int, str)):
            if isinstance(data['priority'], str):
                data['priority'] = TaskPriority[data['priority'].upper()]
            else:
                data['priority'] = TaskPriority(data['priority'])

        # 转换 TaskResult
        if 'result' in data and isinstance(data['result'], dict):
            data['result'] = TaskResult(**data['result'])

        return cls(**data)

    @classmethod
    def from_url(cls, url: str, **kwargs) -> 'Task':
        """从 URL 创建任务"""
        return cls(product_url=url, **kwargs)

    def mark_running(self):
        """标记为运行中"""
        self.status = TaskStatus.RUNNING
        self.started_at = datetime.now().isoformat()

    def mark_completed(self, result: TaskResult = None):
        """标记为完成"""
        self.status = TaskStatus.COMPLETED
        self.completed_at = datetime.now().isoformat()
        if result:
            self.result = result

    def mark_failed(self, error: str, can_retry: bool = True):
        """标记为失败"""
        self.error_history.append(f"{datetime.now().isoformat()}: {error}")

        if can_retry and self.retry_count < self.max_retries:
            self.status = TaskStatus.RETRY
            self.retry_count += 1
            logger.info(f"任务 {self.id} 标记为重试 (第 {self.retry_count} 次)")
        else:
            self.status = TaskStatus.FAILED
            self.completed_at = datetime.now().isoformat()
            self.result = TaskResult(success=False, error=error)
            logger.error(f"任务 {self.id} 最终失败: {error}")

    def mark_cancelled(self):
        """标记为取消"""
        self.status = TaskStatus.CANCELLED
        self.completed_at = datetime.now().isoformat()

    def can_retry(self) -> bool:
        """是否可以重试"""
        return (
            self.status in [TaskStatus.FAILED, TaskStatus.RETRY] and
            self.retry_count < self.max_retries
        )

    def is_finished(self) -> bool:
        """是否已结束"""
        return self.status in [
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.CANCELLED
        ]

    def save_to_file(self, directory: Path):
        """保存到文件"""
        # 根据状态选择目录
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

        logger.debug(f"任务保存到: {file_path}")
        return file_path

    def __str__(self):
        return f"Task({self.id}, {self.platform}, {self.status.value})"
