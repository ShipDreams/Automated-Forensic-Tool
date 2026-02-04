#!/usr/bin/env python3
"""
录屏管理模块 - 实时保 App 版本
负责通过"实时保"App进行屏幕录制（取证专用）
"""

import time
import logging
from typing import Optional

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class ScreenRecorder:
    """屏幕录制管理器（实时保 App版本）"""

    def __init__(self, adb_controller):
        """
        初始化录屏管理器

        Args:
            adb_controller: ADBController 实例
        """
        self.adb = adb_controller
        self.locator = None  # 将在 start_recording 时注入
        self.is_recording = False

    def start_recording(self) -> bool:
        """
        通过"实时保"App启动录屏（智能检测页面状态）

        流程:
        1. 打开"实时保"App
        2. 检测当前页面状态：
           - 如果有"开始录屏"按钮，直接点击（跳过屏幕录像步骤）
           - 如果有"屏幕录像"按钮，执行完整流程
        3. 点击弹窗"立即开始"（如需）
        4. 点击"开始录制"
        5. 等待4秒确保录屏启动

        Returns:
            是否成功启动录屏
        """
        try:
            try:
                from .ui_locator import UILocator
            except ImportError:
                from ui_locator import UILocator
            if not self.locator:
                self.locator = UILocator(self.adb)

            logger.info("=" * 60)
            logger.info("通过实时保 App 启动录屏")
            logger.info("=" * 60)

            # 步骤 1: 打开实时保 App
            logger.info("步骤 1: 打开实时保 App...")
            if not self.adb.open_shishibao_app():
                logger.error("✗ 打开实时保 App 失败")
                return False

            # 步骤 2: 检测当前页面状态
            logger.info("步骤 2: 检测当前页面状态...")
            time.sleep(2)  # 等待页面加载
            root = self.locator.dump_and_parse()
            if not root:
                logger.error("✗ 无法获取实时保 UI 层级")
                return False

            # 先检测是否已经在录屏准备页面（有"开始录屏"按钮）
            start_record_btn = self.locator.find_shishibao_start_record_button(root)
            if start_record_btn:
                logger.info("✓ 检测到'开始录屏'按钮，跳过'屏幕录像'步骤")
                # 直接点击"开始录屏"
                if not self.locator.click_element(start_record_btn):
                    logger.error("✗ 点击'开始录屏'按钮失败")
                    return False
            else:
                # 需要先点击"屏幕录像"
                logger.info("检测到需要先点击'屏幕录像'按钮...")
                screen_record_btn = self.locator.find_shishibao_screen_record_button(root)
                if not screen_record_btn:
                    logger.error("✗ 未找到'屏幕录像'按钮")
                    return False

                if not self.locator.click_element(screen_record_btn):
                    logger.error("✗ 点击'屏幕录像'按钮失败")
                    return False

                # 步骤 3: 点击弹窗"立即开始"
                logger.info("步骤 3: 查找并点击'立即开始'按钮...")
                time.sleep(2)  # 等待弹窗出现
                root = self.locator.dump_and_parse()
                if not root:
                    logger.error("✗ 无法获取弹窗 UI 层级")
                    return False

                start_now_btn = self.locator.find_shishibao_start_now_button(root)
                if not start_now_btn:
                    logger.error("✗ 未找到'立即开始'按钮")
                    return False

                if not self.locator.click_element(start_now_btn):
                    logger.error("✗ 点击'立即开始'按钮失败")
                    return False

                # 步骤 4: 点击"开始录制"
                logger.info("步骤 4: 查找并点击'开始录制'按钮...")
                time.sleep(2)  # 等待页面响应
                root = self.locator.dump_and_parse()
                if not root:
                    logger.error("✗ 无法获取 UI 层级")
                    return False

                start_record_btn = self.locator.find_shishibao_start_record_button(root)
                if not start_record_btn:
                    logger.error("✗ 未找到'开始录制'按钮")
                    return False

                if not self.locator.click_element(start_record_btn):
                    logger.error("✗ 点击'开始录制'按钮失败")
                    return False

            # 步骤 5: 等待录屏启动稳定
            logger.info("步骤 5: 等待 4 秒确保录屏启动稳定...")
            time.sleep(4)

            self.is_recording = True
            logger.info("=" * 60)
            logger.info("✓ 实时保录屏已启动")
            logger.info("=" * 60)
            return True

        except Exception as e:
            logger.error(f"启动实时保录屏失败: {e}", exc_info=True)
            return False

    def stop_recording(self, wait_time: int = 3, max_retries: int = 3) -> bool:
        """
        通过"实时保"App停止录屏并保存

        流程:
        1. 打开"实时保"App
        2. 点击"结束录屏"（带重试）
        3. 点击"保存"
        4. 等待保存完成

        Args:
            wait_time: 保存后等待时间（秒）
            max_retries: 查找按钮最大重试次数

        Returns:
            是否成功停止并保存
        """
        try:
            try:
                from .ui_locator import UILocator
            except ImportError:
                from ui_locator import UILocator
            if not self.locator:
                self.locator = UILocator(self.adb)

            logger.info("=" * 60)
            logger.info("通过实时保 App 停止录屏")
            logger.info("=" * 60)

            # 步骤 1: 打开实时保 App
            logger.info("步骤 1: 打开实时保 App...")
            if not self.adb.open_shishibao_app():
                logger.error("✗ 打开实时保 App 失败")
                return False

            # 新增：按返回键确保淘宝页面退到后台，让实时保App显示在前台
            logger.info("按返回键关闭淘宝页面，确保实时保在前台...")
            time.sleep(2)
            self.adb.press_back()  # 关闭淘宝营业执照页面
            time.sleep(2)

            # 验证当前焦点是否为实时保
            current_focus = self.adb.get_current_focus()
            if current_focus and 'rdbao' not in current_focus:
                logger.warning("实时保未在前台，再次按返回键...")
                self.adb.press_back()
                time.sleep(1)
            else:
                logger.info("✓ 实时保App已在前台")

            # 步骤 2: 点击"结束录屏"（带重试机制）
            logger.info("步骤 2: 查找并点击'结束录屏'按钮...")
            stop_btn = None
            for attempt in range(1, max_retries + 1):
                logger.info(f"第 {attempt}/{max_retries} 次尝试查找'结束录屏'按钮...")
                time.sleep(3)  # 等待实时保界面完全加载
                root = self.locator.dump_and_parse()
                if not root:
                    logger.warning(f"第 {attempt} 次无法获取 UI 层级")
                    continue

                stop_btn = self.locator.find_shishibao_stop_record_button(root)
                if stop_btn:
                    logger.info(f"✓ 第 {attempt} 次找到'结束录屏'按钮")
                    break
                else:
                    logger.warning(f"第 {attempt} 次未找到'结束录屏'按钮")
                    if attempt < max_retries:
                        # 尝试按返回键刷新界面
                        self.adb.press_back()
                        time.sleep(1)
                        self.adb.open_shishibao_app()
                        time.sleep(2)

            if not stop_btn:
                logger.error(f"✗ 经过 {max_retries} 次尝试仍未找到'结束录屏'按钮")
                return False

            if not self.locator.click_element(stop_btn):
                logger.error("✗ 点击'结束录屏'按钮失败")
                return False

            # 步骤 3: 点击"保存"
            logger.info("步骤 3: 查找并点击'保存'按钮...")
            time.sleep(2)  # 等待响应
            root = self.locator.dump_and_parse()
            if not root:
                logger.error("✗ 无法获取 UI 层级")
                return False

            save_btn = self.locator.find_shishibao_save_button(root)
            if not save_btn:
                logger.error("✗ 未找到'保存'按钮")
                return False

            if not self.locator.click_element(save_btn):
                logger.error("✗ 点击'保存'按钮失败")
                return False

            # 步骤 4: 等待保存完成
            logger.info(f"步骤 4: 等待 {wait_time} 秒让文件保存完成...")
            time.sleep(wait_time)

            self.is_recording = False
            logger.info("=" * 60)
            logger.info("✓ 实时保录屏已停止并保存")
            logger.info("录屏文件已保存在实时保App后台")
            logger.info("=" * 60)
            return True

        except Exception as e:
            logger.error(f"停止实时保录屏失败: {e}", exc_info=True)
            return False

    def cancel_recording(self, max_retries: int = 3) -> bool:
        """
        通过"实时保"App停止录屏但不保存（取消）

        用于任务失败时清理录屏状态，不保存当前录屏。

        流程:
        1. 打开"实时保"App
        2. 点击"结束录屏"（带重试）
        3. 点击"取消"
        4. 等待界面恢复

        Args:
            max_retries: 查找按钮最大重试次数

        Returns:
            是否成功取消录屏
        """
        try:
            try:
                from .ui_locator import UILocator
            except ImportError:
                from ui_locator import UILocator
            if not self.locator:
                self.locator = UILocator(self.adb)

            logger.info("=" * 60)
            logger.info("通过实时保 App 取消录屏（不保存）")
            logger.info("=" * 60)

            # 步骤 1: 打开实时保 App
            logger.info("步骤 1: 打开实时保 App...")
            if not self.adb.open_shishibao_app():
                logger.error("✗ 打开实时保 App 失败")
                return False

            # 按返回键确保实时保在前台
            logger.info("按返回键确保实时保在前台...")
            time.sleep(2)
            self.adb.press_back()
            time.sleep(2)

            # 验证当前焦点是否为实时保
            current_focus = self.adb.get_current_focus()
            if current_focus and 'rdbao' not in current_focus:
                logger.warning("实时保未在前台，再次按返回键...")
                self.adb.press_back()
                time.sleep(1)
            else:
                logger.info("✓ 实时保App已在前台")

            # 步骤 2: 点击"结束录屏"（带重试机制）
            logger.info("步骤 2: 查找并点击'结束录屏'按钮...")
            stop_btn = None
            for attempt in range(1, max_retries + 1):
                logger.info(f"第 {attempt}/{max_retries} 次尝试查找'结束录屏'按钮...")
                time.sleep(3)
                root = self.locator.dump_and_parse()
                if not root:
                    logger.warning(f"第 {attempt} 次无法获取 UI 层级")
                    continue

                stop_btn = self.locator.find_shishibao_stop_record_button(root)
                if stop_btn:
                    logger.info(f"✓ 第 {attempt} 次找到'结束录屏'按钮")
                    break
                else:
                    logger.warning(f"第 {attempt} 次未找到'结束录屏'按钮")
                    if attempt < max_retries:
                        self.adb.press_back()
                        time.sleep(1)
                        self.adb.open_shishibao_app()
                        time.sleep(2)

            if not stop_btn:
                logger.error(f"✗ 经过 {max_retries} 次尝试仍未找到'结束录屏'按钮")
                return False

            if not self.locator.click_element(stop_btn):
                logger.error("✗ 点击'结束录屏'按钮失败")
                return False

            # 步骤 3: 点击"取消"
            logger.info("步骤 3: 查找并点击'取消'按钮...")
            time.sleep(2)
            root = self.locator.dump_and_parse()
            if not root:
                logger.error("✗ 无法获取 UI 层级")
                return False

            cancel_btn = self.locator.find_shishibao_cancel_button(root)
            if not cancel_btn:
                logger.error("✗ 未找到'取消'按钮")
                return False

            if not self.locator.click_element(cancel_btn):
                logger.error("✗ 点击'取消'按钮失败")
                return False

            # 步骤 4: 等待界面恢复
            logger.info("步骤 4: 等待界面恢复...")
            time.sleep(2)

            self.is_recording = False
            logger.info("=" * 60)
            logger.info("✓ 实时保录屏已取消（未保存）")
            logger.info("=" * 60)
            return True

        except Exception as e:
            logger.error(f"取消实时保录屏失败: {e}", exc_info=True)
            return False

    def export_recording(self, output_dir: str = "./output") -> Optional[str]:
        """
        导出录屏文件（实时保版本无需导出，文件保存在App内）

        Args:
            output_dir: 输出目录（未使用）

        Returns:
            None（文件已保存在实时保后台）
        """
        logger.info("实时保录屏文件已自动保存在App后台，无需导出")
        logger.info("如需获取文件，请在实时保App中手动导出或查看")
        return None

    def cleanup_device_files(self) -> bool:
        """清理设备文件（实时保版本无需清理）"""
        logger.info("实时保录屏无需清理设备临时文件")
        return True


if __name__ == "__main__":
    # 测试代码
    try:
        from .adb_controller import ADBController
    except ImportError:
        from adb_controller import ADBController

    controller = ADBController()
    if not controller.device_id:
        logger.error("未检测到设备")
        exit(1)

    recorder = ScreenRecorder(controller)

    # 测试启动录屏
    logger.info("开始测试实时保录屏...")
    if recorder.start_recording():
        logger.info("录屏启动成功，等待 10 秒...")
        time.sleep(10)

        if recorder.stop_recording():
            logger.info("✓ 测试成功，录屏已保存在实时保App中")
        else:
            logger.error("✗ 停止录屏失败")
    else:
        logger.error("✗ 启动录屏失败")
