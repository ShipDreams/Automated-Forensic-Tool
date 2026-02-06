#!/usr/bin/env python3
"""
Cross-Platform Notifier
Desktop notification with sound support for macOS, Linux, and Windows.
"""

import os
import platform
import logging
import threading
from typing import Optional

from locales import t

logger = logging.getLogger(__name__)


class CrossPlatformNotifier:
    """
    Cross-platform desktop notification with sound.

    Features:
    - Desktop notification via plyer (unified API for all platforms)
    - Sound alert via platform-specific methods
    - Thread-safe notification
    - Configurable sound enable/disable
    """

    def __init__(self, sound_enabled: bool = True):
        """
        Initialize notifier.

        Args:
            sound_enabled: Whether to play sound with notifications
        """
        self._sound_enabled = sound_enabled
        self._system = platform.system()
        self._plyer_available = self._check_plyer()

    def _check_plyer(self) -> bool:
        """Check if plyer is available."""
        try:
            from plyer import notification
            return True
        except ImportError:
            logger.warning(t('notify.plyer_not_installed'))
            return False

    def notify(
        self,
        title: str,
        message: str,
        sound: bool = True,
        timeout: int = 10
    ) -> bool:
        """
        Send desktop notification with optional sound.

        Args:
            title: Notification title
            message: Notification message body
            sound: Whether to play sound (overrides instance setting if False)
            timeout: Notification display duration in seconds

        Returns:
            Whether notification was sent successfully
        """
        success = False

        # Use platform-specific notification method
        if self._system == "Darwin":
            success = self._notify_macos(title, message, sound)
        elif self._system == "Windows":
            success = self._notify_windows(title, message, timeout)
        elif self._system == "Linux":
            success = self._notify_linux(title, message)
        else:
            # Fallback: use terminal bell
            self._terminal_bell()
            logger.info(t('notify.fallback_terminal_bell'))

        # Play sound separately if notification method didn't include sound
        if sound and self._sound_enabled and not success:
            sound_thread = threading.Thread(target=self._play_sound, daemon=True)
            sound_thread.start()

        return success

    def _notify_macos(self, title: str, message: str, sound: bool = True) -> bool:
        """Send notification on macOS using osascript dialog (no dependencies)."""
        try:
            import subprocess

            # Play sound in background first
            if sound:
                subprocess.Popen(
                    ["afplay", "/System/Library/Sounds/Glass.aiff"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )

            # Escape quotes in title and message
            title_escaped = title.replace('"', '\\"')
            message_escaped = message.replace('"', '\\"')

            # Use display dialog (modal popup, not affected by notification permissions)
            script = f'display dialog "{message_escaped}" with title "{title_escaped}" buttons {{"OK"}} default button 1 with icon caution'

            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                timeout=300  # 5 minutes timeout for user to respond
            )

            if result.returncode == 0:
                logger.info(t('notify.send_success'))
                return True
            else:
                logger.warning(t('notify.send_failed', error=result.stderr.decode()))
                return False

        except subprocess.TimeoutExpired:
            logger.warning(t('notify.send_failed', error="Dialog timeout"))
            return False
        except Exception as e:
            logger.warning(t('notify.send_failed', error=str(e)))
            self._terminal_bell()
            return False

    def _notify_linux(self, title: str, message: str) -> bool:
        """Send notification on Linux using notify-send."""
        try:
            import subprocess
            result = subprocess.run(
                ["notify-send", "-u", "critical", title, message],
                capture_output=True,
                timeout=5
            )

            if result.returncode == 0:
                logger.info(t('notify.send_success'))
                # Play sound separately on Linux
                sound_thread = threading.Thread(target=self._play_sound, daemon=True)
                sound_thread.start()
                return True
            else:
                logger.warning(t('notify.send_failed', error="notify-send failed"))
                return False

        except FileNotFoundError:
            logger.warning(t('notify.send_failed', error="notify-send not installed"))
            self._terminal_bell()
            return False
        except Exception as e:
            logger.warning(t('notify.send_failed', error=str(e)))
            self._terminal_bell()
            return False

    def _notify_windows(self, title: str, message: str, timeout: int = 10) -> bool:
        """Send notification on Windows using plyer."""
        if self._plyer_available:
            try:
                from plyer import notification
                notification.notify(
                    title=title,
                    message=message,
                    timeout=timeout,
                    app_name="Forensic Tool"
                )
                logger.info(t('notify.send_success'))
                # Play sound separately
                sound_thread = threading.Thread(target=self._play_sound, daemon=True)
                sound_thread.start()
                return True
            except Exception as e:
                logger.warning(t('notify.send_failed', error=str(e)))

        # Fallback: terminal bell and sound
        self._terminal_bell()
        sound_thread = threading.Thread(target=self._play_sound, daemon=True)
        sound_thread.start()
        return False

    def _terminal_bell(self):
        """Play terminal bell as fallback notification."""
        print('\a', end='', flush=True)

    def _play_sound(self):
        """Play platform-specific notification sound."""
        try:
            if self._system == "Darwin":
                self._play_sound_macos()
            elif self._system == "Linux":
                self._play_sound_linux()
            elif self._system == "Windows":
                self._play_sound_windows()
            else:
                logger.warning(t('notify.unsupported_platform', platform=self._system))
        except Exception as e:
            logger.warning(t('notify.sound_play_failed', error=str(e)))

    def _play_sound_macos(self):
        """Play sound on macOS using afplay."""
        # Use system sound files
        sound_files = [
            "/System/Library/Sounds/Glass.aiff",
            "/System/Library/Sounds/Ping.aiff",
            "/System/Library/Sounds/Pop.aiff",
        ]

        for sound_file in sound_files:
            if os.path.exists(sound_file):
                os.system(f"afplay '{sound_file}' &")
                return

        # Fallback: terminal bell
        self._terminal_bell()

    def _play_sound_linux(self):
        """Play sound on Linux using paplay, aplay, or espeak."""
        # Try PulseAudio first
        sound_files = [
            "/usr/share/sounds/freedesktop/stereo/bell.oga",
            "/usr/share/sounds/freedesktop/stereo/complete.oga",
            "/usr/share/sounds/freedesktop/stereo/message.oga",
        ]

        for sound_file in sound_files:
            if os.path.exists(sound_file):
                result = os.system(f"paplay '{sound_file}' 2>/dev/null &")
                if result == 0:
                    return

        # Try ALSA
        alsa_sounds = [
            "/usr/share/sounds/alsa/Front_Center.wav",
        ]

        for sound_file in alsa_sounds:
            if os.path.exists(sound_file):
                result = os.system(f"aplay '{sound_file}' 2>/dev/null &")
                if result == 0:
                    return

        # Fallback: terminal bell
        self._terminal_bell()

    def _play_sound_windows(self):
        """Play sound on Windows using winsound."""
        try:
            import winsound
            # Play system beep: frequency=1000Hz, duration=500ms
            winsound.Beep(1000, 500)
        except ImportError:
            # winsound not available, use terminal bell
            self._terminal_bell()
        except Exception:
            self._terminal_bell()

    def notify_captcha(self, device_id: str, sound: bool = True) -> bool:
        """
        Convenience method to notify about captcha detection.

        Args:
            device_id: Device identifier that encountered captcha
            sound: Whether to play sound

        Returns:
            Whether notification was sent successfully
        """
        title = t('notify.captcha_title')
        message = t('notify.captcha_message', device_id=device_id)
        return self.notify(title=title, message=message, sound=sound)


# Singleton instance for convenience
_notifier_instance: Optional[CrossPlatformNotifier] = None


def get_notifier(sound_enabled: bool = True) -> CrossPlatformNotifier:
    """
    Get singleton notifier instance.

    Args:
        sound_enabled: Whether to enable sound (only used on first call)

    Returns:
        CrossPlatformNotifier instance
    """
    global _notifier_instance
    if _notifier_instance is None:
        _notifier_instance = CrossPlatformNotifier(sound_enabled=sound_enabled)
    return _notifier_instance


def notify_captcha(device_id: str, sound: bool = True) -> bool:
    """
    Convenience function to send captcha notification.

    Args:
        device_id: Device identifier that encountered captcha
        sound: Whether to play sound

    Returns:
        Whether notification was sent successfully
    """
    notifier = get_notifier()
    return notifier.notify_captcha(device_id=device_id, sound=sound)
