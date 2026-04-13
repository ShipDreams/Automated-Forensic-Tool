#!/usr/bin/env python3
"""
External OCR worker entrypoint for packaged Windows builds.

This script is executed by a separately installed Python runtime so the
main packaged GUI process does not need to host PaddleOCR itself.
"""

import sys
from pathlib import Path


def main() -> int:
    script_dir = Path(__file__).resolve().parent
    if str(script_dir) not in sys.path:
        sys.path.insert(0, str(script_dir))

    from core.ocr_engine import _subprocess_cli

    return _subprocess_cli()


if __name__ == "__main__":
    raise SystemExit(main())
