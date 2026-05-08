#!/usr/bin/env python3
"""Wrapper for running the deterministic ScriptMem accuracy evaluator."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from evaluate import main  # noqa: E402


if __name__ == "__main__":
    main()
