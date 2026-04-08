#!/usr/bin/env python3
"""
Grouped Evidence Executor.
Orchestrates the two-phase forensic flow for each evidence group:
  Phase 1: Pre-screen products and add valid ones to favorites (no recording)
  Phase 2: Record evidence from favorites list (with Shishibao recording)
"""

import time
import logging
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

from locales import t
from .shop_grouper import EvidenceGroup

logger = logging.getLogger(__name__)


@dataclass
class GroupResult:
    """Result of executing one evidence group."""
    success: bool
    evidence_name: str = ""
    reason: str = ""
    valid_count: int = 0
    invalid_count: int = 0
    company_name: Optional[str] = None
    failed_urls: List[str] = field(default_factory=list)


class GroupedExecutor:
    """
    Grouped evidence execution engine.

    For each EvidenceGroup, executes:
      Phase 1: Pre-screen + add valid products to favorites (no recording)
      Phase 2: Record evidence from favorites list (with Shishibao recording)
    """

    def __init__(self, collector, favorites, handler, db_loader=None, group_size: int = 3):
        """
        Args:
            collector: EvidenceCollector instance (for recording start/stop)
            favorites: TaobaoFavorites instance (for favorites operations)
            handler: TaobaoHandler instance (for product navigation/video/qualification)
            db_loader: Optional DBTaskLoader for writing results to database
        """
        self.collector = collector
        self.favorites = favorites
        self.handler = handler
        self.db_loader = db_loader
        self.group_size = max(1, group_size)

    def execute_all_groups(self, groups: List[EvidenceGroup],
                           video_duration: int = 30,
                           taobao_antibot=None) -> List[GroupResult]:
        """
        Execute all evidence groups sequentially.

        Args:
            groups: List of EvidenceGroup objects
            video_duration: Video recording duration per product (seconds)
            taobao_antibot: Optional TaobaoAntiBot for cooldown management

        Returns:
            List of GroupResult objects
        """
        results = []
        planned_total = len(groups)
        shop_task_queues = self._build_shop_task_queues(groups)
        executed_count = 0

        for shop_name, pending_tasks in shop_task_queues.items():
            group_index = 1

            while pending_tasks:
                group = EvidenceGroup(
                    shop_name=shop_name,
                    group_index=group_index,
                    tasks=[],
                )

                logger.info("=" * 70)
                logger.info(f"Processing evidence group {executed_count + 1}: "
                            f"{group.evidence_name} (remaining shop tasks: {len(pending_tasks)})")
                logger.info("=" * 70)

                # Check antibot cooldown between groups
                if taobao_antibot and executed_count > 0:
                    if hasattr(taobao_antibot, 'check_cooldown'):
                        remaining = taobao_antibot.check_cooldown()
                        if remaining > 0:
                            logger.info(f"Antibot cooldown: waiting {remaining:.0f}s...")
                            time.sleep(remaining)

                try:
                    result = self.execute_group(group, video_duration, task_source=pending_tasks)
                    consumed_count = len(group.tasks)
                    if consumed_count <= 0:
                        raise RuntimeError(f"No tasks consumed for group '{group.evidence_name}'")

                    del pending_tasks[:consumed_count]
                    results.append(result)
                    executed_count += 1

                    if result.success:
                        logger.info(f"Group '{group.evidence_name}' completed successfully "
                                    f"({result.valid_count} valid products)")
                    else:
                        logger.warning(f"Group '{group.evidence_name}' failed: {result.reason}")

                except KeyboardInterrupt:
                    logger.warning("Execution interrupted by user")
                    raise
                except Exception as e:
                    logger.error(f"Group '{group.evidence_name}' error: {e}")
                    results.append(GroupResult(
                        success=False,
                        evidence_name=group.evidence_name,
                        reason=str(e),
                    ))
                    break
                finally:
                    # Cleanup between groups
                    self._cleanup_between_groups()

                group_index += 1

        logger.info(f"Grouped execution complete: executed {executed_count} evidence groups "
                    f"(planned chunks: {planned_total})")

        return results

    def execute_group(self, group: EvidenceGroup, video_duration: int = 30,
                      task_source: Optional[List] = None) -> GroupResult:
        """
        Execute one evidence group (Phase 1 + Phase 2).

        Args:
            group: EvidenceGroup to execute
            video_duration: Video recording duration per product (seconds)

        Returns:
            GroupResult
        """
        # === Phase 1: Pre-screen and collect favorites (no recording) ===
        valid_tasks = self._phase1_collect_favorites(group, task_source=task_source)

        if not valid_tasks:
            return GroupResult(
                success=False,
                evidence_name=group.evidence_name,
                reason="所有链接均无效",
                invalid_count=len(group.tasks),
                failed_urls=[t.product_url for t in group.tasks],
            )

        group.valid_tasks = valid_tasks

        # === Phase 2: Record evidence from favorites (with recording) ===
        return self._phase2_record_evidence(group, video_duration)

    def _phase1_collect_favorites(self, group: EvidenceGroup,
                                  task_source: Optional[List] = None) -> list:
        """
        Phase 1: Pre-screen products and add valid ones to favorites.

        Steps:
        1. Check environment
        2. Open Taobao
        3. Clear favorites
        4. For each task: navigate to product → check validity → add to favorites
        5. Close Taobao

        Returns:
            List of valid Task objects
        """
        tasks_to_process = task_source if task_source is not None else group.tasks
        logger.info(f"[Phase 1] Pre-screening products for '{group.shop_name}' "
                    f"(pending tasks: {len(tasks_to_process)})")

        # Environment check
        self.collector.stage_1_check_environment()

        # Open Taobao directly
        package_name = self.handler.get_app_package()
        self.handler.adb.launch_app(package_name)
        time.sleep(5)

        # Clear favorites
        logger.info("[Phase 1] Clearing existing favorites...")
        self.favorites.clear_favorites()

        # Kill Taobao to ensure next launch starts from home page
        logger.info("[Phase 1] Killing Taobao to reset to home page...")
        self.handler.adb.force_stop_app(package_name)
        time.sleep(2)

        # Relaunch Taobao (will open to home page)
        self.handler.adb.launch_app(package_name)
        time.sleep(5)

        valid_tasks = []
        processed_tasks = []

        for task in tasks_to_process:
            processed_tasks.append(task)
            task.group_id = f"{group.shop_name}_{group.group_index}"
            logger.info(f"[Phase 1] Checking product {len(processed_tasks)}/{len(tasks_to_process)}: "
                        f"{task.product_url}")

            try:
                # Navigate to product
                if not self.handler.navigate_to_product(task.product_url):
                    logger.warning(f"Failed to navigate to product: {task.product_url}")
                    task.is_valid = False
                    group.invalid_tasks.append(task)
                    self._mark_task_failed(task, "无法跳转到商品页面")
                    # Kill and relaunch to reset to home page
                    self.handler.adb.force_stop_app(package_name)
                    time.sleep(2)
                    self.handler.adb.launch_app(package_name)
                    time.sleep(5)
                    continue

                # Wait for page to fully load (invalid product hints may appear late)
                time.sleep(2)

                # Check validity
                if not self.handler.check_product_validity():
                    logger.info(f"Product is invalid/expired: {task.product_url}")
                    # Dump UI for debug verification
                    root = self.handler.locator.dump_and_parse()
                    if root:
                        for node in root.iter():
                            text = node.attrib.get('text', '')
                            if text:
                                logger.debug(f"  UI text: {text}")
                    task.is_valid = False
                    group.invalid_tasks.append(task)
                    self._mark_task_failed(task, "链接失效")
                    # Kill and relaunch to reset to home page
                    self.handler.adb.force_stop_app(package_name)
                    time.sleep(2)
                    self.handler.adb.launch_app(package_name)
                    time.sleep(5)
                    continue

                # Product is valid, add to favorites
                task.is_valid = True
                if self.favorites.add_to_favorites():
                    valid_tasks.append(task)
                    logger.info(f"Product added to favorites: {task.product_url}")
                else:
                    logger.warning(f"Failed to add to favorites: {task.product_url}")
                    valid_tasks.append(task)  # Still consider valid

                if len(valid_tasks) >= self.group_size:
                    logger.info(f"[Phase 1] Reached group capacity ({self.group_size} valid products)")
                    break

                # Kill and relaunch to reset to home page for next product
                logger.info("Resetting Taobao to home page for next product...")
                self.handler.adb.force_stop_app(package_name)
                time.sleep(2)
                self.handler.adb.launch_app(package_name)
                time.sleep(5)

            except Exception as e:
                logger.error(f"Error checking product {task.product_url}: {e}")
                task.is_valid = False
                group.invalid_tasks.append(task)
                self._mark_task_failed(task, str(e))

        # Close Taobao after phase 1
        self.handler.adb.force_stop_app(package_name)
        time.sleep(1)

        group.tasks = processed_tasks

        logger.info(f"[Phase 1] Complete: {len(valid_tasks)} valid, "
                    f"{len(group.invalid_tasks)} invalid")

        return valid_tasks

    def _build_shop_task_queues(self, groups: List[EvidenceGroup]) -> "OrderedDict[str, List]":
        """Flatten planned groups into per-shop pending task queues."""
        shop_task_queues = OrderedDict()
        for group in groups:
            if group.shop_name not in shop_task_queues:
                shop_task_queues[group.shop_name] = []
            shop_task_queues[group.shop_name].extend(group.tasks)
        return shop_task_queues

    def _phase2_record_evidence(self, group: EvidenceGroup,
                                 video_duration: int = 30) -> GroupResult:
        """
        Phase 2: Record evidence from favorites list.

        Steps:
        1. Start Shishibao recording
        2. Show Beijing time
        3. Open Taobao from app store
        4. Navigate to favorites
        5. For each valid task: click item → play video → wait → (last: view qualification)
        6. Stop recording and save evidence

        Returns:
            GroupResult
        """
        logger.info(f"[Phase 2] Recording {len(group.valid_tasks)} products "
                    f"for '{group.evidence_name}'")

        company_name = None
        result_note = None

        try:
            self.handler.reset_qualification_context(cleanup_file=True)

            # Step 1: Start Shishibao recording
            if not self.collector.stage_2_start_recording():
                return GroupResult(
                    success=False,
                    evidence_name=group.evidence_name,
                    reason="无法启动实时保录制",
                    valid_count=len(group.valid_tasks),
                )

            # Enable screenshot callback now that Shishibao is recording
            self.handler.set_screenshot_callback(self.collector.click_screenshot_button)

            # Step 2: Show Beijing time anchor
            self.collector.stage_3_show_beijing_time()

            # Step 3: Open Taobao from app store (for evidence chain)
            if not self.handler.open_app_from_store():
                return self._fail_and_stop_recording(group, "无法在应用商店搜索淘宝")

            if not self.handler.launch_app():
                return self._fail_and_stop_recording(group, "无法启动淘宝")

            # Step 4: Navigate to favorites list
            if not self.favorites.navigate_to_favorites():
                return self._fail_and_stop_recording(group, "无法进入收藏夹")

            # Step 5: Process each product from favorites
            total_valid = len(group.valid_tasks)
            for i, task in enumerate(group.valid_tasks):
                logger.info(f"[Phase 2] Recording product {i + 1}/{total_valid}: {task.product_url}")

                # Click the ith item in favorites
                if not self.favorites.click_favorite_item(i):
                    logger.warning(f"Failed to click favorite item {i}")
                    if i == total_valid - 1:
                        self.handler.set_qualification_issue("资质查看失败")
                    continue

                # Play video
                self.handler.replay_video_from_start()

                # Wait for video recording duration
                logger.info(f"Recording video for {video_duration}s...")
                time.sleep(video_duration)

                # Screenshot: product page evidence (clicks Shishibao floating button)
                self.handler.take_screenshot(f"商品页面证据 {i + 1}/{total_valid}")

                # Only for the last product: view qualification certificates
                if i == total_valid - 1:
                    logger.info("Last product in group: viewing qualification certificates")
                    self.handler.view_qualification()

                # Go back to favorites list
                self.favorites.go_back_to_favorites_list()

            # Step 6: Stop recording and save evidence
            if not self.collector.stage_9_export_evidence(evidence_name=group.evidence_name):
                self.handler.reset_qualification_context(cleanup_file=True)
                return GroupResult(
                    success=False,
                    evidence_name=group.evidence_name,
                    reason="保存证据失败",
                    valid_count=total_valid,
                    company_name=company_name,
                )

            company_name, result_note = self.handler.finalize_qualification_ocr()
            if result_note:
                logger.warning(t('log.ocr_phase2_note', note=result_note))
            if company_name:
                logger.info(t('log.ocr_phase2_company_name', company_name=company_name))

            # Mark all valid tasks as completed
            for task in group.valid_tasks:
                self._mark_task_completed(task, company_name, result_note)

            return GroupResult(
                success=True,
                evidence_name=group.evidence_name,
                valid_count=total_valid,
                invalid_count=len(group.invalid_tasks),
                company_name=company_name,
                failed_urls=[t.product_url for t in group.invalid_tasks],
            )

        except Exception as e:
            logger.error(f"[Phase 2] Error: {e}")
            return self._fail_and_stop_recording(group, str(e))

    def _fail_and_stop_recording(self, group: EvidenceGroup, reason: str) -> GroupResult:
        """Cancel recording and return failure result."""
        try:
            self.collector.recorder.cancel_recording()
        except Exception:
            pass

        self.handler.reset_qualification_context(cleanup_file=True)

        return GroupResult(
            success=False,
            evidence_name=group.evidence_name,
            reason=reason,
            valid_count=len(group.valid_tasks),
        )

    def _mark_task_failed(self, task, error: str):
        """Mark a task as failed, optionally write to database."""
        if self.db_loader:
            try:
                db_id = task.metadata.get('db_id') or task.id
                self.db_loader.mark_failed(int(db_id), error)
            except Exception as e:
                logger.warning(f"Failed to update DB for task {task.id}: {e}")

    def _mark_task_completed(self, task, company_name: Optional[str] = None,
                             result_note: Optional[str] = None):
        """Mark a task as completed, optionally write to database."""
        if self.db_loader:
            try:
                db_id = task.metadata.get('db_id') or task.id
                result_text = "取证成功"
                if result_note:
                    result_text = f"{result_text}；{result_note}"
                self.db_loader.mark_completed(
                    int(db_id),
                    result=result_text,
                    company_name=company_name or '',
                )
            except Exception as e:
                logger.warning(f"Failed to update DB for task {task.id}: {e}")

    def _cleanup_between_groups(self):
        """Cleanup between groups: close apps, wait."""
        try:
            self.handler.adb.force_stop_app("com.taobao.taobao")
            self.handler.adb.force_stop_app("com.taobao.taobao4android")
            self.handler.adb.force_stop_app("com.a1010bao.web.rdbao")
        except Exception:
            pass
        time.sleep(2)
