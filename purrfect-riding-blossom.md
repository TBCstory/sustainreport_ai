# sustainreport_ai - 시스템 기획 및 아키텍처 플랜

## Context

ESG 지속가능경영보고서 작성 업무 전체를 **통제 가능한 반자동 프로세스**로 전환하는 내부 운영 시스템을 만든다. 기존 `esgreport_writing`(v1.7b, 958 tests)에서 검증된 패턴을 계승하되, 세 가지 핵심 약점을 해결하는 새로운 아키텍처를 설계한다.

### ★ 시스템 목표 — 초안 생성 시스템

**본 시스템은 최종 납품본을 자동 완성하는 것이 아니다.** 컨설턴트가 후속 검토·수정·편집·템플릿 이관을 할 수 있는 **근거 기반 초안**을 생성하는 것이 목표이다.

따라서 설계의 중심은:
- **출판 품질이 아니라** → 초안 작성 가능성 (available evidence로 어디까지 쓸 수 있는가)
- **완벽한 문안이 아니라** → 누락 표시, 확인 필요 지점 표기 (어디가 불확실한지 숨기지 않는 것)
- **최종 레이아웃이 아니라** → 후속 수정 용이성 (컨설턴트가 템플릿에 옮기기 쉬운 구조)
- **페이지 기반 인덱싱이 아니라** → 구조적 앵커 기반 인덱싱 (프레임워크 인덱스가 편집 후에도 유효)

**초안 시스템의 핵심 원칙:**
1. **불확실성을 숨기지 않는다**: placeholder, 확인 필요 표시, 낮은 신뢰도 경고가 초안의 정상적인 일부
2. **컨설턴트 다음 행동을 명확히 한다**: 초안을 받은 뒤 무엇을 먼저 확인해야 하는지 바로 보임
3. **후속 프레임워크 인덱싱과 연결된다**: 초안 단계부터 구조적 앵커를 심어 GRI/KSSB/TCFD/ESRS 인덱싱 준비

### 사용 환경 결정사항
| 항목 | 결정 |
|------|------|
| 사용자 | LJ 본인 1인 운영 |
| 인터페이스 | **Claude Code / OpenClaw 등 AI 코딩 에이전트 세션 안에서 자연어 대화형** |
| 자료 입력 | 로컬 폴더 + Google Drive (MCP) |
| 산출물 | Markdown/JSON (작업용) + 초안 핸드오프 패키지 (컨설턴트 검토·템플릿 이관용) |

### 이 결정이 아키텍처에 미치는 영향

**별도 CLI 앱을 만들지 않는다.** 시스템의 실행 환경은 Claude Code 세션 자체이다.

- **오케스트레이터 = CLAUDE.md + 시스템 프롬프트**: Claude Code가 프로젝트 폴더에 진입하면 CLAUDE.md를 읽고 오케스트레이터 역할을 수행
- **서브에이전트 = Claude Code의 Agent 도구**: Paperclip 패턴의 서브에이전트를 Claude Code의 `Agent` 도구(서브프로세스)로 구현
- **상태 관리 = 파일 시스템**: 워크스페이스의 JSON/MD 파일이 상태 저장소
- **사용자 상호작용 = 자연어 대화**: "현재 상태?" → 오케스트레이터가 워크스페이스를 읽고 자연어로 응답
- **Google Drive 접근 = MCP 도구**: `mcp__google_drive_search`, `mcp__google_drive_fetch` 등 활용
- **CLI 명령어 불필요**: `sr init-project` 대신 "새 프로젝트 시작해줘" 라고 말하면 됨

**실제 사용 흐름 예시:**
```
사용자: "태양금속 2025 보고서 프로젝트 시작하자. 자료는 ~/ESG/태양금속/ 폴더에 있어"

오케스트레이터(Claude Code):
  1. CLAUDE.md에서 시스템 규칙 로드
  2. 워크스페이스 디렉토리 생성 (00_definition/ ~ 10_evidence_pack/)
  3. Agent 도구로 자료분석 서브에이전트 실행 → 파일 투입·정규화
  4. 결과를 자연어로 보고:
     "52개 파일을 분석했습니다. 47개 정규화 완료, 5개 HWP 파일은 수동 변환이 필요합니다.
      3개 중복 그룹이 있는데, 환경데이터_v2.xlsx와 환경데이터_final.xlsx 중 어떤 걸 쓸까요?"

사용자: "final 쓰자. 다음 단계 진행해"

오케스트레이터:
  5. Agent 도구로 목차/구조 서브에이전트 실행 → writing_blueprint 생성
  6. blueprint 내용을 자연어로 설명:
     "42개 섹션의 목차를 구성했습니다. 주요 구조:
      - 3.1 온실가스 배출량: 상세(Lv3), 데이터+서술 방식, 800-1200단어
      - 4.1 안전보건: 표준(Lv2), 서술 중심, 500-800단어
      ...
      검토하시고 수정할 부분 말씀해 주세요."
```

**이 접근의 장점:**
- 별도 앱 설치/빌드/배포 불필요
- LLM이 이미 자연어 인터페이스를 제공하므로 UI 개발 비용 제로
- Claude Code의 Agent 도구가 서브에이전트 프레임워크를 이미 제공
- MCP 도구로 Google Drive, Obsidian 등 외부 시스템과 이미 연결
- 1인 사용에 최적화 (멀티유저 인프라 불필요)

### 기존 시스템의 검증된 강점 (계승)
- Contract-first 설계 (Pydantic 스키마 → 구현)
- 3-layer 중복 탐지 (바이너리 해시 → 구조적 지문 → 의미적 서명)
- 파일/세그먼트/초안/계산/가이드라인 상태머신
- 증거 기반 작성 원칙 (출처 없으면 쓰지 않음)
- 출처 추적 체인 (문장 → 계산 → 세그먼트 → 파일)

### 기존 시스템의 약점 (해결 대상)
1. **중간 연결 고리 부재**: 자료 정규화 → 섹션 배분 사이의 분석·라우팅이 약함
2. **수동적 오케스트레이터**: 상태 리포팅만 가능, 능동적 작업 순서 제어·안내 없음
3. **사전 구조 설계 부재**: 목차 깊이, 서술 방식, 소주제 구조를 정하지 않고 바로 초안 작성으로 진입

---

## 1. 시스템 아키텍처 개요

### 1.1 전체 구조 — 런타임 중립 + AI 에이전트 네이티브

```
┌──────────────────────────────────────────────────────┐
│          AI 코딩 에이전트 세션                          │
│          (Claude Code / OpenClaw / 기타)               │
│                                                       │
│  사용자 ←→ 오케스트레이터                                │
│              │                                        │
│    ┌─────── CLAUDE.md (헌법: 정책·원칙)                  │
│    ├─────── orchestration/ (세부 규칙·게이트·모델정책)    │
│    └─────── agents/ (런타임 중립 에이전트 프롬프트)       │
│              │                                        │
│         ┌────┼────┐                                   │
│         │    │    │                                   │
│    Agent 도구 / scripts/run_agent.py / 외부 API        │
│    (Claude)    (GPT/Gemini/DeepSeek)                   │
│         │    │    │                                   │
│         └────┼────┘                                   │
│              │                                        │
│    ┌─────────▼──────────┐                              │
│    │  프로젝트 워크스페이스  │  ← 파일 시스템              │
│    │  (JSON + MD)        │                              │
│    │  + 파생 상태 요약     │  ← project_state.json 등    │
│    └─────────────────────┘                              │
│                                                       │
│  MCP 도구: Google Drive, Obsidian 등                    │
└──────────────────────────────────────────────────────┘
```

**핵심 구현 매핑:**

| 개념 | 구현체 |
|------|--------|
| 오케스트레이터 정책 | `CLAUDE.md` (헌법: 원칙, 철학, 금지사항) |
| 오케스트레이터 결정 엔진 | `orchestration/` (phase_rules, gate_rules, model_routing 등) |
| 에이전트 프롬프트 | `agents/*.md` (런타임 중립, 프로젝트 루트) |
| 런타임 어댑터 | `.claude/agents/` (Claude Code용), `openclaw/skills/` (OpenClaw용) |
| 서브에이전트 실행 | Claude 모델 → Agent 도구 / 외부 모델 → `llm/` 패키지 |
| 상태 저장소 | 워크스페이스 JSON/MD + 파생 상태 요약 파일 |
| 이벤트/로그 | `scripts/log_event.py`, `scripts/update_progress.py` (결정적 도구) |
| Google Drive 접근 | MCP 도구 + ingestion 메타데이터 |
| 파일 변환 | `scripts/normalize.py` (MarkItDown + HWP 표준 파이프라인) |
| DOCX 생성 | `scripts/export_docx.py` |

### 1.2 에이전트 구현 방식

#### 1.2.0 에이전트 실행 모델 — Stateful/Stateless 혼합형

**핵심 원칙:**
- 세션은 유지할 수 있다. 하지만 **세션이 진실의 원천이면 안 된다**.
- **장기 기억 = 파일**, **단기/작업 기억 = 세션**, **최종 결정 = 게이트/규칙 파일**

서브에이전트는 역할에 따라 persistent(세션 유지) 또는 ephemeral(단발 호출) 중 선택:

| 역할 | 실행 모드 | 범위 | 이유 |
|------|----------|------|------|
| toc-planner | **persistent** | per project | 보고서 구조를 계속 이해하고 있어야 |
| internal-reviewer | **persistent** | per project | 프로젝트 맥락을 누적해야 검수 품질 향상 |
| section-writer | **persistent** | **per section-group** | 문맥이 너무 커지면 세션 오염. E/S/G별 분리 |
| fact-checker | ephemeral → (후기) persistent | per project | 초기엔 stateless, 프로젝트 맥락 필요시 전환 |
| data-analyst | ephemeral | per task | 파일 분석은 stateless로 충분 |
| framework-mapper | ephemeral | per task | 규칙 기반, 세션 불필요 |
| provenance-builder | ephemeral | per task | 결정적 조립, 세션 불필요 |

**4축 분리 — 역할 / 모델 정책 / 실행 런타임 / 상태성:**

`orchestration/agent_runtime_policy.json`에 정의:

```json
{
  "section-writer": {
    "role": "section-writer",
    "model_policy": "writing_primary",      // → model_routing.json 참조
    "runtime": "claude_agent_session",       // claude_agent | openclaw_session | python_api
    "statefulness": "persistent",
    "scope": "section_group",                // project | section_group | section | task
    "max_session_age_hours": 48,
    "resync_triggers": ["blueprint_change", "style_guide_change", "bucket_rebuild"],
    "dispose_strategy": "on_section_lock"    // on_section_lock | on_phase_complete | manual
  }
}
```

**세션 레지스트리** (`orchestration/session_registry.json`):
persistent 세션의 상태를 추적:

```json
{
  "sessions": [
    {
      "session_id": "sess-writer-env-001",
      "agent_role": "section-writer",
      "scope": "section_group:environment",
      "runtime": "claude_agent_session",
      "created_at": "2026-04-01T10:00:00Z",
      "last_active_at": "2026-04-02T14:30:00Z",
      "context_version": "cv-003",
      "artifact_versions": {
        "writing_blueprint": "v1.2",
        "style_guide": "v1.0",
        "section_buckets": "v2.0"
      },
      "status": "active",
      "resync_required": false,
      "workspace_snapshot_version": "ws-v003",
      "last_resync_at": "2026-04-02T10:00:00Z",
      "staleness_reason": null,
      "resume_allowed": true
    }
  ]
}
```

**컨텍스트 재동기화 규칙** (`orchestration/context_sync_rules.json`):
persistent 세션의 stale context 문제를 해결:

```json
{
  "sync_rules": [
    {
      "trigger": "blueprint_change",
      "affected_roles": ["section-writer", "toc-planner"],
      "action": "resync",
      "resync_method": "inject_updated_artifact",
      "severity": "blocking"
    },
    {
      "trigger": "style_guide_change",
      "affected_roles": ["section-writer"],
      "action": "resync",
      "resync_method": "inject_updated_artifact",
      "severity": "warning"
    },
    {
      "trigger": "bucket_rebuild",
      "affected_roles": ["section-writer"],
      "action": "dispose_and_recreate",
      "severity": "blocking"
    }
  ]
}
```

#### 1.2.1 에이전트 정의 — 런타임 중립

에이전트 프롬프트는 **프로젝트 루트의 `agents/`**에 런타임 중립으로 보관한다. 런타임별 어댑터만 분리:

```
agents/                          # ★ 진실의 원천 (런타임 중립)
  data-analyst.md
  toc-planner.md
  framework-mapper.md
  section-writer.md
  internal-reviewer.md
  fact-checker.md
  provenance-builder.md

.claude/agents/                  # Claude Code용 (agents/를 참조하는 래퍼)
openclaw/skills/                 # OpenClaw용 (향후 확장시)
```

각 에이전트 프롬프트에는 다음이 포함된다:
- 역할과 책임 범위
- 입력/출력 계약 (어떤 파일을 읽고, 어떤 파일을 생성하는지)
- 작업 규칙과 금지 사항
- **일관성 계약** (아래 1.2.2 참조)
- **모델 정책** (아래 1.2.3 참조)
- **이벤트 기록 의무** (아래 1.2.4 참조)

#### 1.2.2 일관성 유지 — 강한 사전 계약

서브에이전트마다 별도 API 호출이 발생하므로, **사전 계약 문서**로 일관성을 보장한다:

```
모든 서브에이전트가 작업 전에 반드시 읽어야 하는 파일:
  guidance/
    writing_blueprint.json      # 섹션별 깊이, 방식, 제약 (★ 핵심)
    style_guide.json            # 문체, 어미, 인칭, 문장 길이 규칙
    terminology_dictionary.json # 용어 통일 ("온실가스" vs "GHG", "tCO2e" 등)
    tone_reference.md           # 톤 레퍼런스 (실제 문단 예시)
```

**일관성 체크 흐름:**
1. 서브에이전트가 초안 작성 시 → 위 계약 파일들을 context에 주입
2. 작성 완료 후 → 오케스트레이터가 결과를 읽고 계약 위반 여부 검토
3. 불일치 발견 → 오케스트레이터가 "SEC-3.1의 톤이 다른 섹션과 다릅니다. 재작성하겠습니다" 보고 후 재작성 지시
4. 최종 편집 단계(P6)에서 → 전체 보고서 차원의 톤/용어/수치 일관성 최종 검수

#### 1.2.3 멀티 모델 — 역할 기반 정책 + 실행 기록 필수

**원칙: "모델 자유 선택"이 아니라 "모델 실행 기록이 남는 자유 선택"**

각 에이전트의 모델 정책은 `orchestration/model_routing.json`에 정의:

```json
{
  "section-writer": {
    "primary_model": "gpt-4o",
    "allowed_alternatives": ["claude-sonnet-4-6", "deepseek-v3", "gemini-2.5-pro"],
    "forbidden_models": [],
    "cost_limit_per_section_usd": 0.50,
    "timeout_seconds": 120,
    "fallback_model": "claude-sonnet-4-6",
    "review_required": true
  }
}
```

**모델-역할 분리**: "section-writer는 GPT-4o"가 아니라 "section-writer는 writing policy를 따르고, 현재 primary model은 GPT-4o"

**실행 기록 필수** — 모든 LLM 호출은 아래를 남긴다:

```json
{
  "call_id": "LLM-20260402-0042",
  "agent_role": "section-writer",
  "model_provider": "openai",
  "model_name": "gpt-4o-2025-04-01",
  "prompt_template_version": "section-writer-v1.2",
  "input_artifact_ids": ["SEC-3.1_bucket", "writing_blueprint#SEC-3.1"],
  "output_hash": "sha256:abc123...",
  "temperature": 0.3,
  "execution_timestamp": "2026-04-02T10:30:00Z",
  "tokens_used": {"input": 4200, "output": 1800},
  "cost_usd": 0.12,
  "reviewer_model": "claude-sonnet-4-6"
}
```

**구현 — adapter/router 구조:**

```
llm/
  adapters/
    anthropic.py          # Claude API
    openai.py             # GPT-4o, o3 등
    google.py             # Gemini
    deepseek.py           # DeepSeek
  router.py               # 역할 → 모델 매핑, fallback, 재시도
  policies.py             # 비용 한도, timeout, 허용 모델 체크
  call_log.py             # 실행 기록 자동 저장
  __main__.py             # python -m llm --role section-writer --task SEC-3.1
```

호출 방식:
- Claude 모델 → Claude Code `Agent` 도구 직접 사용
- 외부 모델 → `python -m llm --role section-writer --task SEC-3.1` (Bash로 실행)
- 오케스트레이터 자연어 지시도 가능: "SEC-3.1은 DeepSeek로 써봐"

#### 1.2.4 이벤트 기록 — 스크립트로 강제

프롬프트 자율에 맡기면 기록이 빠지므로, **결정적 스크립트 도구로 강제**한다:

```bash
# 에이전트가 진행 상황을 기록할 때
python scripts/log_event.py --type progress --agent data-analyst --phase P1 \
  --message "포맷 변환 32/47 완료" --done 32 --total 47

# 예외/실패/사람 개입 필요 사항을 기록할 때
python scripts/log_event.py --type incident --agent data-analyst --phase P1 \
  --message "F-0012: HWP 형식, 수동 변환 필요" --severity warning

# 상태 전이를 기록할 때
python scripts/log_event.py --type state_change --entity F-0012 \
  --from received --to manual_required
```

**3종 로그 분리:**

| 파일 | 역할 | 특성 |
|------|------|------|
| `context_bus/events.jsonl` | 모든 이벤트 | append-only, 전체 이력 |
| `context_bus/runs.json` | 현재 실행 중 작업의 최신 상태 | 덮어쓰기, "지금 뭐 하고 있나" |
| `context_bus/incidents.json` | 예외/실패/사람 개입 필요 | 차단 요인 목록 |

오케스트레이터는 `runs.json`으로 실시간 보고, `incidents.json`으로 차단 요인 안내:

```
오케스트레이터: "자료분석 에이전트 진행 중...
  ✓ 52개 파일 스캔 완료
  ✓ 포맷 변환 중: 32/47 완료 (68%)
  → 현재: F-0033_환경데이터.pdf 변환 중
  ⚠ F-0012: HWP 형식, 수동 변환 필요로 건너뜀"
```

### 1.3 통신 모델

- 에이전트 간 **직접 호출 없음** — 모든 통신은 파일 기반 워크스페이스를 통해
- 서브에이전트는 이전 페이즈의 산출물을 읽고(입력 계약), 결과를 워크스페이스에 작성(출력 계약)
- 오케스트레이터만 에이전트를 디스패치하고 게이트 조건을 확인
- 이벤트 기록은 `scripts/log_event.py`를 통해 결정적으로 강제
- 3종 로그 분리: events.jsonl (전체 이력) + runs.json (현재 상태) + incidents.json (차단 요인)

### 1.4 오케스트레이터 이원화

**오케스트레이터 = CLAUDE.md만이 아니라, CLAUDE.md + orchestration/ + approval_gates.json**

| 계층 | 파일 | 역할 |
|------|------|------|
| 정책 (헌법) | `CLAUDE.md` | 원칙, 철학, 금지사항, 워크플로우 개요. **얇게 유지** |
| 결정 규칙 | `orchestration/phase_rules.json` | **무엇이 필요하고 언제 끝나는가** — 페이즈별 진입/종료 조건, 필수 산출물 |
| 게이트 규칙 | `orchestration/gate_rules.json` | **누가 승인하고 무엇이 차단되는가** — 자동 vs 사람 승인 구분 |
| 모델 정책 | `orchestration/model_routing.json` | **어떤 모델을 쓰는가** — 역할별 모델 선택, 비용 한도, fallback |
| 에이전트 계약 | `orchestration/agent_contracts.json` | **무엇을 읽고 무엇을 쓰는가** — 입출력 파일 계약 |
| 실행 정책 | `orchestration/agent_runtime_policy.json` | **어떻게 실행되는가** — persistent/ephemeral, 범위, 수명 |
| 세션 관리 | `orchestration/session_registry.json` | **세션이 지금 어떤 상태인가** — 활성/stale/resume 가능 여부 |
| 동기화 규칙 | `orchestration/context_sync_rules.json` | **세션이 언제 stale이 되는가** — 트리거, resync 방법 |
| 다음 행동 | `orchestration/next_action_policy.md` | **지금 뭘 하면 되는가** — 상태별 제안 규칙 |
| 예외 처리 | `orchestration/fallback_routes.json` | **실패 시 어디로 우회하는가** — 대응 경로 |

**게이트 판정도 스크립트로 분리:**
```bash
python scripts/check_gate.py --phase P2 --workspace ./workspaces/PRJ-2025-TYMK-001/
# → {"gate_passed": false, "blockers": ["writing_blueprint not approved"], "next_actions": [...]}
```

이렇게 하면 자연어 인터페이스는 유지하면서도, 결정 자체는 재현 가능해진다.

### 1.5 상태 관리

**객체 수준 상태머신** (기존 검증 패턴 계승):
- 파일: received → registered → active → superseded → archived
- 세그먼트: extracted → validated → version_relinked → deprecated
- 초안: not_started → drafted → review_issue_open ⟷ needs_redraft → ready_for_handoff → handed_off
- 계산: generated → recomputed → verified → invalidated
- 가이드라인: active → breaking_change → propagated → rescan_required

**페이즈 수준 프로젝트 상태** (신규):
- P0 → P1 → P2 → P3 → P4 → P5 → P6 → P7
- 각 페이즈 전환 조건은 `orchestration/phase_rules.json`에 정의
- 게이트 판정은 `scripts/check_gate.py`로 결정적 실행
- 섹션별 독립 진행 가능 (전체 프로젝트 페이즈는 선도 에지 반영)

**파생 상태 요약 파일** — 오케스트레이터가 매번 전체 파일을 읽지 않도록:

| 파일 | 내용 | 갱신 시점 |
|------|------|----------|
| `project_state.json` | 현재 페이즈, 섹션별 상태 요약, 완료율 | 매 작업 완료시 |
| `blocking_issues.json` | 진행을 막는 이슈 목록 | incidents 발생시 |
| `next_actions.json` | 현재 상태에서 가능한 다음 행동 3개 이하 | project_state 변경시 |

**파생 요약 파일의 3원칙:**
1. **소스 오브 트루스가 아니다** — 항상 원본 산출물에서 재생성 가능한 파생물
2. **수동 편집 금지** — `scripts/update_project_state.py`만 갱신
3. **불일치 시 원본 기준 재생성** — `scripts/rebuild_summaries.py`로 언제든 재구축

오케스트레이터는 우선 이 요약 파일을 읽고 사용자에게 설명한다. 상세 내용이 필요하면 원본 파일을 추가로 읽는다.

### 1.6 운영자 오버라이드 계층

실무에서 반드시 발생하는 **사람의 수동 개입**을 정식으로 기록하는 계층:

`manual_overrides.json`:
```json
{
  "overrides": [
    {
      "override_id": "OVR-001",
      "override_type": "file_selection",
      "target_artifact": "F-0015",
      "reason": "환경데이터_final.xlsx가 최신 검증본",
      "before": {"version_decision_state": "pending_human_gate"},
      "after": {"version_decision_state": "active_file"},
      "operator": "LJ",
      "timestamp": "2026-04-02T11:00:00Z"
    }
  ]
}
```

오버라이드 유형:
- `file_selection`: 정본 파일 강제 선택
- `routing_override`: 라우팅 결과 수정
- `auto_judgment_bypass`: 자동 판단 무시
- `text_confirmation`: 특정 문안 수동 확정
- `calculation_adjustment`: 계산값 보정/제외
- `draft_placeholder_insertion`: 자료 부족으로 의도적으로 placeholder/확인필요 문구를 삽입한 경우 기록
- `kpi_status_override`: 시스템이 판단한 KPI 상태(provisional 등)를 컨설턴트가 수동으로 confirmed/unresolved로 변경
- `confidence_override`: 섹션 신뢰도를 컨설턴트가 수동으로 조정 (예: 증거는 부족하나 경험적으로 작성 가능)

이 계층이 있어야 **"시스템 판단"과 "운영자 판단"이 구분**된다.

### 1.7 상태 갱신 원자성과 복구

산출물 생성 시 여러 파일이 연쇄적으로 바뀐다 (draft → meta → provenance → event → project_state). 중간 실패 시 상태가 꼬이지 않도록:

**갱신 순서 (commit order):**
1. 산출물 임시 파일로 생성 (`.tmp` 접미사)
2. 내용 검증 (스키마 체크)
3. 임시 → 정식 파일로 원자적 이동 (`os.rename`)
4. 이벤트 기록 (`scripts/log_event.py`)
5. 파생 상태 요약 재생성 (`scripts/update_project_state.py`)

**부분 실패 복구:**
- 3단계 전 실패 → 임시 파일 삭제, 재시도
- 4단계 실패 → 산출물은 반영됨, 이벤트만 재기록
- 5단계 실패 → `scripts/rebuild_summaries.py`로 요약 재구축
- **모든 경우 원본 산출물 기준으로 재생성 가능**

---

## 2. 에이전트 설계

### 2.1 메인 오케스트레이터 = CLAUDE.md + orchestration/

오케스트레이터는 `CLAUDE.md`(정책 헌법)와 `orchestration/`(결정 규칙)의 결합이다.

| 항목 | 내용 |
|------|------|
| 역할 | 전체 프로젝트 생명주기의 단일 통제점. 도메인 작업은 서브에이전트에 위임. |
| 정책 계층 | `CLAUDE.md` — 원칙, 철학, 금지사항 (얇게 유지) |
| 결정 계층 | `orchestration/` — phase_rules, gate_rules, model_routing 등 (machine-readable) |
| 입력 | 파생 상태 요약 (project_state, blocking_issues, next_actions) + 사용자 자연어 |
| 출력 | Agent 도구/LLM 호출, 파일 읽기/쓰기, 자연어 상태 보고, **상태 기반 다음 행동 제안** |
| LLM | Claude Code 자체 (오케스트레이터는 별도 모델 불필요) |

**상태 기반 제안**: 사용자가 명령을 기억할 필요 없음. 오케스트레이터가 매번 상태를 읽고 다음 행동을 3개 이하로 제안:

```
바로 진행 가능: "blueprint 승인하시겠습니까?"
검토 필요: "중복 정본 선택이 필요합니다 (환경데이터_v2 vs _final)"
보류 가능: "HWP 5건은 나중에 처리해도 됩니다"
```
| 자율도 | 읽기/상태보고=높음, 결정적 페이즈 디스패치=중간, 게이트 오버라이드=낮음(사람 승인 필요) |

**핵심 개선**: 기존 `project-next-step`은 읽기 전용. 새 오케스트레이터는 능동적:
> "자료분석이 52개 파일 중 47개를 완료했습니다. 5개는 수동 변환이 필요합니다. 47개로 기획을 먼저 진행할까요, 전체 완료를 기다릴까요?"

### 2.2 자료분석 에이전트 (Data Analyst)

| 항목 | 내용 |
|------|------|
| 역할 | 파일 투입, 포맷 변환, 정규화, 3-layer 중복탐지, 세그먼트 추출, 주제 태깅 |
| 출력 | file_registry/, normalized_md/, segment_registry, duplicate_summary |
| 자율도 | 완전자동: 해시 중복, 포맷 변환, 세그먼트 추출 / 반자동: 구조적 지문 중복 / 사람 필요: 교차 포맷 동치 판단, HWP/스캔 수동 검토 |

### 2.3 목차/구조 에이전트 (TOC/Structure Agent) — 핵심 신규 에이전트

| 항목 | 내용 |
|------|------|
| 역할 | **초안 작성 전에** 보고서 구조를 설계: TOC 계층, 소주제별 서술 깊이, 작성 방식, 프레임워크 정렬 |
| 입력 | report_basis, framework_outline_matrix, evidence_catalog, 업계 참고 보고서, 클라이언트 선호 |
| 핵심 출력 | **`writing_blueprint.json`** — 섹션별 작성 명세서 |
| 자율도 | 반자동: 구조 제안 → 사람 검토 → 승인. **승인 없이 초안 작성 진입 불가 (하드 게이트)** |

**`writing_blueprint.json` 섹션별 명세:**

blueprint는 "섹션 설명서"가 아니라 **"섹션 실행 계약서"**이다.

```json
{
  "section_id": "SEC-3.1",
  "title": "온실가스 배출량",

  // --- 구조 계약 ---
  "depth_level": 3,
  "writing_approach": "data_table_with_narrative",
  "expected_length_range": {"min_words": 800, "max_words": 1200},
  "required_subsections": ["Scope 1", "Scope 2", "Scope 3 관련 카테고리"],
  "framework_disclosures": ["GRI 305-1", "GRI 305-2", "TCFD Metrics-a"],
  "writing_constraints": ["기준연도 필수 포함", "원단위 지표 필수"],
  "tone": "formal_technical",
  "flexibility_mode": "rigid",
  "model_recommendation": "sonnet",

  // --- ★ 실행 계약 ---
  "required_evidence_confidence": 0.8,          // 이 이상이어야 "높은 신뢰도" 초안
  "numeric_dependency_level": "high",           // high=모든 수치 필수, medium=핵심만, low=선택적
  "human_approval_scope": "numbers_only",       // all | numbers_only | none
  "disclosure_completeness_threshold": 0.9,     // 이 이상이어야 공시 완전으로 간주

  // --- ★ 불확실성 처리 정책 (초안 시스템 핵심) ---
  "fallback_if_evidence_missing": "placeholder_with_query",
  // ↑ 증거 부족 시 동작:
  //   "placeholder_with_query" — [확인필요] 마커 삽입 + draft_queries에 질문 등록 (★ 기본값)
  //   "low_confidence_draft"   — 낮은 신뢰도로 초안 생성, 메타에 경고 표시
  //   "evidence_summary_only"  — 초안 대신 가용 증거 요약만 제공
  //   "skip_with_note"         — 건너뛰되 누락 이유 기록
  //   "escalate"               — 작성 중단, 컨설턴트에게 즉시 보고
  "placeholder_policy": {
    "marker_format": "[확인필요: {reason}]",     // 본문에 삽입되는 placeholder 형식
    "auto_register_query": true                  // placeholder 삽입 시 draft_queries에 자동 등록
  },

  "approved": false
}
```

**깊이 수준 정의:**
| 수준 | 분량 | 설명 | 예시 |
|------|------|------|------|
| 1 (개요) | 100-300단어 | 고수준 요약 | "당사는 온실가스 감축에 주력하고 있습니다" |
| 2 (표준) | 300-800단어 | 핵심 수치와 간략 설명 | Scope 1/2 합계, 방법론 노트 |
| 3 (상세) | 800-1500단어 | 전체 분석, 추세, 목표 | Scope 1/2/3 분해, YoY 비교, 원단위, 감축 목표 |
| 4 (종합) | 1500단어+ | 완전한 처리 | Scope 3 카테고리별, 시나리오 분석, 검증 성명서 |

### 2.4 프레임워크 에이전트

| 항목 | 내용 |
|------|------|
| 역할 | GRI, TCFD, KSSB/IFRS S2, ESRS, SASB, UNGC, ISO 26000, SDGs, EcoVadis, Hyundai KAP, RMAP 매핑 |
| 출력 | framework_outline_matrix, framework_applicability_matrix, framework_gap_report |
| LLM | 최소 사용. 프레임워크 매핑은 규칙 기반 룩업. 엣지 케이스만 LLM |

### 2.5 작성 에이전트 (Writer Agents, 도메인별 복수)

| 항목 | 내용 |
|------|------|
| 역할 | 증거 기반 섹션 초안 작성 (환경/사회/지배구조/개요/부록) |
| 핵심 입력 | writing_blueprint 항목 + section_bucket (라우팅된 증거) + 원본 정규화 콘텐츠 |
| 출력 | 초안 markdown (provenance 태그 삽입) + **초안 메타 JSON (불확실성 포함)** |
| 핵심 규칙 | 모든 문장에 `<!-- src:SEG-XXXXX@vN -->` 또는 `<!-- src:CALC-XXXX -->` 태그 필수 |

**섹션 유형별 차등 처리:**
- **rigid** (정량 데이터): 템플릿 기반, LLM은 값만 채움
- **flex** (데이터+서술): blueprint 제약 내에서 LLM이 초안
- **manual** (CEO 메시지, 민감 문안): 사람이 작성, 시스템은 증거 요약만 제공

**★ 초안 메타 — 불확실성을 숨기지 않는 구조:**

초안의 핵심은 "완벽한 문안"이 아니라 "어디가 불확실한지 보이는 것"이다. 각 섹션 초안(`SEC-X.Y_meta.json`)에는 아래 정보가 필수:

```json
{
  "section_id": "SEC-3.1",
  "draft_version": 1,
  "draft_confidence": 0.72,                    // 초안 전체 신뢰도 (0-1)
  "confidence_breakdown": {
    "evidence_coverage": 0.85,                 // 필요 증거 중 확보된 비율
    "numeric_completeness": 0.60,              // 필요 수치 중 확정된 비율
    "framework_alignment": 0.90                // 공시 요구사항 충족도
  },

  // --- 컨설턴트 액션 포인트 ---
  "missing_evidence": [
    {"description": "Scope 3 카테고리 6-8 배출량 데이터", "severity": "high",
     "fallback_used": "placeholder_with_query"}
  ],
  "client_confirmation_needed": [
    {"point": "기준연도를 2021에서 2022로 변경했는지 확인", "related_segments": ["SEG-00014"],
     "query_id": "DQ-003"}
  ],
  "source_conflicts": [
    {"description": "Scope 2 배출량: 환경데이터.xlsx=23,456 vs 온실가스보고서.pdf=23,890",
     "segments": ["SEG-00014", "SEG-00032"], "resolution": "pending"}
  ],
  "placeholders_inserted": [
    {"location": "SEC-3.1, para 5", "marker": "[확인필요: Scope 3 데이터 미확보]",
     "query_id": "DQ-004"}
  ],
  "kpi_status_summary": {
    "confirmed": 4, "provisional": 2, "missing": 1
  }
}
```

**★ 초안 질문 트래커 (`draft_queries.json`):**

초안 작성 중 발생한 확인 질문, 추가 자료 요청, 수치 불일치 등을 체계적으로 추적한다. 고객사 최종 승인 워크플로우가 아니라, **컨설턴트가 초안 보완을 위해 확인해야 할 항목 목록**이다.

```json
{
  "queries": [
    {
      "query_id": "DQ-003",
      "query_type": "data_confirmation",      // data_confirmation | additional_data_request |
                                               // numeric_discrepancy | policy_clarification |
                                               // scope_question
      "section_id": "SEC-3.1",
      "question": "온실가스 기준연도가 2021인지 2022인지 확인 필요",
      "context": "환경데이터.xlsx에는 2021, 온실가스보고서.pdf에는 2022로 기재",
      "related_segments": ["SEG-00014", "SEG-00032"],
      "priority": "high",                     // high | medium | low
      "status": "open",                       // open | answered | deferred
      "created_at": "2026-04-02T10:30:00Z",
      "answer": null,
      "answered_at": null
    }
  ]
}
```

질문 유형:
- `data_confirmation`: 기존 데이터의 정확성 확인
- `additional_data_request`: 누락 데이터 추가 요청
- `numeric_discrepancy`: 출처 간 수치 불일치
- `policy_clarification`: 정책/제도 존재 여부 확인
- `scope_question`: 보고 범위/경계 관련 질문

### 2.6 KPI 잠정 수치 상태 관리

초안 단계에서는 모든 수치가 확정된 것이 아니다. 각 KPI/수치에 **잠정 상태**를 부여하여, 컨설턴트가 어떤 수치를 그대로 쓸 수 있고 어떤 수치를 먼저 확인해야 하는지 구분한다.

**KPI 수치 상태 3단계:**

| 상태 | 의미 | 초안 표시 | 컨설턴트 행동 |
|------|------|----------|-------------|
| `confirmed` | 원본 확인 완료, 교차 검증 통과 | 그대로 사용 | 없음 |
| `provisional` | 원본은 있으나 미확인/단일 출처 | `(잠정)` 표기 | 고객사에 확인 요청 |
| `unresolved` | 출처 간 불일치 또는 데이터 미확보 | `[확인필요]` placeholder | 데이터 확보 후 작성 |

`kpi_definition_registry.json`의 각 항목에 상태 필드 추가:
```json
{
  "kpi_id": "KPI-GHG-SCOPE1",
  "name": "Scope 1 직접 온실가스 배출량",
  "value": 12345,
  "unit": "tCO2e",
  "data_status": "provisional",              // confirmed | provisional | unresolved
  "source_segments": ["SEG-00014@v2"],
  "cross_validated": false,
  "discrepancy_note": null,
  "query_id": "DQ-005"                       // unresolved/provisional이면 draft_queries 연결
}
```

### 2.7 검수 에이전트 (Review Agent)

내부 팩트체크: 수치 일치, provenance 태그 유효성, 섹션 간 내부 모순 검출

### 2.8 팩트체크 에이전트 (Fact-Check Agent)

외부 검증: 업계 벤치마크 주장, 공공 데이터 참조, 규제 준수 주장 확인

### 2.9 출처추적 에이전트 (Provenance Agent)

증거 체인 구축: provenance_index, KPI 레지스트리, numeric trace view, evidence pack

---

## 3. 데이터 아키텍처

### 3.1 워크스페이스 디렉토리 구조

```
PF-2025-001/                                 # Portfolio
  project_relationship_map.json
  report_output_map.json
  shared_asset_scope.json

  PRJ-2025-COMP-001/                         # Project
    project.json

    00_definition/                           # P0: 프로젝트 정의
      project_charter.json                   # 범위, 경계, 프레임워크, 자동화 수준
      stakeholder_matrix.json                # 누가 무엇을 승인하는지

    01_raw/                                  # P1: 원본 파일 (불변)
      F-NNNN_original.*                      # 원본 파일
      F-NNNN_ingestion_meta.json             # ★ 투입 메타 (source_type, fetched_at 등)

    02_file_registry/                        # 파일 추적
      F-NNNN.json, _index.json, duplicate_summary.json, version_groups.json

    03_normalized_md/                        # 정규화된 콘텐츠
      F-NNNN.md, F-NNNN_meta.json

    04_segments/                             # 추출된 세그먼트
      segment_registry.json, SEG-NNNNN.json

    05_planning/                             # P2: 기획 산출물
      report_basis.json
      framework_outline_matrix.json
      section_manifest.json                  # TOC
      structure_index.json                   # ★ 구조적 앵커 레지스트리 (인덱싱의 근간)
      writing_blueprint.json                 # ★ 섹션 실행 계약서
      section_depth_map.json
      evidence_catalog.json
      kpi_definition_registry.json           # KPI별 data_status (confirmed/provisional/unresolved)
      workflow_readiness_report.json

    draft_queries.json                       # ★ 초안 질문 트래커 (교차 페이즈)

    06_buckets/                              # P3: 증거 라우팅 (★ 강화)
      SEC-X.Y.json                           # 라우팅된 세그먼트 + 라우팅 메타데이터
      section_gap_report.json
      routing_conflicts.json                 # 교차 섹션 충돌 목록

    07_drafts/                               # P4: 섹션 초안
      SEC-X.Y.md                             # 초안 본문 (anchor 태그 + provenance 태그 포함)
      SEC-X.Y_meta.json                      # ★ 초안 메타 (불확실성, 신뢰도, placeholder 등)

    08_review/                               # P5: 검수 결과
      internal_fact_check_report.json
      framework_review_report.json
      external_fact_check_report.json
      review_issues.json

    09_handoff/                              # P6: ★ 초안 정리 및 핸드오프 (기존 09_editorial → 변경)
      draft_report.md                        # 전체 초안 조립본
      draft_report_summary.json              # 초안 요약 (전체 신뢰도, 완료율)
      section_confidence_matrix.json         # 섹션별 신뢰도
      unresolved_queries.json                # 미해결 질문 목록
      kpi_status_summary.json                # KPI 상태 요약
      placeholder_registry.json              # placeholder 위치·이유
      framework_indexing_readiness.json      # ★ 프레임워크 인덱싱 준비 상태

    10_evidence_pack/                        # P7: 감사 대비 패키지
      evidence_pack_manifest.json
      provenance_index.json
      kpi_registry.json
      numeric_trace_view.json

    guidance/                                # 교차 페이즈 가이드라인
      style_guide.json
      terminology_dictionary.json
      section_flexibility_matrix.json

    context_bus/                             # 3종 로그
      events.jsonl                           # append-only 전체 이벤트 로그
      runs.json                              # 현재 실행 중 작업 상태
      incidents.json                         # 예외/실패/사람 개입 필요

    project_state.json                       # ★ 파생 상태 요약
    blocking_issues.json                     # ★ 진행 차단 이슈
    next_actions.json                        # ★ 다음 행동 제안
    approval_gates.json
```

### 3.2 섹션 버킷 구조 (★ 강화 — 시스템 성패 좌우)

P3는 실무 난이도가 가장 높다. 같은 자료가 여러 섹션에 동시에 걸칠 수 있기 때문이다. (예: 안전보건 교육 자료 → 인적자원/안전보건/법규준수/공급망/리스크 모두 해당 가능)

**버킷은 단순 라우팅이 아니라 라우팅 메타데이터를 포함한다:**

```json
{
  "section_id": "SEC-4.1",
  "routed_segments": [
    {
      "segment_id": "SEG-00042",
      "primary_section": "SEC-4.1",
      "secondary_sections": ["SEC-5.2", "SEC-6.3"],
      "routing_reason": "heading_match: '사업장 안전보건' + framework: GRI 403-1",
      "confidence_score": 0.92,
      "evidence_unit_type": "numeric",
      "evidence_binding_mode": "inline_citation",
      "required_for_section": true,
      "conflict_flag": false,
      "human_review_required": false
    }
  ]
}
```

**evidence_unit_type 4종:**

| 유형 | 설명 | writer 활용 방식 |
|------|------|-----------------|
| `text` | 본문 인용/참조용 텍스트 | 서술에 근거로 인용 |
| `numeric` | KPI 숫자, 통계 | 표/본문에 수치로 삽입, 정밀 provenance 필수 |
| `calculation` | 계산 결과 (CALC-XXXX) | 산식과 함께 제시, 검증 상태 표시 |
| `policy_control` | 정책/제도/규정 존재 근거 | 존재 자체가 증거, "~제도를 운영하고 있다" 식으로 활용 |

**evidence_binding_mode:**
- `inline_citation`: 본문에 직접 인용
- `table_entry`: 데이터 표 항목으로 삽입
- `reference_only`: 참고만 하고 직접 인용하지 않음
- `existence_proof`: 존재 자체가 증거 (정책/인증서 등)
```

**라우팅 3단계:** (Open Multi-Agent의 planner→implementer→reviewer 패턴 차용)
1. **규칙 기반 1차**: 키워드, 프레임워크 코드, 결정적 별칭으로 매칭
2. **LLM 보조 2차**: 1차에서 동점이거나 낮은 신뢰도일 때 LLM이 판정
3. **리뷰어 검토 3차**: 충돌(conflict_flag) 있는 항목만 사람이 검토

### 3.3 출처 추적 — 이중화 (Provenance Dual-Track)

**문제**: `<!-- src:SEG-XXXXX -->` HTML 주석만으로는:
- DOCX 변환 시 태그 손실 가능
- 편집 단계에서 문장 수정시 태그-문장 관계 어긋남
- 복수 출처 추적이 난잡해짐

**해결 — 본문 경량 태그 + 이중 추적 맵 (문단 기본 + 문장 정밀):**

| 트랙 | 파일 | 역할 | 대상 |
|------|------|------|------|
| 경량 태그 | 본문 MD 안의 `<!-- src:SEG-XXXXX -->` | 사람이 읽기 좋게. 디버깅용 | 전체 |
| 문단 추적 (기본) | `paragraph_provenance_map.json` | 문단 단위 기본 추적 | **전체 문단** |
| 문장 추적 (정밀) | `sentence_provenance_map.json` | 수치/핵심 문장만 정밀 추적 | **numeric + critical만** |

**문단 추적 (기본, 전체 보고서 대상):**
```json
{
  "P-SEC3.1-003": {
    "section_id": "SEC-3.1",
    "paragraph_index": 3,
    "source_refs": ["SEG-00014@v2", "SEG-00015@v1"],
    "text_hash": "sha256:abc123..."
  }
}
```

**문장 추적 (정밀, 수치/핵심 문장만):**
```json
{
  "SENT-000421": {
    "text_hash": "sha256:def456...",
    "section_id": "SEC-3.1",
    "paragraph_id": "P-SEC3.1-003",
    "source_refs": ["SEG-00014@v2", "CALC-0021"],
    "evidence_confidence": 0.95,
    "tracking_reason": "numeric_claim",
    "last_validated_at": "2026-04-02T10:00:00Z"
  }
}
```

**초안 시스템에서의 provenance 원칙:**
- 목적은 "모든 문장의 완벽한 추적"이 아니라 "컨설턴트가 중요한 주장과 수치를 검토·수정할 수 있을 만큼 충분히 추적 가능하게 만드는 것"
- 과도한 정밀 추적은 초안 생성 속도를 저하시키므로, **문단 기본 + 수치/핵심만 정밀** 원칙을 엄격히 유지
- 전 문장을 sentence-level로 관리하는 부담 없이 문단 기본 추적
- 수치 주장, 핵심 공시 문장만 sentence-level 정밀 추적
- DOCX 변환/편집 후에도 text_hash 비교로 변경 감지 가능

### 3.4 출처 추적 체인 (전체 흐름)

```
최종 보고서 문장 (SENT-000421)
  │
  ├── sentence_provenance_map.json → source_refs
  │     ├── SEG-00014@v2
  │     │     ├── source_file: F-0001
  │     │     │     ├── 01_raw/F-0001_GHG_data.xlsx
  │     │     │     └── ingestion_meta: {source_type: "google_drive", fetched_at: ...}
  │     │     └── text_excerpt: "Scope 1 직접배출: 12,345 tCO2e"
  │     │
  │     └── CALC-0021
  │           ├── inputs: [SEG-00014@v2, SEG-00045@v1]
  │           ├── formula: "scope1 + scope2"
  │           └── result: 45,678 tCO2e
  │
  └── section_bucket: SEC-3.1
        ├── routing_reason: "framework: GRI 305-1"
        └── confidence_score: 0.95
```

### 3.5 구조적 앵커 기반 인덱싱 (★ 핵심 신규)

**문제**: 프레임워크 인덱싱(GRI Content Index, TCFD 대조표, KSSB 공시 위치 등)은 전통적으로 "p.42" 같은 페이지 번호를 사용한다. 하지만:
- 편집 과정에서 페이지 번호는 계속 바뀜
- 초안 단계에서는 최종 페이지를 알 수 없음
- 페이지 기반 인덱스는 편집할 때마다 재작업 필요

**해결**: 페이지가 아니라 **구조적 앵커(heading anchor)**를 인덱싱 기준으로 사용한다. 초안 단계부터 모든 섹션/하위 섹션/소제목에 고정 ID를 부여하고, 프레임워크 인덱스는 이 ID를 참조한다.

**구조 ID 체계:**
```
SEC-3           # 장 (Chapter)
SEC-3.1         # 절 (Section)
SEC-3.1.1       # 소절 (Subsection)
SUB-SEC-3.1-A   # 소제목 (Sub-heading, 별도 번호 체계가 없는 경우)
```

**`structure_index.json` — 구조 앵커 레지스트리:**

모든 제목 계층의 고정 앵커를 관리한다. `section_manifest.json`을 확장하거나 별도 파일로 분리:

```json
{
  "structure_version": "v1.0",
  "entries": [
    {
      "section_id": "SEC-3.1",
      "parent_section_id": "SEC-3",
      "heading_text": "온실가스 배출량",
      "heading_level": 2,
      "heading_anchor": "ghg-emissions",
      "toc_path": ["환경", "기후변화 대응", "온실가스 배출량"],
      "draft_artifact_ref": "07_drafts/SEC-3.1.md",
      "framework_mappings": [
        {"framework": "GRI", "disclosure": "305-1", "coverage_type": "primary"},
        {"framework": "GRI", "disclosure": "305-2", "coverage_type": "primary"},
        {"framework": "TCFD", "disclosure": "Metrics-a", "coverage_type": "partial"}
      ]
    },
    {
      "section_id": "SEC-3.1.1",
      "parent_section_id": "SEC-3.1",
      "heading_text": "Scope 1 직접 배출",
      "heading_level": 3,
      "heading_anchor": "ghg-emissions-scope1",
      "toc_path": ["환경", "기후변화 대응", "온실가스 배출량", "Scope 1 직접 배출"],
      "draft_artifact_ref": "07_drafts/SEC-3.1.md#scope1",
      "framework_mappings": [
        {"framework": "GRI", "disclosure": "305-1", "coverage_type": "primary"}
      ]
    }
  ]
}
```

**핵심 규칙:**
- `section_id`는 한번 부여되면 변경하지 않음 (heading_text는 바뀔 수 있어도 ID는 고정)
- writing_blueprint, section_manifest, drafts, provenance_map, framework_index가 **모두 같은 section_id 체계를 공유**
- 초안 본문에는 heading anchor 메타를 유지: `<!-- anchor:SEC-3.1.1 -->`

**초안 본문에서의 앵커 사용 예시:**
```markdown
<!-- anchor:SEC-3.1 -->
## 3.1 온실가스 배출량

<!-- anchor:SEC-3.1.1 -->
### Scope 1 직접 배출
당사의 2024년 Scope 1 직접 온실가스 배출량은 12,345 tCO2e입니다. <!-- src:SEG-00014@v2 -->
```

**프레임워크 인덱싱 파일 — 앵커 기반 참조:**

향후 GRI Content Index, TCFD 대조표 등은 페이지가 아니라 구조 앵커를 참조:

```json
{
  "framework": "GRI",
  "disclosure": "305-1",
  "disclosure_title": "Direct (Scope 1) GHG emissions",
  "mapped_locations": [
    {
      "section_id": "SEC-3.1.1",
      "heading_anchor": "ghg-emissions-scope1",
      "subsection_path": ["환경", "기후변화 대응", "온실가스 배출량", "Scope 1 직접 배출"],
      "coverage_type": "primary",
      "evidence_status": "confirmed"
    }
  ],
  "unmapped_requirements": [],
  "notes": null
}
```

이렇게 하면:
- 편집/레이아웃 변경 후에도 인덱스 재작업 불필요
- 페이지 번호는 최종 DOCX/PDF 확정 후 한 번만 부여하면 됨
- 같은 structure_index로 GRI/KSSB/TCFD/ESRS/SASB 인덱스를 모두 생성 가능

### 3.6 초안 핸드오프 패키지의 프레임워크 인덱싱 준비 상태

초안 핸드오프 시, 프레임워크 인덱싱이 얼마나 준비되었는지 보여주는 `framework_indexing_readiness.json`:

```json
{
  "overall_status": "partially_ready",         // ready | partially_ready | not_ready

  "summary": {
    "mappable_sections_count": 38,             // 인덱싱 가능한 완전 앵커 섹션
    "total_sections": 42,
    "total_disclosures_required": 48,
    "total_disclosures_mapped": 42,
    "coverage_rate": 0.875
  },

  // --- 판정 기준별 체크 ---
  "anchor_completeness": {
    "all_sections_have_anchor": false,
    "anchor_missing_sections": [
      {"section_id": "SEC-5.3", "heading_text": "공급망 인권", "reason": "structure_index 미등록"}
    ]
  },

  "draft_linkage": {
    "all_anchors_linked_to_drafts": false,
    "unlinked_anchors": [
      {"section_id": "SEC-5.3", "reason": "draft 미생성"}
    ]
  },

  "unmapped_disclosures": [
    {"framework": "GRI", "disclosure": "308-2",
     "disclosure_title": "Negative environmental impacts in the supply chain",
     "status": "no_section_mapped",
     "suggestion": "SEC-5.2 또는 SEC-3.4에 매핑 검토 필요"}
  ],

  "placeholder_only_disclosures": [
    {"framework": "GRI", "disclosure": "403-9", "section_id": "SEC-4.3",
     "reason": "본문이 placeholder만으로 구성, 실질 내용 없음",
     "placeholder_count": 3, "related_queries": ["DQ-012", "DQ-013"]}
  ],

  "multi_section_disclosures": [
    {"framework": "GRI", "disclosure": "302-1",
     "mapped_sections": [
       {"section_id": "SEC-3.2", "coverage_type": "primary"},
       {"section_id": "SEC-3.4", "coverage_type": "secondary"}
     ],
     "primary_secondary_distinguished": true}
  ],

  "manual_review_required_items": [
    {"item": "SEC-5.3 앵커 미등록 — 구조 설계 보완 필요", "priority": "high"},
    {"item": "GRI 308-2 매핑 누락 — 해당 섹션 지정 필요", "priority": "medium"},
    {"item": "SEC-4.3 placeholder 3건 — 본문 보완 후 인덱싱 가능", "priority": "medium"}
  ]
}
```

이 파일이 있으면 컨설턴트가:
- 어떤 프레임워크 인덱스가 바로 생성 가능한지
- 어떤 섹션에 매핑이 아직 빠져 있는지
- 어떤 공시 항목이 본문 구조와 연결되지 않았는지
- placeholder 때문에 인덱싱 전 보완이 필요한 부분이 어디인지
를 한눈에 파악할 수 있다.

---

## 4. 워크플로우 파이프라인

### P0. 프로젝트 정의
- **게이트 출구**: 프로젝트 차터 승인 (프레임워크, 경계, 범위, 이해관계자 매트릭스)
- 프로젝트 생성 → 워크스페이스 디렉토리 구조 생성 → 차터 작성 → 이해관계자 매트릭스 정의

### P1. 자료 투입 및 정규화
- **게이트 출구**: 모든 파일 등록, 정규화 예외 해결 또는 인정
- 원본 복사(불변) → 파일 ID 부여 → 포맷 변환 → 3-layer 중복탐지 → 세그먼트 추출 → 주제 태깅

**투입 메타데이터 (ingestion_meta):**
모든 원본 파일에 투입 경로 메타를 남긴다:
```json
{"source_type": "google_drive", "source_file_id": "1abc...", "source_modified_time": "...",
 "fetched_at": "2026-04-01T09:00:00Z", "fetch_hash": "sha256:...", "fetch_operator": "LJ"}
```
→ "이 수치가 어느 버전 시트에서 왔는가"를 항상 추적 가능

**HWP 표준 파이프라인** (예외가 아니라 정식 분기):
1. HWP direct parse 시도 (pyhwp 등)
2. 실패 → PDF 변환본 탐색 (같은 이름의 .pdf가 있으면 연결)
3. 실패 → 수동 변환 요청 (incident 기록)
4. 수동 변환 완료 → checksum linking (원본 HWP ↔ 변환 MD 메타 연결)

**Google Drive 투입 규칙:**
- Drive 파일 ID로 고정 추적 (파일명 변경에도 동일 파일 인식)
- 다운로드 시점 기록
- 원본 vs 캐시본 구분
- 동일 파일명 다른 버전 충돌 → 중복탐지 파이프라인으로 진입
- 권한 오류/공유 해제 → incident 기록 + fallback 안내

### P2. 기획 (★ 핵심 신규 페이즈)
- **게이트 출구**: writing_blueprint 운영자 승인
- 프레임워크 매핑 → TOC 제안 → **섹션별 깊이·방식·제약 설정** → 사람 검토 루프 → blueprint 승인 → 워크플로우 준비도 검증
- **이 게이트를 통과하지 않으면 초안 작성 진입 불가**

### P3. 섹션 버킷 구축 (★ 실무 난이도 최고)
- **게이트 출구**: 모든 섹션에 증거 라우팅 완료 (또는 갭 인정), 충돌 해결
- **3단계 라우팅:**
  1. 규칙 기반 1차 (키워드, 프레임워크 코드, 결정적 별칭)
  2. LLM 보조 2차 (동점/저신뢰도 판정)
  3. 리뷰어 검토 3차 (충돌 있는 항목만 사람 검토)
- 각 라우팅에 primary_section, secondary_sections, routing_reason, confidence_score, conflict_flag 포함
- 갭 리포트 + 충돌 리포트 생성 → 사람 검토

### P4. 증거 기반 초안 작성
- **게이트 출구**: 모든 섹션 초안 완료 (또는 manual 섹션 사람 대기)
- 의존성 그래프 구축 → 배치별 작성자 디스패치 → blueprint 기반 초안 생성 → provenance 태그 검증

### P5. 다층 검수
- **게이트 출구**: 모든 리뷰 이슈 해결 또는 수용
- 내부 팩트체크 + 프레임워크 리뷰 + 외부 검증 (병렬 수행 가능)

### P6. 초안 정리 및 핸드오프 (★ 재정의)

**목적**: 납품본 완성이 아니라, 컨설턴트가 템플릿에 옮기기 쉬운 상태로 초안을 정리하는 것.

- **게이트 출구**: 초안 핸드오프 패키지 생성 완료
- **이 단계에서 하는 것:**
  - 문체 최소 정리 (용어사전 기반 통일, 심각한 톤 불일치만 수정)
  - 중복/충돌 제거 (섹션 간 같은 내용 반복, 수치 불일치 해소)
  - placeholder/질문 정리 (`draft_queries` 최종 정리, 미해결 항목 명시)
  - KPI 상태 최종 정리 (confirmed/provisional/unresolved 요약)
  - 초안 핸드오프 패키지 묶음 (아래 참조)

- **이 단계에서 하지 않는 것:**
  - 출판 수준 편집, 디자인 레이아웃, 페이지 번호 부여
  - 완전한 최종 보고서 조립 (템플릿 이관은 컨설턴트의 후속 작업)

**초안 핸드오프 패키지 구성:**
```
09_handoff/                                  # (기존 09_editorial/ → 09_handoff/로 변경)
  draft_report.md                            # 전체 초안 (placeholder 포함)
  draft_report_summary.json                  # 초안 전체 요약 (신뢰도, 완료율, 미해결 항목 수)
  section_confidence_matrix.json             # 섹션별 신뢰도 한눈에
  unresolved_queries.json                    # 미해결 질문 목록 (컨설턴트 최우선 검토 대상)
  kpi_status_summary.json                    # KPI별 confirmed/provisional/unresolved
  placeholder_registry.json                  # placeholder 위치·이유·연결된 질문
  framework_indexing_readiness.json          # ★ 프레임워크 인덱싱 준비 상태 (아래 3.6 참조)
```

### P7. 증거 패키지 생성
- **게이트 출구**: evidence pack 무결성 통과
- provenance_index → KPI 레지스트리 → numeric trace view → 무결성 검사

---

## 5. 품질 및 검증 체계

### 세 가지 검수 계층

| 계층 | 에이전트 | 초점 | 방법 |
|------|---------|------|------|
| 내부 팩트체크 | 검수 에이전트 | 수치, 출처, 내부 일관성 | 결정적 + LLM 의미 검사 |
| 프레임워크 리뷰 | 프레임워크 에이전트 | 공시 완전성, 프레임워크 준수 | 결정적 규칙 매칭 |
| 외부 검증 | 팩트체크 에이전트 | 외부 주장, 벤치마크, 공공 데이터 | LLM 주장 추출 + 외부 API |

### 할루시네이션 방지 다층 방어
1. **예방**: 작성자는 section bucket 증거만 수신. 추측 금지 프롬프트.
2. **구조적 탐지**: provenance 태그 없는 문장 자동 플래그.
3. **의미적 탐지**: 주장 값과 원본 세그먼트 값 비교.
4. **외부 탐지**: 정량 주장의 공공 데이터 검증.
5. **사람 검증**: provenance index로 모든 문장의 원본 역추적 가능.

---

## 6. 사용자 경험 (UX) — 자연어 대화형

### 사용 방식

별도 CLI 명령어를 외울 필요 없다. Claude Code 세션에서 자연어로 대화한다:

```
사용자: "현재 상태?"

Claude Code (오케스트레이터):
  [워크스페이스의 project_state.json, approval_gates.json 등을 읽고]

  "프로젝트 '태양금속공업 2025' 현황:

  ✓ Phase 1 (자료 투입): 완료
    - 52개 파일 등록, 47개 정규화 완료
    - 5개 HWP 파일은 수동 변환 필요

  → Phase 2 (기획): 진행 중
    - 목차 초안 42개 섹션 생성됨
    - writing_blueprint 승인 대기 중

  차단 요인:
    1. 환경데이터_v2.xlsx vs _final.xlsx — 어느 쪽을 정본으로 쓸까요?
    2. writing_blueprint 검토 후 '승인' 또는 수정 요청을 해주세요

  다음에 할 수 있는 것:
    - '중복 해결해줘' → 정본 선택 진행
    - 'blueprint 보여줘' → 목차·깊이·방식 검토
    - 'blueprint 승인' → P3(섹션 버킷 구축)으로 진행"
```

### 대화형 명령 예시

| 사용자가 말하면 | 오케스트레이터가 하는 일 |
|----------------|----------------------|
| "새 프로젝트 시작" | 워크스페이스 생성, project_charter 작성 안내 |
| "이 폴더 자료 분석해" | Agent(data-analyst) 실행 → 투입·정규화·중복탐지 |
| "구글드라이브에서 자료 가져와" | MCP google_drive_search → 다운로드 → 투입 |
| "목차 짜줘" | Agent(toc-planner) 실행 → writing_blueprint 생성 |
| "3.1 온실가스 섹션 깊이를 상세로 바꿔" | writing_blueprint.json 수정 |
| "blueprint 승인" | approval_gates.json 업데이트 → P3 진입 가능 |
| "초안 작성 시작" | Agent(section-writer) 배치 실행 |
| "SEC-3.1 검수해" | Agent(internal-reviewer) 실행 |
| "팩트체크 돌려" | Agent(fact-checker) 실행 |
| "DOCX로 내보내" | Python 스크립트 실행 → DOCX 생성 |

### 슬래시 커맨드 (선택적)

자주 쓰는 작업은 Claude Code 커스텀 슬래시 커맨드로도 등록 가능:

```
/esg-status          → 프로젝트 상태 요약
/esg-import          → 자료 투입 시작
/esg-blueprint       → writing_blueprint 보기/수정
/esg-write SEC-3.1   → 특정 섹션 초안 작성
/esg-review          → 검수 실행
```

---

## 7. 멀티프로젝트 지원

| 유형 | 구조 | 산출물 |
|------|------|--------|
| SINGLE | 1개 기업, 1개 보고서 | 단독 보고서 1건 |
| GROUP_UNIFIED_FULL | N개 기업, 완전 통합 | 통합 보고서 1건 |
| GROUP_UNIFIED_PARTIAL | 일부 챕터 통합, 일부 개별 | 통합 보고서 1건 |
| GROUP_PARALLEL | 같은 기준, 개별 보고서 | 독립 보고서 N건 |
| HYBRID_MATRIX | 통합+병렬 혼합 | 보고서 M건 |

포트폴리오 수준에서 `project_relationship_map`, `report_output_map`, `shared_asset_scope`으로 관리.

---

## 8. 구현 로드맵 — PoC 먼저, 나머지는 후순위

### 핵심 루프 먼저 살려놓기 (PoC)

**PoC에 꼭 필요한 것:**
- CLAUDE.md + orchestration/ (phase_rules, gate_rules)
- agents/ (toc-planner, section-writer, internal-reviewer)
- project_state.json, blocking_issues.json, next_actions.json
- writing_blueprint.json + structure_index.json (구조 앵커)
- draft_queries.json (질문 트래커)
- SEC-X.Y_meta.json (초안 불확실성 메타)
- kpi_definition_registry.json (KPI 잠정 상태)
- build_buckets.py 1차 버전
- validate_provenance.py
- llm/router.py (단일 모델로 시작해도 됨)
- session_registry.json (persistent planner 1개 + persistent writer 1~2개)

**나중에 넣어도 되는 것:**
- sentence_provenance_map 완전체
- framework_indexing_readiness.json (핸드오프 시 생성)
- 외부 팩트체크 자동화
- 멀티프로젝트 full matrix
- DeepSeek/Gemini/OpenAI 전부 동시 지원
- 완전한 incidents UX
- 고급 fallback route 전부

### Phase I: 핵심 루프 (PoC)

만들어야 할 것:
- `CLAUDE.md`: 오케스트레이터 정책 (얇게)
- `orchestration/`: phase_rules, gate_rules, agent_runtime_policy, model_routing
- `agents/`: toc-planner, section-writer, internal-reviewer (persistent 세션 3개)
- `agents/`: data-analyst, framework-mapper, provenance-builder (stateless 3개)
- `.claude/agents/`: Claude Code 어댑터
- `scripts/init_workspace.py`: 워크스페이스 구조 생성
- `scripts/normalize.py`: 파일 변환 (MarkItDown + HWP 파이프라인)
- `scripts/log_event.py`, `scripts/check_gate.py`, `scripts/update_project_state.py`
- `schemas/`: writing_blueprint, file_registry, section_bucket 스키마
- `templates/`: blueprint 기본 구조
- `llm/router.py`: 단일 모델(Claude)로 시작

**검증**: "새 프로젝트 시작" → 워크스페이스 생성 → "자료 분석" → 투입·정규화 → "목차 짜줘" → blueprint → "승인" → "초안 작성" → provenance 태그 포함 초안 → "검수" → 리뷰 이슈 → 재작성

### Phase II: 출력 + 품질 안정화

- `scripts/export_docx.py`: Markdown → DOCX
- `scripts/validate_provenance.py` 고도화: sentence_provenance_map 교차 검증
- `scripts/build_evidence_pack.py`: evidence pack 조립
- 일관성 검토 루프 안정화
- 세션 컨텍스트 재동기화 검증

**검증**: "DOCX로 내보내줘" → 납품용 파일 + provenance 역추적 가능 확인

### Phase III: 멀티모델 + 확장

- `llm/adapters/`: OpenAI, Google, DeepSeek 추가
- 멀티프로젝트 지원
- Google Drive 투입 흐름 고도화
- 프레임워크 DB 확장 (TCFD, KSSB, ESRS)
- 외부 팩트체크 자동화

---

## 9. 기존 프로젝트에서 참고할 핵심 자산

설계 참고용 (직접 코드 계승보다는 패턴과 규칙을 참조):
- `esgreport_writing/esg_multi_agent_system_design_v_1.md` — 상태머신, ID 체계, 게이트 규칙의 원천 설계
- `esgreport_writing/app/core/states.py` — 상태 전이 규칙 참조
- `esgreport_writing/app/core/ids.py` — ID 패턴 참조
- `esgreport_writing/app/models/section_flexibility_matrix.py` — rigid/flex/manual 패턴

Claude Code 네이티브 방식에서는 **Pydantic 모델과 서비스 코드 대신** 에이전트 프롬프트와 JSON 스키마가 계약을 정의한다. 기존 코드를 그대로 복사하지 않고, 검증된 규칙(상태머신, ID, 게이트)을 에이전트 프롬프트에 녹여넣는다.

---

## 10. 핵심 설계 결정 요약

1. **오케스트레이터 이원화**: CLAUDE.md(헌법, 얇게) + orchestration/(결정 규칙, machine-readable). 자연어 인터페이스를 유지하면서 결정은 재현 가능.
2. **런타임 중립 에이전트**: `agents/`에 런타임 중립 프롬프트, `.claude/agents/`와 `openclaw/skills/`는 어댑터만.
3. **Stateful/Stateless 혼합형 세션**: planner/reviewer/writer는 persistent (프로젝트/섹션군 단위), mapper/provenance-builder는 stateless. 세션은 유지하되, **진실의 원천은 파일**. 세션은 "전문가 작업 메모리" 역할만.
4. **세션 관리 3종**: agent_runtime_policy(실행 모드), session_registry(세션 추적), context_sync_rules(stale context 재동기화).
5. **파일 기반 워크스페이스 + 파생 상태 요약**: 원본 상태는 상세 JSON, 오케스트레이터는 project_state/blocking_issues/next_actions 요약 파일을 우선 읽음.
6. **Writing Blueprint가 게이트**: 승인된 blueprint 없이 초안 작성 불가.
7. **강한 사전 계약으로 일관성**: blueprint + 스타일가이드 + 용어사전을 모든 에이전트에 주입. 불일치시 재작성.
8. **멀티 모델 — 4축 분리**: 역할(A) / 모델 정책(B) / 실행 런타임(C) / 상태성(D). 모든 호출에 실행 기록 필수.
9. **3종 로그 분리 + 스크립트 강제**: events.jsonl + runs.json + incidents.json. `scripts/log_event.py`로 포맷 강제.
10. **섹션 버킷 라우팅 메타데이터**: primary/secondary, routing_reason, confidence, conflict_flag. 3단계 라우팅.
11. **Provenance 이중화**: 본문 경량 태그 + 문단 기본 추적 + 수치/핵심만 문장 정밀 추적. 과도한 정밀 추적 지양.
12. **HWP 표준 파이프라인**: 예외 아닌 정식 분기.
13. **Google Drive 투입 메타**: source_file_id, fetched_at, fetch_hash.
14. **상태 기반 제안 UX**: 다음 행동 3개 이하 제안.
15. **게이트 판정 스크립트 분리**: `scripts/check_gate.py`.
16. **통제 > 자동화**: 시스템이 제안하고, 사람이 결정.
17. **PoC 먼저**: 핵심 루프(투입→기획→작성→검수)를 먼저 살려놓고, 나머지(멀티모델 전체, 외부 팩트체크, 멀티프로젝트)는 후순위.
18. **초안 시스템 목표**: 납품본 자동 완성이 아니라 근거 기반 초안 생성. 불확실성을 숨기지 않고, 컨설턴트 다음 행동을 명확히 한다.
19. **초안 메타 필수**: 매 섹션 초안에 draft_confidence, missing_evidence, client_confirmation_needed, source_conflicts, placeholders_inserted를 메타로 기록.
20. **draft_queries 트래커**: 초안 작성 중 발생한 확인 질문·추가 자료 요청·수치 불일치를 체계적으로 추적.
21. **KPI 잠정 수치 상태**: confirmed/provisional/unresolved 3단계로 각 수치의 사용 가능 상태 구분.
22. **P6 = 초안 핸드오프**: 납품본 완성이 아니라 컨설턴트가 템플릿에 옮기기 쉬운 상태로 초안 정리 + 핸드오프 패키지 생성.
23. **구조적 앵커 기반 인덱싱**: 페이지 번호 대신 section_id + heading_anchor로 프레임워크 인덱싱. structure_index.json이 모든 산출물의 공통 ID 체계.
24. **프레임워크 인덱싱 준비 상태**: 핸드오프 패키지에 framework_indexing_readiness.json 포함. 인덱싱 가능 앵커, 미매핑 섹션, 미연결 공시 항목, placeholder 보완 필요 섹션을 한눈에 파악.

---

## 11. 프로젝트 디렉토리 구조

```
sustainreport_ai/
  CLAUDE.md                     # 오케스트레이터 정책 (헌법, 얇게 유지)

  agents/                       # ★ 런타임 중립 에이전트 프롬프트 (진실의 원천)
    data-analyst.md
    toc-planner.md
    framework-mapper.md
    section-writer.md
    internal-reviewer.md
    fact-checker.md
    provenance-builder.md

  orchestration/                # ★ 결정 규칙 (machine-readable)
    phase_rules.json            # 페이즈 진입/종료 조건, 필수 산출물
    gate_rules.json             # 자동 vs 사람 승인 구분
    model_routing.json          # 에이전트별 모델 정책
    agent_contracts.json        # 에이전트별 입출력 계약 요약
    agent_runtime_policy.json   # ★ 역할별 실행 모드 (persistent/ephemeral, 범위)
    session_registry.json       # ★ persistent 세션 상태 추적
    context_sync_rules.json     # ★ stale context 재동기화 규칙
    next_action_policy.md       # 상태별 다음 행동 제안 규칙
    fallback_routes.json        # 예외 발생 시 대응 경로

  .claude/                      # Claude Code 런타임 어댑터
    agents/                     # agents/를 참조하는 Claude Code용 래퍼
    settings.json

  openclaw/                     # OpenClaw 런타임 어댑터 (향후)
    skills/

  llm/                          # ★ 멀티모델 adapter/router
    adapters/
      anthropic.py
      openai.py
      google.py
      deepseek.py
    router.py                   # 역할 → 모델 매핑, fallback, 재시도
    policies.py                 # 비용 한도, timeout, 허용 모델 체크
    call_log.py                 # 실행 기록 자동 저장
    __main__.py                 # python -m llm --role section-writer --task SEC-3.1

  scripts/                      # 보조 스크립트
    init_workspace.py           # 워크스페이스 디렉토리 생성
    normalize.py                # 파일 포맷 변환 (MarkItDown + HWP 파이프라인)
    build_buckets.py            # 결정적 라우팅 (1차)
    validate_provenance.py      # provenance 태그 + sentence_map 교차 검증
    export_docx.py              # Markdown → DOCX
    build_evidence_pack.py      # evidence pack 조립
    check_gate.py               # 게이트 판정 (결정적)
    log_event.py                # 이벤트 기록 (포맷 강제)
    update_progress.py          # 진행 상태 업데이트
    update_project_state.py     # 파생 상태 요약 갱신

  schemas/                      # JSON 스키마 정의
    project_charter.schema.json
    file_registry.schema.json
    writing_blueprint.schema.json
    section_bucket.schema.json
    structure_index.schema.json     # ★ 구조적 앵커 레지스트리
    draft_meta.schema.json          # ★ 초안 메타 (불확실성 포함)
    draft_queries.schema.json       # ★ 초안 질문 트래커
    kpi_registry.schema.json        # ★ KPI 잠정 상태 포함
    sentence_provenance_map.schema.json
    review_finding.schema.json
    evidence_pack.schema.json
    framework_index.schema.json     # ★ 앵커 기반 프레임워크 인덱스
    llm_call_log.schema.json

  templates/                    # 산출물 템플릿
    blueprint_template.json
    framework_db/               # 프레임워크 공시 요구사항 DB
      gri_2021.json
      tcfd.json
      kssb.json
      sasb_tr_ap.json

  workspaces/                   # 프로젝트별 워크스페이스 (gitignore)
    PRJ-2025-TYMK-001/
      00_definition/ ~ 10_evidence_pack/ (09_handoff/ 포함)
      context_bus/ (events.jsonl, runs.json, incidents.json)
      draft_queries.json
      project_state.json, blocking_issues.json, next_actions.json
```

---

## 12. 검증 방법

### E2E 시나리오 (Claude Code 세션에서 대화로 실행)
1. "태양금속 보고서 프로젝트 시작해줘" → 워크스페이스 생성 확인
2. "~/ESG/태양금속/ 폴더 자료 분석해줘" → 파일 등록·정규화·중복탐지 결과 확인
3. "목차 짜줘" → writing_blueprint + structure_index 생성 확인
4. blueprint 검토 → "3.1 깊이를 상세로 바꿔" → 수정 확인 → "승인"
5. **blueprint 수정 후 구조 안정성 확인**: section_id / heading_anchor가 수정 전후로 일관되게 유지되는지, 구조 연결이 깨지지 않는지 확인
6. "초안 작성 시작" → provenance 태그 + anchor 태그 포함 초안 확인
7. 초안 메타 확인: draft_confidence, missing_evidence, placeholders — 시스템 성공 기준은 "문장을 뽑아냈는가"가 아니라 "불확실성을 숨기지 않았는가"
8. draft_queries 확인: 미해결 질문 목록이 정확하게 생성되었는지 확인
9. **컨설턴트 개입 검증**: 정본 파일 선택 또는 placeholder 삽입 override 실행 후, 관련 section bucket / 초안 메타 / handoff 패키지가 올바르게 재생성되는지 확인
10. "SEC-3.1 검수해줘" → 리뷰 리포트 확인 → 이슈 해결
11. "핸드오프 패키지 만들어줘" → 09_handoff/ 생성 확인, 특히:
    - 미해결 draft_queries가 핸드오프 패키지에 누락 없이 반영되는가
    - placeholder가 있는 섹션이 핸드오프에서 별도 표시되는가
    - 고객 확인 필요 포인트가 섹션별로 정리되는가
12. framework_indexing_readiness.json 확인: overall_status, anchor_missing_sections, unmapped_disclosures, placeholder_only_disclosures, manual_review_required_items
13. 초안 임의 문장에서 원본 파일까지 역추적 가능한지 확인
14. structure_index의 section_id / heading_anchor / toc_path를 기준으로 GRI Content Index가 재생성 가능하며, blueprint 수정 후에도 구조 연결이 안정적으로 유지되는지 확인

### Python 스크립트 단위 테스트 (우선순위 순)
- **check_gate.py**: 게이트 판정 (실행 계약/페이즈 전이 조건) 검증
- **rebuild_summaries.py**: 파생 상태 재생성 — 원본에서 project_state/blocking_issues/next_actions 올바르게 재생성되는지
- **structure_index 생성/재생성**: blueprint 수정 후에도 section_id 안정성 유지, 앵커 재생성 규칙 일관성
- **draft_queries / handoff 집계**: 미해결 질문이 핸드오프에 정확하게 반영되는지
- **manual_overrides 반영**: override 실행 후 관련 산출물 연쇄 업데이트
- normalize.py: 다양한 포맷(PDF, Excel, 이미지) 변환 검증
- build_buckets.py: 라우팅 규칙 정확도 검증
- validate_provenance.py: 태그 파싱/유효성 검증
- export_docx.py: MD → DOCX 변환 (후순위, 초안 시스템의 핵심은 아님)

---

## 다음 단계: 기술 스택 논의

이 큰 그림이 확정되면, 다음으로 논의할 항목:
- Python 버전 및 핵심 라이브러리 (MarkItDown, python-docx, pyhwp 등)
- `llm/` adapter/router 구조 상세 설계
- `orchestration/` 규칙 파일 스키마 상세 설계
- 프레임워크 DB 구조 (GRI/TCFD/KSSB/SASB 공시 요구사항 정의 방식)
- 에이전트 프롬프트 설계 패턴 (입력/출력 계약 명시 방식, 일관성 계약 주입 방식)
- JSON 스키마 vs Pydantic 모델 선택
- sentence_provenance_map 문장 ID 생성/관리 규칙
- Google Drive MCP 연동 + 투입 메타데이터 상세
- HWP 표준 파이프라인 구현 (pyhwp, hwp5 등 라이브러리 조사)
- 이벤트 로그 포맷 표준화
