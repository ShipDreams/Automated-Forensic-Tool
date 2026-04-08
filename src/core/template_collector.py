#!/usr/bin/env python3
"""
Template image collector utility.
Crops template images from raw screenshots for use with ImageLocator.

Usage:
    python -m core.template_collector          # Crop all templates
    python -m core.template_collector --show   # Show raw images for coordinate inspection
"""

import logging
from pathlib import Path
from typing import Tuple, Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# Project root
PROJECT_ROOT = Path(__file__).parent.parent.parent
RAW_DIR = PROJECT_ROOT / "config" / "templates" / "raw"
OUTPUT_DIR = PROJECT_ROOT / "config" / "templates"


# Template definitions: output_name -> (source_file, x1, y1, x2, y2)
# Coordinates are based on 1080x2400 resolution screenshots.
# ImageLocator's multi-scale matching compensates for other resolutions.
TEMPLATE_DEFINITIONS = {
    # From screenshot_product_video.png: mute/unmute button (video area bottom-right, speaker icon)
    "mute_btn.png": ("screenshot_product_video.png", 990, 580, 1070, 650),

    # From screenshot_product_detail_bottom.png: bottom bar "店铺" text+icon (leftmost button)
    "shop_btn.png": ("screenshot_product_detail_bottom.png", 0, 2310, 140, 2400),
    # From screenshot_product_detail_bottom.png: bottom bar favorite/heart icon (second from left)
    "favorite_btn.png": ("screenshot_product_detail_bottom.png", 140, 2310, 280, 2400),

    # From screenshot_my_taobao.png: "收藏" entry icon+text area
    "favorites_entry.png": ("screenshot_my_taobao.png", 270, 970, 430, 1120),

    # From screenshot_favorites_list.png: "管理" button (top-right)
    "manage_btn.png": ("screenshot_favorites_list.png", 910, 100, 1060, 180),

    # From screenshot_favorites_manage.png: "退出管理" button (top-right)
    "exit_manage_btn.png": ("screenshot_favorites_manage.png", 860, 100, 1060, 180),

    # From screenshot_favorites_manage.png: bottom bar "全选" (leftmost)
    "select_all_btn.png": ("screenshot_favorites_manage.png", 0, 2300, 160, 2400),

    # From screenshot_favorites_manage.png: bottom bar "删除" (rightmost, red button)
    "delete_btn.png": ("screenshot_favorites_manage.png", 900, 2300, 1080, 2400),
}


class TemplateCollector:
    """Utility for cropping template images from raw screenshots."""

    def __init__(self, raw_dir=None, output_dir=None):
        self.raw_dir = Path(raw_dir) if raw_dir else RAW_DIR
        self.output_dir = Path(output_dir) if output_dir else OUTPUT_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def crop_template(self, source_name: str, x1: int, y1: int, x2: int, y2: int,
                      output_name: str, padding: int = 5) -> Optional[str]:
        """
        Crop a region from a source image and save as template.

        Args:
            source_name: Filename in raw directory
            x1, y1, x2, y2: Crop region coordinates
            output_name: Output filename
            padding: Extra pixels around crop region

        Returns:
            Output path or None on failure
        """
        source_path = self.raw_dir / source_name
        if not source_path.exists():
            logger.error(f"Source image not found: {source_path}")
            return None

        img = cv2.imread(str(source_path))
        if img is None:
            logger.error(f"Failed to read image: {source_path}")
            return None

        h, w = img.shape[:2]

        # Apply padding with bounds check
        crop_y1 = max(0, y1 - padding)
        crop_y2 = min(h, y2 + padding)
        crop_x1 = max(0, x1 - padding)
        crop_x2 = min(w, x2 + padding)

        cropped = img[crop_y1:crop_y2, crop_x1:crop_x2]
        if cropped.size == 0:
            logger.error(f"Empty crop region for {output_name}")
            return None

        output_path = self.output_dir / output_name
        cv2.imwrite(str(output_path), cropped)
        logger.info(f"Saved template: {output_path} ({cropped.shape[1]}x{cropped.shape[0]})")
        return str(output_path)

    def crop_all_templates(self) -> dict:
        """
        Crop all predefined templates from raw screenshots.

        Returns:
            {template_name: output_path or None}
        """
        results = {}
        for output_name, (source, x1, y1, x2, y2) in TEMPLATE_DEFINITIONS.items():
            path = self.crop_template(source, x1, y1, x2, y2, output_name)
            results[output_name] = path
            if path:
                print(f"  OK: {output_name}")
            else:
                print(f"  FAIL: {output_name}")
        return results

    def show_raw_image(self, source_name: str):
        """Display a raw image for coordinate inspection (interactive use)."""
        source_path = self.raw_dir / source_name
        if not source_path.exists():
            print(f"Not found: {source_path}")
            return

        img = cv2.imread(str(source_path))
        if img is None:
            print(f"Cannot read: {source_path}")
            return

        # Resize for display (raw screenshots are very large)
        h, w = img.shape[:2]
        scale = min(1.0, 800 / w)
        display = cv2.resize(img, (int(w * scale), int(h * scale)))

        window_name = f"{source_name} (scale={scale:.2f}, click to get coords)"

        def mouse_callback(event, x, y, flags, param):
            if event == cv2.EVENT_LBUTTONDOWN:
                # Convert back to original coordinates
                orig_x = int(x / scale)
                orig_y = int(y / scale)
                print(f"  Clicked: display=({x},{y}) -> original=({orig_x},{orig_y})")

        cv2.imshow(window_name, display)
        cv2.setMouseCallback(window_name, mouse_callback)
        print(f"Showing {source_name} ({w}x{h}). Click to get coordinates. Press any key to close.")
        cv2.waitKey(0)
        cv2.destroyAllWindows()

    def list_raw_images(self):
        """List all raw screenshot files."""
        print(f"Raw screenshots in {self.raw_dir}:")
        for f in sorted(self.raw_dir.glob("*.png")):
            img = cv2.imread(str(f))
            if img is not None:
                h, w = img.shape[:2]
                print(f"  {f.name} ({w}x{h})")
            else:
                print(f"  {f.name} (unreadable)")


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO)
    collector = TemplateCollector()

    if "--show" in sys.argv:
        collector.list_raw_images()
        for f in sorted(RAW_DIR.glob("*.png")):
            collector.show_raw_image(f.name)
    elif "--list" in sys.argv:
        collector.list_raw_images()
    else:
        print("Cropping all templates...")
        results = collector.crop_all_templates()
        success = sum(1 for v in results.values() if v)
        print(f"\nDone: {success}/{len(results)} templates generated")
