#!/usr/bin/env python3
"""Backward-compatible wrapper for `scripts/export_dataset.py`."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from export import main  # noqa: E402


if __name__ == "__main__":
    main()
