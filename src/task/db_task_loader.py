#!/usr/bin/env python3
"""
Database Task Loader.
Loads forensic tasks from MySQL app_goods table and writes back results.
"""

import logging
from typing import List, Optional

from .task_model import Task
from .db_connector import DatabaseConnector

logger = logging.getLogger(__name__)


class DBTaskLoader:
    """Load tasks from and write results to MySQL database."""

    # Status values matching customer database convention
    STATUS_PENDING = -1
    STATUS_RUNNING = 1
    STATUS_COMPLETED = 2
    STATUS_FAILED = 3

    RESULT_RUNNING = "进行中"
    RESULT_COMPLETED = "已存证"

    TABLE = 'app_goods'

    def __init__(self, config_path: str = None):
        """
        Args:
            config_path: Path to database config JSON file
        """
        self.db = DatabaseConnector(config_path)

    def load_batch(self, batch_size: int = 100) -> List[Task]:
        """
        Load a batch of pending tasks from database.

        Reads records with status=-1 (pending), ordered by id ASC.

        Args:
            batch_size: Maximum number of tasks to load

        Returns:
            List of Task objects
        """
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cursor:
                sql = f"""SELECT id, goods_url, shop_name, platform, evidence_name, goods_title
                          FROM {self.TABLE}
                          WHERE status = %s
                            AND platform IN (%s, %s)
                          ORDER BY id ASC
                          LIMIT %s"""
                cursor.execute(sql, (self.STATUS_PENDING, '淘宝', '天猫', batch_size))
                rows = cursor.fetchall()
        except Exception as e:
            logger.error(f"Failed to load tasks from database: {e}")
            return []

        tasks = []
        for row in rows:
            task = Task(
                id=str(row['id']),
                product_url=row.get('goods_url') or '',
                shop_name=row.get('shop_name') or '',
                platform=row.get('platform') or '',
                evidence_name=row.get('evidence_name') or '',
                metadata={
                    'db_id': row['id'],
                    'goods_title': row.get('goods_title') or '',
                }
            )
            tasks.append(task)

        logger.info(f"Loaded {len(tasks)} pending tasks from database")
        return tasks

    def mark_running(self, db_id: int, device_id: str = ''):
        """
        Mark a task as running.

        Args:
            db_id: Database record ID
            device_id: Device ID performing the task
        """
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cursor:
                sql = f"""UPDATE {self.TABLE}
                          SET status = %s, result = %s, device_id = %s, modified_at = NOW()
                          WHERE id = %s"""
                cursor.execute(sql, (self.STATUS_RUNNING, self.RESULT_RUNNING, device_id, db_id))
            logger.debug(f"Task {db_id} marked as running on device {device_id}")
        except Exception as e:
            logger.error(f"Failed to mark task {db_id} as running: {e}")

    def mark_completed(self, db_id: int, result: str = '',
                       company_name: str = '', evidence_start_time: str = ''):
        """
        Mark a task as completed and write back results.

        Args:
            db_id: Database record ID
            result: Result description
            company_name: OCR-recognized company name (Requirement 6)
            evidence_start_time: Recording start time
        """
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cursor:
                sql = f"""UPDATE {self.TABLE}
                          SET status = %s, result = %s, company_name = %s,
                              evidence_start_time = %s, modified_at = NOW()
                          WHERE id = %s"""
                cursor.execute(sql, (
                    self.STATUS_COMPLETED, result or self.RESULT_COMPLETED, company_name,
                    evidence_start_time, db_id
                ))
            logger.info(f"Task {db_id} marked as completed")
        except Exception as e:
            logger.error(f"Failed to mark task {db_id} as completed: {e}")

    def update_ocr_result(self, db_id: int, company_name: str = ''):
        """
        Update OCR-derived fields for an already-saved evidence record.

        Keeps the current status/result unchanged.
        """
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cursor:
                sql = f"""UPDATE {self.TABLE}
                          SET company_name = %s, modified_at = NOW()
                          WHERE id = %s"""
                cursor.execute(sql, (company_name, db_id))
            logger.info(f"Task {db_id} OCR fields updated")
        except Exception as e:
            logger.error(f"Failed to update OCR result for task {db_id}: {e}")

    def mark_failed(self, db_id: int, error: str = ''):
        """
        Mark a task as failed.

        Args:
            db_id: Database record ID
            error: Error description
        """
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cursor:
                sql = f"""UPDATE {self.TABLE}
                          SET status = %s, result = %s, modified_at = NOW()
                          WHERE id = %s"""
                cursor.execute(sql, (self.STATUS_FAILED, error, db_id))
            logger.info(f"Task {db_id} marked as failed: {error}")
        except Exception as e:
            logger.error(f"Failed to mark task {db_id} as failed: {e}")

    def get_pending_count(self) -> int:
        """Get count of pending tasks in database."""
        conn = self.db.get_connection()
        try:
            with conn.cursor() as cursor:
                sql = f"SELECT COUNT(*) as cnt FROM {self.TABLE} WHERE status = %s"
                cursor.execute(sql, (self.STATUS_PENDING,))
                row = cursor.fetchone()
                return row['cnt'] if row else 0
        except Exception as e:
            logger.error(f"Failed to get pending count: {e}")
            return 0

    def close(self):
        """Close database connection."""
        self.db.close()
