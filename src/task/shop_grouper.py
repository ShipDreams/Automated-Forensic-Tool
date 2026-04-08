#!/usr/bin/env python3
"""
Shop Grouper Module.
Groups forensic tasks by shop name and creates evidence groups.
"""

import logging
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import List, Optional

from .task_model import Task

logger = logging.getLogger(__name__)


@dataclass
class EvidenceGroup:
    """
    One evidence group, corresponds to a single Shishibao recording.

    All tasks in a group come from the same shop. During Phase 2 (recording),
    all products are opened from favorites and recorded as one evidence.
    """
    shop_name: str
    group_index: int  # 1-based index within the shop
    tasks: List[Task]
    evidence_name: str = ""
    valid_tasks: List[Task] = field(default_factory=list)
    invalid_tasks: List[Task] = field(default_factory=list)

    def __post_init__(self):
        if not self.evidence_name:
            platform = "淘宝"
            self.evidence_name = f"{self.shop_name}_{self.group_index}_{platform}"


class ShopGrouper:
    """
    Groups tasks by shop name and splits into evidence groups.

    Each group contains up to `group_size` tasks from the same shop.
    """

    def __init__(self, group_size: int = 3):
        """
        Args:
            group_size: Maximum number of tasks per evidence group
        """
        self.group_size = max(1, group_size)

    def group_tasks(self, tasks: List[Task]) -> List[EvidenceGroup]:
        """
        Group tasks by shop_name, then split each shop into chunks.

        Args:
            tasks: List of Task objects (must have shop_name set)

        Returns:
            List of EvidenceGroup objects
        """
        if not tasks:
            return []

        # Group by shop_name, preserving insertion order
        shop_groups = OrderedDict()
        for task in tasks:
            shop_name = self._extract_shop_name(task)
            if shop_name not in shop_groups:
                shop_groups[shop_name] = []
            shop_groups[shop_name].append(task)

        # Split each shop group into chunks of group_size
        evidence_groups = []
        for shop_name, shop_tasks in shop_groups.items():
            chunks = [shop_tasks[i:i + self.group_size]
                      for i in range(0, len(shop_tasks), self.group_size)]

            for idx, chunk in enumerate(chunks):
                group = EvidenceGroup(
                    shop_name=shop_name,
                    group_index=idx + 1,
                    tasks=chunk,
                )
                # Assign group_id to each task
                for task in chunk:
                    task.group_id = f"{shop_name}_{idx + 1}"

                evidence_groups.append(group)

        logger.info(f"Grouped {len(tasks)} tasks into {len(evidence_groups)} evidence groups "
                    f"across {len(shop_groups)} shops")
        return evidence_groups

    def _extract_shop_name(self, task: Task) -> str:
        """
        Extract shop name from a task.

        Priority:
        1. task.shop_name
        2. task.metadata.get('shop_name')
        3. Parse from task.evidence_name (format: "店铺名_平台")
        4. Default "unknown_shop"
        """
        if task.shop_name:
            return task.shop_name

        if task.metadata.get('shop_name'):
            return task.metadata['shop_name']

        if task.evidence_name:
            # Try to extract shop name from evidence_name
            # Format is typically "店铺名__平台" or "店铺名_平台"
            parts = task.evidence_name.rsplit('_', 1)
            if len(parts) == 2 and parts[0]:
                # Remove trailing underscores
                name = parts[0].rstrip('_')
                if name:
                    return name

        return "unknown_shop"
