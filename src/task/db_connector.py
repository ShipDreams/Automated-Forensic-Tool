#!/usr/bin/env python3
"""
Database Connector for MySQL.
Manages connection to the forensic database (app_goods table).
"""

import json
import logging
from pathlib import Path
from typing import Optional

import pymysql
import pymysql.cursors

logger = logging.getLogger(__name__)


class DatabaseConnector:
    """MySQL database connection manager."""

    def __init__(self, config_path: str = None):
        """
        Initialize database connector.

        Args:
            config_path: Path to database config JSON file.
                         Defaults to config/database.json
        """
        if config_path is None:
            config_path = str(Path(__file__).parent.parent.parent / 'config' / 'database.json')

        config_path = Path(config_path)
        if not config_path.exists():
            raise FileNotFoundError(f"Database config not found: {config_path}")

        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = json.load(f)

        self._conn = None
        logger.info(f"Database connector initialized: {self.config.get('host')}:{self.config.get('port', 3306)}"
                     f"/{self.config.get('database')}")

    def get_connection(self):
        """
        Get database connection with auto-reconnect.

        Returns:
            pymysql Connection object
        """
        if self._conn is None or not self._conn.open:
            self._conn = pymysql.connect(
                host=self.config['host'],
                port=self.config.get('port', 3306),
                user=self.config['user'],
                password=self.config['password'],
                database=self.config['database'],
                charset=self.config.get('charset', 'utf8mb4'),
                cursorclass=pymysql.cursors.DictCursor,
                autocommit=True,
                connect_timeout=self.config.get('connect_timeout', 10),
            )
            logger.info("Database connected")
        else:
            # Ping to ensure connection is alive
            try:
                self._conn.ping(reconnect=True)
            except Exception:
                self._conn = None
                return self.get_connection()

        return self._conn

    def close(self):
        """Close database connection."""
        if self._conn and self._conn.open:
            self._conn.close()
            logger.info("Database connection closed")
        self._conn = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
