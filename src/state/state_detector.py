#!/usr/bin/env python3
"""
状态检测器
根据 UI 层级识别当前页面状态
"""

import re
import logging
from typing import Optional, List, Dict, Tuple
from dataclasses import dataclass

from .states import (
    PageState,
    StateFeature,
    StateDefinition,
    get_all_states_for_platform,
    COMMON_STATES,
)

logger = logging.getLogger(__name__)


@dataclass
class StateMatch:
    """状态匹配结果"""
    state: PageState
    confidence: float
    matched_features: List[str]
    platform: str


class StateDetector:
    """
    状态检测器

    核心功能：
    - 从 UI 层级识别当前页面状态
    - 支持多平台状态定义
    - 返回置信度最高的匹配
    """

    def __init__(self, platform: str = None):
        """
        初始化状态检测器

        Args:
            platform: 平台名称，用于加载特定平台的状态定义
        """
        self.platform = platform
        self.state_definitions = get_all_states_for_platform(platform)

    def detect(
        self,
        ui_root,
        package_name: str = None,
        activity_name: str = None
    ) -> StateMatch:
        """
        检测当前页面状态

        Args:
            ui_root: UI 层级树根节点
            package_name: 当前包名
            activity_name: 当前 Activity 名

        Returns:
            最佳匹配的状态
        """
        if ui_root is None:
            return StateMatch(
                state=PageState.ERROR,
                confidence=0.9,
                matched_features=['ui_root is None'],
                platform='common'
            )

        # 收集 UI 信息
        ui_info = self._collect_ui_info(ui_root)

        # 尝试匹配所有状态
        matches = []
        for state, definition in self.state_definitions.items():
            match = self._match_state(definition, ui_info, package_name, activity_name)
            if match:
                matches.append(match)

        # 选择置信度最高的
        if matches:
            best_match = max(matches, key=lambda m: m.confidence)
            logger.debug(f"检测到状态: {best_match.state.name} "
                        f"(置信度: {best_match.confidence:.2f})")
            return best_match

        # 没有匹配到任何状态
        return StateMatch(
            state=PageState.UNKNOWN,
            confidence=0.0,
            matched_features=[],
            platform='common'
        )

    def _collect_ui_info(self, ui_root) -> Dict:
        """收集 UI 层级信息"""
        texts = []
        elements = []

        for elem in ui_root.iter():
            attrib = elem.attrib

            # 收集文本
            text = attrib.get('text', '')
            content_desc = attrib.get('content-desc', '')
            if text:
                texts.append(text.lower())
            if content_desc:
                texts.append(content_desc.lower())

            # 收集元素信息
            elements.append({
                'class': attrib.get('class', ''),
                'resource-id': attrib.get('resource-id', ''),
                'text': text,
                'content-desc': content_desc,
                'clickable': attrib.get('clickable', 'false'),
                'bounds': attrib.get('bounds', ''),
            })

        return {
            'texts': texts,
            'all_text': ' '.join(texts),
            'elements': elements,
            'node_count': len(elements),
        }

    def _match_state(
        self,
        definition: StateDefinition,
        ui_info: Dict,
        package_name: str = None,
        activity_name: str = None
    ) -> Optional[StateMatch]:
        """尝试匹配单个状态"""
        features = definition.features
        matched = []
        score = 0.0
        total_weight = 0.0

        # 匹配必需文本（权重高）
        if features.required_texts:
            required_match = 0
            for text in features.required_texts:
                if text.lower() in ui_info['all_text']:
                    required_match += 1
                    matched.append(f"text:{text}")

            if required_match == 0:
                return None  # 没有匹配到任何必需文本

            weight = 3.0
            score += (required_match / len(features.required_texts)) * weight
            total_weight += weight

        # 匹配可选文本
        if features.optional_texts:
            optional_match = 0
            for text in features.optional_texts:
                if text.lower() in ui_info['all_text']:
                    optional_match += 1
                    matched.append(f"optional_text:{text}")

            weight = 1.0
            score += (optional_match / len(features.optional_texts)) * weight
            total_weight += weight

        # 检查排除文本
        if features.excluded_texts:
            for text in features.excluded_texts:
                if text.lower() in ui_info['all_text']:
                    return None  # 包含排除文本，不匹配

        # 匹配包名
        if features.package_patterns and package_name:
            for pattern in features.package_patterns:
                if re.search(pattern, package_name, re.IGNORECASE):
                    matched.append(f"package:{pattern}")
                    score += 2.0
                    total_weight += 2.0
                    break
            else:
                # 包名不匹配，降低置信度
                if total_weight == 0:
                    return None

        # 匹配 Activity
        if features.activity_patterns and activity_name:
            for pattern in features.activity_patterns:
                if re.search(pattern, activity_name, re.IGNORECASE):
                    matched.append(f"activity:{pattern}")
                    score += 1.5
                    total_weight += 1.5
                    break

        # 匹配必需元素
        if features.required_elements:
            element_match = 0
            for required in features.required_elements:
                if self._match_element(required, ui_info['elements']):
                    element_match += 1
                    matched.append(f"element:{required}")

            if element_match == 0:
                return None

            weight = 2.0
            score += (element_match / len(features.required_elements)) * weight
            total_weight += weight

        # 匹配可选元素
        if features.optional_elements:
            optional_match = 0
            for optional in features.optional_elements:
                if self._match_element(optional, ui_info['elements']):
                    optional_match += 1
                    matched.append(f"optional_element")

            weight = 0.5
            score += (optional_match / len(features.optional_elements)) * weight
            total_weight += weight

        # 计算最终置信度
        if total_weight == 0:
            return None

        confidence = score / total_weight

        # 检查阈值
        if confidence < features.confidence_threshold:
            return None

        return StateMatch(
            state=definition.state,
            confidence=min(confidence, 1.0),
            matched_features=matched,
            platform=definition.platform
        )

    def _match_element(self, required: Dict, elements: List[Dict]) -> bool:
        """匹配单个元素"""
        for elem in elements:
            match = True

            for key, value in required.items():
                if key.endswith('_pattern'):
                    # 正则匹配
                    actual_key = key[:-8]  # 去掉 _pattern
                    actual_value = elem.get(actual_key, '')
                    if not re.search(value, actual_value, re.IGNORECASE):
                        match = False
                        break
                else:
                    # 精确匹配
                    if elem.get(key) != value:
                        match = False
                        break

            if match:
                return True

        return False

    def is_risk_state(self, state: PageState) -> bool:
        """判断是否为风险状态"""
        return state in [
            PageState.CAPTCHA,
            PageState.LOGIN_REQUIRED,
            PageState.BLOCKED,
            PageState.RATE_LIMITED,
        ]

    def is_popup_state(self, state: PageState) -> bool:
        """判断是否为弹窗状态"""
        return state in [
            PageState.POPUP_AD,
            PageState.POPUP_PERMISSION,
            PageState.POPUP_UPDATE,
            PageState.POPUP_OTHER,
        ]

    def detect_quick(self, ui_root) -> PageState:
        """
        快速检测（只返回状态，不返回详细信息）

        Args:
            ui_root: UI 层级树根节点

        Returns:
            页面状态
        """
        match = self.detect(ui_root)
        return match.state
