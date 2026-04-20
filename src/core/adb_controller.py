#!/usr/bin/env python3
"""
ADB command wrapper module.
Provides basic capabilities for Android device control.
"""

import subprocess
import tempfile
import time
import logging
from pathlib import Path
from typing import Optional, List, Tuple

from locales import t

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def _get_subprocess_window_kwargs() -> dict:
    """Hide child console windows on Windows GUI builds."""
    if subprocess.os.name == 'nt':
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


class ADBController:
    """ADB Controller - wraps all ADB commands"""

    def __init__(self, device_id: Optional[str] = None):
        """
        Initialize ADB controller.

        Args:
            device_id: Device ID, auto-detect if None
        """
        self.device_id = device_id
        if not self.device_id:
            self.device_id = self._auto_detect_device()
        # Original IME saved before switching to ADBKeyboard
        self._original_ime: Optional[str] = None
        self._adb_keyboard_active: bool = False

    def _auto_detect_device(self) -> Optional[str]:
        """Auto-detect connected device"""
        devices = self.get_devices()
        if not devices:
            logger.error(t('log.no_device_detected'))
            return None

        if len(devices) > 1:
            logger.warning(t('log.multiple_devices_detected', devices=devices))

        device_id = devices[0]
        logger.info(t('log.device_selected', device_id=device_id))
        return device_id

    def get_devices(self) -> List[str]:
        """Get list of all connected devices"""
        try:
            result = subprocess.run(
                ["adb", "devices"],
                capture_output=True,
                text=True,
                timeout=10,
                **_get_subprocess_window_kwargs(),
            )

            devices = []
            for line in result.stdout.split('\n')[1:]:  # Skip header line
                line = line.strip()
                if line and '\t' in line:
                    device_id = line.split('\t')[0]
                    devices.append(device_id)

            return devices
        except Exception as e:
            logger.error(t('log.get_device_list_failed', error=e))
            return []

    def check_connection(self) -> bool:
        """Check device connection status"""
        if not self.device_id:
            return False

        try:
            result = self._run_adb_command(["shell", "echo", "test"])
            return result.returncode == 0
        except Exception as e:
            logger.error(t('log.device_connection_check_failed', error=e))
            return False

    def get_screen_size(self) -> Optional[Tuple[int, int]]:
        """Get screen resolution"""
        try:
            result = self._run_adb_command(["shell", "wm", "size"])
            if result.returncode == 0:
                # Output format: Physical size: 1080x2400
                output = result.stdout.strip()
                if ":" in output:
                    size_str = output.split(":")[-1].strip()
                    width, height = map(int, size_str.split("x"))
                    logger.info(t('log.screen_resolution', width=width, height=height))
                    return (width, height)
        except Exception as e:
            logger.error(t('log.get_screen_resolution_failed', error=e))
        return None

    def get_current_focus(self) -> Optional[str]:
        """Get current focus application"""
        try:
            result = self._run_adb_command(["shell", "dumpsys", "window", "|", "grep", "mCurrentFocus"])
            if result.returncode == 0:
                focus = result.stdout.strip()
                logger.info(t('log.current_focus', focus=focus))
                return focus
        except Exception as e:
            logger.error(t('log.get_current_focus_failed', error=e))
        return None

    def wake_screen(self) -> bool:
        """Wake up screen"""
        try:
            # KEYCODE_WAKEUP = 224
            result = self._run_adb_command(["shell", "input", "keyevent", "224"])
            time.sleep(1)
            return result.returncode == 0
        except Exception as e:
            logger.error(t('log.wake_screen_failed', error=e))
            return False

    def tap(self, x: int, y: int, max_retries: int = 3) -> bool:
        """
        Tap screen coordinates with retry mechanism.

        Args:
            x: X coordinate
            y: Y coordinate
            max_retries: Maximum retry attempts

        Returns:
            Whether tap was successful
        """
        for attempt in range(1, max_retries + 1):
            try:
                if attempt > 1:
                    logger.info(t('log.tap_coordinate_retry', x=x, y=y, attempt=attempt))
                else:
                    logger.info(t('log.tap_coordinate', x=x, y=y))
                result = self._run_adb_command(["shell", "input", "tap", str(x), str(y)])
                time.sleep(0.5)

                if result.returncode == 0:
                    return True

                # Print error info for debugging
                logger.warning(t('log.tap_return_code', code=result.returncode))
                if result.stdout:
                    logger.warning(t('log.stdout', output=result.stdout.strip()))
                if result.stderr:
                    logger.warning(t('log.stderr', output=result.stderr.strip()))

                # Wait before retry if not last attempt
                if attempt < max_retries:
                    logger.info(t('log.wait_retry'))
                    time.sleep(1)

            except Exception as e:
                logger.error(t('log.tap_exception', error=e))
                if attempt < max_retries:
                    time.sleep(1)

        logger.error(t('log.tap_failed', x=x, y=y, retries=max_retries))
        return False

    def start_activity(self, action: str, data_uri: str) -> bool:
        """Start Activity"""
        try:
            logger.info(t('log.start_activity', action=action, uri=data_uri))
            result = self._run_adb_command([
                "shell", "am", "start",
                "-a", action,
                "-d", data_uri
            ])
            time.sleep(2)
            return result.returncode == 0
        except Exception as e:
            logger.error(t('log.start_activity_failed', error=e))
            return False

    def open_url(self, url: str) -> bool:
        """Open URL (uses system browser or corresponding app)"""
        return self.start_activity("android.intent.action.VIEW", url)

    def _get_u2_device(self):
        """Connect to current device through uiautomator2."""
        try:
            import uiautomator2 as u2

            logger.info(t('log.u2_connecting_device', device_id=self.device_id or 'default'))
            if self.device_id:
                return u2.connect_usb(self.device_id)
            return u2.connect()
        except Exception as e:
            logger.error(t('log.u2_connect_failed', error=e))
            return None

    def _dismiss_xiaomi_browser_dialogs(self, d) -> None:
        """Dismiss known Xiaomi browser popups without failing the flow."""
        try:
            dialog_root = d(resourceId="com.android.browser:id/dialog_root_view")
            if dialog_root.exists:
                cancel_btn = dialog_root.child(text="取消")
                if cancel_btn.exists:
                    cancel_btn.click()
                    logger.info(t('log.xiaomi_browser_dialog_dismissed', name='取消弹框'))
                    time.sleep(1)
        except Exception:
            pass

        try:
            if d(resourceId="com.android.browser:id/btn_agree").exists:
                d(resourceId="com.android.browser:id/btn_agree").click()
                logger.info(t('log.xiaomi_browser_dialog_dismissed', name='同意弹框'))
                time.sleep(1)
        except Exception:
            pass

        try:
            if d(text="“AI搜索”功能上线").exists:
                d(text="“AI搜索”功能上线").click()
                logger.info(t('log.xiaomi_browser_dialog_dismissed', name='AI搜索上线弹框'))
                time.sleep(1)
        except Exception:
            pass

    def _require_u2_exists(self, selector, name: str, timeout: float = 5.0) -> bool:
        """Wait for a selector and log clearly when not found."""
        try:
            if selector.wait(timeout=timeout):
                return True
        except Exception:
            pass
        logger.error(t('log.xiaomi_browser_missing_element', name=name))
        return False

    def _clear_xiaomi_browser_data(self, d) -> bool:
        """Follow the customer-provided Xiaomi browser clear-data flow."""
        logger.info(t('log.xiaomi_browser_clear_data'))
        self._dismiss_xiaomi_browser_dialogs(d)

        mine_tab = d(text="我的")
        mine_tab_alt = d(description="我的")
        if not self._require_u2_exists(mine_tab, "我的", timeout=8.0):
            if mine_tab_alt.exists:
                mine_tab = mine_tab_alt
            else:
                return False
        if not mine_tab.exists:
            return False
        mine_tab.click()
        time.sleep(1)

        self._dismiss_xiaomi_browser_dialogs(d)

        settings_btn = d(resourceId="com.android.browser:id/person_setting")
        if not self._require_u2_exists(settings_btn, "设置按钮"):
            return False
        settings_btn.click()
        time.sleep(1)

        for _ in range(2):
            try:
                d.swipe_ext("up")
            except Exception:
                self.swipe(540, 1800, 540, 600, 300)
            time.sleep(1)

        clear_data_item = d(resourceId="android:id/title", text="清除数据")
        if not self._require_u2_exists(clear_data_item, "清除数据"):
            return False
        clear_data_item.click()
        time.sleep(1)

        clean_btn = d(resourceId="com.android.browser:id/btn_clean")
        fallback_clean_btn = d(resourceId="com.android.browser:id/button")
        if clean_btn.exists:
            clean_btn.click()
        elif fallback_clean_btn.exists:
            fallback_clean_btn.click()
        else:
            logger.error(t('log.xiaomi_browser_missing_element', name='清理按钮'))
            return False
        time.sleep(1)

        confirm_btn = d(resourceId="android:id/button1")
        if not self._require_u2_exists(confirm_btn, "确认按钮"):
            return False
        screenshot_pos = self.get_overlay_button_position()
        if screenshot_pos:
            logger.info(t('log.xiaomi_browser_prefetched_screenshot_pos', x=screenshot_pos[0], y=screenshot_pos[1]))
        confirm_btn.click()
        time.sleep(1)
        if screenshot_pos:
            self.tap(screenshot_pos[0], screenshot_pos[1])
        time.sleep(0.5)
        logger.info(t('log.xiaomi_browser_clear_data_confirmed'))

        self.press_back()
        time.sleep(1)
        self.press_back()
        time.sleep(1)
        self._dismiss_xiaomi_browser_dialogs(d)

        home_tab = d(text="主页")
        if not self._require_u2_exists(home_tab, "主页"):
            return False
        home_tab.click()
        time.sleep(1)
        return True

    def _search_beijing_time_in_xiaomi_browser(self, d) -> bool:
        """Search Beijing time in Xiaomi browser."""
        logger.info(t('log.xiaomi_browser_search_beijing_time'))

        search_hint = d(resourceId="com.android.browser:id/search_hint")
        if not self._require_u2_exists(search_hint, "搜索框入口"):
            return False
        search_hint.click()
        time.sleep(1)

        search_input = d(resourceId="com.android.browser:id/url")
        if not self._require_u2_exists(search_input, "搜索输入框"):
            return False
        search_input.set_text("北京时间")
        time.sleep(1)

        search_btn = d(resourceId="com.android.browser:id/rightText")
        if not self._require_u2_exists(search_btn, "搜索按钮"):
            return False
        search_btn.click()
        time.sleep(3)

        if d(text="中国北京时间 UTC+8").exists:
            logger.info(t('log.xiaomi_browser_beijing_time_ready'))
            return True

        baidu_engine = d(resourceId="com.android.browser:id/tv_engine_name", text="百度")
        if baidu_engine.exists:
            baidu_engine.click()
            time.sleep(3)

        if d(text="中国北京时间 UTC+8").exists:
            logger.info(t('log.xiaomi_browser_beijing_time_ready'))
            return True

        # Some browser versions open the direct website instead of search results.
        if d(textContains="北京时间").exists or d(descriptionContains="北京时间").exists:
            logger.info(t('log.xiaomi_browser_beijing_time_ready'))
            return True

        logger.error(t('log.xiaomi_browser_missing_element', name='北京时间结果页'))
        return False

    def show_beijing_time_with_xiaomi_browser(self) -> bool:
        """Use Xiaomi browser + uiautomator2 to clear data and open Beijing time."""
        d = None
        try:
            logger.info(t('log.xiaomi_browser_flow_start'))
            d = self._get_u2_device()
            if not d:
                return False

            self.force_stop_app('com.android.browser')
            time.sleep(1)
            d.app_start('com.android.browser')
            logger.info(t('log.xiaomi_browser_opened'))
            time.sleep(5)

            if not self._clear_xiaomi_browser_data(d):
                return False

            return self._search_beijing_time_in_xiaomi_browser(d)
        except Exception as e:
            logger.error(t('log.show_beijing_time_failed', error=e))
            return False
        finally:
            if d is not None:
                try:
                    d.stop_uiautomator()
                    time.sleep(2)
                except Exception:
                    pass

    def get_device_brand(self) -> str:
        """
        Get device brand.

        Returns:
            Device brand name (lowercase), e.g., xiaomi, huawei, oppo
        """
        try:
            result = self._run_adb_command(["shell", "getprop", "ro.product.brand"])
            if result.returncode == 0:
                brand = result.stdout.strip().lower()
                logger.info(t('log.device_brand_detected', brand=brand))
                return brand
            else:
                logger.warning(t('log.cannot_get_device_brand'))
                return "unknown"
        except Exception as e:
            logger.error(t('log.get_device_brand_failed', error=e))
            return "unknown"

    def get_device_manufacturer(self) -> str:
        """Get device manufacturer"""
        try:
            result = self._run_adb_command(["shell", "getprop", "ro.product.manufacturer"])
            if result.returncode == 0:
                manufacturer = result.stdout.strip().lower()
                return manufacturer
        except Exception as e:
            logger.error(t('log.get_manufacturer_failed', error=e))
        return "unknown"

    def open_app_store_and_search_taobao(self) -> bool:
        """
        Brand-adaptive open app store and search for Taobao.
        Supports Xiaomi, Huawei, OPPO, vivo, Samsung and other major brands.
        """
        try:
            # Get device brand
            brand = self.get_device_brand()
            logger.info(t('log.device_brand', brand=brand))

            # Brand-specific app store search protocols
            search_urls = {
                "xiaomi": "mimarket://search?q=淘宝",
                "redmi": "mimarket://search?q=淘宝",
                "huawei": "appmarket://search?keyword=淘宝",
                "honor": "appmarket://search?keyword=淘宝",
                "oppo": "oppomarket://search?keyword=淘宝",
                "oneplus": "oppomarket://search?keyword=淘宝",
                "realme": "oppomarket://search?keyword=淘宝",
                "vivo": "vivomarket://search?keyword=淘宝",
                "iqoo": "vivomarket://search?keyword=淘宝",
                "samsung": "samsungapps://SearchDetail/淘宝",
                "meizu": "mstore://search?keyword=淘宝"
            }

            # Get search URL for brand
            search_url = search_urls.get(brand, "market://search?q=淘宝")
            logger.info(t('log.using_search_protocol', url=search_url))

            # Try to open app store search
            result = self._run_adb_command([
                "shell", "am", "start",
                "-a", "android.intent.action.VIEW",
                "-d", search_url
            ])
            time.sleep(4)  # Wait for search results to load

            if result.returncode == 0:
                logger.info(t('log.app_store_search_opened'))
                return True

            # If brand-specific protocol fails, try generic protocol
            if brand != "unknown" and brand in search_urls:
                logger.warning(t('log.brand_protocol_failed_trying_generic'))
                generic_url = "market://search?q=淘宝"
                result = self._run_adb_command([
                    "shell", "am", "start",
                    "-a", "android.intent.action.VIEW",
                    "-d", generic_url
                ])
                time.sleep(4)

                if result.returncode == 0:
                    logger.info(t('log.generic_protocol_success'))
                    return True

            logger.error(t('log.open_app_store_search_failed'))
            return False

        except Exception as e:
            logger.error(t('log.open_app_store_search_exception', error=e))
            return False

    def open_shishibao_app(self) -> bool:
        """
        Open "Shishibao" App.

        Package: com.a1010bao.web.rdbao
        Main Activity: com.a1010bao.web.rdbao.LaunchActivity

        Returns:
            Whether successfully opened
        """
        try:
            logger.info(t('log.opening_shishibao'))

            result = self._run_adb_command([
                "shell", "am", "start",
                "-n", "com.a1010bao.web.rdbao/com.a1010bao.web.rdbao.LaunchActivity"
            ])
            time.sleep(3)  # Wait for app to start

            if result.returncode == 0:
                logger.info(t('log.shishibao_opened'))
                return True
            else:
                logger.error(t('log.shishibao_open_failed', code=result.returncode))
                return False

        except Exception as e:
            logger.error(t('log.shishibao_open_exception', error=e))
            return False

    def launch_taobao_with_product(self, product_url: str) -> bool:
        """
        Open product link in running Taobao app.
        Uses ACTION_VIEW Intent without restarting app to avoid app switching issues.

        Args:
            product_url: Product link (supports full or short links)

        Returns:
            Whether successfully opened product
        """
        try:
            logger.info(t('log.open_product_in_taobao', url=product_url))

            # Use ACTION_VIEW Intent to open product in foreground Taobao
            # Without -S (no restart) and -n (no specific Activity)
            result = self._run_adb_command([
                "shell", "am", "start",
                "-a", "android.intent.action.VIEW",
                "-d", product_url
            ])
            time.sleep(3)

            if result.returncode == 0:
                logger.info(t('log.product_opened_in_taobao'))
                return True
            else:
                logger.error(t('log.open_product_failed', code=result.returncode))
                logger.error(t('log.open_product_error', error=result.stderr))
                return False
        except Exception as e:
            logger.error(t('log.open_product_exception', error=e))
            return False

    def input_text(self, text: str) -> bool:
        """
        Input text via ADBKeyboard broadcast (supports Unicode/Chinese/special chars).

        Falls back to legacy 'adb shell input text' if ADBKeyboard is not active.

        Args:
            text: Text to input

        Returns:
            Whether successful
        """
        try:
            logger.info(t('log.input_text', text=text))

            if self._adb_keyboard_active:
                # Use ADBKeyboard broadcast - supports all Unicode characters
                result = self._run_adb_command([
                    "shell", "am", "broadcast",
                    "-a", "ADB_INPUT_TEXT",
                    "--es", "msg", text
                ])
                time.sleep(0.5)
                return result.returncode == 0
            else:
                # Fallback: legacy adb input text (ASCII only)
                escaped_text = text.replace(" ", "%s")
                result = self._run_adb_command(["shell", "input", "text", escaped_text])
                time.sleep(0.5)
                return result.returncode == 0
        except Exception as e:
            logger.error(t('log.input_text_failed', error=e))
            return False

    def press_key(self, keycode: int) -> bool:
        """
        Press key.

        Args:
            keycode: Key code
                66 = ENTER
                4 = BACK
                3 = HOME
                82 = MENU

        Returns:
            Whether successful
        """
        try:
            logger.info(t('log.press_key', keycode=keycode))
            result = self._run_adb_command(["shell", "input", "keyevent", str(keycode)])
            time.sleep(0.5)
            return result.returncode == 0
        except Exception as e:
            logger.error(t('log.press_key_failed', error=e))
            return False

    def press_enter(self) -> bool:
        """Press Enter key"""
        return self.press_key(66)

    def press_back(self) -> bool:
        """Press Back key"""
        return self.press_key(4)

    def press_home(self) -> bool:
        """Press Home key"""
        return self.press_key(3)

    def dump_ui_hierarchy(self, output_path: str = "/sdcard/window_dump.xml", use_compressed: bool = True) -> bool:
        """
        Dump UI hierarchy (enhanced version, optimized for Xiaomi MIUI and recording scenarios).

        Args:
            output_path: Output file path
            use_compressed: Whether to use --compressed parameter (recommended, improves success rate during recording)

        Returns:
            Whether successfully dumped
        """
        max_attempts = 5  # Increased from 3 to handle recording instability

        # Detect if Xiaomi device
        is_xiaomi = self.get_device_brand() in ['xiaomi', 'redmi']
        if is_xiaomi:
            logger.info(t('log.xiaomi_device_detected'))

        for attempt in range(1, max_attempts + 1):
            try:
                logger.info(t('log.dump_ui_hierarchy_attempt', attempt=attempt, max_attempts=max_attempts))

                # Delete old dump file before each attempt to prevent reading stale cache
                # when uiautomator dump silently fails (returns success but doesn't update file)
                self.delete_file(output_path)

                # Build command, prefer --compressed (improves success rate during recording)
                if use_compressed:
                    result = self._run_adb_command(["shell", "uiautomator", "dump", "--compressed", output_path])
                else:
                    result = self._run_adb_command(["shell", "uiautomator", "dump", output_path])

                if result.returncode == 0:
                    # Verify file was actually created (uiautomator may return success but not create file)
                    time.sleep(0.5)  # Reduced from 1s to improve performance
                    if self.file_exists(output_path):
                        logger.info(t('log.ui_hierarchy_dump_success'))
                        return True
                    else:
                        # Silent failure: command succeeded but file not created
                        logger.warning(f"dump command returned success but file not created, attempt {attempt}/{max_attempts}")
                        if attempt < max_attempts:
                            # Progressive wait: 2s, 3s, 4s, 5s (let screen recording stabilize)
                            wait_time = 1 + attempt
                            time.sleep(wait_time)
                        continue

                # Check for known MIUI theme compatibility bug on first Xiaomi failure
                if attempt == 1 and is_xiaomi and result.stderr and "theme_compatibility" in result.stderr:
                    logger.info(t('log.miui_theme_bug_retry'))
                    # Retry immediately without waiting
                    continue

                # Log detailed error for other cases
                logger.warning(t('log.dump_attempt_failed', attempt=attempt, code=result.returncode))
                if result.stdout:
                    logger.warning(t('log.stdout', output=result.stdout.strip()))
                if result.stderr:
                    # Limit error message length to avoid log overflow
                    stderr_msg = result.stderr.strip()
                    if len(stderr_msg) > 500:
                        stderr_msg = stderr_msg[:500] + "... (truncated)"
                    logger.warning(t('log.stderr', output=stderr_msg))

                # Wait before retry if not last attempt
                if attempt < max_attempts:
                    logger.info(t('log.wait_2s_retry'))
                    time.sleep(2)

            except Exception as e:
                logger.error(t('log.dump_ui_hierarchy_exception', attempt=attempt, error=e))
                if attempt < max_attempts:
                    time.sleep(2)

        logger.error(t('log.dump_ui_hierarchy_failed', attempts=max_attempts))
        return False

    def pull_file(self, remote_path: str, local_path: str) -> bool:
        """Pull file from device"""
        try:
            logger.info(t('log.pull_file', remote=remote_path, local=local_path))
            result = self._run_adb_command(["pull", remote_path, local_path])
            return result.returncode == 0
        except Exception as e:
            logger.error(t('log.pull_file_failed', error=e))
            return False

    def push_file(self, local_path: str, remote_path: str) -> bool:
        """Push file to device"""
        try:
            logger.info(t('log.push_file', local=local_path, remote=remote_path))
            result = self._run_adb_command(["push", local_path, remote_path])
            return result.returncode == 0
        except Exception as e:
            logger.error(t('log.push_file_failed', error=e))
            return False

    def file_exists(self, remote_path: str) -> bool:
        """Check if file exists on device"""
        try:
            result = self._run_adb_command(["shell", "ls", remote_path])
            return result.returncode == 0
        except Exception as e:
            return False

    def delete_file(self, remote_path: str) -> bool:
        """Delete file on device"""
        try:
            logger.info(t('log.delete_file', path=remote_path))
            result = self._run_adb_command(["shell", "rm", remote_path])
            return result.returncode == 0
        except Exception as e:
            logger.error(t('log.delete_file_failed', error=e))
            return False

    def get_file_size(self, remote_path: str) -> Optional[int]:
        """Get file size on device (bytes)"""
        try:
            result = self._run_adb_command(["shell", "ls", "-l", remote_path])
            if result.returncode == 0:
                # Output format: -rw-rw---- 1 shell shell 12345 2026-01-16 12:00 filename
                parts = result.stdout.strip().split()
                if len(parts) >= 5:
                    size = int(parts[4])
                    return size
        except Exception as e:
            logger.error(t('log.get_file_size_failed', error=e))
        return None

    def get_process_pid(self, process_name: str) -> Optional[int]:
        """Get process PID (fixed version, supports pipe commands)"""
        try:
            # Method 1: Get all processes then filter in Python (more reliable)
            result = self._run_adb_command(["shell", "ps"])
            if result.returncode == 0 and result.stdout.strip():
                # Output format: USER PID PPID VSZ RSS WCHAN ADDR S NAME
                lines = result.stdout.strip().split('\n')
                for line in lines:
                    if process_name in line:
                        parts = line.split()
                        if len(parts) >= 2:
                            try:
                                pid = int(parts[1])
                                logger.info(t('log.process_found', name=process_name, pid=pid))
                                return pid
                            except ValueError:
                                # PID may not be in second column, continue searching
                                continue
        except Exception as e:
            logger.error(t('log.get_process_pid_failed', error=e))
        return None

    def kill_process(self, pid: int, signal: str = "INT") -> bool:
        """Kill process"""
        try:
            logger.info(t('log.kill_process', pid=pid, signal=signal))
            result = self._run_adb_command(["shell", "kill", f"-{signal}", str(pid)])
            time.sleep(1)
            return result.returncode == 0
        except Exception as e:
            logger.error(t('log.kill_process_failed', error=e))
            return False

    def enable_visual_feedback(self) -> bool:
        """
        Enable touch visual feedback (for forensic recording).
        - Shows touch points (white circles)
        """
        try:
            logger.info(t('log.enable_visual_feedback'))
            # Only show touch points, not pointer trails
            result = self._run_adb_command(["shell", "settings", "put", "system", "show_touches", "1"])

            if result.returncode == 0:
                logger.info(t('log.visual_feedback_enabled'))
                return True
            else:
                logger.warning(t('log.visual_feedback_failed', error=''))
                return False
        except Exception as e:
            logger.error(t('log.visual_feedback_failed', error=e))
            return False

    def disable_visual_feedback(self) -> bool:
        """
        Disable touch visual feedback.
        """
        try:
            logger.info(t('log.disable_visual_feedback'))
            # Only disable touch point display
            result = self._run_adb_command(["shell", "settings", "put", "system", "show_touches", "0"])

            if result.returncode == 0:
                logger.info(t('log.visual_feedback_disabled'))
                return True
            else:
                logger.warning(t('log.visual_feedback_disable_failed', error=''))
                return False
        except Exception as e:
            logger.error(t('log.visual_feedback_disable_failed', error=e))
            return False

    def take_screenshot(self, remote_path: str = "/sdcard/screenshot.png") -> bool:
        """
        Take screenshot.

        Args:
            remote_path: Path to save screenshot on device

        Returns:
            Whether screenshot was successful
        """
        try:
            logger.info(t('log.take_screenshot', path=remote_path))
            result = self._run_adb_command(["shell", "screencap", "-p", remote_path])
            time.sleep(0.5)
            return result.returncode == 0
        except Exception as e:
            logger.error(t('log.screenshot_failed', error=e))
            return False

    def take_screenshot_to_file(self, local_path: str = None) -> Optional[str]:
        """
        Take a screenshot and pull it to a local file.

        Args:
            local_path: Optional local file path. If omitted, generate a temp path.

        Returns:
            Local screenshot path on success, otherwise None
        """
        safe_id = (self.device_id or "default").replace(':', '_').replace('/', '_')
        temp_root = Path(tempfile.gettempdir()) / "automated_forensic_tool" / "ocr" / safe_id
        temp_root.mkdir(parents=True, exist_ok=True)

        target_path = Path(local_path) if local_path else temp_root / f"screenshot_{int(time.time() * 1000)}.png"
        target_path.parent.mkdir(parents=True, exist_ok=True)

        remote_path = f"/sdcard/ocr_capture_{int(time.time() * 1000)}.png"

        try:
            if not self.take_screenshot(remote_path):
                logger.warning(t('log.ocr_device_capture_failed', path=remote_path))
                return None

            if not self.pull_file(remote_path, str(target_path)):
                logger.warning(t('log.ocr_pull_local_failed', path=target_path))
                try:
                    target_path.unlink()
                except FileNotFoundError:
                    pass
                return None

            logger.info(t('log.ocr_screenshot_saved_local', path=target_path))
            return str(target_path)
        except Exception as e:
            logger.error(t('log.screenshot_failed', error=e))
            try:
                target_path.unlink()
            except FileNotFoundError:
                pass
            return None
        finally:
            self.delete_file(remote_path)

    def force_stop_app(self, package_name: str) -> bool:
        """
        Force stop application process.

        Args:
            package_name: Application package name

        Returns:
            Whether successful
        """
        try:
            logger.info(t('log.force_stop_app', package=package_name))
            result = self._run_adb_command(["shell", "am", "force-stop", package_name])
            time.sleep(0.5)
            return result.returncode == 0
        except Exception as e:
            logger.error(t('log.force_stop_failed', error=e))
            return False

    def launch_app(self, package_name: str) -> bool:
        """
        Launch app directly via ADB monkey command.

        Uses monkey to launch app's main activity, ensuring it opens to the default home page
        rather than any promotional/marketing tab.

        Args:
            package_name: Application package name (e.g., "com.taobao.taobao")

        Returns:
            Whether launch was successful
        """
        try:
            logger.info(t('log.launch_app_direct', package=package_name))
            result = self._run_adb_command([
                "shell", "monkey", "-p", package_name,
                "-c", "android.intent.category.LAUNCHER", "1"
            ])
            time.sleep(1)
            return result.returncode == 0
        except Exception as e:
            logger.error(t('log.launch_app_direct_failed', package=package_name, error=e))
            return False

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> bool:
        """
        Perform swipe operation.

        Args:
            x1: Start x coordinate
            y1: Start y coordinate
            x2: End x coordinate
            y2: End y coordinate
            duration_ms: Swipe duration (milliseconds)

        Returns:
            Whether successful
        """
        try:
            logger.debug(t('log.swipe', x1=x1, y1=y1, x2=x2, y2=y2, duration=duration_ms))
            result = self._run_adb_command([
                "shell", "input", "swipe",
                str(x1), str(y1), str(x2), str(y2), str(duration_ms)
            ])
            return result.returncode == 0
        except Exception as e:
            logger.error(t('log.swipe_failed', error=e))
            return False

    def run_command(self, command: str) -> bool:
        """
        Execute arbitrary shell command.

        Args:
            command: Command to execute

        Returns:
            Whether successful
        """
        try:
            result = self._run_adb_command(["shell"] + command.split())
            return result.returncode == 0
        except Exception as e:
            logger.error(t('log.run_command_failed', error=e))
            return False

    def get_overlay_button_position(self) -> Optional[Tuple[int, int]]:
        """
        Get Shishibao floating screenshot button coordinates.

        Parses APPLICATION_OVERLAY type windows from dumpsys window windows,
        finds floating button position in bottom-right corner.

        Returns:
            (x, y) coordinate tuple, None if not found
        """
        import re

        try:
            logger.info(t('log.get_overlay_button_position'))

            # Get screen size to determine bottom-right corner
            screen_size = self.get_screen_size()
            if not screen_size:
                logger.error(t('log.cannot_get_screen_size'))
                return None

            screen_width, screen_height = screen_size

            # Execute dumpsys command
            result = self._run_adb_command(["shell", "dumpsys", "window", "windows"])
            if result.returncode != 0:
                logger.error(t('log.dumpsys_window_failed'))
                return None

            output = result.stdout

            # Multiple pattern matching for APPLICATION_OVERLAY windows
            # Pattern 1: Get window position via mFrame (more reliable)
            # Format: mFrame=[x1,y1][x2,y2] ... ty=APPLICATION_OVERLAY
            overlay_positions = []

            # Split by window blocks, find those containing APPLICATION_OVERLAY
            window_blocks = re.split(r'Window #\d+', output)
            for block in window_blocks:
                if 'APPLICATION_OVERLAY' in block:
                    # Try to extract coordinates from mFrame or frame (support both formats)
                    frame_match = re.search(r'(?:mFrame|frame)=\[(\d+),(\d+)\]\[(\d+),(\d+)\]', block)
                    if not frame_match:
                        # Backup: extract from Frames: line
                        frame_match = re.search(r'Frames:.*?frame=\[(\d+),(\d+)\]\[(\d+),(\d+)\]', block)
                    if frame_match:
                        x1, y1, x2, y2 = map(int, frame_match.groups())
                        # Calculate center point
                        center_x = (x1 + x2) // 2
                        center_y = (y1 + y2) // 2
                        overlay_positions.append((center_x, center_y, x1, y1, x2, y2))
                        logger.info(t('log.found_overlay_window', x1=x1, y1=y1, x2=x2, y2=y2, cx=center_x, cy=center_y))

            if not overlay_positions:
                # Backup mode: get via mAttrs
                pattern = r'mAttrs=.*?\((\d+),(\d+)\).*?ty=APPLICATION_OVERLAY'
                matches = re.findall(pattern, output, re.DOTALL)
                if matches:
                    for match in matches:
                        x, y = int(match[0]), int(match[1])
                        overlay_positions.append((x, y, x, y, x, y))
                        logger.info(t('log.backup_mode_found_overlay', x=x, y=y))

            if not overlay_positions:
                logger.warning(t('log.no_overlay_window_found'))
                return None

            # Filter for buttons in bottom-right corner (center x > half screen width and y > half screen height)
            for pos in overlay_positions:
                center_x, center_y = pos[0], pos[1]
                if center_x > screen_width // 2 and center_y > screen_height // 2:
                    logger.info(t('log.found_shishibao_button', x=center_x, y=center_y))
                    return (center_x, center_y)

            # If not found in bottom-right, return first APPLICATION_OVERLAY (button may have been moved)
            center_x, center_y = overlay_positions[0][0], overlay_positions[0][1]
            logger.warning(t('log.no_button_in_bottom_right', x=center_x, y=center_y))
            return (center_x, center_y)

        except Exception as e:
            logger.error(t('log.get_overlay_button_failed', error=e))
            return None

    # ==================== ADBKeyboard IME ====================

    def setup_adb_keyboard(self) -> bool:
        """
        Install and enable ADBKeyboard for Unicode text input.

        Automatically installs APK if not present, saves original IME,
        and switches to ADBKeyboard.

        Returns:
            Whether setup was successful
        """
        if self._adb_keyboard_active:
            logger.info("ADBKeyboard already active, skipping setup")
            return True

        try:
            adb_ime = "com.android.adbkeyboard/.AdbIME"

            # Check if ADBKeyboard is already installed
            result = self._run_adb_command(["shell", "ime", "list", "-s"])
            installed = adb_ime.split('/')[0] in result.stdout

            if not installed:
                # Find APK path
                from pathlib import Path
                apk_path = Path(__file__).parent.parent.parent / 'tools' / 'ADBKeyboard.apk'
                if not apk_path.exists():
                    logger.error(f"ADBKeyboard.apk not found at {apk_path}")
                    return False

                logger.info("Installing ADBKeyboard...")
                install_result = self._run_adb_command(["install", str(apk_path)])
                if install_result.returncode != 0:
                    logger.error(f"ADBKeyboard install failed: {install_result.stderr}")
                    return False
                logger.info("ADBKeyboard installed successfully")

            # Save original IME
            result = self._run_adb_command(["shell", "settings", "get", "secure", "default_input_method"])
            original = result.stdout.strip()
            if original and adb_ime not in original:
                self._original_ime = original
                logger.info(f"Saved original IME: {self._original_ime}")

            # Enable and set ADBKeyboard
            self._run_adb_command(["shell", "ime", "enable", adb_ime])
            self._run_adb_command(["shell", "ime", "set", adb_ime])
            self._adb_keyboard_active = True
            logger.info("ADBKeyboard enabled and set as current IME")
            return True

        except Exception as e:
            logger.error(f"Failed to setup ADBKeyboard: {e}")
            return False

    def restore_original_ime(self) -> bool:
        """
        Restore the original input method.

        Returns:
            Whether restore was successful
        """
        if not self._original_ime:
            logger.info("No original IME saved, skipping restore")
            return True

        try:
            logger.info(f"Restoring original IME: {self._original_ime}")
            self._run_adb_command(["shell", "ime", "set", self._original_ime])
            self._adb_keyboard_active = False
            logger.info("Original IME restored")
            return True
        except Exception as e:
            logger.error(f"Failed to restore IME: {e}")
            return False

    def _run_adb_command(self, args: List[str]) -> subprocess.CompletedProcess:
        """Execute ADB command"""
        cmd = ["adb"]
        if self.device_id:
            cmd.extend(["-s", self.device_id])
        cmd.extend(args)

        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,
            **_get_subprocess_window_kwargs(),
        )


if __name__ == "__main__":
    # Test code
    controller = ADBController()

    if controller.device_id:
        logger.info(t('log.device_connected', device_id=controller.device_id))

        # Test basic functionality
        if controller.check_connection():
            logger.info(t('log.device_connection_normal'))

        screen_size = controller.get_screen_size()
        if screen_size:
            logger.info(t('log.screen_resolution_info', width=screen_size[0], height=screen_size[1]))
    else:
        logger.error(t('log.device_not_connected'))
