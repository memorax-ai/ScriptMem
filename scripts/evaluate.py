#!/usr/bin/env python3
"""Backward-compatible wrapper for `scripts/run_eval.py`."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from evaluate import main  # noqa: E402


if __name__ == "__main__":
    main()
