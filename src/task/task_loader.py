#!/usr/bin/env python3
"""
Task Loader
Load tasks from files or other sources.
"""

import json
import logging
from pathlib import Path
from typing import List, Optional, Generator
import csv

from locales import t
from .task_model import Task, TaskStatus

logger = logging.getLogger(__name__)


class TaskLoader:
    """
    Task Loader

    Supports loading tasks from multiple sources:
    - JSON file (single task)
    - JSON file (task list)
    - CSV file
    - Text file (one URL per line)
    - Directory (batch load)
    """

    def __init__(self, tasks_dir: str = None):
        """
        Initialize task loader.

        Args:
            tasks_dir: Tasks directory path, defaults to tasks/
        """
        if tasks_dir:
            self.tasks_dir = Path(tasks_dir)
        else:
            self.tasks_dir = Path(__file__).parent.parent.parent / 'tasks'

    def load_from_json(self, file_path: str) -> List[Task]:
        """
        Load tasks from JSON file.

        Args:
            file_path: JSON file path

        Returns:
            Task list
        """
        path = Path(file_path)
        if not path.exists():
            logger.error(t('log.file_not_found', path=file_path))
            return []

        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # Determine if single task or task list
            if isinstance(data, list):
                tasks = [Task.from_dict(item) for item in data]
            elif isinstance(data, dict):
                if 'tasks' in data:
                    tasks = [Task.from_dict(item) for item in data['tasks']]
                else:
                    tasks = [Task.from_dict(data)]
            else:
                logger.error(t('log.invalid_json_format', path=file_path))
                return []

            logger.info(t('log.tasks_loaded_count', path=file_path, count=len(tasks)))
            return tasks

        except json.JSONDecodeError as e:
            logger.error(t('log.json_parse_error', error=e))
            return []
        except Exception as e:
            logger.error(t('log.task_load_error', error=e))
            return []

    def load_from_csv(self, file_path: str) -> List[Task]:
        """
        Load tasks from CSV file.

        CSV format:
        - Must have 'url' or 'product_url' column
        - Optional columns: platform, video_duration, priority

        Args:
            file_path: CSV file path

        Returns:
            Task list
        """
        path = Path(file_path)
        if not path.exists():
            logger.error(t('log.file_not_found', path=file_path))
            return []

        tasks = []
        try:
            with open(path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)

                for row in reader:
                    # Get URL
                    url = row.get('url') or row.get('product_url') or row.get('URL')
                    if not url:
                        continue

                    # Create task
                    task_data = {
                        'product_url': url.strip(),
                        'platform': row.get('platform', ''),
                        'video_duration': int(row.get('video_duration', 30)),
                        'evidence_name': row.get('evidence_name', '').strip(),
                        'shop_name': row.get('shop_name', row.get('store_name', '')).strip(),
                    }

                    # Handle priority
                    if 'priority' in row:
                        try:
                            task_data['priority'] = int(row['priority'])
                        except ValueError:
                            pass

                    tasks.append(Task.from_dict(task_data))

            logger.info(t('log.tasks_loaded_count', path=file_path, count=len(tasks)))
            return tasks

        except Exception as e:
            logger.error(t('log.csv_load_error', error=e))
            return []

    def load_from_text(self, file_path: str) -> List[Task]:
        """
        Load tasks from text file (one URL per line).

        Args:
            file_path: Text file path

        Returns:
            Task list
        """
        path = Path(file_path)
        if not path.exists():
            logger.error(t('log.file_not_found', path=file_path))
            return []

        tasks = []
        try:
            with open(path, 'r', encoding='utf-8') as f:
                for line in f:
                    url = line.strip()
                    if url and not url.startswith('#'):  # Skip empty lines and comments
                        tasks.append(Task.from_url(url))

            logger.info(t('log.tasks_loaded_count', path=file_path, count=len(tasks)))
            return tasks

        except Exception as e:
            logger.error(t('log.text_load_error', error=e))
            return []

    def load_pending_tasks(self) -> List[Task]:
        """
        Load all pending tasks.

        Returns:
            Task list
        """
        pending_dir = self.tasks_dir / 'pending'
        if not pending_dir.exists():
            return []

        tasks = []
        for file_path in pending_dir.glob('*.json'):
            loaded = self.load_from_json(str(file_path))
            tasks.extend(loaded)

        # Load retry tasks
        retry_tasks = [t for t in tasks if t.status == TaskStatus.RETRY]
        pending_tasks = [t for t in tasks if t.status == TaskStatus.PENDING]

        # Retry tasks have priority
        return retry_tasks + pending_tasks

    def load_all_tasks(self) -> dict:
        """
        Load all tasks (grouped by status).

        Returns:
            {'pending': [...], 'completed': [...], 'failed': [...]}
        """
        result = {
            'pending': [],
            'completed': [],
            'failed': [],
        }

        for status in ['pending', 'completed', 'failed']:
            status_dir = self.tasks_dir / status
            if status_dir.exists():
                for file_path in status_dir.glob('*.json'):
                    loaded = self.load_from_json(str(file_path))
                    result[status].extend(loaded)

        return result

    def scan_directory(self, directory: str) -> Generator[Task, None, None]:
        """
        Scan task files in directory.

        Args:
            directory: Directory path

        Yields:
            Task objects
        """
        path = Path(directory)
        if not path.exists():
            return

        # Supported file formats
        for json_file in path.glob('**/*.json'):
            for task in self.load_from_json(str(json_file)):
                yield task

        for csv_file in path.glob('**/*.csv'):
            for task in self.load_from_csv(str(csv_file)):
                yield task

        for txt_file in path.glob('**/*.txt'):
            for task in self.load_from_text(str(txt_file)):
                yield task

    def create_task_from_urls(self, urls: List[str], **default_params) -> List[Task]:
        """
        Create tasks from URL list.

        Args:
            urls: URL list
            **default_params: Default task parameters

        Returns:
            Task list
        """
        return [Task.from_url(url, **default_params) for url in urls]

    def move_task_file(self, task: Task, from_status: str, to_status: str):
        """
        Move task file to corresponding status directory.

        Args:
            task: Task object
            from_status: Original status directory name
            to_status: Target status directory name
        """
        from_dir = self.tasks_dir / from_status
        to_dir = self.tasks_dir / to_status
        to_dir.mkdir(parents=True, exist_ok=True)

        from_path = from_dir / f"{task.id}.json"
        to_path = to_dir / f"{task.id}.json"

        if from_path.exists():
            from_path.rename(to_path)
            logger.debug(t('log.task_file_moved', from_path=from_path, to_path=to_path))
        else:
            # File doesn't exist, save directly to target directory
            task.save_to_file(self.tasks_dir)
