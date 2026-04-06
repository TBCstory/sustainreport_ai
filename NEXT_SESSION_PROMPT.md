# 다음 세션 시작 프롬프트

아래 프롬프트를 새 Claude Code 세션에서 **첫 메시지**로 붙여넣으세요.

---

## 프롬프트 (복비용)

```
sustainreport_ai 구현 세션을 시작합니다.

## 1. 컨텍스트 부트스트랩 (필수 읽기)

아래 파일을 **순서대로** 읽고 현재 상태를 파악하세요:

1. `CLAUDE.md` — 오케스트레이터 헌법 (전체 아키텍처, 금지사항, ID 체계)
2. `SESSION_LOG.md` — 이전 세션 완료/미완료 기록 ← 여기서 이어받을 작업 확인
3. `.env.example` — API 키 설정 양식

그 다음 실제 파일 현황을 확인하세요:
```bash
ls orchestration/ scripts/ agents/ schemas/ templates/framework_db/ guidance/ llm/ .claude/agents/
```

## 2. 현재 상태 요약 (세션 #8 완료 후)

**✅ 완료된 항목 (코드 구현 100%):**
- Step 1: pyproject.toml, scripts/init_workspace.py, .gitignore, .env.example
- Step 2: orchestration/*.json 5개 (phase_rules, gate_rules, agent_contracts, model_routing, agent_runtime_policy)
- Step 3: 핵심 스크립트 5개 (log_event, check_gate, update_project_state, rebuild_summaries, normalize)
- Step 4: agents/*.md 7개 (section-writer + 6개 에이전트 프롬프트 — 5섹션 구조)
- Step 5: schemas/*.schema.json 8개
- Step 6: llm/router.py, llm/call_log.py
- Step 7: .claude/agents/*.md 7개
- templates/framework_db/: gri_db.json, tcfd_db.json, kssb_db.json, esrs_db.json, sasb_db.json
- guidance/: style_guide.json, terminology_dictionary.json

**⚠️ 실행 위해 필요한 것:**
- `.env` 파일 생성 + `ANTHROPIC_API_KEY` 설정
- 테스트용 PDF/보고서 파일 (실제 ESG 보고서)

**🔧 후순위 (미수정):**
- check_gate.py: phase_rules의 review_complete, handoff_package_complete, evidence_pack_complete type 미처리
- normalize.py: 세그먼트 추출 시 첫 H1만 heading_path로 설정

## 3. 세션 작업 규칙

### 작업 단위 = Step
한 세션에서 1~2 Step만 집중합니다.

### 서브에이전트 활용 원칙
- **병렬 가능한 파일**은 Agent 도구로 동시 디스패치
- 각 서브에이전트에게는 **해당 파일만 생성**하도록 명확한 입출력 지시

### 컨텍스트 보호 규칙
- 긴 파일 전체를 읽지 말 것 → 필요한 부분만 offset/limit으로 읽기
- 이미 완성된 파일은 다시 읽지 말 것 → SESSION_LOG.md에서 완료 여부 확인

### 세션 종료 시 반드시 할 것
SESSION_LOG.md에 아래 형식으로 추가:

```markdown
## 세션 YYYY-MM-DD #N

### 완료
- [x] {구체적인 완료 항목}

### 미완료 / 다음 세션에서 이어갈 것
- [ ] {구체적으로 무엇을 해야 하는지}

### 결정 사항
- {이번 세션에서 내린 설계 결정이 있으면 기록}
```

## 4. 시작

SESSION_LOG.md를 읽고 마지막 세션의 미완료 항목을 확인한 뒤, 이번 세션에서 할 작업 목록을 제안하고 내 확인을 받은 후 진행하세요.

**자동으로 코드를 작성하지 마세요.** 현재 상태를 보고한 뒤, 작업 목록을 제안하고 내 확인을 받은 후 진행하세요.
```

---

## 현재 상태 요약 (세션 #8 완료 후)

### ✅ 구현 완료 (100%)

| 구분 | 항목 | 상태 |
|------|------|------|
| **Step 1** | pyproject.toml, init_workspace.py, .gitignore, .env.example | ✅ 완료 |
| **Step 2** | orchestration/*.json 5개 | ✅ 완료 |
| **Step 3** | scripts/*.py 5개 | ✅ 완료 |
| **Step 4** | agents/*.md 7개 (5섹션 구조) | ✅ 완료 |
| **Step 5** | schemas/*.schema.json 8개 | ✅ 완료 |
| **Step 6** | llm/router.py, llm/call_log.py | ✅ 완료 |
| **Step 7** | .claude/agents/*.md 7개 | ✅ 완료 |
| **Bonus** | templates/framework_db/*.json 5개 | ✅ 완료 |
| **Bonus** | guidance/*.json 2개 | ✅ 완료 |

### ⚠️ 실행 전 필요 사항

1. **API 키 설정**
   ```bash
   cp .env.example .env
   # .env 파일을 편집하여 ANTHROPIC_API_KEY=sk-ant-xxxxx 설정
   ```

2. **의존성 설치** (이미 완료되어 있지만 확인)
   ```bash
   uv sync
   ```

### 🔧 후순위 (구현 이상 무, 필요 시 개선)

| 파일 | 문제 | 심각도 |
|------|------|--------|
| check_gate.py | phase_rules의 complex exit condition type 미처리 | MEDIUM |
| normalize.py | 세그먼트 추출 시 첫 H1만 heading_path로 설정 | LOW |

### 📋 세션 #9 추천 작업

**선행**: `.env`에 `ANTHROPIC_API_KEY` 설정 후:

1. **LLM 호출 테스트** — `uv run python -c "from llm.router import ModelRouter; r=ModelRouter(); print(r.complete('data-analyst', '안녕하세요'))"`
2. **전체 워크플로우 데모** — 실제 PDF 파일 1개 투입 → P0→P7 1회 실습
3. **후순위 버그 수정** — check_gate.py, normalize.py