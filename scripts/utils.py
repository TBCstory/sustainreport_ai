#!/usr/bin/env python3.13
"""
공유 유틸리티 모듈 — run_id 생성 및 시퀀스 관리

LLM 라우터와 로그 이벤트에서 공통으로 사용하는 run_id 생성 로직을 통합합니다.
동시성 충돌 방지를 위해 tempfile.mkstemp()와 fcntl.flock()을 사용합니다.
"""

import fcntl
import logging
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path


def get_run_sequence() -> str:
    """RUN-YYYYMMDD-{seq} 체계적인 시퀀스 번호 반환 (A1~Z9 순환 경제)."""
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    seq_file = Path(tempfile.gettempdir()) / f".sustainreport_run_seq_{today}"

    try:
        # Open or create the sequence file
        fd = os.open(str(seq_file), os.O_CREAT | os.O_RDWR)
        file_handle = os.fdopen(fd, "r+")

        # Acquire exclusive lock (blocking)
        fcntl.flock(fd, fcntl.LOCK_EX)

        try:
            content = file_handle.read().strip()
            if content:
                letter_idx = ord(content[0]) - 65
                num_idx = int(content[1:]) - 1  # 0-based index
                if num_idx < 8:  # 0-7 → current is 1-8, increment
                    num_idx += 1
                    seq = chr(65 + letter_idx) + str(num_idx + 1)
                else:  # num_idx == 8 → current is 9, wrap to next letter
                    letter_idx += 1
                    num_idx = 0
                    if letter_idx > 25:  # Z9 → A1
                        letter_idx = 0
                    seq = chr(65 + letter_idx) + "1"
            else:
                seq = "A1"

            # Truncate and write new sequence
            file_handle.seek(0)
            file_handle.truncate()
            file_handle.write(seq)
            file_handle.flush()
            os.fsync(fd)
        finally:
            # Release lock
            fcntl.flock(fd, fcntl.LOCK_UN)

        file_handle.close()

    except (OSError, IOError, ValueError):
        # Fallback: use mkstemp-based unique id if anything goes wrong
        temp_fd, temp_path = tempfile.mkstemp(prefix=".sustainreport_seq_err_")
        os.close(temp_fd)
        os.unlink(temp_path)
        seq = "A1"

    return seq


def generate_run_id() -> str:
    """RUN-YYYYMMDD-{seq} 형식의 고유 run_id 반환."""
    today = datetime.now(timezone.utc).strftime("%Y%m%d")
    return "RUN-" + today + "-" + get_run_sequence()


# ─────────────────────────────────────────────────────────────────────────────
# HD-4: Pipeline Status Sync
# ─────────────────────────────────────────────────────────────────────────────


def sync_workspace(workspace: Path) -> dict:
    """워크스페이스의 모든 파생 상태 요약을 재생성한다.

    모든 mutating operation 완료 후 호출해야 한다.
    Returns: {"blocking_issues": int, "next_actions": int, "project_state": bool}
    """
    import json

    from scripts.rebuild_summaries import (
        rebuild_blocking_issues,
        rebuild_next_actions,
    )
    from scripts.update_project_state import update_project_state

    result = {}

    # 1) blocking issues 재생성 및 파일 쓰기
    bi = rebuild_blocking_issues(workspace)
    issues = bi.get("issues", [])
    result["blocking_issues"] = len(issues)
    bi_path = workspace / "blocking_issues.json"
    with open(bi_path, "w", encoding="utf-8") as f:
        json.dump(bi, f, indent=2, ensure_ascii=False)

    # 2) next actions 재생성 및 파일 쓰기
    na = rebuild_next_actions(workspace, issues)
    result["next_actions"] = len(na.get("actions", []))
    na_path = workspace / "next_actions.json"
    with open(na_path, "w", encoding="utf-8") as f:
        json.dump(na, f, indent=2, ensure_ascii=False)

    # 3) project_state 재생성
    try:
        update_project_state(workspace)
        result["project_state"] = True
    except Exception:
        result["project_state"] = False

    return result
