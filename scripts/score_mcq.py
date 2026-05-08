#!/usr/bin/env python3
"""Wrapper for the deterministic MCQ scorer."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from score_mcq import main  # noqa: E402


if __name__ == "__main__":
    main()
