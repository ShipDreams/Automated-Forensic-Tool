#!/usr/bin/env python3
"""
Task Manager
Responsible for task queue management, scheduling, execution, and retry.
"""

import json
import logging
import time
from typing import Optional, List, Callable, Dict, Any
from pathlib import Path
from datetime import datetime
from queue import PriorityQueue
from dataclasses import dataclass, field

from locales import t
from .task_model import Task, TaskStatus, TaskResult, TaskPriority
from .task_loader import TaskLoader

logger = logging.getLogger(__name__)


@dataclass(order=True)
class PrioritizedTask:
    """Prioritized task (for priority queue)"""
    priority: int
    task: Task = field(compare=False)


class TaskManager:
    """
    Task Manager

    Core features:
    - Task queue management (with priority support)
    - Task scheduling and execution
    - Failure retry (max 3 times)
    - Task status persistence
    - Execution statistics
    """

    def __init__(
        self,
        tasks_dir: str = None,
        max_retries: int = 3,
        retry_delay: int = 60
    ):
        """
        Initialize task manager.

        Args:
            tasks_dir: Tasks directory path
            max_retries: Maximum retry count
            retry_delay: Retry delay (seconds)
        """
        self.loader = TaskLoader(tasks_dir)
        self.tasks_dir = self.loader.tasks_dir
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        # Source file path (for report)
        self.source_file: Optional[str] = None

        # Task queue
        self._queue: PriorityQueue = PriorityQueue()
        self._all_tasks: Dict[str, Task] = {}

        # Executor (injected externally)
        self._executor: Optional[Callable[[Task], TaskResult]] = None

        # Callbacks
        self._on_task_start: List[Callable[[Task], None]] = []
        self._on_task_complete: List[Callable[[Task, TaskResult], None]] = []
        self._on_task_failed: List[Callable[[Task, str], None]] = []

        # Statistics
        self.stats = {
            'total': 0,
            'completed': 0,
            'failed': 0,
            'retried': 0,
            'start_time': None,
            'end_time': None,
        }

    def set_executor(self, executor: Callable[[Task], TaskResult]):
        """
        Set task executor.

        Args:
            executor: Execution function, takes Task, returns TaskResult
        """
        self._executor = executor

    def add_task(self, task: Task) -> str:
        """
        Add task to queue.

        Args:
            task: Task object

        Returns:
            Task ID
        """
        # Set default retry count
        task.max_retries = self.max_retries

        # Add to queue (negate priority because PriorityQueue is min-heap)
        priority = -task.priority.value
        self._queue.put(PrioritizedTask(priority=priority, task=task))

        # Save reference
        self._all_tasks[task.id] = task

        logger.info(t('log.task_added', id=task.id, url=task.product_url[:50]))
        return task.id

    def add_tasks(self, tasks: List[Task]) -> List[str]:
        """Batch add tasks"""
        return [self.add_task(task) for task in tasks]

    def add_url(self, url: str, **params) -> str:
        """
        Add task by URL.

        Args:
            url: Product link
            **params: Other task parameters

        Returns:
            Task ID
        """
        task = Task.from_url(url, **params)
        return self.add_task(task)

    def add_urls(self, urls: List[str], **params) -> List[str]:
        """Batch add URLs"""
        return [self.add_url(url, **params) for url in urls]

    def load_tasks_from_file(self, file_path: str) -> int:
        """
        Load tasks from file.

        Args:
            file_path: File path

        Returns:
            Number of tasks loaded
        """
        path = Path(file_path)
        self.source_file = str(path.resolve())  # Record source file path

        if path.suffix == '.json':
            tasks = self.loader.load_from_json(file_path)
        elif path.suffix == '.csv':
            tasks = self.loader.load_from_csv(file_path)
        elif path.suffix == '.txt':
            tasks = self.loader.load_from_text(file_path)
        else:
            logger.error(t('log.unsupported_file_format', suffix=path.suffix))
            return 0

        self.add_tasks(tasks)
        return len(tasks)

    def load_tasks_from_db(self, db_loader, batch_size: int = 100) -> int:
        """
        Load tasks from database.

        Args:
            db_loader: DBTaskLoader instance
            batch_size: Maximum number of tasks to load

        Returns:
            Number of tasks loaded
        """
        tasks = db_loader.load_batch(batch_size)
        self.add_tasks(tasks)
        return len(tasks)

    def load_pending_tasks(self) -> int:
        """
        Load all pending tasks.

        Returns:
            Number of tasks loaded
        """
        tasks = self.loader.load_pending_tasks()
        self.add_tasks(tasks)
        return len(tasks)

    def get_next_task(self) -> Optional[Task]:
        """
        Get next task to execute.

        Returns:
            Task object, None if queue is empty
        """
        if self._queue.empty():
            return None

        prioritized = self._queue.get()
        return prioritized.task

    def peek_next_task(self) -> Optional[Task]:
        """Peek next task (without removing from queue)"""
        if self._queue.empty():
            return None
        # PriorityQueue doesn't support peek, simple implementation here
        prioritized = self._queue.get()
        self._queue.put(prioritized)
        return prioritized.task

    def execute_task(self, task: Task) -> TaskResult:
        """
        Execute single task.

        Args:
            task: Task object

        Returns:
            Execution result
        """
        if not self._executor:
            raise RuntimeError(t('log.executor_not_set'))

        # Mark as running
        task.mark_running()

        # Trigger callbacks
        for callback in self._on_task_start:
            try:
                callback(task)
            except Exception as e:
                logger.error(t('log.task_start_callback_failed', error=e))

        try:
            # Execute task
            logger.info(t('log.task_started', id=task.id))
            result = self._executor(task)

            if result.success:
                task.mark_completed(result)
                self.stats['completed'] += 1
                logger.info(t('log.task_completed', id=task.id))

                # Trigger complete callback
                for callback in self._on_task_complete:
                    try:
                        callback(task, result)
                    except Exception as e:
                        logger.error(t('log.task_complete_callback_failed', error=e))
            else:
                self._handle_task_failure(task, result.error or "Unknown error")

        except Exception as e:
            logger.error(t('log.task_execution_error', error=e), exc_info=True)
            self._handle_task_failure(task, str(e))
            result = TaskResult(success=False, error=str(e))

        return result

    def _handle_task_failure(self, task: Task, error: str):
        """Handle task failure"""
        # Determine if can retry
        can_retry = task.retry_count < self.max_retries

        task.mark_failed(error, can_retry=can_retry)

        if task.status == TaskStatus.RETRY:
            # Add back to queue for retry
            self.stats['retried'] += 1
            logger.warning(t('log.task_retry_scheduled', id=task.id, delay=self.retry_delay,
                           count=task.retry_count, max=self.max_retries))

            # Lower priority (retry tasks have lower priority)
            task.priority = TaskPriority.LOW
            self._queue.put(PrioritizedTask(
                priority=-task.priority.value + task.retry_count,
                task=task
            ))
        else:
            self.stats['failed'] += 1

            # Trigger failure callback
            for callback in self._on_task_failed:
                try:
                    callback(task, error)
                except Exception as e:
                    logger.error(t('log.task_failed_callback_error', error=e))

    def run_all(self, delay_between_tasks: int = 5) -> Dict[str, Any]:
        """
        Execute all tasks in queue.

        Args:
            delay_between_tasks: Delay between tasks (seconds)

        Returns:
            Execution statistics
        """
        self.stats['start_time'] = datetime.now().isoformat()
        self.stats['total'] = self._queue.qsize()

        logger.info(t('log.batch_execution_start', count=self.stats['total']))

        while not self._queue.empty():
            task = self.get_next_task()
            if not task:
                break

            try:
                self.execute_task(task)
            except Exception as e:
                logger.error(t('log.task_execution_error', error=e))

            # Delay between tasks
            if not self._queue.empty():
                logger.info(t('log.waiting_next_task', seconds=delay_between_tasks))
                time.sleep(delay_between_tasks)

        self.stats['end_time'] = datetime.now().isoformat()

        # Print statistics
        self._print_stats()

        return self.stats

    def run_single(self) -> Optional[TaskResult]:
        """
        Execute single task.

        Returns:
            Execution result, None if queue is empty
        """
        task = self.get_next_task()
        if not task:
            return None

        return self.execute_task(task)

    def _print_stats(self):
        """Print execution statistics"""
        logger.info("=" * 50)
        logger.info(t('log.task_stats_title'))
        logger.info("=" * 50)
        logger.info(t('log.task_stat_total', count=self.stats['total']))
        logger.info(t('log.task_stat_completed', count=self.stats['completed']))
        logger.info(t('log.task_stat_failed', count=self.stats['failed']))
        logger.info(t('log.task_stat_retried', count=self.stats['retried']))
        if self.stats['start_time'] and self.stats['end_time']:
            start = datetime.fromisoformat(self.stats['start_time'])
            end = datetime.fromisoformat(self.stats['end_time'])
            duration = end - start
            logger.info(t('log.task_stat_duration', duration=duration))
        logger.info("=" * 50)

    # ==================== Callback Registration ====================

    def on_task_start(self, callback: Callable[[Task], None]):
        """Register task start callback"""
        self._on_task_start.append(callback)

    def on_task_complete(self, callback: Callable[[Task, TaskResult], None]):
        """Register task complete callback"""
        self._on_task_complete.append(callback)

    def on_task_failed(self, callback: Callable[[Task, str], None]):
        """Register task failed callback"""
        self._on_task_failed.append(callback)

    # ==================== Status Query ====================

    def get_task(self, task_id: str) -> Optional[Task]:
        """Get task"""
        return self._all_tasks.get(task_id)

    def get_queue_size(self) -> int:
        """Get queue size"""
        return self._queue.qsize()

    def is_empty(self) -> bool:
        """Check if queue is empty"""
        return self._queue.empty()

    def get_all_tasks(self) -> List[Task]:
        """Get all tasks"""
        return list(self._all_tasks.values())

    def get_tasks_by_status(self, status: TaskStatus) -> List[Task]:
        """Get tasks by status"""
        return [t for t in self._all_tasks.values() if t.status == status]

    def cancel_task(self, task_id: str) -> bool:
        """Cancel task"""
        task = self._all_tasks.get(task_id)
        if not task:
            return False

        if task.status == TaskStatus.RUNNING:
            logger.warning(t('log.cannot_cancel_running'))
            return False

        task.mark_cancelled()
        return True

    def clear_queue(self):
        """Clear queue"""
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except:
                break
        logger.info(t('log.queue_cleared'))

    def reset_stats(self):
        """Reset statistics"""
        self.stats = {
            'total': 0,
            'completed': 0,
            'failed': 0,
            'retried': 0,
            'start_time': None,
            'end_time': None,
        }

    # ==================== Report Generation ====================

    def generate_report(self, output_dir: str = None) -> str:
        """
        Generate batch task summary report.

        Args:
            output_dir: Report output directory, defaults to project root's reports/

        Returns:
            Report file path
        """
        # Determine output directory
        if output_dir:
            reports_dir = Path(output_dir)
        else:
            # Default to project root's reports/
            reports_dir = Path(__file__).parent.parent.parent / 'reports'

        reports_dir.mkdir(parents=True, exist_ok=True)

        # Generate report filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        report_file = reports_dir / f'batch_report_{timestamp}.json'

        # Calculate duration
        duration_seconds = 0
        if self.stats['start_time'] and self.stats['end_time']:
            start = datetime.fromisoformat(self.stats['start_time'])
            end = datetime.fromisoformat(self.stats['end_time'])
            duration_seconds = int((end - start).total_seconds())

        # Count tasks by status
        pending_count = len([t for t in self._all_tasks.values()
                            if t.status == TaskStatus.PENDING])

        # Build task list (simplified fields)
        tasks_list = []
        for task in self._all_tasks.values():
            task_info = {
                'id': task.id,
                'url': task.product_url,
                'status': task.status.value,
            }

            # Add time info (if available)
            if task.started_at:
                task_info['started_at'] = task.started_at
            if task.completed_at:
                task_info['completed_at'] = task.completed_at

            # Add error info (if failed)
            if task.status == TaskStatus.FAILED and task.result and task.result.error:
                task_info['error'] = task.result.error

            tasks_list.append(task_info)

        # Build report
        report = {
            'report_time': datetime.now().isoformat(),
            'source_file': self.source_file,
            'summary': {
                'total': self.stats['total'],
                'completed': self.stats['completed'],
                'failed': self.stats['failed'],
                'pending': pending_count,
                'duration_seconds': duration_seconds,
            },
            'tasks': tasks_list
        }

        # Write to file
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)

        logger.info(t('log.report_generated', path=report_file))
        return str(report_file)
