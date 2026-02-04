#!/usr/bin/env python3
"""
平台处理器基类
定义所有电商平台取证的统一接口
"""

from abc import ABC, abstractmethod
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class BasePlatformHandler(ABC):
    """
    平台处理器抽象基类

    所有平台（淘宝、京东、抖音等）都必须继承此类并实现所有抽象方法。
    公共流程（环境检查、录屏、时间锚点）由 EvidenceCollector 处理，
    平台特定流程（打开App、商品页、视频播放、店铺资质）由各 Handler 实现。
    """

    def __init__(self, adb_controller, ui_locator, antibot=None):
        """
        初始化平台处理器

        Args:
            adb_controller: ADBController 实例
            ui_locator: UILocator 实例
            antibot: AntiBot 实例（可选，用于人类行为模拟）
        """
        self.adb = adb_controller
        self.locator = ui_locator
        self.antibot = antibot

    @abstractmethod
    def get_platform_name(self) -> str:
        """
        返回平台名称

        Returns:
            平台名称，如 "taobao", "jd", "douyin"
        """
        pass

    @abstractmethod
    def get_platform_display_name(self) -> str:
        """
        返回平台显示名称（中文）

        Returns:
            显示名称，如 "淘宝", "京东", "抖音"
        """
        pass

    @abstractmethod
    def get_app_package(self) -> str:
        """
        返回 App 包名

        Returns:
            包名，如 "com.taobao.taobao"
        """
        pass

    @abstractmethod
    def get_app_store_search_keyword(self) -> str:
        """
        返回在应用商店搜索时使用的关键词

        Returns:
            搜索关键词，如 "淘宝", "京东"
        """
        pass

    @abstractmethod
    def open_app_from_store(self, wait_time: int = 6) -> bool:
        """
        从应用商店搜索并打开 App

        Args:
            wait_time: 等待搜索结果加载的时间（秒）

        Returns:
            是否成功打开
        """
        pass

    @abstractmethod
    def launch_app(self, wait_time: int = 10) -> bool:
        """
        启动 App（从应用商店点击"打开"或直接启动）

        Args:
            wait_time: 等待 App 启动的时间（秒）

        Returns:
            是否成功启动
        """
        pass

    @abstractmethod
    def navigate_to_product(self, product_url: str, wait_time: int = 8) -> bool:
        """
        导航到商品页面

        Args:
            product_url: 商品链接
            wait_time: 等待页面加载的时间（秒）

        Returns:
            是否成功打开商品页
        """
        pass

    @abstractmethod
    def play_video(self, max_attempts: int = 3) -> bool:
        """
        播放商品视频

        Args:
            max_attempts: 最大尝试次数

        Returns:
            是否成功播放（部分商品可能无视频，返回 False 不一定是错误）
        """
        pass

    @abstractmethod
    def unmute_video(self, max_attempts: int = 2) -> bool:
        """
        打开视频声音

        Args:
            max_attempts: 最大尝试次数

        Returns:
            是否成功打开声音
        """
        pass

    @abstractmethod
    def view_shop_info(self) -> bool:
        """
        查看店铺信息

        Returns:
            是否成功查看
        """
        pass

    @abstractmethod
    def view_qualification(self) -> bool:
        """
        查看店铺资质证照

        Returns:
            是否成功查看
        """
        pass

    # ==================== AntiBot 辅助方法 ====================

    def _sleep(self, min_ms: int = None, max_ms: int = None):
        """人类化随机延迟"""
        if self.antibot:
            self.antibot.sleep(min_ms, max_ms)
        else:
            import time
            import random
            delay = random.uniform((min_ms or 500) / 1000, (max_ms or 2000) / 1000)
            time.sleep(delay)

    def _sleep_after_click(self):
        """点击后延迟"""
        if self.antibot:
            self.antibot.sleep_after_click()
        else:
            import time
            import random
            time.sleep(random.uniform(0.8, 1.5))

    def _check_risk(self) -> bool:
        """
        检查当前页面风险

        Returns:
            是否安全（True = 安全，False = 有风险）
        """
        if not self.antibot:
            return True

        root = self.locator.dump_and_parse()
        return self.antibot.is_safe(root)

    # ==================== 模板方法 ====================

    def execute(self, product_url: str, video_play_duration: int = 30) -> bool:
        """
        执行完整的平台取证流程

        这是一个模板方法，定义了平台取证的标准流程。
        子类可以重写此方法来自定义流程，但通常只需实现各个抽象方法。

        Args:
            product_url: 商品链接
            video_play_duration: 视频录制时长（秒）

        Returns:
            是否成功完成取证
        """
        import time

        platform_name = self.get_platform_display_name()
        logger.info(f"开始执行 {platform_name} 平台取证流程")

        # 步骤 1: 从应用商店打开 App
        logger.info(f"步骤 1: 从应用商店打开 {platform_name}")
        if not self.open_app_from_store():
            logger.error(f"打开应用商店搜索 {platform_name} 失败")
            return False

        # 步骤 2: 启动 App
        logger.info(f"步骤 2: 启动 {platform_name} App")
        if not self.launch_app():
            logger.error(f"启动 {platform_name} App 失败")
            return False

        # 步骤 3: 导航到商品页
        logger.info("步骤 3: 打开商品页面")
        if not self.navigate_to_product(product_url):
            logger.error("打开商品页失败")
            return False

        # 风险检查
        if not self._check_risk():
            logger.warning("检测到风险状态，流程可能受阻")

        # 步骤 4: 打开声音
        logger.info("步骤 4: 打开视频声音")
        self.unmute_video()  # 失败不影响流程
        self._sleep_after_click()

        # 步骤 5: 播放视频
        logger.info("步骤 5: 播放商品视频")
        video_played = self.play_video()
        if not video_played:
            logger.warning("未能自动播放视频，但继续录制")

        # 步骤 6: 持续录制
        logger.info(f"步骤 6: 持续录制 {video_play_duration} 秒")
        time.sleep(video_play_duration)

        # 步骤 7: 查看店铺资质
        logger.info("步骤 7: 查看店铺资质")
        qualification_viewed = self.view_qualification()
        if not qualification_viewed:
            logger.warning("店铺资质查看失败或跳过，继续流程")

        logger.info(f"✓ {platform_name} 平台取证流程完成")
        return True
