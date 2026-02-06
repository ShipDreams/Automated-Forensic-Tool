#!/usr/bin/env python3
"""
State Detector
Recognizes current page state based on UI hierarchy.
"""

import re
import logging
from typing import Optional, List, Dict, Tuple
from dataclasses import dataclass

from locales import t
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
    """State match result."""
    state: PageState
    confidence: float
    matched_features: List[str]
    platform: str


class StateDetector:
    """
    State Detector

    Core features:
    - Recognize current page state from UI hierarchy
    - Support multi-platform state definitions
    - Return the highest confidence match
    """

    def __init__(self, platform: str = None):
        """
        Initialize state detector.

        Args:
            platform: Platform name, used to load platform-specific state definitions
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
        Detect current page state.

        Args:
            ui_root: UI hierarchy tree root node
            package_name: Current package name
            activity_name: Current Activity name

        Returns:
            Best matching state
        """
        if ui_root is None:
            return StateMatch(
                state=PageState.ERROR,
                confidence=0.9,
                matched_features=['ui_root is None'],
                platform='common'
            )

        # Collect UI info
        ui_info = self._collect_ui_info(ui_root)

        # Try to match all states
        matches = []
        for state, definition in self.state_definitions.items():
            match = self._match_state(definition, ui_info, package_name, activity_name)
            if match:
                matches.append(match)

        # Select highest confidence
        if matches:
            best_match = max(matches, key=lambda m: m.confidence)
            logger.debug(t('log.state_detected',
                          state=best_match.state.name,
                          confidence=best_match.confidence))
            return best_match

        # No state matched
        return StateMatch(
            state=PageState.UNKNOWN,
            confidence=0.0,
            matched_features=[],
            platform='common'
        )

    def _collect_ui_info(self, ui_root) -> Dict:
        """Collect UI hierarchy info."""
        texts = []
        elements = []

        for elem in ui_root.iter():
            attrib = elem.attrib

            # Collect texts
            text = attrib.get('text', '')
            content_desc = attrib.get('content-desc', '')
            if text:
                texts.append(text.lower())
            if content_desc:
                texts.append(content_desc.lower())

            # Collect element info
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
        """Try to match a single state."""
        features = definition.features
        matched = []
        score = 0.0
        total_weight = 0.0

        # Match required texts (high weight)
        if features.required_texts:
            required_match = 0
            for text in features.required_texts:
                if text.lower() in ui_info['all_text']:
                    required_match += 1
                    matched.append(f"text:{text}")

            if required_match == 0:
                return None  # No required text matched

            weight = 3.0
            score += (required_match / len(features.required_texts)) * weight
            total_weight += weight

        # Match optional texts
        if features.optional_texts:
            optional_match = 0
            for text in features.optional_texts:
                if text.lower() in ui_info['all_text']:
                    optional_match += 1
                    matched.append(f"optional_text:{text}")

            weight = 1.0
            score += (optional_match / len(features.optional_texts)) * weight
            total_weight += weight

        # Check excluded texts
        if features.excluded_texts:
            for text in features.excluded_texts:
                if text.lower() in ui_info['all_text']:
                    return None  # Contains excluded text, no match

        # Match package name
        if features.package_patterns and package_name:
            for pattern in features.package_patterns:
                if re.search(pattern, package_name, re.IGNORECASE):
                    matched.append(f"package:{pattern}")
                    score += 2.0
                    total_weight += 2.0
                    break
            else:
                # Package name doesn't match, lower confidence
                if total_weight == 0:
                    return None

        # Match Activity
        if features.activity_patterns and activity_name:
            for pattern in features.activity_patterns:
                if re.search(pattern, activity_name, re.IGNORECASE):
                    matched.append(f"activity:{pattern}")
                    score += 1.5
                    total_weight += 1.5
                    break

        # Match required elements
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

        # Match optional elements
        if features.optional_elements:
            optional_match = 0
            for optional in features.optional_elements:
                if self._match_element(optional, ui_info['elements']):
                    optional_match += 1
                    matched.append(f"optional_element")

            weight = 0.5
            score += (optional_match / len(features.optional_elements)) * weight
            total_weight += weight

        # Calculate final confidence
        if total_weight == 0:
            return None

        confidence = score / total_weight

        # Check threshold
        if confidence < features.confidence_threshold:
            return None

        return StateMatch(
            state=definition.state,
            confidence=min(confidence, 1.0),
            matched_features=matched,
            platform=definition.platform
        )

    def _match_element(self, required: Dict, elements: List[Dict]) -> bool:
        """Match a single element."""
        for elem in elements:
            match = True

            for key, value in required.items():
                if key.endswith('_pattern'):
                    # Regex match
                    actual_key = key[:-8]  # Remove _pattern
                    actual_value = elem.get(actual_key, '')
                    if not re.search(value, actual_value, re.IGNORECASE):
                        match = False
                        break
                else:
                    # Exact match
                    if elem.get(key) != value:
                        match = False
                        break

            if match:
                return True

        return False

    def is_risk_state(self, state: PageState) -> bool:
        """Check if state is a risk state."""
        return state in [
            PageState.CAPTCHA,
            PageState.LOGIN_REQUIRED,
            PageState.BLOCKED,
            PageState.RATE_LIMITED,
        ]

    def is_popup_state(self, state: PageState) -> bool:
        """Check if state is a popup state."""
        return state in [
            PageState.POPUP_AD,
            PageState.POPUP_PERMISSION,
            PageState.POPUP_UPDATE,
            PageState.POPUP_OTHER,
        ]

    def detect_quick(self, ui_root) -> PageState:
        """
        Quick detection (returns only state, no detailed info).

        Args:
            ui_root: UI hierarchy tree root node

        Returns:
            Page state
        """
        match = self.detect(ui_root)
        return match.state
