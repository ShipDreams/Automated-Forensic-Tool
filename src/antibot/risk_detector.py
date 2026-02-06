#!/usr/bin/env python3
"""
Risk Detector
Detects captcha, login page, rate limits, and other risk signals.
"""

import re
import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class RiskType(Enum):
    """Risk type enumeration."""
    NONE = "none"
    CAPTCHA = "captcha"
    LOGIN_REQUIRED = "login_required"
    RATE_LIMIT = "rate_limit"
    BLOCKED = "blocked"
    UI_ANOMALY = "ui_anomaly"
    UNKNOWN = "unknown"


@dataclass
class RiskSignal:
    """Risk signal data class."""
    risk_type: RiskType
    confidence: float  # 0.0 - 1.0
    source: str  # Detection source (text, ui, element)
    details: str  # Detailed information
    element_info: Optional[Dict] = None  # Related UI element info


class RiskDetector:
    """
    Risk Detector

    Core features:
    - Detect captcha pages
    - Detect login requirements
    - Detect rate limits
    - Detect account blocks
    - Detect UI anomalies
    """

    def __init__(self, config: dict = None):
        """
        Initialize risk detector.

        Args:
            config: Config dictionary, from config/antibot.json risk_detection section
        """
        self.config = config or {}
        self._load_config()

    def _load_config(self):
        """Load config parameters."""
        self.captcha_keywords = self.config.get('captcha_keywords', [
            '验证码', '滑动验证', '安全验证', 'captcha', 'verify', '拼图'
        ])
        self.login_keywords = self.config.get('login_keywords', [
            '登录', '请登录', '登录后查看', 'login', 'sign in'
        ])
        self.rate_limit_keywords = self.config.get('rate_limit_keywords', [
            '操作频繁', '请稍后再试', '访问过于频繁', '请稍后'
        ])
        self.block_keywords = self.config.get('block_keywords', [
            '账号异常', '暂时无法访问', '违规', '封禁'
        ])

        ui_config = self.config.get('ui_anomaly', {})
        self.min_node_count = ui_config.get('min_node_count', 10)
        self.empty_page_threshold = ui_config.get('empty_page_threshold', 5)

    def detect_from_ui_tree(self, root) -> List[RiskSignal]:
        """
        Detect risks from UI hierarchy tree.

        Args:
            root: XML Element root node

        Returns:
            List of detected risk signals
        """
        if root is None:
            return [RiskSignal(
                risk_type=RiskType.UI_ANOMALY,
                confidence=0.9,
                source='ui',
                details='Cannot get UI hierarchy'
            )]

        signals = []

        # Collect all texts
        texts = self._collect_all_texts(root)

        # Count nodes
        node_count = len(list(root.iter()))

        # Detect various risks
        captcha_signal = self._detect_captcha(texts, root)
        if captcha_signal:
            signals.append(captcha_signal)

        login_signal = self._detect_login(texts, root)
        if login_signal:
            signals.append(login_signal)

        rate_limit_signal = self._detect_rate_limit(texts)
        if rate_limit_signal:
            signals.append(rate_limit_signal)

        block_signal = self._detect_block(texts)
        if block_signal:
            signals.append(block_signal)

        anomaly_signal = self._detect_ui_anomaly(node_count, texts)
        if anomaly_signal:
            signals.append(anomaly_signal)

        return signals

    def _collect_all_texts(self, root) -> List[str]:
        """Collect all texts from UI tree."""
        texts = []
        for elem in root.iter():
            text = elem.attrib.get('text', '')
            content_desc = elem.attrib.get('content-desc', '')
            if text:
                texts.append(text)
            if content_desc:
                texts.append(content_desc)
        return texts

    def _detect_captcha(self, texts: List[str], root) -> Optional[RiskSignal]:
        """Detect captcha."""
        combined_text = ' '.join(texts).lower()
        matched_keywords = []

        for keyword in self.captcha_keywords:
            if keyword.lower() in combined_text:
                matched_keywords.append(keyword)

        if not matched_keywords:
            return None

        # Further confirm: find captcha-related UI elements
        captcha_elements = self._find_captcha_elements(root)
        confidence = min(0.5 + len(matched_keywords) * 0.15 + len(captcha_elements) * 0.1, 1.0)

        return RiskSignal(
            risk_type=RiskType.CAPTCHA,
            confidence=confidence,
            source='text',
            details=f"Detected captcha keywords: {matched_keywords}",
            element_info={'captcha_elements': len(captcha_elements)}
        )

    def _find_captcha_elements(self, root) -> List:
        """Find captcha-related UI elements."""
        elements = []
        captcha_patterns = [
            r'captcha', r'verify', r'slider', r'puzzle',
            r'验证', r'滑块', r'拼图'
        ]

        for elem in root.iter():
            resource_id = elem.attrib.get('resource-id', '').lower()
            class_name = elem.attrib.get('class', '').lower()
            content_desc = elem.attrib.get('content-desc', '').lower()

            for pattern in captcha_patterns:
                if (re.search(pattern, resource_id) or
                    re.search(pattern, class_name) or
                    re.search(pattern, content_desc)):
                    elements.append(elem)
                    break

        return elements

    def _detect_login(self, texts: List[str], root) -> Optional[RiskSignal]:
        """Detect login requirement."""
        combined_text = ' '.join(texts).lower()
        matched_keywords = []

        for keyword in self.login_keywords:
            if keyword.lower() in combined_text:
                matched_keywords.append(keyword)

        if not matched_keywords:
            return None

        # Confirm by finding login button
        has_login_button = self._find_login_button(root)
        confidence = 0.4 + len(matched_keywords) * 0.15
        if has_login_button:
            confidence += 0.2
        confidence = min(confidence, 1.0)

        return RiskSignal(
            risk_type=RiskType.LOGIN_REQUIRED,
            confidence=confidence,
            source='text',
            details=f"Detected login keywords: {matched_keywords}"
        )

    def _find_login_button(self, root) -> bool:
        """Find login button."""
        login_patterns = [r'登录', r'login', r'sign.?in']

        for elem in root.iter():
            if elem.attrib.get('clickable') != 'true':
                continue

            text = elem.attrib.get('text', '').lower()
            content_desc = elem.attrib.get('content-desc', '').lower()

            for pattern in login_patterns:
                if re.search(pattern, text) or re.search(pattern, content_desc):
                    return True

        return False

    def _detect_rate_limit(self, texts: List[str]) -> Optional[RiskSignal]:
        """Detect rate limit."""
        combined_text = ' '.join(texts).lower()
        matched_keywords = []

        for keyword in self.rate_limit_keywords:
            if keyword.lower() in combined_text:
                matched_keywords.append(keyword)

        if not matched_keywords:
            return None

        return RiskSignal(
            risk_type=RiskType.RATE_LIMIT,
            confidence=0.7 + len(matched_keywords) * 0.1,
            source='text',
            details=f"Detected rate limit keywords: {matched_keywords}"
        )

    def _detect_block(self, texts: List[str]) -> Optional[RiskSignal]:
        """Detect account block."""
        combined_text = ' '.join(texts).lower()
        matched_keywords = []

        for keyword in self.block_keywords:
            if keyword.lower() in combined_text:
                matched_keywords.append(keyword)

        if not matched_keywords:
            return None

        return RiskSignal(
            risk_type=RiskType.BLOCKED,
            confidence=0.8,
            source='text',
            details=f"Detected block keywords: {matched_keywords}"
        )

    def _detect_ui_anomaly(self, node_count: int, texts: List[str]) -> Optional[RiskSignal]:
        """Detect UI anomaly."""
        # Too few nodes may be empty or error page
        if node_count < self.min_node_count:
            return RiskSignal(
                risk_type=RiskType.UI_ANOMALY,
                confidence=0.6,
                source='ui',
                details=f"UI node count abnormally low: {node_count}"
            )

        # Almost no text may be load failure
        if len(texts) < self.empty_page_threshold:
            return RiskSignal(
                risk_type=RiskType.UI_ANOMALY,
                confidence=0.5,
                source='ui',
                details=f"Page text very few: {len(texts)} text elements"
            )

        return None

    def get_highest_risk(self, signals: List[RiskSignal]) -> Optional[RiskSignal]:
        """
        Get highest risk signal.

        Args:
            signals: List of risk signals

        Returns:
            Highest confidence risk signal
        """
        if not signals:
            return None

        # Sort by priority: BLOCKED > CAPTCHA > LOGIN > RATE_LIMIT > UI_ANOMALY
        priority = {
            RiskType.BLOCKED: 5,
            RiskType.CAPTCHA: 4,
            RiskType.LOGIN_REQUIRED: 3,
            RiskType.RATE_LIMIT: 2,
            RiskType.UI_ANOMALY: 1,
        }

        return max(signals, key=lambda s: (priority.get(s.risk_type, 0), s.confidence))

    def is_safe(self, signals: List[RiskSignal], threshold: float = 0.6) -> bool:
        """
        Determine if current page is safe.

        Args:
            signals: List of risk signals
            threshold: Confidence threshold

        Returns:
            Whether safe
        """
        high_risk_signals = [s for s in signals if s.confidence >= threshold]
        return len(high_risk_signals) == 0

    def detect_captcha_type(self, root) -> Optional[str]:
        """
        Detect captcha type.

        Args:
            root: XML Element root node

        Returns:
            Captcha type: 'slider', 'puzzle', 'click', 'sms', 'image', None
        """
        if root is None:
            return None

        # Collect all relevant info
        all_info = []
        for elem in root.iter():
            resource_id = elem.attrib.get('resource-id', '').lower()
            class_name = elem.attrib.get('class', '').lower()
            text = elem.attrib.get('text', '').lower()
            content_desc = elem.attrib.get('content-desc', '').lower()
            all_info.extend([resource_id, class_name, text, content_desc])

        combined = ' '.join(all_info)

        # Slider captcha
        slider_patterns = ['slider', '滑块', '滑动', 'seekbar', '向右滑动']
        for pattern in slider_patterns:
            if pattern in combined:
                return 'slider'

        # Puzzle captcha
        puzzle_patterns = ['puzzle', '拼图', '拖动', '缺口']
        for pattern in puzzle_patterns:
            if pattern in combined:
                return 'puzzle'

        # Click captcha
        click_patterns = ['点击', '选择', '依次点击', '按顺序']
        for pattern in click_patterns:
            if pattern in combined:
                return 'click'

        # SMS captcha
        sms_patterns = ['短信', '验证码已发送', '获取验证码', 'sms']
        for pattern in sms_patterns:
            if pattern in combined:
                return 'sms'

        # Image captcha (input text)
        image_patterns = ['输入图中', '看不清', '换一张', '图片验证']
        for pattern in image_patterns:
            if pattern in combined:
                return 'image'

        return None
