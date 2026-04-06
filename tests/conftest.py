#!/usr/bin/env python3.13
"""
tests/conftest.py — 공통 pytest fixtures
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def tmp_workspace(tmp_path: Path) -> Path:
    """최소 워크스페이스 구조 fixture.

    Creates the standard directory layout used across all tests.
    """
    dirs = [
        "00_definition",
        "01_raw",
        "02_file_registry",
        "03_normalized_md",
        "04_segments",
        "05_planning",
        "06_buckets",
        "07_drafts",
        "08_review",
        "09_handoff",
        "10_evidence_pack",
        "guidance",
        "context_bus",
    ]
    for d in dirs:
        (tmp_path / d).mkdir(parents=True, exist_ok=True)
    return tmp_path
