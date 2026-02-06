#!/usr/bin/env python3
"""
Platform Router
Auto-detect platform from product URL and return corresponding handler.
"""

import re
import logging
from typing import Optional, Dict, Type
from urllib.parse import urlparse

from locales import t

logger = logging.getLogger(__name__)


class PlatformRouter:
    """
    Platform Router

    Auto-detect platform type from product URL and return corresponding Handler instance.
    """

    # Platform URL pattern mapping
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
            r'3\.cn',  # JD short link
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
        Initialize router.

        Args:
            adb_controller: ADBController instance
            ui_locator: UILocator instance
            antibot: AntiBot instance (optional)
        """
        self.adb = adb_controller
        self.locator = ui_locator
        self.antibot = antibot
        self._handlers: Dict[str, object] = {}

    def detect_platform(self, url: str) -> Optional[str]:
        """
        Detect platform type from URL.

        Args:
            url: Product link

        Returns:
            Platform name (taobao/alibaba/jd/douyin) or None
        """
        url_lower = url.lower()

        for platform, patterns in self.PLATFORM_PATTERNS.items():
            for pattern in patterns:
                if re.search(pattern, url_lower):
                    logger.info(t('log.platform_detected', platform=platform, url=url[:50]))
                    return platform

        logger.warning(t('log.platform_not_detected', url=url[:50]))
        return None

    def get_handler(self, url: str):
        """
        Get platform handler for URL.

        Args:
            url: Product link

        Returns:
            Corresponding PlatformHandler instance

        Raises:
            ValueError: If platform is not recognized
            NotImplementedError: If platform is not yet implemented
        """
        platform = self.detect_platform(url)
        if not platform:
            raise ValueError(t('log.cannot_recognize_platform', url=url))

        # Lazy import to avoid circular references
        if platform == 'taobao':
            from .taobao_handler import TaobaoHandler
            return TaobaoHandler(self.adb, self.locator, self.antibot)

        elif platform == 'alibaba':
            # TODO: To be implemented
            raise NotImplementedError(t('log.alibaba_not_implemented'))

        elif platform == 'jd':
            # TODO: To be implemented
            raise NotImplementedError(t('log.jd_not_implemented'))

        elif platform == 'douyin':
            # TODO: To be implemented
            raise NotImplementedError(t('log.douyin_not_implemented'))

        else:
            raise ValueError(t('log.unsupported_platform', platform=platform))

    def is_supported(self, url: str) -> bool:
        """
        Check if URL belongs to a supported platform.

        Args:
            url: Product link

        Returns:
            Whether supported
        """
        platform = self.detect_platform(url)
        # Currently only Taobao is fully implemented
        return platform == 'taobao'

    def get_supported_platforms(self) -> list:
        """
        Get list of supported platforms.

        Returns:
            List of platform names
        """
        # Currently only Taobao is fully implemented
        return ['taobao']

    def get_all_platforms(self) -> list:
        """
        Get all known platforms (including unimplemented ones).

        Returns:
            List of platform names
        """
        return list(self.PLATFORM_PATTERNS.keys())
