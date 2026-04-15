#!/usr/bin/env python3
"""
Platform Handler Base Class
Defines unified interface for e-commerce platform forensics.
"""

from abc import ABC, abstractmethod
from concurrent.futures import Future, TimeoutError
from typing import Optional, Callable
import json
import logging
from pathlib import Path

from locales import t

logger = logging.getLogger(__name__)
_OCR_DEBUG_SCREENSHOT_KEEP_CACHE: Optional[bool] = None
_OCR_FINALIZE_TIMEOUT_SECONDS = 360


def _should_keep_ocr_debug_screenshots() -> bool:
    """Load OCR debug screenshot retention flag from config/device.json."""
    global _OCR_DEBUG_SCREENSHOT_KEEP_CACHE
    if _OCR_DEBUG_SCREENSHOT_KEEP_CACHE is not None:
        return _OCR_DEBUG_SCREENSHOT_KEEP_CACHE

    config_path = Path(__file__).parent.parent.parent / 'config' / 'device.json'
    keep_files = False
    try:
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            keep_files = bool(config.get('ocr_settings', {}).get('keep_debug_screenshots', False))
    except Exception as e:
        logger.warning(t('log.ocr_debug_config_load_failed', error=e))

    _OCR_DEBUG_SCREENSHOT_KEEP_CACHE = keep_files
    return keep_files


class BasePlatformHandler(ABC):
    """
    Platform Handler Abstract Base Class

    All platforms (Taobao, JD, Douyin, etc.) must inherit this class and implement all abstract methods.
    Common flows (environment check, recording, time anchor) are handled by EvidenceCollector.
    Platform-specific flows (open App, product page, video playback, shop qualification) are implemented by each Handler.
    """

    def __init__(self, adb_controller, ui_locator, antibot=None):
        """
        Initialize platform handler.

        Args:
            adb_controller: ADBController instance
            ui_locator: UILocator instance
            antibot: AntiBot instance (optional, for human behavior simulation)
        """
        self.adb = adb_controller
        self.locator = ui_locator
        self.antibot = antibot
        # Screenshot callback function (set by EvidenceCollector)
        self._screenshot_callback: Optional[Callable[[], bool]] = None
        self._pending_qualification_capture_path: Optional[str] = None
        self._pending_qualification_ocr_future: Optional[Future] = None
        self._qualification_issue: Optional[str] = None

    def set_screenshot_callback(self, callback: Callable[[], bool]):
        """Set screenshot callback function."""
        self._screenshot_callback = callback

    def take_screenshot(self, description: str = ""):
        """
        Call screenshot callback.

        Args:
            description: Screenshot description (for logging)
        """
        if self._screenshot_callback:
            if description:
                logger.info(t('log.taking_screenshot', description=description))
            self._screenshot_callback()
        else:
            logger.warning(t('log.screenshot_callback_not_set'))

    def reset_qualification_context(self, cleanup_file: bool = False):
        """Reset cached qualification screenshot and issue state."""
        capture_path = self._pending_qualification_capture_path
        self._pending_qualification_capture_path = None
        self._pending_qualification_ocr_future = None
        self._qualification_issue = None

        if cleanup_file and capture_path and not _should_keep_ocr_debug_screenshots():
            try:
                Path(capture_path).unlink()
                logger.info(t('log.ocr_screenshot_removed', path=capture_path))
            except FileNotFoundError:
                pass
            except Exception as e:
                logger.debug(f"Failed to remove stale qualification capture '{capture_path}': {e}")
        elif cleanup_file and capture_path:
            logger.info(t('log.ocr_screenshot_kept', path=capture_path))

    def set_pending_qualification_capture(self, image_path: Optional[str]):
        """Cache local screenshot path for post-export OCR."""
        self._pending_qualification_capture_path = image_path
        if image_path:
            logger.info(t('log.ocr_screenshot_cached', path=image_path))
        else:
            logger.warning(t('log.ocr_screenshot_cache_empty'))

    def set_pending_qualification_ocr_future(self, future: Optional[Future]):
        """Cache background OCR future for post-export result collection."""
        self._pending_qualification_ocr_future = future

    def set_qualification_issue(self, issue: Optional[str]):
        """Cache qualification warning note for post-export handling."""
        self._qualification_issue = issue

    def consume_pending_qualification_capture(self) -> Optional[str]:
        """Return and clear cached qualification screenshot path."""
        image_path = self._pending_qualification_capture_path
        self._pending_qualification_capture_path = None
        return image_path

    def consume_pending_qualification_ocr_future(self) -> Optional[Future]:
        """Return and clear cached OCR future."""
        future = self._pending_qualification_ocr_future
        self._pending_qualification_ocr_future = None
        return future

    def consume_qualification_issue(self) -> Optional[str]:
        """Return and clear cached qualification issue note."""
        issue = self._qualification_issue
        self._qualification_issue = None
        return issue

    def finalize_qualification_ocr(self) -> tuple[Optional[str], Optional[str]]:
        """
        Run OCR against cached qualification screenshot after evidence export.

        Returns:
            (company_name, note)
        """
        qualification_issue = self.consume_qualification_issue()
        capture_path = self.consume_pending_qualification_capture()
        ocr_future = self.consume_pending_qualification_ocr_future()

        logger.info(t('log.ocr_finalize_started'))

        if qualification_issue:
            logger.warning(t('log.ocr_finalize_skipped_issue', issue=qualification_issue))
            if capture_path and not _should_keep_ocr_debug_screenshots():
                try:
                    Path(capture_path).unlink()
                    logger.info(t('log.ocr_screenshot_removed', path=capture_path))
                except FileNotFoundError:
                    pass
                except Exception as e:
                    logger.debug(f"Failed to remove qualification capture '{capture_path}': {e}")
            elif capture_path:
                logger.info(t('log.ocr_screenshot_kept', path=capture_path))
            return None, qualification_issue

        if not capture_path:
            logger.warning(t('log.ocr_finalize_skipped_missing_capture'))
            return None, "OCR截图缺失"

        try:
            logger.info(t('log.ocr_finalize_using_screenshot', path=capture_path))
            if ocr_future is None:
                from core.ocr_engine import extract_company_name_with_status_subprocess
                logger.warning("[ocr_finalize] no background OCR task found; using subprocess OCR")
                result = extract_company_name_with_status_subprocess(
                    capture_path,
                    timeout_seconds=_OCR_FINALIZE_TIMEOUT_SECONDS,
                )
            else:
                logger.info(f"{t('log.ocr_async_wait_start')} timeout={_OCR_FINALIZE_TIMEOUT_SECONDS}s")
                result = ocr_future.result(timeout=_OCR_FINALIZE_TIMEOUT_SECONDS)
                logger.info(t('log.ocr_async_wait_done'))
            company_name, note = result
            if company_name:
                logger.info(f"[ocr_finalize] success: company_name={company_name}")
            else:
                logger.warning(f"[ocr_finalize] completed without company name: note={note or '无结果'}")
            logger.info(t('log.ocr_finalize_finished'))
            return result
        except TimeoutError:
            logger.error(f"[ocr_finalize] timeout after {_OCR_FINALIZE_TIMEOUT_SECONDS}s")
            return None, f"OCR超时({_OCR_FINALIZE_TIMEOUT_SECONDS}s)"
        except Exception as e:
            logger.error(f"[ocr_finalize] exception: {e}", exc_info=True)
            return None, f"OCR异常: {e}"
        finally:
            if _should_keep_ocr_debug_screenshots():
                logger.info(t('log.ocr_screenshot_kept', path=capture_path))
            else:
                try:
                    Path(capture_path).unlink()
                    logger.info(t('log.ocr_screenshot_removed', path=capture_path))
                except FileNotFoundError:
                    pass
                except Exception as e:
                    logger.debug(f"Failed to remove qualification capture '{capture_path}': {e}")

    def detach_pending_qualification_ocr(self) -> tuple[Optional[str], Optional[str], Optional[Future]]:
        """
        Detach current qualification OCR state for deferred processing.

        Returns:
            (qualification_issue, capture_path, ocr_future)
        """
        qualification_issue = self.consume_qualification_issue()
        capture_path = self.consume_pending_qualification_capture()
        ocr_future = self.consume_pending_qualification_ocr_future()
        return qualification_issue, capture_path, ocr_future

    def resolve_detached_qualification_ocr(
        self,
        qualification_issue: Optional[str],
        capture_path: Optional[str],
        ocr_future: Optional[Future],
    ) -> tuple[Optional[str], Optional[str]]:
        """
        Resolve a previously detached OCR task and cleanup its cached screenshot.

        Returns:
            (company_name, note)
        """
        self._qualification_issue = qualification_issue
        self._pending_qualification_capture_path = capture_path
        self._pending_qualification_ocr_future = ocr_future
        return self.finalize_qualification_ocr()

    @abstractmethod
    def get_platform_name(self) -> str:
        """
        Return platform name.

        Returns:
            Platform name, e.g., "taobao", "jd", "douyin"
        """
        pass

    @abstractmethod
    def get_platform_display_name(self) -> str:
        """
        Return platform display name.

        Returns:
            Display name, e.g., "Taobao", "JD", "Douyin"
        """
        pass

    @abstractmethod
    def get_app_package(self) -> str:
        """
        Return app package name.

        Returns:
            Package name, e.g., "com.taobao.taobao"
        """
        pass

    @abstractmethod
    def get_app_store_search_keyword(self) -> str:
        """
        Return keyword for app store search.

        Returns:
            Search keyword, e.g., "Taobao", "JD"
        """
        pass

    @abstractmethod
    def open_app_from_store(self, wait_time: int = 6) -> bool:
        """
        Search and open app from app store.

        Args:
            wait_time: Time to wait for search results (seconds)

        Returns:
            Whether successfully opened
        """
        pass

    @abstractmethod
    def launch_app(self, wait_time: int = 10) -> bool:
        """
        Launch app (click "Open" from app store or direct launch).

        Args:
            wait_time: Time to wait for app to launch (seconds)

        Returns:
            Whether successfully launched
        """
        pass

    @abstractmethod
    def navigate_to_product(self, product_url: str, wait_time: int = 8) -> bool:
        """
        Navigate to product page.

        Args:
            product_url: Product link
            wait_time: Time to wait for page load (seconds)

        Returns:
            Whether successfully opened product page
        """
        pass

    @abstractmethod
    def play_video(self, max_attempts: int = 3) -> bool:
        """
        Play product video.

        Args:
            max_attempts: Maximum number of attempts

        Returns:
            Whether successfully played (some products may not have video, False is not necessarily an error)
        """
        pass

    @abstractmethod
    def unmute_video(self, max_attempts: int = 2) -> bool:
        """
        Unmute video.

        Args:
            max_attempts: Maximum number of attempts

        Returns:
            Whether successfully unmuted
        """
        pass

    @abstractmethod
    def view_shop_info(self) -> bool:
        """
        View shop information.

        Returns:
            Whether successfully viewed
        """
        pass

    @abstractmethod
    def view_qualification(self) -> bool:
        """
        View shop qualification certificates.

        Returns:
            Whether successfully viewed
        """
        pass

    # ==================== AntiBot Helper Methods ====================

    def _sleep(self, min_ms: int = None, max_ms: int = None):
        """Human-like random delay."""
        if self.antibot:
            self.antibot.sleep(min_ms, max_ms)
        else:
            import time
            import random
            delay = random.uniform((min_ms or 500) / 1000, (max_ms or 2000) / 1000)
            time.sleep(delay)

    def _sleep_after_click(self):
        """Delay after click."""
        if self.antibot:
            self.antibot.sleep_after_click()
        else:
            import time
            import random
            time.sleep(random.uniform(0.8, 1.5))

    def _check_risk(self) -> bool:
        """
        Check current page risk.

        Returns:
            Whether safe (True = safe, False = risky)
        """
        if not self.antibot:
            return True

        root = self.locator.dump_and_parse()
        return self.antibot.is_safe(root)

    def _handle_captcha_if_detected(self) -> bool:
        """
        Check for captcha and handle it with human assistance if found.

        Flow:
        1. Dump UI and check for captcha
        2. If no captcha → return True (safe to continue)
        3. If captcha found → notify human via blocking dialog
        4. Human clicks OK → re-check captcha
           - No captcha → return True (continue current flow)
           - Still captcha → trigger protection mode, return False
        5. Human clicks Cancel / timeout → trigger protection mode, return False

        Returns:
            True: No captcha or captcha resolved, continue current flow
            False: Captcha unresolved, task should fail
        """
        import time

        root = self.locator.dump_and_parse()
        if not root or not self.locator.detect_captcha(root):
            return True  # No captcha, safe to continue

        logger.warning("Captcha detected, notifying human for assistance...")
        device_id = self.adb.device_id or "unknown"

        # Send blocking notification (waits up to 3 min for human)
        human_confirmed = False
        try:
            from core.notifier import notify_captcha
            human_confirmed = notify_captcha(device_id=device_id, sound=True)
        except Exception as e:
            logger.warning(f"Failed to send captcha notification: {e}")

        if not human_confirmed:
            # Timeout or cancelled → protection mode
            logger.warning(f"[{device_id}] No human response, entering protection mode")
            if self.antibot and hasattr(self.antibot, 'enter_protection_mode'):
                self.antibot.enter_protection_mode(reason="captcha_timeout")
            return False

        # Human confirmed → wait briefly then re-check
        logger.info(f"[{device_id}] Human confirmed captcha handled, verifying...")
        time.sleep(3)

        root = self.locator.dump_and_parse()
        if root and self.locator.detect_captcha(root):
            # Captcha still present → not actually handled
            logger.warning(f"[{device_id}] Captcha still present after confirmation, entering protection mode")
            if self.antibot and hasattr(self.antibot, 'enter_protection_mode'):
                self.antibot.enter_protection_mode(reason="captcha_unresolved")
            return False

        logger.info(f"[{device_id}] Captcha resolved, continuing current flow")
        return True

    # ==================== Template Method ====================

    def execute(self, product_url: str, video_play_duration: int = 30) -> tuple:
        """
        Execute complete platform forensic workflow.

        This is a template method that defines the standard forensic workflow.
        Subclasses can override this method to customize the flow, but usually only need to implement the abstract methods.

        Args:
            product_url: Product link
            video_play_duration: Video recording duration (seconds)

        Returns:
            (success: bool, error: str or None) - Whether successful, error reason on failure
        """
        import time

        platform_name = self.get_platform_display_name()
        logger.info(t('log.start_platform_forensic', platform=platform_name))
        self.reset_qualification_context(cleanup_file=True)

        # Step 1: Open app from app store
        logger.info(t('log.step_open_app_store', platform=platform_name))
        if not self.open_app_from_store():
            error = t('log.open_app_store_failed', platform=platform_name)
            logger.error(error)
            return False, error

        # Step 2: Launch app
        logger.info(t('log.step_launch_app', platform=platform_name))
        if not self.launch_app():
            error = t('log.launch_app_failed', platform=platform_name)
            logger.error(error)
            return False, error

        # Step 3: Navigate to product page
        logger.info(t('log.step_open_product'))
        if not self.navigate_to_product(product_url):
            error = t('log.open_product_failed')
            logger.error(error)
            return False, error

        # Risk check (captcha detection with human assistance)
        if not self._check_risk():
            if not self._handle_captcha_if_detected():
                error = "RISK_DETECTED: Platform risk control triggered (captcha/login required)"
                logger.error(error)
                return False, error
            # Captcha resolved by human, continue flow

        # Step 4+5: Video playback (unmute + replay from start)
        # Prefer replay_video_from_start (Taobao), otherwise use old unmute + play
        logger.info(t('log.step_video_playback'))
        if hasattr(self, 'replay_video_from_start'):
            self.replay_video_from_start()
        else:
            # Old flow: unmute first, then play
            logger.info(t('log.step_unmute_video'))
            self.unmute_video()
            self._sleep_after_click()

            logger.info(t('log.step_play_video'))
            video_played = self.play_video()
            if not video_played:
                logger.warning(t('log.video_play_failed_continue'))

        # Step 6: Continue recording
        logger.info(t('log.step_continue_recording', seconds=video_play_duration))
        time.sleep(video_play_duration)

        # Step 7: View shop qualification (required for complete forensic)
        logger.info(t('log.step_view_qualification'))
        qualification_viewed = self.view_qualification()
        if not qualification_viewed:
            if not self._qualification_issue:
                self.set_qualification_issue("资质查看失败")
            logger.warning(t('log.qualification_view_failed_continue'))

        logger.info(t('log.platform_forensic_complete', platform=platform_name))
        return True, None
