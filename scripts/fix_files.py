#!/usr/bin/env python3.13
"""Backward-compatible entrypoint for the workspace corruption fixer."""

from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.fix_corrupted_files import fix_file, main  # noqa: E402

__all__ = ["fix_file", "main"]


if __name__ == "__main__":
    main()
