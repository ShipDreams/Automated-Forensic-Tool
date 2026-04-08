#!/usr/bin/env python3
"""
OCR engine for extracting company names from qualification screenshots.
"""

from concurrent.futures import Future, ThreadPoolExecutor
import os
from pathlib import Path
import logging
import re
import threading
from typing import Dict, List, Optional, Tuple

from locales import t

logger = logging.getLogger(__name__)

_OCR_LOCAL = threading.local()
_OCR_SEMAPHORE = threading.BoundedSemaphore(2)
_OCR_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="ocr-worker")


class OCREngine:
    """PaddleOCR-based recognizer with per-thread lazy initialization."""

    COMPANY_FIELD_LABELS = ("公司名称", "企业名称", "名称")
    EXCLUDED_FIELD_KEYWORDS = (
        "公司类型", "企业类型", "类型", "法定代表人", "统一社会信用代码",
        "注册号", "营业执照注册号", "注册地址", "注册资本", "经营范围",
        "登记机关", "经营期限", "经营期限至", "经营期限自", "营业期限",
        "经营场所", "住所", "成立日期", "核准日期", "社会信用代码",
    )
    COMPANY_SUFFIXES = ("有限责任公司", "股份有限公司", "有限公司", "集团")

    def _get_ocr(self):
        """Lazily initialize one PaddleOCR 3.4.0 instance per worker thread."""
        if not hasattr(_OCR_LOCAL, "instance"):
            logger.info(t('log.ocr_init_start'))
            os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
            from paddleocr import PaddleOCR
            _OCR_LOCAL.instance = PaddleOCR(
                lang='ch',
            )
            logger.info(t('log.ocr_init_done'))
        return _OCR_LOCAL.instance

    def recognize_text(self, image_path: str) -> List[Dict]:
        """
        Recognize all text blocks in an image.

        Returns:
            [{"text": "...", "confidence": 0.95, "box": [[x1, y1], ...]}]
        """
        logger.info(t('log.ocr_recognition_start', path=image_path))
        with _OCR_SEMAPHORE:
            logger.info(t('log.ocr_semaphore_acquired'))
            result = self._get_ocr().predict(image_path)
        logger.info(t('log.ocr_recognition_done', path=image_path))

        texts = []
        if result and result[0]:
            first_result = result[0]
            rec_texts = list(first_result.get('rec_texts', []))
            rec_scores = list(first_result.get('rec_scores', []))
            rec_polys = list(first_result.get('rec_polys', []))

            for index, text in enumerate(rec_texts):
                confidence = rec_scores[index] if index < len(rec_scores) else 0.0
                box = rec_polys[index] if index < len(rec_polys) else []
                texts.append({
                    "text": text,
                    "confidence": confidence,
                    "box": box,
                })
        logger.info(t('log.ocr_text_blocks_extracted', count=len(texts)))
        return texts

    def extract_company_name(self, image_path: str) -> Optional[str]:
        """Extract company name from a qualification screenshot."""
        logger.info(t('log.ocr_company_extract_start', path=image_path))
        texts = self.recognize_text(image_path)
        normalized_items = self._prepare_items(texts)
        all_text = [item["text"] for item in normalized_items]

        candidate = self._extract_from_labeled_items(normalized_items)
        if candidate:
            logger.info(t('log.ocr_company_match_labeled', company_name=candidate))
            return candidate

        for text in all_text:
            candidate = self._match_labeled_company_name(text)
            if candidate:
                logger.info(t('log.ocr_company_match_labeled', company_name=candidate))
                return candidate

        full_text = " ".join(all_text)
        candidate = self._match_labeled_company_name(full_text)
        if candidate:
            logger.info(t('log.ocr_company_match_merged', company_name=candidate))
            return candidate

        for text in all_text:
            candidate = self._match_unlabeled_company_name(text)
            if candidate:
                logger.info(t('log.ocr_company_match_unlabeled', company_name=candidate))
                return candidate

        logger.warning(t('log.ocr_company_no_match'))
        return None

    @staticmethod
    def _normalize_text(text: str) -> str:
        """Normalize OCR text while preserving Chinese punctuation."""
        return re.sub(r"\s+", " ", (text or "")).strip()

    def _prepare_items(self, texts: List[Dict]) -> List[Dict]:
        """Normalize and sort OCR lines by their top Y coordinate."""
        prepared = []
        for item in texts:
            text = self._normalize_text(item.get("text", ""))
            if not text:
                continue
            box = item.get("box")
            if box is None:
                box = []
            elif hasattr(box, "tolist"):
                box = box.tolist()
            prepared.append({
                "text": text,
                "confidence": item.get("confidence", 0.0),
                "box": box,
                "top": self._box_top(box),
            })
        prepared.sort(key=lambda item: item["top"])
        return prepared

    @staticmethod
    def _box_top(box) -> float:
        """Get the smallest Y from an OCR polygon box."""
        try:
            ys = [point[1] for point in box if len(point) >= 2]
            if ys:
                return min(ys)
        except Exception:
            pass
        return float('inf')

    def _extract_from_labeled_items(self, items: List[Dict]) -> Optional[str]:
        """Prefer company-name labels and nearby text over generic fallbacks."""
        for index, item in enumerate(items):
            text = item["text"]

            candidate = self._match_labeled_company_name(text)
            if candidate:
                return candidate

            if not self._is_company_label_only(text):
                continue

            for neighbor in items[index + 1:index + 3]:
                if self._same_line(item, neighbor):
                    continue
                neighbor_candidate = self._match_unlabeled_company_name(neighbor["text"])
                if neighbor_candidate:
                    return neighbor_candidate

        return None

    def _is_company_label_only(self, text: str) -> bool:
        """Check whether the OCR line is only a company-name label."""
        stripped = re.sub(r"[：:\s]", "", text)
        return stripped in self.COMPANY_FIELD_LABELS

    def _same_line(self, current: Dict, other: Dict) -> bool:
        """Check whether two OCR boxes are visually on the same row."""
        current_top = current.get("top", float('inf'))
        other_top = other.get("top", float('inf'))
        if current_top == float('inf') or other_top == float('inf'):
            return False
        return abs(current_top - other_top) <= 12

    def _match_labeled_company_name(self, text: str) -> Optional[str]:
        pattern = (
            r"(?:名\s*称|企业名称|公司名称)"
            r"[：:\s]*"
            r"(.+?(?:有限责任公司|股份有限公司|有限公司|集团))"
        )
        match = re.search(pattern, text)
        if not match:
            return None
        return self._clean_company_name(match.group(1))

    def _match_unlabeled_company_name(self, text: str) -> Optional[str]:
        if self._contains_excluded_field(text):
            return None
        if not any(keyword in text for keyword in self.COMPANY_SUFFIXES):
            return None
        cleaned = re.sub(r"^.*?(?:名称|企业名称|公司名称)[：:\s]*", "", text)
        return self._clean_company_name(cleaned)

    def _contains_excluded_field(self, text: str) -> bool:
        """Reject non-company fields that often contain company suffix words."""
        return any(keyword in text for keyword in self.EXCLUDED_FIELD_KEYWORDS)

    def _clean_company_name(self, text: str) -> Optional[str]:
        cleaned = re.sub(r"[^\w\u4e00-\u9fff（）()·\-.]", "", text or "")
        cleaned = cleaned.strip("：:;；,，。 ")
        if len(cleaned) < 4:
            return None
        if self._contains_excluded_field(cleaned):
            return None

        for suffix in self.COMPANY_SUFFIXES:
            idx = cleaned.find(suffix)
            if idx != -1:
                candidate = cleaned[:idx + len(suffix)]
                if self._contains_excluded_field(candidate):
                    return None
                return candidate
        return None


def extract_company_name_with_status(image_path: str) -> Tuple[Optional[str], Optional[str]]:
    """
    Extract company name and convert failures into result notes.

    Returns:
        (company_name, note)
    """
    if not image_path:
        logger.warning(t('log.ocr_skipped_empty_path'))
        return None, "OCR截图缺失"

    if not Path(image_path).exists():
        logger.warning(t('log.ocr_skipped_missing_path', path=image_path))
        return None, "OCR截图缺失"

    try:
        logger.info(t('log.ocr_post_process_start', path=image_path))
        company_name = OCREngine().extract_company_name(image_path)
        if company_name:
            logger.info(t('log.ocr_post_process_success', company_name=company_name))
            return company_name, None
        logger.warning(t('log.ocr_post_process_no_result'))
        return None, "OCR未识别公司名称"
    except ImportError:
        logger.warning(t('log.ocr_import_missing'))
        return None, "PaddleOCR未安装"
    except Exception as e:
        logger.warning(t('log.ocr_extract_failed', error=e))
        return None, f"OCR异常: {e}"


def start_company_name_extraction_async(image_path: str) -> Future:
    """Start OCR company name extraction in the background."""
    logger.info(t('log.ocr_async_submit', path=image_path))
    return _OCR_EXECUTOR.submit(extract_company_name_with_status, image_path)
