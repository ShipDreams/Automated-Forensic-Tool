#!/usr/bin/env python3
"""
任务加载器
从文件或其他来源加载任务
"""

import json
import logging
from pathlib import Path
from typing import List, Optional, Generator
import csv

from .task_model import Task, TaskStatus

logger = logging.getLogger(__name__)


class TaskLoader:
    """
    任务加载器

    支持从多种来源加载任务：
    - JSON 文件（单个任务）
    - JSON 文件（任务列表）
    - CSV 文件
    - 文本文件（每行一个 URL）
    - 目录（批量加载）
    """

    def __init__(self, tasks_dir: str = None):
        """
        初始化任务加载器

        Args:
            tasks_dir: 任务目录路径，默认使用 tasks/
        """
        if tasks_dir:
            self.tasks_dir = Path(tasks_dir)
        else:
            self.tasks_dir = Path(__file__).parent.parent.parent / 'tasks'

    def load_from_json(self, file_path: str) -> List[Task]:
        """
        从 JSON 文件加载任务

        Args:
            file_path: JSON 文件路径

        Returns:
            任务列表
        """
        path = Path(file_path)
        if not path.exists():
            logger.error(f"文件不存在: {file_path}")
            return []

        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # 判断是单个任务还是任务列表
            if isinstance(data, list):
                tasks = [Task.from_dict(item) for item in data]
            elif isinstance(data, dict):
                if 'tasks' in data:
                    tasks = [Task.from_dict(item) for item in data['tasks']]
                else:
                    tasks = [Task.from_dict(data)]
            else:
                logger.error(f"无效的 JSON 格式: {file_path}")
                return []

            logger.info(f"从 {file_path} 加载了 {len(tasks)} 个任务")
            return tasks

        except json.JSONDecodeError as e:
            logger.error(f"JSON 解析失败: {e}")
            return []
        except Exception as e:
            logger.error(f"加载任务失败: {e}")
            return []

    def load_from_csv(self, file_path: str) -> List[Task]:
        """
        从 CSV 文件加载任务

        CSV 格式：
        - 必须有 'url' 或 'product_url' 列
        - 可选列：platform, video_duration, priority

        Args:
            file_path: CSV 文件路径

        Returns:
            任务列表
        """
        path = Path(file_path)
        if not path.exists():
            logger.error(f"文件不存在: {file_path}")
            return []

        tasks = []
        try:
            with open(path, 'r', encoding='utf-8') as f:
                reader = csv.DictReader(f)

                for row in reader:
                    # 获取 URL
                    url = row.get('url') or row.get('product_url') or row.get('URL')
                    if not url:
                        continue

                    # 创建任务
                    task_data = {
                        'product_url': url.strip(),
                        'platform': row.get('platform', ''),
                        'video_duration': int(row.get('video_duration', 30)),
                    }

                    # 处理优先级
                    if 'priority' in row:
                        try:
                            task_data['priority'] = int(row['priority'])
                        except ValueError:
                            pass

                    tasks.append(Task.from_dict(task_data))

            logger.info(f"从 {file_path} 加载了 {len(tasks)} 个任务")
            return tasks

        except Exception as e:
            logger.error(f"加载 CSV 失败: {e}")
            return []

    def load_from_text(self, file_path: str) -> List[Task]:
        """
        从文本文件加载任务（每行一个 URL）

        Args:
            file_path: 文本文件路径

        Returns:
            任务列表
        """
        path = Path(file_path)
        if not path.exists():
            logger.error(f"文件不存在: {file_path}")
            return []

        tasks = []
        try:
            with open(path, 'r', encoding='utf-8') as f:
                for line in f:
                    url = line.strip()
                    if url and not url.startswith('#'):  # 跳过空行和注释
                        tasks.append(Task.from_url(url))

            logger.info(f"从 {file_path} 加载了 {len(tasks)} 个任务")
            return tasks

        except Exception as e:
            logger.error(f"加载文本文件失败: {e}")
            return []

    def load_pending_tasks(self) -> List[Task]:
        """
        加载所有待处理任务

        Returns:
            任务列表
        """
        pending_dir = self.tasks_dir / 'pending'
        if not pending_dir.exists():
            return []

        tasks = []
        for file_path in pending_dir.glob('*.json'):
            loaded = self.load_from_json(str(file_path))
            tasks.extend(loaded)

        # 加载重试任务
        retry_tasks = [t for t in tasks if t.status == TaskStatus.RETRY]
        pending_tasks = [t for t in tasks if t.status == TaskStatus.PENDING]

        # 重试任务优先
        return retry_tasks + pending_tasks

    def load_all_tasks(self) -> dict:
        """
        加载所有任务（按状态分组）

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
        扫描目录中的任务文件

        Args:
            directory: 目录路径

        Yields:
            Task 对象
        """
        path = Path(directory)
        if not path.exists():
            return

        # 支持的文件格式
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
        从 URL 列表创建任务

        Args:
            urls: URL 列表
            **default_params: 默认任务参数

        Returns:
            任务列表
        """
        return [Task.from_url(url, **default_params) for url in urls]

    def move_task_file(self, task: Task, from_status: str, to_status: str):
        """
        移动任务文件到对应状态目录

        Args:
            task: 任务对象
            from_status: 原状态目录名
            to_status: 目标状态目录名
        """
        from_dir = self.tasks_dir / from_status
        to_dir = self.tasks_dir / to_status
        to_dir.mkdir(parents=True, exist_ok=True)

        from_path = from_dir / f"{task.id}.json"
        to_path = to_dir / f"{task.id}.json"

        if from_path.exists():
            from_path.rename(to_path)
            logger.debug(f"移动任务文件: {from_path} -> {to_path}")
        else:
            # 文件不存在，直接保存到目标目录
            task.save_to_file(self.tasks_dir)
