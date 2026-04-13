#!/usr/bin/env python3
"""
External OCR worker entrypoint for packaged Windows builds.

This script is executed by a separately installed Python runtime so the
main packaged GUI process does not need to host PaddleOCR itself.
"""

import sys
from pathlib import Path
import importlib.util


def main() -> int:
    script_dir = Path(__file__).resolve().parent
    if str(script_dir) not in sys.path:
        sys.path.insert(0, str(script_dir))

    ocr_engine_path = script_dir / "core" / "ocr_engine.py"
    spec = importlib.util.spec_from_file_location("ocr_engine_worker", ocr_engine_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load OCR worker module: {ocr_engine_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    return module._subprocess_cli()


if __name__ == "__main__":
    raise SystemExit(main())
