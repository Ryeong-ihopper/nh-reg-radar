#!/usr/bin/env python
"""Canonical CLI for P1/P3 integration and search-document generation."""
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from rag.operational.prepare_inputs import main  # noqa: E402


if __name__ == "__main__":
    main()
