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
                timeout=180  # 3 minutes timeout for user to respond
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
        """Send blocking notification on Linux using zenity (fallback to notify-send)."""
        try:
            import subprocess

            # Play sound in background
            sound_thread = threading.Thread(target=self._play_sound, daemon=True)
            sound_thread.start()

            # Try zenity first (blocking dialog)
            try:
                result = subprocess.run(
                    ["zenity", "--info", "--title", title, "--text", message,
                     "--width", "400", "--height", "200"],
                    capture_output=True,
                    timeout=180  # 3 minutes timeout
                )
                if result.returncode == 0:
                    logger.info(t('notify.send_success'))
                    return True
            except FileNotFoundError:
                pass  # zenity not installed, try next
            except subprocess.TimeoutExpired:
                logger.warning(t('notify.send_failed', error="Dialog timeout"))
                return False

            # Fallback: notify-send (non-blocking, but better than nothing)
            result = subprocess.run(
                ["notify-send", "-u", "critical", title, message],
                capture_output=True,
                timeout=5
            )

            if result.returncode == 0:
                logger.info(t('notify.send_success'))
                return True
            else:
                logger.warning(t('notify.send_failed', error="notify-send failed"))
                return False

        except FileNotFoundError:
            logger.warning(t('notify.send_failed', error="zenity/notify-send not installed"))
            self._terminal_bell()
            return False
        except Exception as e:
            logger.warning(t('notify.send_failed', error=str(e)))
            self._terminal_bell()
            return False

    def _notify_windows(self, title: str, message: str, timeout: int = 10) -> bool:
        """
        Send blocking notification on Windows using MessageBoxTimeoutW.

        Uses undocumented but widely available MessageBoxTimeoutW API for 3-minute timeout.
        Returns True if user clicked OK, False if timed out or failed.
        """
        try:
            import ctypes

            # Play sound in background
            sound_thread = threading.Thread(target=self._play_sound, daemon=True)
            sound_thread.start()

            # MB_OKCANCEL | MB_ICONERROR (red X icon) | MB_TOPMOST | MB_SETFOREGROUND
            # Use OKCANCEL so timeout returns IDTIMEOUT (32000) instead of IDOK (1)
            MB_OKCANCEL = 0x00000001
            MB_ICONERROR = 0x00000010
            MB_TOPMOST = 0x00040000
            MB_SETFOREGROUND = 0x00010000
            flags = MB_OKCANCEL | MB_ICONERROR | MB_TOPMOST | MB_SETFOREGROUND

            TIMEOUT_MS = 180000  # 3 minutes in milliseconds
            IDOK = 1

            # Try MessageBoxTimeoutW first (available on Windows XP+)
            try:
                MessageBoxTimeoutW = ctypes.windll.user32.MessageBoxTimeoutW
                MessageBoxTimeoutW.argtypes = [
                    ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_wchar_p,
                    ctypes.c_uint, ctypes.c_ushort, ctypes.c_ulong
                ]
                MessageBoxTimeoutW.restype = ctypes.c_int

                result = MessageBoxTimeoutW(0, message, title, flags, 0, TIMEOUT_MS)

                if result == IDOK:
                    logger.info("Human clicked OK (captcha handled)")
                    return True
                else:
                    # IDCANCEL (2) = user clicked Cancel, IDTIMEOUT (32000) = timed out
                    logger.warning(f"Captcha dialog closed without OK (result={result})")
                    return False

            except AttributeError:
                # MessageBoxTimeoutW not available, fallback to regular MessageBoxW with thread timeout
                logger.warning("MessageBoxTimeoutW not available, using thread-based timeout")
                return self._notify_windows_thread_fallback(title, message, flags, TIMEOUT_MS // 1000)

        except Exception as e:
            logger.warning(t('notify.send_failed', error=str(e)))

        # Fallback: terminal bell and sound
        self._terminal_bell()
        sound_thread = threading.Thread(target=self._play_sound, daemon=True)
        sound_thread.start()
        return False

    def _notify_windows_thread_fallback(self, title: str, message: str, flags: int, timeout_sec: int) -> bool:
        """Fallback: run MessageBoxW in a thread with timeout."""
        import ctypes

        IDOK = 1
        result_holder = [None]

        def show_dialog():
            result_holder[0] = ctypes.windll.user32.MessageBoxW(0, message, title, flags)

        dialog_thread = threading.Thread(target=show_dialog, daemon=True)
        dialog_thread.start()
        dialog_thread.join(timeout=timeout_sec)

        if dialog_thread.is_alive():
            # Timeout - dialog still open, no human response
            logger.warning("Captcha dialog timed out (3 min), no human response")
            return False
        elif result_holder[0] == IDOK:
            logger.info("Human clicked OK (captcha handled)")
            return True
        else:
            logger.warning(f"Captcha dialog closed without OK (result={result_holder[0]})")
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
        """Play alarm sound on Windows using winsound (loud, repeating, hard to miss)."""
        try:
            import winsound
            # Alarm pattern: ascending frequency sweep, 2 rounds (~3 seconds total)
            for _ in range(2):
                winsound.Beep(800, 300)
                winsound.Beep(1200, 300)
                winsound.Beep(1600, 300)
                winsound.Beep(2000, 200)
        except ImportError:
            self._terminal_bell()
        except Exception:
            self._terminal_bell()

    def notify_captcha(self, device_id: str, sound: bool = True) -> bool:
        """
        Convenience method to notify about captcha detection.

        Blocks until user confirms or timeout (3 min).

        Args:
            device_id: Device identifier that encountered captcha
            sound: Whether to play sound

        Returns:
            True: User confirmed (captcha handled), can continue
            False: Timeout or failed (no human response), should enter protection mode
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

    Blocks until user confirms or timeout (3 min).

    Args:
        device_id: Device identifier that encountered captcha
        sound: Whether to play sound

    Returns:
        True: User confirmed (captcha handled), can continue
        False: Timeout or failed (no human response), should enter protection mode
    """
    notifier = get_notifier()
    return notifier.notify_captcha(device_id=device_id, sound=sound)
