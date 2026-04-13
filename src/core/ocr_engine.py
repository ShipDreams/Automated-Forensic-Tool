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
import json
import subprocess
import sys
import argparse
from typing import Dict, List, Optional, Tuple
import tempfile

import cv2
from locales import t

logger = logging.getLogger(__name__)

_OCR_LOCAL = threading.local()
_OCR_SEMAPHORE = threading.BoundedSemaphore(1)
_OCR_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ocr-worker")
_OCR_MAX_IMAGE_SIDE = 1280


class OCREngine:
    """PaddleOCR-based recognizer with per-thread lazy initialization."""

    COMPANY_FIELD_LABELS = ("公司名称", "企业名称", "名称")
    EXCLUDED_FIELD_KEYWORDS = (
        "公司类型", "企业类型", "类型", "法定代表人", "统一社会信用代码",
        "注册号", "营业执照注册号", "注册地址", "注册资本", "经营范围",
        "登记机关", "经营期限", "经营期限至", "经营期限自", "营业期限",
        "经营场所", "住所", "成立日期", "核准日期", "社会信用代码",
    )
    COMPANY_SUFFIXES = (
        "有限责任公司", "股份有限公司", "有限公司", "集团",
        "百货店", "商行", "经营部", "工作室", "商贸中心", "服务部",
        "门市部", "便利店", "商店", "中心"
    )
    INDIVIDUAL_BUSINESS_MARKERS = ("个体工商户",)

    def _get_ocr(self):
        """Lazily initialize one lightweight PaddleOCR instance per worker thread."""
        if not hasattr(_OCR_LOCAL, "instance"):
            logger.info(t('log.ocr_init_start'))
            os.environ.setdefault("DISABLE_MODEL_SOURCE_CHECK", "True")
            os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
            from paddleocr import PaddleOCR
            _OCR_LOCAL.instance = PaddleOCR(
                lang='ch',
                ocr_version='PP-OCRv4',
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
                text_det_limit_side_len=_OCR_MAX_IMAGE_SIDE,
            )
            logger.info(t('log.ocr_init_done'))
        return _OCR_LOCAL.instance

    def _prepare_image_for_ocr(self, image_path: str) -> Tuple[str, Optional[Path]]:
        """
        Resize large screenshots before OCR to reduce Windows CPU inference time.

        Returns:
            (path_to_use, temp_file_to_cleanup)
        """
        image = cv2.imread(image_path)
        if image is None:
            logger.warning(f"Failed to read OCR image via OpenCV, using original file: {image_path}")
            return image_path, None

        height, width = image.shape[:2]
        longest = max(height, width)
        if longest <= _OCR_MAX_IMAGE_SIDE:
            return image_path, None

        scale = _OCR_MAX_IMAGE_SIDE / float(longest)
        resized = cv2.resize(
            image,
            (max(1, int(width * scale)), max(1, int(height * scale))),
            interpolation=cv2.INTER_AREA,
        )

        temp_dir = Path(tempfile.gettempdir()) / "automated_forensic_tool" / "ocr_resized"
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_path = temp_dir / f"{Path(image_path).stem}_lite{Path(image_path).suffix}"
        cv2.imwrite(str(temp_path), resized)
        logger.info(f"OCR image resized for lightweight inference: {temp_path}")
        return str(temp_path), temp_path

    def recognize_text(self, image_path: str) -> List[Dict]:
        """
        Recognize all text blocks in an image.

        Returns:
            [{"text": "...", "confidence": 0.95, "box": [[x1, y1], ...]}]
        """
        logger.info(t('log.ocr_recognition_start', path=image_path))
        prepared_path, temp_path = self._prepare_image_for_ocr(image_path)
        with _OCR_SEMAPHORE:
            logger.info(t('log.ocr_semaphore_acquired'))
            try:
                result = self._get_ocr().predict(prepared_path)
            finally:
                if temp_path:
                    try:
                        temp_path.unlink()
                    except FileNotFoundError:
                        pass
                    except Exception as e:
                        logger.debug(f"Failed to remove temporary OCR image '{temp_path}': {e}")
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
            r"(.+?(?:有限责任公司|股份有限公司|有限公司|集团|百货店|商行|经营部|工作室|商贸中心|服务部|门市部|便利店|商店|中心)(?:（个体工商户）|\(个体工商户\))?)"
        )
        match = re.search(pattern, text)
        if not match:
            return None
        return self._clean_company_name(match.group(1))

    def _match_unlabeled_company_name(self, text: str) -> Optional[str]:
        if self._contains_excluded_field(text):
            return None
        if not any(keyword in text for keyword in self.COMPANY_SUFFIXES) and \
           not any(marker in text for marker in self.INDIVIDUAL_BUSINESS_MARKERS):
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

        cleaned = re.sub(r"(（个体工商户）|\(个体工商户\))$", "", cleaned)
        cleaned = cleaned.strip()

        for suffix in self.COMPANY_SUFFIXES:
            idx = cleaned.find(suffix)
            if idx != -1:
                candidate = cleaned[:idx + len(suffix)]
                if self._contains_excluded_field(candidate):
                    return None
                return candidate

        # Some individual-business subjects are easiest to detect by their marker,
        # while the actual主体名称 ends right before "(个体工商户)".
        for marker in self.INDIVIDUAL_BUSINESS_MARKERS:
            idx = cleaned.find(marker)
            if idx > 0:
                candidate = cleaned[:idx].rstrip("（()）")
                if len(candidate) >= 4 and not self._contains_excluded_field(candidate):
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


def _extract_company_name_with_status_quiet(image_path: str) -> Tuple[Optional[str], Optional[str]]:
    """Run OCR without emitting Python logger output from the worker process."""
    logging.disable(logging.CRITICAL)
    try:
        return extract_company_name_with_status(image_path)
    finally:
        logging.disable(logging.NOTSET)


def _parse_subprocess_json(stdout: str) -> Tuple[Optional[str], Optional[str]]:
    """Parse the last JSON line emitted by the OCR subprocess."""
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        return payload.get("company_name"), payload.get("note")
    return None, None


def _trim_subprocess_output(output: str, limit: int = 400) -> str:
    """Keep subprocess diagnostics short in parent-process logs."""
    output = (output or "").strip()
    if len(output) <= limit:
        return output
    return output[-limit:]


def extract_company_name_with_status_subprocess(
    image_path: str,
    timeout_seconds: int = 90,
) -> Tuple[Optional[str], Optional[str]]:
    """
    Run OCR in a separate Python process so native Paddle failures do not kill
    the main workflow process.
    """
    if not image_path:
        logger.warning("[ocr_subprocess] skipped: empty image path")
        return None, "OCR截图缺失"

    if not Path(image_path).exists():
        logger.warning(f"[ocr_subprocess] skipped: missing image path={image_path}")
        return None, "OCR截图缺失"

    module_cwd = str(Path(__file__).resolve().parents[1])
    cmd = [
        sys.executable,
        "-m",
        "core.ocr_engine",
        "--subprocess-ocr",
        image_path,
    ]
    logger.info(
        f"[ocr_subprocess] start: timeout={timeout_seconds}s, image_path={image_path}"
    )

    try:
        completed = subprocess.run(
            cmd,
            cwd=module_cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as e:
        stderr_tail = _trim_subprocess_output(e.stderr or "")
        if stderr_tail:
            logger.error(f"[ocr_subprocess] timeout stderr_tail={stderr_tail}")
        logger.error(f"[ocr_subprocess] timeout after {timeout_seconds}s")
        return None, f"OCR超时({timeout_seconds}s)"
    except Exception as e:
        logger.error(f"[ocr_subprocess] launch failed: {e}", exc_info=True)
        return None, f"OCR子进程启动失败: {e}"

    stderr_tail = _trim_subprocess_output(completed.stderr)
    if completed.returncode != 0:
        if stderr_tail:
            logger.error(
                f"[ocr_subprocess] crashed: exit_code={completed.returncode}, stderr_tail={stderr_tail}"
            )
        else:
            logger.error(f"[ocr_subprocess] crashed: exit_code={completed.returncode}")
        return None, f"OCR子进程异常退出(exit_code={completed.returncode})"

    company_name, note = _parse_subprocess_json(completed.stdout)
    if company_name:
        logger.info(f"[ocr_subprocess] success: company_name={company_name}")
        return company_name, None
    if note:
        logger.warning(f"[ocr_subprocess] completed without company name: note={note}")
        return None, note

    if stderr_tail:
        logger.error(f"[ocr_subprocess] invalid output, stderr_tail={stderr_tail}")
    else:
        logger.error("[ocr_subprocess] invalid output: missing JSON payload")
    return None, "OCR子进程未返回结果"


def start_company_name_extraction_async(image_path: str) -> Future:
    """Start OCR company name extraction in the background."""
    logger.info(t('log.ocr_async_submit', path=image_path))

    def _run_and_log_result() -> Tuple[Optional[str], Optional[str]]:
        result = extract_company_name_with_status(image_path)
        company_name, note = result
        if company_name:
            logger.info(f"OCR background result: company_name={company_name}")
        else:
            logger.warning(f"OCR background result: note={note or '无结果'}")
        return result

    return _OCR_EXECUTOR.submit(_run_and_log_result)


def _subprocess_cli() -> int:
    """Internal CLI entry used by the parent process to isolate OCR execution."""
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--subprocess-ocr", dest="image_path")
    args = parser.parse_args()
    if not args.image_path:
        return 2

    company_name, note = _extract_company_name_with_status_quiet(args.image_path)
    print(json.dumps({
        "company_name": company_name,
        "note": note,
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(_subprocess_cli())
