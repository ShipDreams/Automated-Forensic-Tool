#!/usr/bin/env python3
"""
淘宝平台处理器
实现淘宝/天猫商品取证的完整流程
"""

import time
import logging
from typing import Optional

from .base_handler import BasePlatformHandler

logger = logging.getLogger(__name__)


class TaobaoHandler(BasePlatformHandler):
    """
    淘宝平台处理器

    负责淘宝/天猫商品的取证流程，包括：
    - 从应用商店打开淘宝
    - 在搜索框输入商品链接
    - 播放商品视频
    - 查看店铺资质证照
    """

    def get_platform_name(self) -> str:
        return "taobao"

    def get_platform_display_name(self) -> str:
        return "淘宝"

    def get_app_package(self) -> str:
        return "com.taobao.taobao"

    def get_app_store_search_keyword(self) -> str:
        return "淘宝"

    def open_app_from_store(self, wait_time: int = 6) -> bool:
        """从应用商店搜索淘宝"""
        logger.info("=" * 60)
        logger.info("打开应用商店并搜索淘宝")
        logger.info("=" * 60)

        # 使用品牌自适应搜索协议打开应用商店
        if not self.adb.open_app_store_and_search_taobao():
            logger.error("✗ 无法打开应用商店搜索")
            return False

        # 等待搜索结果加载（带人类化延迟）
        logger.info(f"等待 {wait_time} 秒让搜索结果加载...")
        self._sleep(wait_time * 1000 - 500, wait_time * 1000 + 500)

        logger.info("✓ 应用商店搜索结果已加载")
        return True

    def launch_app(self, wait_time: int = 10) -> bool:
        """从应用商店搜索结果点击"打开"启动淘宝"""
        logger.info("=" * 60)
        logger.info("从应用商店搜索结果打开淘宝 App")
        logger.info("=" * 60)

        # 查找并点击搜索结果中的"打开"按钮
        if not self.locator.find_and_click_app_store_open_button(max_attempts=3):
            logger.error("✗ 未能点击'打开'按钮")
            return False

        self._sleep_after_click()

        # 等待淘宝 App 完全启动
        logger.info(f"等待 {wait_time} 秒让淘宝 App 完全启动...")
        self._sleep(wait_time * 1000 - 1000, wait_time * 1000 + 1000)

        # 确认淘宝已打开
        current_focus = self.adb.get_current_focus()
        if current_focus:
            logger.info(f"当前应用: {current_focus}")
            if 'taobao' in current_focus.lower():
                logger.info("✓ 淘宝 App 已启动")
                return True

        logger.warning("⚠ 无法确认淘宝是否启动，继续执行...")
        return True

    def navigate_to_product(self, product_url: str, wait_time: int = 8) -> bool:
        """在淘宝中通过搜索框打开商品链接"""
        logger.info("=" * 60)
        logger.info("在淘宝中通过搜索框打开商品链接")
        logger.info("=" * 60)

        try:
            # 额外等待确保淘宝首页完全加载
            logger.info("等待淘宝首页完全加载...")
            self._sleep(2500, 3500)

            # 尝试关闭可能的弹窗
            logger.info("尝试关闭可能的弹窗...")
            self.adb.press_back()
            self._sleep(800, 1200)

            # 导出 UI 层级并查找搜索框（带重试）
            max_dump_attempts = 2
            root = None

            for attempt in range(1, max_dump_attempts + 1):
                logger.info(f"查找淘宝搜索框（第 {attempt}/{max_dump_attempts} 次尝试）...")
                root = self.locator.dump_and_parse()
                if root:
                    break

                if attempt < max_dump_attempts:
                    logger.warning("UI 导出失败，重试...")
                    self.adb.press_back()
                    self._sleep(1500, 2500)

            if not root:
                logger.error("✗ 无法获取 UI 层级")
                return False

            search_box = self.locator.find_taobao_search_box(root)
            if not search_box:
                logger.error("✗ 未找到淘宝搜索框")
                return False

            # 点击搜索框激活输入
            logger.info("点击搜索框...")
            if not self.locator.click_element(search_box):
                logger.error("✗ 点击搜索框失败")
                return False

            self._sleep_after_click()

            # 输入商品链接
            logger.info(f"输入商品链接: {product_url}")
            if not self.adb.input_text(product_url):
                logger.error("✗ 输入商品链接失败")
                return False

            self._sleep(800, 1200)

            # 按回车键触发搜索
            logger.info("按回车键触发搜索...")
            if not self.adb.press_enter():
                logger.error("✗ 按回车键失败")

                # 尝试查找并点击搜索按钮
                logger.info("尝试点击搜索按钮...")
                root = self.locator.dump_and_parse()
                if root:
                    search_button = self.locator.find_search_button(root)
                    if search_button:
                        if not self.locator.click_element(search_button):
                            logger.error("✗ 点击搜索按钮失败")
                            return False
                        self._sleep_after_click()
                    else:
                        logger.error("✗ 未找到搜索按钮")
                        return False
                else:
                    return False

            # 等待商品页加载
            logger.info(f"等待 {wait_time} 秒让商品页加载...")
            self._sleep(wait_time * 1000 - 1000, wait_time * 1000 + 1000)

            logger.info("✓ 商品页已打开")
            return True

        except Exception as e:
            logger.error(f"打开商品页失败: {e}")
            return False

    def play_video(self, max_attempts: int = 3) -> bool:
        """播放商品视频"""
        logger.info("=" * 60)
        logger.info("播放商品视频")
        logger.info("=" * 60)

        # 使用 UI 定位器查找并点击视频
        success = self.locator.find_and_click_video(max_attempts=max_attempts)

        if success:
            logger.info("✓ 视频播放已触发")
            self._sleep(2500, 3500)
        else:
            logger.warning("⚠ 未能自动触发视频播放（可能商品无视频）")

        return success

    def unmute_video(self, max_attempts: int = 2) -> bool:
        """打开视频声音"""
        logger.info("=" * 60)
        logger.info("打开视频声音")
        logger.info("=" * 60)

        for attempt in range(1, max_attempts + 1):
            logger.info(f"查找音量按钮（第 {attempt}/{max_attempts} 次尝试）...")

            root = self.locator.dump_and_parse()
            if not root:
                logger.warning("无法获取 UI 层级")
                if attempt < max_attempts:
                    self._sleep(1500, 2500)
                continue

            volume_btn = self.locator.find_volume_button(root)
            if volume_btn:
                if self.locator.click_element(volume_btn):
                    logger.info("✓ 已打开视频声音")
                    self._sleep(1500, 2500)
                    return True
                else:
                    logger.warning("点击音量按钮失败")
            else:
                logger.warning("未找到音量按钮")

            if attempt < max_attempts:
                self._sleep(1500, 2500)

        logger.warning("⚠ 未能打开视频声音（继续流程）")
        return False

    def view_shop_info(self) -> bool:
        """查看店铺信息（点击店铺按钮进入店铺页）"""
        logger.info("步骤: 点击'店铺'按钮...")

        root = self.locator.dump_and_parse()
        if not root:
            logger.error("✗ 无法获取 UI 层级")
            return False

        shop_btn = self.locator.find_shop_button(root)
        if not shop_btn:
            logger.error("✗ 未找到'店铺'按钮")
            return False

        if not self.locator.click_element(shop_btn):
            logger.error("✗ 点击'店铺'按钮失败")
            return False

        self._sleep_after_click()

        logger.info("等待店铺页面加载...")
        self._sleep(2500, 3500)

        # 点击店铺名称或头像进入店铺主页
        logger.info("点击店铺名称或头像进入店铺主页...")
        root = self.locator.dump_and_parse()
        if not root:
            logger.error("✗ 无法获取店铺页面 UI 层级")
            return False

        shop_name = self.locator.find_shop_name_or_avatar(root)
        if not shop_name:
            logger.error("✗ 未找到店铺名称或头像")
            return False

        if not self.locator.click_element(shop_name):
            logger.error("✗ 点击店铺名称/头像失败")
            return False

        self._sleep_after_click()

        logger.info("等待店铺主页加载...")
        self._sleep(3500, 4500)

        logger.info("✓ 已进入店铺主页")
        return True

    def view_qualification(self) -> bool:
        """查看店铺资质证照"""
        logger.info("=" * 60)
        logger.info("查看店铺资质证照")
        logger.info("=" * 60)

        try:
            # 先进入店铺页
            if not self.view_shop_info():
                return False

            # 点击"资质证照"
            logger.info("查找并点击'资质证照'...")
            root = self.locator.dump_and_parse()
            if not root:
                logger.error("✗ 无法获取店铺主页 UI 层级")
                return False

            qualification_btn = self.locator.find_qualification_button(root)
            if not qualification_btn:
                logger.warning("⚠ 未找到'资质证照'按钮")
                logger.warning("可能原因：该店铺未上传资质证照或按钮位置变化")
                return False

            if not self.locator.click_element(qualification_btn):
                logger.error("✗ 点击'资质证照'按钮失败")
                return False

            self._sleep_after_click()

            logger.info("等待证照页面加载...")
            self._sleep(2500, 3500)

            # 检测验证码
            root = self.locator.dump_and_parse()
            if root and self.locator.detect_captcha(root):
                logger.warning("⚠ 检测到验证码，需要人工干预")
                logger.info("等待 15 秒供人工完成验证...")
                time.sleep(15)

            # 停留录制证照信息
            logger.info("停留 10 秒录制资质证照信息...")
            time.sleep(10)

            logger.info("✓ 店铺资质证照查看完成")
            return True

        except Exception as e:
            logger.error(f"查看店铺资质证照失败: {e}")
            return False
