#!/usr/bin/env python3
"""
Image-based UI element locator using OpenCV template matching.
Used as fallback when XML dump fails or for WebView pages.
"""

import subprocess
import logging
import time
from pathlib import Path
from typing import Optional, Tuple, List

import numpy as np
import cv2

logger = logging.getLogger(__name__)


class ImageLocator:
    """UI element locator based on OpenCV template matching."""

    def __init__(self, adb_controller, templates_dir=None):
        """
        Initialize image locator.

        Args:
            adb_controller: ADBController instance
            templates_dir: Path to template images directory
        """
        self.adb = adb_controller
        if templates_dir:
            self.template_dir = Path(templates_dir)
        else:
            self.template_dir = Path(__file__).parent.parent.parent / "config" / "templates"
        self.template_dir.mkdir(parents=True, exist_ok=True)
        self._template_cache = {}
        self._screen_size = None

    def _get_screen_size(self):
        """Get and cache screen size."""
        if self._screen_size is None:
            self._screen_size = self.adb.get_screen_size()
        return self._screen_size

    def capture_screen(self) -> Optional[np.ndarray]:
        """
        Capture current screen via ADB screencap.

        Returns:
            OpenCV BGR numpy array or None on failure
        """
        try:
            device_args = []
            if self.adb.device_id:
                device_args = ['-s', self.adb.device_id]

            cmd = ['adb'] + device_args + ['exec-out', 'screencap', '-p']
            result = subprocess.run(cmd, capture_output=True, timeout=10)

            if result.returncode != 0 or not result.stdout:
                logger.warning("screencap failed or returned empty data")
                return None

            # Decode PNG bytes to numpy array
            arr = np.frombuffer(result.stdout, dtype=np.uint8)
            img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if img is None:
                logger.warning("Failed to decode screenshot")
                return None

            return img
        except subprocess.TimeoutExpired:
            logger.warning("screencap timed out")
            return None
        except Exception as e:
            logger.warning(f"capture_screen error: {e}")
            return None

    def _load_template(self, template_name: str) -> Optional[np.ndarray]:
        """Load template image with caching."""
        if template_name in self._template_cache:
            return self._template_cache[template_name]

        # Try with and without .png extension
        if not template_name.endswith('.png'):
            template_name_full = template_name + '.png'
        else:
            template_name_full = template_name

        path = self.template_dir / template_name_full
        if not path.exists():
            logger.warning(f"Template not found: {path}")
            return None

        img = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if img is None:
            logger.warning(f"Failed to load template: {path}")
            return None

        self._template_cache[template_name] = img
        return img

    def _list_template_variants(self, template_name: str) -> list:
        """
        List all template variants for a logical name.

        Convention: a template can have multiple variants with suffixes:
            mute_btn.png, mute_btn_2.png, mute_btn_3.png, ...

        All variants are tried and the best match across them is returned.
        This allows the same logical button to have multiple visual styles
        (e.g. dark vs light background).
        """
        # Strip .png if present
        if template_name.endswith('.png'):
            base = template_name[:-4]
        else:
            base = template_name

        variants = []
        # Primary template
        primary = self.template_dir / f"{base}.png"
        if primary.exists():
            variants.append(f"{base}.png")

        # Numbered variants: _2, _3, _4, ...
        for i in range(2, 10):
            variant = self.template_dir / f"{base}_{i}.png"
            if variant.exists():
                variants.append(f"{base}_{i}.png")
            else:
                break

        return variants

    def find_template(self, template_name: str, threshold: float = 0.8,
                      scales: list = None, screen: np.ndarray = None
                      ) -> Optional[Tuple[int, int, float]]:
        """
        Find a template on the current screen.

        Supports template variants: if `template_name` is "mute_btn",
        will also try "mute_btn_2.png", "mute_btn_3.png", etc.,
        and return the best match across all variants.

        Args:
            template_name: Template image filename (with or without .png)
            threshold: Minimum confidence threshold (0-1)
            scales: Scale factors to try (default: [0.6, 0.8, 1.0, 1.2, 1.5])
            screen: Pre-captured screen image (captures new one if None)

        Returns:
            (center_x, center_y, confidence) or None
        """
        if screen is None:
            screen = self.capture_screen()
        if screen is None:
            return None

        # Get all variants for this template name
        variants = self._list_template_variants(template_name)
        if not variants:
            logger.warning(f"No template variants found for '{template_name}'")
            return None

        if scales is None:
            scales = [0.6, 0.8, 1.0, 1.2, 1.5]

        screen_gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)

        best_match = None
        best_confidence = 0.0
        best_variant = None

        # Try each variant
        for variant_name in variants:
            template = self._load_template(variant_name)
            if template is None:
                continue
            template_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)

            for scale in scales:
                if scale == 1.0:
                    resized = template_gray
                else:
                    new_w = int(template_gray.shape[1] * scale)
                    new_h = int(template_gray.shape[0] * scale)
                    if new_w < 5 or new_h < 5:
                        continue
                    resized = cv2.resize(template_gray, (new_w, new_h))

                # Template must be smaller than screen
                if resized.shape[0] > screen_gray.shape[0] or resized.shape[1] > screen_gray.shape[1]:
                    continue

                result = cv2.matchTemplate(screen_gray, resized, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, max_loc = cv2.minMaxLoc(result)

                if max_val > best_confidence:
                    best_confidence = max_val
                    h, w = resized.shape
                    center_x = max_loc[0] + w // 2
                    center_y = max_loc[1] + h // 2
                    best_match = (center_x, center_y, best_confidence)
                    best_variant = variant_name

        if best_match and best_match[2] >= threshold:
            if len(variants) > 1:
                logger.info(f"Template '{template_name}' matched via '{best_variant}' "
                            f"at ({best_match[0]}, {best_match[1]}) confidence={best_match[2]:.3f}")
            else:
                logger.info(f"Template '{template_name}' matched at ({best_match[0]}, {best_match[1]}) "
                            f"confidence={best_match[2]:.3f}")
            return best_match

        if best_match:
            logger.debug(f"Template '{template_name}' best match (via {best_variant}) "
                         f"confidence={best_match[2]:.3f} < threshold={threshold}")
        return None

    def find_and_click(self, template_name: str, threshold: float = 0.65,
                       max_attempts: int = 3, scales: list = None) -> bool:
        """
        Capture screen, find template, and tap the matched position.

        Args:
            template_name: Template image filename
            threshold: Minimum confidence threshold
            max_attempts: Maximum retry attempts
            scales: Scale factors to try

        Returns:
            Whether the template was found and clicked
        """
        for attempt in range(1, max_attempts + 1):
            match = self.find_template(template_name, threshold, scales)
            if match:
                x, y, confidence = match
                logger.info(f"Image click: '{template_name}' at ({x}, {y}), "
                            f"confidence={confidence:.3f}, attempt={attempt}")
                if self.adb.tap(x, y):
                    time.sleep(1.0)
                    return True
                else:
                    logger.warning(f"Tap failed at ({x}, {y})")

            if attempt < max_attempts:
                time.sleep(1.0)

        logger.warning(f"find_and_click failed for '{template_name}' after {max_attempts} attempts")
        return False

    def find_all_matches(self, template_name: str, threshold: float = 0.8,
                         max_count: int = 20, screen: np.ndarray = None
                         ) -> List[Tuple[int, int, float]]:
        """
        Find all occurrences of a template on screen.

        Args:
            template_name: Template image filename
            threshold: Minimum confidence threshold
            max_count: Maximum number of matches to return
            screen: Pre-captured screen image

        Returns:
            List of (center_x, center_y, confidence) sorted by y-coordinate
        """
        template = self._load_template(template_name)
        if template is None:
            return []

        if screen is None:
            screen = self.capture_screen()
        if screen is None:
            return []

        screen_gray = cv2.cvtColor(screen, cv2.COLOR_BGR2GRAY)
        template_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)

        if template_gray.shape[0] > screen_gray.shape[0] or \
           template_gray.shape[1] > screen_gray.shape[1]:
            return []

        result = cv2.matchTemplate(screen_gray, template_gray, cv2.TM_CCOEFF_NORMED)
        h, w = template_gray.shape

        matches = []
        result_copy = result.copy()

        for _ in range(max_count):
            _, max_val, _, max_loc = cv2.minMaxLoc(result_copy)
            if max_val < threshold:
                break

            center_x = max_loc[0] + w // 2
            center_y = max_loc[1] + h // 2
            matches.append((center_x, center_y, max_val))

            # Zero out the region around this match to find next one
            x_start = max(0, max_loc[0] - w // 2)
            y_start = max(0, max_loc[1] - h // 2)
            x_end = min(result_copy.shape[1], max_loc[0] + w)
            y_end = min(result_copy.shape[0], max_loc[1] + h)
            result_copy[y_start:y_end, x_start:x_end] = 0

        # Sort by y-coordinate (top to bottom)
        matches.sort(key=lambda m: m[1])

        if matches:
            logger.info(f"Found {len(matches)} matches for '{template_name}'")

        return matches

    def template_exists(self, template_name: str) -> bool:
        """Check if a template image file exists (any variant)."""
        return len(self._list_template_variants(template_name)) > 0
