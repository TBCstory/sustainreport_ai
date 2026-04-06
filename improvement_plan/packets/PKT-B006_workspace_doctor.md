# PKT-B006: workspace doctor — 파생 상태 파일 lint + 자동 재생성

## 목표
워크스페이스의 파생 상태 파일(project_state.json, next_actions.json 등)이 실제 산출물과 불일치할 때 자동으로 감지하고, 선택적으로 재생성하는 lint 도구를 만든다.

## 배경
project_state.json의 current_phase가 "P2"인데 실제로는 07_drafts/에 초안이 있는 경우, approval_gates.json의 게이트 상태가 실제 산출물과 맞지 않는 경우 등이 운영 중 발생할 수 있다. 이를 수동으로 확인하는 것은 비효율적.

## 입력 파일 (반드시 먼저 읽을 것)
- `/Users/lj_homemac/tools/sustainreport_ai/scripts/update_project_state.py` — 기존 상태 갱신 로직 참조
- `/Users/lj_homemac/tools/sustainreport_ai/orchestration/phase_rules.json` — 각 phase의 필수 산출물 정의
- 실제 워크스페이스 예시: `workspaces/PRJ-2026-KRS-001/project_state.json`

## 상세 작업

### 작업 1: scripts/workspace_doctor.py 신규 생성

**CLI 인터페이스:**
```bash
uv run python scripts/workspace_doctor.py --workspace <path> --check   # 검사만 (기본)
uv run python scripts/workspace_doctor.py --workspace <path> --fix     # 검사 + 자동 재생성
uv run python scripts/workspace_doctor.py --workspace <path> --json    # 결과를 JSON으로 출력
```

### 작업 2: 검사 항목 구현

다음 검사를 순서대로 실행:

#### 검사 1: phase 일관성 (PHASE_CONSISTENCY)
- `project_state.json`의 `current_phase`를 읽음
- 실제 산출물 기반으로 `update_project_state.py`의 `determine_phase()` 로직을 호출하여 계산된 phase와 비교
- 불일치 시: `WARNING: project_state says P2, actual artifacts suggest P4`

#### 검사 2: 게이트 상태 일관성 (GATE_CONSISTENCY)
- `approval_gates.json`의 각 게이트 상태를 읽음
- 해당 게이트의 전제 조건 산출물이 존재하는지 확인
  - 예: `GATE-P15-TO-P2`가 "approved"인데 `toc_draft.json`이 없으면 경고
  - 예: `GATE-P2-TO-P3`가 "waiting"인데 `writing_blueprint.json`이 없으면 경고
- 역방향도 확인: 산출물은 있는데 게이트가 "waiting"이면 안내

#### 검사 3: next_actions.json stale 여부 (NEXT_ACTIONS_STALE)
- `next_actions.json`의 `updated_at` 필드를 읽음
- 마지막 갱신 이후 산출물 파일의 mtime이 변경됐으면: `INFO: next_actions.json may be stale (last updated {date}, but artifacts changed since)`

#### 검사 4: draft_queries.json 미해결 항목 (OPEN_QUERIES)
- `draft_queries.json`의 `status: "open"` 항목 수를 보고
- 해당 query와 관련된 섹션의 초안이 이미 "approved" 상태이면: `WARNING: DQ-NNN is open but SEC-X is already approved`

#### 검사 5: draft_meta 필드명 정규화 (META_FIELD_CHECK)
- `07_drafts/SEC-*_meta.json` 파일들의 필드명을 확인
- PKT-B002에서 정의된 정규 필드(`heading_ko`, `draft_confidence`, `evidence_segments`, `placeholders`, `missing_evidence`)가 없는 파일을 보고
- 구 필드명 사용 시: `INFO: SEC-3_meta.json uses legacy field 'heading_text' instead of 'heading_ko'`

### 작업 3: 출력 포맷

**--check 모드 (기본):**
```
=== Workspace Doctor: PRJ-2026-KRS-001 ===

✅ PHASE_CONSISTENCY: OK (current_phase=P4, computed=P4)
⚠️  GATE_CONSISTENCY: GATE-P15-TO-P2 approved but toc_draft.json missing
✅ NEXT_ACTIONS_STALE: OK
⚠️  OPEN_QUERIES: 2 open queries for already-completed sections
⚠️  META_FIELD_CHECK: 3 files use legacy field names

--- Summary ---
Checks: 5 | Passed: 2 | Warnings: 3 | Errors: 0

Run with --fix to auto-repair fixable issues.
```

**--fix 모드:**
- PHASE_CONSISTENCY: `update_project_state.py` 재실행
- NEXT_ACTIONS_STALE: `next_actions.json` 재생성
- META_FIELD_CHECK: `migrate_draft_meta.py --apply` 호출 (PKT-B002에서 생성)
- GATE_CONSISTENCY, OPEN_QUERIES: 자동 수정 불가, 안내만

**--json 모드:**
```json
{
  "workspace": "PRJ-2026-KRS-001",
  "checked_at": "2026-04-06T12:00:00Z",
  "checks": [
    {
      "name": "PHASE_CONSISTENCY",
      "status": "pass",
      "details": "current_phase=P4, computed=P4"
    },
    ...
  ],
  "summary": { "total": 5, "passed": 2, "warnings": 3, "errors": 0 }
}
```

### 작업 4: 테스트

**신규 파일**: `tests/test_workspace_doctor.py`

```python
def test_doctor_detects_phase_mismatch(tmp_workspace):
    """project_state says P2 but P4 artifacts exist → warning."""

def test_doctor_passes_on_consistent_workspace(tmp_workspace):
    """정상 워크스페이스에서 0 warnings."""

def test_doctor_fix_mode_updates_state(tmp_workspace):
    """--fix 모드에서 project_state.json이 갱신됨."""

def test_doctor_detects_legacy_meta_fields(tmp_workspace):
    """구 필드명 사용 meta 파일 감지."""
```

## 완료 기준
1. `scripts/workspace_doctor.py` 생성
2. `--check` 모드: 정상 워크스페이스에서 0 warnings
3. `--check` 모드: 의도적 불일치(phase mismatch, legacy fields) 워크스페이스에서 경고 출력
4. `--fix` 모드: 수정 가능한 항목이 자동으로 수정됨
5. `uv run pytest tests/ -q` — 전체 통과

## 결정 원칙
- doctor는 읽기 전용이 기본. `--fix`가 없으면 아무것도 수정하지 않음
- 수정 불가능한 항목은 경고만 출력하고 exit code에 반영하지 않음
- `--fix`에서 파일 수정 시 `.bak` 백업 생성
- exit code: 0=모두 통과, 1=경고 있음, 2=에러 있음

## 영향 범위
- `scripts/workspace_doctor.py` — 신규 생성
- `tests/test_workspace_doctor.py` — 신규 생성
- 기존 파일 수정 없음
