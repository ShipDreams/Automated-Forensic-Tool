#!/usr/bin/env python3
"""
Platform Handler Base Class
Defines unified interface for e-commerce platform forensics.
"""

from abc import ABC, abstractmethod
from typing import Optional, Callable
import logging

from locales import t

logger = logging.getLogger(__name__)


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
            error = t('log.qualification_view_failed')
            logger.error(error)
            return False, error

        logger.info(t('log.platform_forensic_complete', platform=platform_name))
        return True, None
