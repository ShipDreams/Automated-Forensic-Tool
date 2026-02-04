#!/usr/bin/env python3
"""
平台路由器
根据商品链接自动识别平台并返回对应的处理器
"""

import re
import logging
from typing import Optional, Dict, Type
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


class PlatformRouter:
    """
    平台路由器

    根据商品 URL 自动识别平台类型，并返回对应的 Handler 实例。
    """

    # 平台 URL 特征映射
    PLATFORM_PATTERNS = {
        'taobao': [
            r'taobao\.com',
            r'tmall\.com',
            r'tb\.cn',
            r'm\.taobao\.com',
            r'item\.taobao\.com',
            r'detail\.tmall\.com',
            r'a\.m\.taobao\.com',
            r'h5\.m\.taobao\.com',
        ],
        'alibaba': [
            r'1688\.com',
            r'm\.1688\.com',
            r'detail\.1688\.com',
            r'alibaba\.com',
        ],
        'jd': [
            r'jd\.com',
            r'm\.jd\.com',
            r'item\.jd\.com',
            r'3\.cn',  # 京东短链接
        ],
        'douyin': [
            r'douyin\.com',
            r'v\.douyin\.com',
            r'm\.douyin\.com',
            r'iesdouyin\.com',
        ],
    }

    def __init__(self, adb_controller, ui_locator, antibot=None):
        """
        初始化路由器

        Args:
            adb_controller: ADBController 实例
            ui_locator: UILocator 实例
            antibot: AntiBot 实例（可选）
        """
        self.adb = adb_controller
        self.locator = ui_locator
        self.antibot = antibot
        self._handlers: Dict[str, object] = {}

    def detect_platform(self, url: str) -> Optional[str]:
        """
        根据 URL 检测平台类型

        Args:
            url: 商品链接

        Returns:
            平台名称 (taobao/alibaba/jd/douyin) 或 None
        """
        url_lower = url.lower()

        for platform, patterns in self.PLATFORM_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, url_lower):
                    logger.info(f"检测到平台: {platform} (URL: {url[:50]}...)")
                    return platform

        logger.warning(f"无法识别平台: {url[:50]}...")
        return None

    def get_handler(self, url: str):
        """
        根据 URL 获取对应的平台处理器

        Args:
            url: 商品链接

        Returns:
            对应的 PlatformHandler 实例，或 None

        Raises:
            ValueError: 如果平台未实现或不支持
        """
        platform = self.detect_platform(url)
        if not platform:
            raise ValueError(f"无法识别商品链接的平台: {url}")

        # 延迟导入，避免循环引用
        if platform == 'taobao':
            from .taobao_handler import TaobaoHandler
            return TaobaoHandler(self.adb, self.locator, self.antibot)

        elif platform == 'alibaba':
            # TODO: 待实现
            raise NotImplementedError("阿里巴巴平台暂未实现")

        elif platform == 'jd':
            # TODO: 待实现
            raise NotImplementedError("京东平台暂未实现")

        elif platform == 'douyin':
            # TODO: 待实现
            raise NotImplementedError("抖音平台暂未实现")

        else:
            raise ValueError(f"不支持的平台: {platform}")

    def is_supported(self, url: str) -> bool:
        """
        检查 URL 是否属于支持的平台

        Args:
            url: 商品链接

        Returns:
            是否支持
        """
        platform = self.detect_platform(url)
        # 目前只有淘宝完整实现
        return platform == 'taobao'

    def get_supported_platforms(self) -> list:
        """
        获取所有支持的平台列表

        Returns:
            平台名称列表
        """
        # 目前只有淘宝完整实现
        return ['taobao']

    def get_all_platforms(self) -> list:
        """
        获取所有已知平台列表（包括未实现的）

        Returns:
            平台名称列表
        """
        return list(self.PLATFORM_PATTERNS.keys())
