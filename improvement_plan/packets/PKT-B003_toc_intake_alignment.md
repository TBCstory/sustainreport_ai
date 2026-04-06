# PKT-B003: run_toc_planner intake 계약 정합 — custom_toc_reference/section_priority

## 목표
run_toc_planner.py가 intake_manifest.schema.json의 **정확한 필드명**을 읽도록 수정한다.

## 문제 진단

| 위치 | 현재 코드 (잘못된 키) | 스키마 정의 (올바른 키) |
|------|---------------------|---------------------|
| `run_toc_planner.py:405` | `preferred_toc_reference` | `custom_toc_reference` |
| `run_toc_planner.py:408` | `priority_sections` | `section_priority` |

참조:
- `schemas/intake_manifest.schema.json` line 18: `custom_toc_reference`
- `schemas/intake_manifest.schema.json` line 21: `section_priority`
- `agents/intake-interviewer.md` line 107, 110: 동일한 정규 키 사용

## 입력 파일 (반드시 먼저 읽을 것)
- `/Users/lj_homemac/tools/sustainreport_ai/scripts/run_toc_planner.py` — line 398-430 (`_build_toc_draft_prompt` 함수)
- `/Users/lj_homemac/tools/sustainreport_ai/schemas/intake_manifest.schema.json`
- `/Users/lj_homemac/tools/sustainreport_ai/agents/intake-interviewer.md` — A_structure 필드 정의 확인

## 상세 작업

### 작업 1: _build_toc_draft_prompt 키 이름 수정

**파일**: `scripts/run_toc_planner.py`

**line 405 변경:**
```python
# 변경 전
preferred_toc = a_structure.get("preferred_toc_reference", "")
# 변경 후 (alias fallback 포함)
preferred_toc = a_structure.get("custom_toc_reference") or a_structure.get("preferred_toc_reference", "")
```

**line 408 변경:**
```python
# 변경 전
priority_sections = a_structure.get("priority_sections", [])
# 변경 후 (alias fallback 포함)
priority_sections = a_structure.get("section_priority") or a_structure.get("priority_sections", [])
```

**alias fallback 패턴**: 정규 키를 먼저 읽고, 없으면 구 키를 fallback. 이렇게 하면 옛 intake_manifest 파일과도 호환됨.

### 작업 2: _build_toc_draft_prompt 내 `toc_style` 참조 확인

**같은 함수 내에서** `a_structure.get("toc_style")`도 사용하는지 확인.
- 스키마상 `toc_style`은 정규 키이므로 변경 불필요
- 만약 다른 이름으로 읽고 있다면 함께 수정

### 작업 3: run_toc_planner.py의 다른 함수에서도 동일 키 사용 여부 확인

`run_toc_planner.py` 전체에서 `preferred_toc_reference`, `priority_sections` 문자열을 grep하여 다른 곳에서도 사용하면 모두 수정.

### 작업 4: 테스트 fixture 갱신

기존 `tests/test_run_toc_planner.py`에서 intake_manifest fixture가 구 키를 사용하는지 확인:
- `preferred_toc_reference` → `custom_toc_reference`로 변경
- `priority_sections` → `section_priority`로 변경
- **추가 테스트 1개**: intake fixture에 `custom_toc_reference`와 `section_priority`를 넣고, LLM 프롬프트에 해당 값이 포함되는지 assert

## 완료 기준
1. `run_toc_planner.py`에서 `preferred_toc_reference`, `priority_sections` 문자열이 alias fallback으로만 존재 (정규 키가 우선)
2. `uv run pytest tests/test_run_toc_planner.py -v` — 전체 통과
3. `uv run pytest tests/ -q` — 전체 통과
4. 새 테스트: intake fixture의 `custom_toc_reference` 값이 LLM 프롬프트에 반영됨을 assert

## 결정 원칙
- alias fallback은 1릴리스 동안만 유지. 다음 메이저 업데이트에서 구 키 fallback 제거 예정
- `toc_style`은 스키마와 일치하므로 변경하지 않음
- 이 패킷은 run_toc_planner.py만 수정. intake-interviewer.md나 스키마는 이미 올바르므로 변경 불필요

## 영향 범위
- `scripts/run_toc_planner.py` — 키 이름 2개 수정 + alias fallback
- `tests/test_run_toc_planner.py` — fixture 수정 + 테스트 1개 추가
