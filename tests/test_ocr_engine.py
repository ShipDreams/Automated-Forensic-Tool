#!/usr/bin/env python3
"""
OCR engine unit tests.
"""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from core.ocr_engine import OCREngine, extract_company_name_with_status


class TestOCREngine(unittest.TestCase):
    def test_extract_company_name_from_labeled_line(self):
        engine = OCREngine()
        with patch.object(engine, 'recognize_text', return_value=[
            {"text": "名称：杭州某某电子商务有限公司", "confidence": 0.99, "box": []}
        ]):
            result = engine.extract_company_name("dummy.png")
        self.assertEqual(result, "杭州某某电子商务有限公司")

    def test_extract_company_name_from_joined_lines(self):
        engine = OCREngine()
        with patch.object(engine, 'recognize_text', return_value=[
            {"text": "企业名称：杭州某某", "confidence": 0.99, "box": []},
            {"text": "网络科技有限公司", "confidence": 0.99, "box": []},
        ]):
            result = engine.extract_company_name("dummy.png")
        self.assertEqual(result, "杭州某某网络科技有限公司")

    def test_extract_company_name_from_enterprise_name_line(self):
        engine = OCREngine()
        with patch.object(engine, 'recognize_text', return_value=[
            {"text": "企业名称：深圳市远航科技有限公司", "confidence": 0.99, "box": []}
        ]):
            result = engine.extract_company_name("dummy.png")
        self.assertEqual(result, "深圳市远航科技有限公司")

    def test_extract_company_name_from_unlabeled_line(self):
        engine = OCREngine()
        with patch.object(engine, 'recognize_text', return_value=[
            {"text": "杭州未来品牌管理有限公司", "confidence": 0.99, "box": []}
        ]):
            result = engine.extract_company_name("dummy.png")
        self.assertEqual(result, "杭州未来品牌管理有限公司")

    def test_extract_company_name_prefers_neighbor_after_label(self):
        engine = OCREngine()
        with patch.object(engine, 'recognize_text', return_value=[
            {"text": "公司名称", "confidence": 0.99, "box": [[0, 10], [10, 10], [10, 20], [0, 20]]},
            {"text": "惠州市江创机械设备有限公司", "confidence": 0.99, "box": [[0, 40], [10, 40], [10, 50], [0, 50]]},
            {"text": "公司类型有限责任公司", "confidence": 0.99, "box": [[0, 70], [10, 70], [10, 80], [0, 80]]},
        ]):
            result = engine.extract_company_name("dummy.png")
        self.assertEqual(result, "惠州市江创机械设备有限公司")

    def test_extract_company_name_prefers_neighbor_after_enterprise_label(self):
        engine = OCREngine()
        with patch.object(engine, 'recognize_text', return_value=[
            {"text": "企业名称", "confidence": 0.99, "box": [[0, 10], [10, 10], [10, 20], [0, 20]]},
            {"text": "杭州远望贸易有限公司", "confidence": 0.99, "box": [[0, 40], [10, 40], [10, 50], [0, 50]]},
            {"text": "企业类型有限责任公司", "confidence": 0.99, "box": [[0, 70], [10, 70], [10, 80], [0, 80]]},
        ]):
            result = engine.extract_company_name("dummy.png")
        self.assertEqual(result, "杭州远望贸易有限公司")

    def test_extract_company_name_rejects_company_type_false_positive(self):
        engine = OCREngine()
        with patch.object(engine, 'recognize_text', return_value=[
            {"text": "公司类型有限责任公司", "confidence": 0.99, "box": []},
            {"text": "法定代表人甘恩凤", "confidence": 0.99, "box": []},
        ]):
            result = engine.extract_company_name("dummy.png")
        self.assertIsNone(result)

    def test_extract_company_name_handles_numpy_boxes(self):
        engine = OCREngine()
        with patch.object(engine, 'recognize_text', return_value=[
            {
                "text": "公司名称",
                "confidence": 0.99,
                "box": np.array([[0, 10], [10, 10], [10, 20], [0, 20]]),
            },
            {
                "text": "惠州市江创机械设备有限公司",
                "confidence": 0.99,
                "box": np.array([[0, 40], [10, 40], [10, 50], [0, 50]]),
            },
        ]):
            result = engine.extract_company_name("dummy.png")
        self.assertEqual(result, "惠州市江创机械设备有限公司")

    def test_extract_company_name_returns_none_when_not_found(self):
        engine = OCREngine()
        with patch.object(engine, 'recognize_text', return_value=[
            {"text": "统一社会信用代码", "confidence": 0.99, "box": []}
        ]):
            result = engine.extract_company_name("dummy.png")
        self.assertIsNone(result)

    def test_extract_company_name_with_status_success(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            image_path = Path(tmpdir) / "capture.png"
            image_path.write_bytes(b"fake")

            with patch.object(OCREngine, 'extract_company_name', return_value="杭州未来品牌管理有限公司"):
                company_name, note = extract_company_name_with_status(str(image_path))

        self.assertEqual(company_name, "杭州未来品牌管理有限公司")
        self.assertIsNone(note)

    def test_extract_company_name_with_status_handles_missing_file(self):
        company_name, note = extract_company_name_with_status("/tmp/does-not-exist.png")
        self.assertIsNone(company_name)
        self.assertEqual(note, "OCR截图缺失")


if __name__ == '__main__':
    unittest.main()
