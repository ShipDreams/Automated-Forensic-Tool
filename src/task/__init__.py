"""
Task Layer
Responsible for task queue, scheduling, retry, and status management.
"""

from .task_manager import TaskManager
from .task_model import Task, TaskStatus, TaskResult, TaskPriority
from .task_loader import TaskLoader
from .task_dispatcher import TaskDispatcher, DispatchStrategy
from .shop_grouper import ShopGrouper, EvidenceGroup
from .grouped_executor import GroupedExecutor
try:
    from .db_connector import DatabaseConnector
    from .db_task_loader import DBTaskLoader
except ImportError:
    DatabaseConnector = None
    DBTaskLoader = None

__all__ = [
    'TaskManager',
    'Task',
    'TaskStatus',
    'TaskResult',
    'TaskPriority',
    'TaskLoader',
    'TaskDispatcher',
    'DispatchStrategy',
    'ShopGrouper',
    'EvidenceGroup',
    'GroupedExecutor',
    'DatabaseConnector',
    'DBTaskLoader',
]
