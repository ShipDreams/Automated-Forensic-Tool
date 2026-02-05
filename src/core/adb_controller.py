#!/usr/bin/env python3
"""
ADB 命令封装模块
提供 Android 设备控制的基础能力
"""

import subprocess
import time
import logging
from typing import Optional, List, Tuple

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class ADBController:
    """ADB 控制器，封装所有 ADB 命令"""

    def __init__(self, device_id: Optional[str] = None):
        """
        初始化 ADB 控制器

        Args:
            device_id: 设备 ID，如果为 None 则自动检测
        """
        self.device_id = device_id
        if not self.device_id:
            self.device_id = self._auto_detect_device()

    def _auto_detect_device(self) -> Optional[str]:
        """自动检测连接的设备"""
        devices = self.get_devices()
        if not devices:
            logger.error("未检测到连接的设备")
            return None

        if len(devices) > 1:
            logger.warning(f"检测到多个设备: {devices}，使用第一个设备")

        device_id = devices[0]
        logger.info(f"自动选择设备: {device_id}")
        return device_id

    def get_devices(self) -> List[str]:
        """获取所有连接的设备列表"""
        try:
            result = subprocess.run(
                ["adb", "devices"],
                capture_output=True,
                text=True,
                timeout=10
            )

            devices = []
            for line in result.stdout.split('\n')[1:]:  # 跳过第一行标题
                line = line.strip()
                if line and '\t' in line:
                    device_id = line.split('\t')[0]
                    devices.append(device_id)

            return devices
        except Exception as e:
            logger.error(f"获取设备列表失败: {e}")
            return []

    def check_connection(self) -> bool:
        """检查设备连接状态"""
        if not self.device_id:
            return False

        try:
            result = self._run_adb_command(["shell", "echo", "test"])
            return result.returncode == 0
        except Exception as e:
            logger.error(f"设备连接检查失败: {e}")
            return False

    def get_screen_size(self) -> Optional[Tuple[int, int]]:
        """获取屏幕分辨率"""
        try:
            result = self._run_adb_command(["shell", "wm", "size"])
            if result.returncode == 0:
                # 输出格式: Physical size: 1080x2400
                output = result.stdout.strip()
                if ":" in output:
                    size_str = output.split(":")[-1].strip()
                    width, height = map(int, size_str.split("x"))
                    logger.info(f"屏幕分辨率: {width}x{height}")
                    return (width, height)
        except Exception as e:
            logger.error(f"获取屏幕分辨率失败: {e}")
        return None

    def get_current_focus(self) -> Optional[str]:
        """获取当前焦点应用"""
        try:
            result = self._run_adb_command(["shell", "dumpsys", "window", "|", "grep", "mCurrentFocus"])
            if result.returncode == 0:
                focus = result.stdout.strip()
                logger.info(f"当前焦点: {focus}")
                return focus
        except Exception as e:
            logger.error(f"获取当前焦点失败: {e}")
        return None

    def wake_screen(self) -> bool:
        """唤醒屏幕"""
        try:
            # KEYCODE_WAKEUP = 224
            result = self._run_adb_command(["shell", "input", "keyevent", "224"])
            time.sleep(1)
            return result.returncode == 0
        except Exception as e:
            logger.error(f"唤醒屏幕失败: {e}")
            return False

    def tap(self, x: int, y: int, max_retries: int = 3) -> bool:
        """
        点击屏幕坐标（带重试机制）

        Args:
            x: X 坐标
            y: Y 坐标
            max_retries: 最大重试次数

        Returns:
            是否成功点击
        """
        for attempt in range(1, max_retries + 1):
            try:
                logger.info(f"点击坐标: ({x}, {y})" + (f" (第 {attempt} 次尝试)" if attempt > 1 else ""))
                result = self._run_adb_command(["shell", "input", "tap", str(x), str(y)])
                time.sleep(0.5)

                if result.returncode == 0:
                    return True

                # 打印错误信息以便调试
                logger.warning(f"点击命令返回码: {result.returncode}")
                if result.stdout:
                    logger.warning(f"stdout: {result.stdout.strip()}")
                if result.stderr:
                    logger.warning(f"stderr: {result.stderr.strip()}")

                # 如果不是最后一次尝试，等待后重试
                if attempt < max_retries:
                    logger.info(f"等待 1 秒后重试...")
                    time.sleep(1)

            except Exception as e:
                logger.error(f"点击异常: {e}")
                if attempt < max_retries:
                    time.sleep(1)

        logger.error(f"点击坐标 ({x}, {y}) 失败，已尝试 {max_retries} 次")
        return False

    def start_activity(self, action: str, data_uri: str) -> bool:
        """启动 Activity"""
        try:
            logger.info(f"启动 Activity: action={action}, uri={data_uri}")
            result = self._run_adb_command([
                "shell", "am", "start",
                "-a", action,
                "-d", data_uri
            ])
            time.sleep(2)
            return result.returncode == 0
        except Exception as e:
            logger.error(f"启动 Activity 失败: {e}")
            return False

    def open_url(self, url: str) -> bool:
        """打开 URL（会使用系统浏览器或对应的 App）"""
        return self.start_activity("android.intent.action.VIEW", url)

    def get_device_brand(self) -> str:
        """
        获取设备品牌

        Returns:
            设备品牌名（小写），如 xiaomi, huawei, oppo 等
        """
        try:
            result = self._run_adb_command(["shell", "getprop", "ro.product.brand"])
            if result.returncode == 0:
                brand = result.stdout.strip().lower()
                logger.info(f"检测到设备品牌: {brand}")
                return brand
            else:
                logger.warning("无法获取设备品牌，使用通用方案")
                return "unknown"
        except Exception as e:
            logger.error(f"获取设备品牌失败: {e}")
            return "unknown"

    def get_device_manufacturer(self) -> str:
        """获取设备制造商"""
        try:
            result = self._run_adb_command(["shell", "getprop", "ro.product.manufacturer"])
            if result.returncode == 0:
                manufacturer = result.stdout.strip().lower()
                return manufacturer
        except Exception as e:
            logger.error(f"获取设备制造商失败: {e}")
        return "unknown"

    def open_app_store_and_search_taobao(self) -> bool:
        """
        品牌自适应打开应用商店并搜索淘宝
        支持小米、华为、OPPO、vivo、三星等主流品牌
        """
        try:
            # 获取设备品牌
            brand = self.get_device_brand()
            logger.info(f"设备品牌: {brand}")

            # 品牌对应的应用商店搜索协议
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

            # 获取品牌对应的搜索URL
            search_url = search_urls.get(brand, "market://search?q=淘宝")
            logger.info(f"使用搜索协议: {search_url}")

            # 尝试打开应用商店搜索
            result = self._run_adb_command([
                "shell", "am", "start",
                "-a", "android.intent.action.VIEW",
                "-d", search_url
            ])
            time.sleep(4)  # 等待搜索结果加载

            if result.returncode == 0:
                logger.info("✓ 应用商店搜索已打开")
                return True

            # 如果品牌特定协议失败，尝试通用协议
            if brand != "unknown" and brand in search_urls:
                logger.warning(f"品牌特定协议失败，尝试通用协议...")
                generic_url = "market://search?q=淘宝"
                result = self._run_adb_command([
                    "shell", "am", "start",
                    "-a", "android.intent.action.VIEW",
                    "-d", generic_url
                ])
                time.sleep(4)

                if result.returncode == 0:
                    logger.info("✓ 使用通用协议打开成功")
                    return True

            logger.error("✗ 打开应用商店搜索失败")
            return False

        except Exception as e:
            logger.error(f"打开应用商店搜索失败: {e}")
            return False

    def open_shishibao_app(self) -> bool:
        """
        打开"实时保"App

        包名: com.a1010bao.web.rdbao
        主Activity: com.a1010bao.web.rdbao.LaunchActivity

        Returns:
            是否成功打开
        """
        try:
            logger.info("打开实时保 App...")

            result = self._run_adb_command([
                "shell", "am", "start",
                "-n", "com.a1010bao.web.rdbao/com.a1010bao.web.rdbao.LaunchActivity"
            ])
            time.sleep(3)  # 等待App启动

            if result.returncode == 0:
                logger.info("✓ 实时保 App 已打开")
                return True
            else:
                logger.error(f"✗ 打开实时保 App 失败，返回码: {result.returncode}")
                return False

        except Exception as e:
            logger.error(f"打开实时保 App 失败: {e}")
            return False

    def launch_taobao_with_product(self, product_url: str) -> bool:
        """
        在已运行的淘宝 App 中打开商品链接
        使用 ACTION_VIEW Intent，不重启应用，避免应用切换问题

        Args:
            product_url: 商品链接（支持完整链接或短链接）

        Returns:
            是否成功打开商品
        """
        try:
            logger.info(f"在淘宝中打开商品: {product_url}")

            # 使用 ACTION_VIEW Intent 在前台淘宝中打开商品
            # 不使用 -S（不重启）和 -n（不指定 Activity）
            result = self._run_adb_command([
                "shell", "am", "start",
                "-a", "android.intent.action.VIEW",
                "-d", product_url
            ])
            time.sleep(3)

            if result.returncode == 0:
                logger.info("✓ 商品链接已在淘宝中打开")
                return True
            else:
                logger.error(f"打开商品失败，返回码: {result.returncode}")
                logger.error(f"错误输出: {result.stderr}")
                return False
        except Exception as e:
            logger.error(f"打开商品失败: {e}")
            return False

    def input_text(self, text: str) -> bool:
        """
        输入文本（增强版，支持 URL 等特殊字符）

        Args:
            text: 要输入的文本

        Returns:
            是否成功
        """
        try:
            logger.info(f"输入文本: {text}")

            # 对于 URL 或包含特殊字符的文本，使用更安全的输入方式
            # 将文本中的特殊字符进行转义
            # 空格 -> %s, & -> \&, 其他特殊字符保持原样
            escaped_text = text.replace(" ", "%s")

            # 对于 URL 中常见的特殊字符，使用双引号包裹
            # 避免 shell 解释问题
            special_chars = ['&', '?', '=', '/', ':', '.', '-', '_']
            has_special = any(char in text for char in special_chars)

            if has_special:
                # 使用 input text 命令直接输入，ADB 会自动处理转义
                result = self._run_adb_command(["shell", "input", "text", escaped_text])
            else:
                result = self._run_adb_command(["shell", "input", "text", escaped_text])

            time.sleep(0.5)
            return result.returncode == 0
        except Exception as e:
            logger.error(f"输入文本失败: {e}")
            return False

    def press_key(self, keycode: int) -> bool:
        """
        按键操作

        Args:
            keycode: 按键码
                66 = ENTER
                4 = BACK
                3 = HOME
                82 = MENU

        Returns:
            是否成功
        """
        try:
            logger.info(f"按键: keycode={keycode}")
            result = self._run_adb_command(["shell", "input", "keyevent", str(keycode)])
            time.sleep(0.5)
            return result.returncode == 0
        except Exception as e:
            logger.error(f"按键失败: {e}")
            return False

    def press_enter(self) -> bool:
        """按回车键"""
        return self.press_key(66)

    def press_back(self) -> bool:
        """按返回键"""
        return self.press_key(4)

    def press_home(self) -> bool:
        """按Home键"""
        return self.press_key(3)

    def dump_ui_hierarchy(self, output_path: str = "/sdcard/window_dump.xml", use_compressed: bool = True) -> bool:
        """
        导出 UI 层级结构（增强版，针对小米 MIUI 和录屏场景优化）

        Args:
            output_path: 输出文件路径
            use_compressed: 是否使用 --compressed 参数（推荐，可提高录屏期间的成功率）

        Returns:
            是否成功导出
        """
        max_attempts = 3

        # 检测是否为小米设备
        is_xiaomi = self.get_device_brand() in ['xiaomi', 'redmi']
        if is_xiaomi:
            logger.info("检测到小米设备，首次 dump 可能因 MIUI 主题 bug 失败（正常现象）")

        for attempt in range(1, max_attempts + 1):
            try:
                logger.info(f"导出 UI 层级结构（第 {attempt}/{max_attempts} 次尝试）...")

                # 构建命令，优先使用 --compressed（提高录屏期间成功率）
                if use_compressed:
                    result = self._run_adb_command(["shell", "uiautomator", "dump", "--compressed", output_path])
                else:
                    result = self._run_adb_command(["shell", "uiautomator", "dump", output_path])

                if result.returncode == 0:
                    logger.info("✓ UI 层级导出成功")
                    time.sleep(1)
                    return True

                # 小米设备第一次失败检查是否为已知的主题兼容性 bug
                if attempt == 1 and is_xiaomi and result.stderr and "theme_compatibility" in result.stderr:
                    logger.info("检测到 MIUI 主题兼容性问题（已知 bug），立即重试...")
                    # 立即重试，不等待
                    continue

                # 其他情况记录详细错误
                logger.warning(f"第 {attempt} 次尝试失败，返回码: {result.returncode}")
                if result.stdout:
                    logger.warning(f"stdout: {result.stdout.strip()}")
                if result.stderr:
                    # 限制错误信息长度，避免日志过长
                    stderr_msg = result.stderr.strip()
                    if len(stderr_msg) > 500:
                        stderr_msg = stderr_msg[:500] + "... (省略部分错误信息)"
                    logger.warning(f"stderr: {stderr_msg}")

                # 如果不是最后一次尝试，等待后重试
                if attempt < max_attempts:
                    logger.info(f"等待 2 秒后重试...")
                    time.sleep(2)

            except Exception as e:
                logger.error(f"导出 UI 层级异常（第 {attempt} 次）: {e}")
                if attempt < max_attempts:
                    time.sleep(2)

        logger.error(f"经过 {max_attempts} 次尝试仍无法导出 UI 层级")
        return False

    def pull_file(self, remote_path: str, local_path: str) -> bool:
        """从设备拉取文件"""
        try:
            logger.info(f"拉取文件: {remote_path} -> {local_path}")
            result = self._run_adb_command(["pull", remote_path, local_path])
            return result.returncode == 0
        except Exception as e:
            logger.error(f"拉取文件失败: {e}")
            return False

    def push_file(self, local_path: str, remote_path: str) -> bool:
        """推送文件到设备"""
        try:
            logger.info(f"推送文件: {local_path} -> {remote_path}")
            result = self._run_adb_command(["push", local_path, remote_path])
            return result.returncode == 0
        except Exception as e:
            logger.error(f"推送文件失败: {e}")
            return False

    def file_exists(self, remote_path: str) -> bool:
        """检查设备上文件是否存在"""
        try:
            result = self._run_adb_command(["shell", "ls", remote_path])
            return result.returncode == 0
        except Exception as e:
            return False

    def delete_file(self, remote_path: str) -> bool:
        """删除设备上的文件"""
        try:
            logger.info(f"删除文件: {remote_path}")
            result = self._run_adb_command(["shell", "rm", remote_path])
            return result.returncode == 0
        except Exception as e:
            logger.error(f"删除文件失败: {e}")
            return False

    def get_file_size(self, remote_path: str) -> Optional[int]:
        """获取设备上文件大小（字节）"""
        try:
            result = self._run_adb_command(["shell", "ls", "-l", remote_path])
            if result.returncode == 0:
                # 输出格式: -rw-rw---- 1 shell shell 12345 2026-01-16 12:00 filename
                parts = result.stdout.strip().split()
                if len(parts) >= 5:
                    size = int(parts[4])
                    return size
        except Exception as e:
            logger.error(f"获取文件大小失败: {e}")
        return None

    def get_process_pid(self, process_name: str) -> Optional[int]:
        """获取进程 PID（修复版，支持管道命令）"""
        try:
            # 方法1：先获取所有进程，再在 Python 中过滤（更可靠）
            result = self._run_adb_command(["shell", "ps"])
            if result.returncode == 0 and result.stdout.strip():
                # 输出格式: USER PID PPID VSZ RSS WCHAN ADDR S NAME
                lines = result.stdout.strip().split('\n')
                for line in lines:
                    if process_name in line:
                        parts = line.split()
                        if len(parts) >= 2:
                            try:
                                pid = int(parts[1])
                                logger.info(f"找到进程 {process_name}, PID: {pid}")
                                return pid
                            except ValueError:
                                # PID 可能不在第二列，继续查找
                                continue
        except Exception as e:
            logger.error(f"获取进程 PID 失败: {e}")
        return None

    def kill_process(self, pid: int, signal: str = "INT") -> bool:
        """终止进程"""
        try:
            logger.info(f"终止进程 PID {pid}, 信号: {signal}")
            result = self._run_adb_command(["shell", "kill", f"-{signal}", str(pid)])
            time.sleep(1)
            return result.returncode == 0
        except Exception as e:
            logger.error(f"终止进程失败: {e}")
            return False

    def enable_visual_feedback(self) -> bool:
        """
        启用触摸可视化反馈（用于取证录屏）
        - 显示触摸点（白色圆圈）
        """
        try:
            logger.info("启用触摸可视化反馈...")
            # 只显示触摸点，不显示指针轨迹
            result = self._run_adb_command(["shell", "settings", "put", "system", "show_touches", "1"])

            if result.returncode == 0:
                logger.info("✓ 触摸可视化已启用")
                return True
            else:
                logger.warning("⚠ 启用触摸可视化失败")
                return False
        except Exception as e:
            logger.error(f"启用触摸可视化失败: {e}")
            return False

    def disable_visual_feedback(self) -> bool:
        """
        关闭触摸可视化反馈
        """
        try:
            logger.info("关闭触摸可视化反馈...")
            # 只关闭触摸点显示
            result = self._run_adb_command(["shell", "settings", "put", "system", "show_touches", "0"])

            if result.returncode == 0:
                logger.info("✓ 触摸可视化已关闭")
                return True
            else:
                logger.warning("⚠ 关闭触摸可视化失败")
                return False
        except Exception as e:
            logger.error(f"关闭触摸可视化失败: {e}")
            return False

    def take_screenshot(self, remote_path: str = "/sdcard/screenshot.png") -> bool:
        """
        截取屏幕截图

        Args:
            remote_path: 设备上保存截图的路径

        Returns:
            是否成功截图
        """
        try:
            logger.info(f"截取屏幕: {remote_path}")
            result = self._run_adb_command(["shell", "screencap", "-p", remote_path])
            time.sleep(0.5)
            return result.returncode == 0
        except Exception as e:
            logger.error(f"截图失败: {e}")
            return False

    def force_stop_app(self, package_name: str) -> bool:
        """
        强制停止应用进程

        Args:
            package_name: 应用包名

        Returns:
            是否成功
        """
        try:
            logger.info(f"强制停止应用: {package_name}")
            result = self._run_adb_command(["shell", "am", "force-stop", package_name])
            time.sleep(0.5)
            return result.returncode == 0
        except Exception as e:
            logger.error(f"强制停止应用失败: {e}")
            return False

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> bool:
        """
        执行滑动操作

        Args:
            x1: 起始 x 坐标
            y1: 起始 y 坐标
            x2: 结束 x 坐标
            y2: 结束 y 坐标
            duration_ms: 滑动持续时间（毫秒）

        Returns:
            是否成功
        """
        try:
            logger.debug(f"滑动: ({x1}, {y1}) -> ({x2}, {y2}), 时长 {duration_ms}ms")
            result = self._run_adb_command([
                "shell", "input", "swipe",
                str(x1), str(y1), str(x2), str(y2), str(duration_ms)
            ])
            return result.returncode == 0
        except Exception as e:
            logger.error(f"滑动失败: {e}")
            return False

    def run_command(self, command: str) -> bool:
        """
        执行任意 shell 命令

        Args:
            command: 要执行的命令

        Returns:
            是否成功
        """
        try:
            result = self._run_adb_command(["shell"] + command.split())
            return result.returncode == 0
        except Exception as e:
            logger.error(f"执行命令失败: {e}")
            return False

    def _run_adb_command(self, args: List[str]) -> subprocess.CompletedProcess:
        """执行 ADB 命令"""
        cmd = ["adb"]
        if self.device_id:
            cmd.extend(["-s", self.device_id])
        cmd.extend(args)

        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30
        )


if __name__ == "__main__":
    # 测试代码
    controller = ADBController()

    if controller.device_id:
        logger.info(f"设备已连接: {controller.device_id}")

        # 测试基础功能
        if controller.check_connection():
            logger.info("✓ 设备连接正常")

        screen_size = controller.get_screen_size()
        if screen_size:
            logger.info(f"✓ 屏幕分辨率: {screen_size[0]}x{screen_size[1]}")
    else:
        logger.error("✗ 未检测到设备")
