#!/usr/bin/env python3
"""
风险检测器
检测验证码、登录页、频率限制等风控信号
"""

import re
import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class RiskType(Enum):
    """风险类型枚举"""
    NONE = "none"
    CAPTCHA = "captcha"
    LOGIN_REQUIRED = "login_required"
    RATE_LIMIT = "rate_limit"
    BLOCKED = "blocked"
    UI_ANOMALY = "ui_anomaly"
    UNKNOWN = "unknown"


@dataclass
class RiskSignal:
    """风险信号数据类"""
    risk_type: RiskType
    confidence: float  # 0.0 - 1.0
    source: str  # 检测来源（text, ui, element）
    details: str  # 详细信息
    element_info: Optional[Dict] = None  # 相关 UI 元素信息


class RiskDetector:
    """
    风险检测器

    核心功能：
    - 检测验证码页面
    - 检测登录要求
    - 检测频率限制
    - 检测账号封禁
    - 检测 UI 异常
    """

    def __init__(self, config: dict = None):
        """
        初始化风险检测器

        Args:
            config: 配置字典，来自 config/antibot.json 的 risk_detection 部分
        """
        self.config = config or {}
        self._load_config()

    def _load_config(self):
        """加载配置参数"""
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
        从 UI 层级树检测风险

        Args:
            root: XML Element 根节点

        Returns:
            检测到的风险信号列表
        """
        if root is None:
            return [RiskSignal(
                risk_type=RiskType.UI_ANOMALY,
                confidence=0.9,
                source='ui',
                details='无法获取 UI 层级'
            )]

        signals = []

        # 收集所有文本
        texts = self._collect_all_texts(root)

        # 统计节点数
        node_count = len(list(root.iter()))

        # 检测各类风险
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
        """收集 UI 树中的所有文本"""
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
        """检测验证码"""
        combined_text = ' '.join(texts).lower()
        matched_keywords = []

        for keyword in self.captcha_keywords:
            if keyword.lower() in combined_text:
                matched_keywords.append(keyword)

        if not matched_keywords:
            return None

        # 进一步确认：查找验证码相关的 UI 元素
        captcha_elements = self._find_captcha_elements(root)
        confidence = min(0.5 + len(matched_keywords) * 0.15 + len(captcha_elements) * 0.1, 1.0)

        return RiskSignal(
            risk_type=RiskType.CAPTCHA,
            confidence=confidence,
            source='text',
            details=f"检测到验证码关键词: {matched_keywords}",
            element_info={'captcha_elements': len(captcha_elements)}
        )

    def _find_captcha_elements(self, root) -> List:
        """查找验证码相关的 UI 元素"""
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
        """检测登录要求"""
        combined_text = ' '.join(texts).lower()
        matched_keywords = []

        for keyword in self.login_keywords:
            if keyword.lower() in combined_text:
                matched_keywords.append(keyword)

        if not matched_keywords:
            return None

        # 查找登录按钮确认
        has_login_button = self._find_login_button(root)
        confidence = 0.4 + len(matched_keywords) * 0.15
        if has_login_button:
            confidence += 0.2
        confidence = min(confidence, 1.0)

        return RiskSignal(
            risk_type=RiskType.LOGIN_REQUIRED,
            confidence=confidence,
            source='text',
            details=f"检测到登录关键词: {matched_keywords}"
        )

    def _find_login_button(self, root) -> bool:
        """查找登录按钮"""
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
        """检测频率限制"""
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
            details=f"检测到频率限制关键词: {matched_keywords}"
        )

    def _detect_block(self, texts: List[str]) -> Optional[RiskSignal]:
        """检测账号封禁"""
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
            details=f"检测到封禁关键词: {matched_keywords}"
        )

    def _detect_ui_anomaly(self, node_count: int, texts: List[str]) -> Optional[RiskSignal]:
        """检测 UI 异常"""
        # 节点太少可能是空白页或错误页
        if node_count < self.min_node_count:
            return RiskSignal(
                risk_type=RiskType.UI_ANOMALY,
                confidence=0.6,
                source='ui',
                details=f"UI 节点数异常少: {node_count}"
            )

        # 几乎没有文本可能是加载失败
        if len(texts) < self.empty_page_threshold:
            return RiskSignal(
                risk_type=RiskType.UI_ANOMALY,
                confidence=0.5,
                source='ui',
                details=f"页面文本极少: {len(texts)} 个文本元素"
            )

        return None

    def get_highest_risk(self, signals: List[RiskSignal]) -> Optional[RiskSignal]:
        """
        获取最高风险的信号

        Args:
            signals: 风险信号列表

        Returns:
            最高置信度的风险信号
        """
        if not signals:
            return None

        # 按优先级排序：BLOCKED > CAPTCHA > LOGIN > RATE_LIMIT > UI_ANOMALY
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
        判断当前页面是否安全

        Args:
            signals: 风险信号列表
            threshold: 置信度阈值

        Returns:
            是否安全
        """
        high_risk_signals = [s for s in signals if s.confidence >= threshold]
        return len(high_risk_signals) == 0

    def detect_captcha_type(self, root) -> Optional[str]:
        """
        检测验证码类型

        Args:
            root: XML Element 根节点

        Returns:
            验证码类型: 'slider', 'puzzle', 'click', 'sms', 'image', None
        """
        if root is None:
            return None

        # 收集所有相关信息
        all_info = []
        for elem in root.iter():
            resource_id = elem.attrib.get('resource-id', '').lower()
            class_name = elem.attrib.get('class', '').lower()
            text = elem.attrib.get('text', '').lower()
            content_desc = elem.attrib.get('content-desc', '').lower()
            all_info.extend([resource_id, class_name, text, content_desc])

        combined = ' '.join(all_info)

        # 滑块验证码
        slider_patterns = ['slider', '滑块', '滑动', 'seekbar', '向右滑动']
        for pattern in slider_patterns:
            if pattern in combined:
                return 'slider'

        # 拼图验证码
        puzzle_patterns = ['puzzle', '拼图', '拖动', '缺口']
        for pattern in puzzle_patterns:
            if pattern in combined:
                return 'puzzle'

        # 点击验证码
        click_patterns = ['点击', '选择', '依次点击', '按顺序']
        for pattern in click_patterns:
            if pattern in combined:
                return 'click'

        # 短信验证码
        sms_patterns = ['短信', '验证码已发送', '获取验证码', 'sms']
        for pattern in sms_patterns:
            if pattern in combined:
                return 'sms'

        # 图片验证码（输入文字）
        image_patterns = ['输入图中', '看不清', '换一张', '图片验证']
        for pattern in image_patterns:
            if pattern in combined:
                return 'image'

        return None
