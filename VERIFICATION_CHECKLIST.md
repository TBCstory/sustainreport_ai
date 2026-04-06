
# 구현 검증 체크리스트 (Implementation Verification Checklist)

**프로젝트**: sustainreport_ai — ESG 지속가능경영보고서 초안 생성 시스템  
**작성일**: 2026-04-02  
**목적**: Step 1~7 전체 구현물의 기능적 검증

---

## 개요

이 체크리스트는 각 Step별 구현 파일이 **문법적으로 유효**하고 **기능적으로 동작**하는지 검증한다.

**검증 원칙**:
- 파일 존재 여부만 확인하지 않는다
- 실제로 import/실행하여 동작을 검증한다
- Python: `python3.13 -m py_compile` + `uv run python -c "import ..."`
- JSON: `jsonschema`로 Schema 검증
- CLI: `click` 기반 명령어 `--help` 또는 실제 실행

---

## 사전 조건

```bash
cd /Users/lj_homemac/tools/sustainreport_ai

# 1. uv sync 완료 (의존성 설치)
uv sync

# 2. Python 3.13 사용
python3.13 --version  # → Python 3.13.x
```

---

## Step 1: 프로젝트 초기화 인프라

### 1.1 `pyproject.toml`
| 검증 항목 | 방법 | 기대 결과 |
|---------|------|----------|
| 문법 유효 | `python3.13 -m py_compile pyproject.toml` | 오류 없음 |
| 필수 의존성 존재 | `grep "litellm" pyproject.toml && grep "jsonschema" pyproject.toml` | both found |
| Python 버전 | `grep "requires-python" pyproject.toml` | `>=3.13` |

### 1.2 `scripts/init_workspace.py`
| 검증 항목 | 방법 | 기대 결과 |
|---------|------|----------|
| 문법 유효 | `python3.13 -m py_compile scripts/init_workspace.py` | 오류 없음 |
| CLI 실행 | `uv run python scripts/init_workspace.py --help` | help 출력 |
| 워크스페이스 생성 | `uv run python scripts/init_workspace.py /tmp/test_prj && ls /tmp/test_prj` | 13개 디렉토리 생성 |

### 1.3 `.gitignore`
| 검증 항목 | 방법 | 기대 결과 |
|---------|------|----------|
| 파일 존재 | `test -f .gitignore` | exit 0 |
| 필수 패턴 존재 | `grep "workspaces/" .gitignore && grep "__pycache__" .gitignore` | both found |

---

## Step 2: 오케스트레이션 규칙 파일

### 2.1 `orchestration/phase_rules.json`
| 검증 항목 | 방법 | 기대 결과 |
|---------|------|----------|
| JSON 유효 | `python3.13 -c "import json; json.load(open('orchestration/phase_rules.json'))"` | 오류 없음 |
| Schema 검증 | `uv run python -c "import jsonschema; jsonschema.validate(json.load(open('orchestration/phase_rules.json')), json.load(open('schemas/phase_rules.schema.json')))"` | 유효 (schema 파일 있다면) |
| 필수 키 존재 | `python3.13 -c "d=json.load(open('orchestration/phase_rules.json')); assert 'phases' in d"` | 통과 |

### 2.2 `orchestration/gate_rules.json`
| 검증 항목 | 방법 | 기대 결과 |
|---------|------|----------|
| JSON 유효 | `python3.13 -c "import json; json.load(open('orchestration/gate_rules.json'))"` | 오류 없음 |
| 게이트 타입 존재 | `python3.13 -c "d=json.load(open('orchestration/gate_rules.json')); assert 'auto_gates' in d or 'human_gates' in d"` | 통과 |

### 2.3 `orchestration/agent_contracts.json`
| 검증 항목 | 방법 | 기대 결과 |
|---------|------|----------|
| JSON 유효 | `python3.13 -c "import json; json.load(open('orchestration/agent_contracts.json'))"` | 오류 없음 |
| 7개 에이전트 존재 | `python3.13 -c "d=json.load(open('orchestration/agent_contracts.json')); agents=['data-analyst','toc-planner','framework-mapper','section-writer','internal-reviewer','fact-checker','provenance-builder']; assert all(a in d['agents'] for a in agents)"` | 통과 |

### 2.4 `orchestration/model_routing.json`
| 검증 항목 | 방법 | 기대 결과 |
|---------|------|----------|
| JSON 유효 | `python3.13 -c "import json; json.load(open('orchestration/model_routing.json'))"` | 오류 없음 |
| POC 모드 존재 | `python3.13 -c "d=json.load(open('orchestration/model_routing.json')); assert d['poc_mode']['enabled']"` | 통과 |
| 에이전트별 정책 존재 | `python3.13 -c "d=json.load(open('orchestration/model_routing.json')); assert 'section-writer' in d['agent_model_policy']"` | 통과 |

### 2.5 `orchestration/agent_runtime_policy.json`
| 검증 항목 | 방법 | 기대 결과 |
|---------|------|----------|
| JSON 유효 | `python3.13 -c "import json; json.load(open('orchestration/agent_runtime_policy.json'))"` | 오류 없음 |
| persistent/ephemeral 존재 | `python3.13 -c "d=json.load(open('orchestration/agent_runtime_policy.json')); assert 'persistent' in d and 'ephemeral' in d"` | 통과 |

---

## Step 3: 핵심 스크립트

### 3.1 `scripts/log_event.py`
| 검증 항목 | 방법 | 기대 결과 |
|---------|------|----------|
| 문법 유효 | `python3.13 -m py_compile scripts/log_event.py` | 오류 없음 |
| CLI 실행 | `uv run python scripts/log_event.py --help` | help 출력 |
| 이벤트 기록 | `uv run python scripts/log_event.py --type test --agent verify --phase P0 --message "test"` | 파일 생성 확인 |

### 3.2 `scripts/check_gate.py`
| 검증 항목 | 방법 | 기대 결과 |
|---------|------|----------|
| 문법 유효 | `python3.13 -m py_compile scripts/check_gate.py` | 오류 없음 |
| CLI 실행 | `uv run python scripts/check_gate.py --help` | help 출력 |
| 함수 import | `uv run python -c "from scripts.check_gate import check_gate, evaluate_p2_to_p3"` | 오류 없음 |

### 3.3 `scripts/update_project_state.py`
| 검증 항목 | 방법 | 기대 결과 |
|---------|------|----------|
| 문법 유효 | `python3.13 -m py_compile scripts/update_project_state.py` | 오류 없음 |
| CLI 실행 | `uv run python scripts/update_project_state.py --help` | help 출력 |

### 3.4 `scripts/rebuild_summaries.py`
| 검증 항목 | 방법 | 기대 결과 |
|---------|------|----------|
| 문법 유효 | `python3.13 -m py_compile scripts/rebuild_summaries.py` | 오류 없음 |
| CLI 실행 | `uv run python scripts/rebuild_summaries.py --help` | help 출력 |

### 3.5 `scripts/normalize.py`
| 검증 항목 | 방법 | 기대 결과 |
|---------|------|----------|
| 문법 유효 | `python3.13 -m py_compile scripts/normalize.py` | 오류 없음 |
| CLI 실행 | `uv run python scripts/normalize.py --help` | help 출력 |

---

## Step 4: 에이전트 프롬프트 (7개)

### 공통 검증 (모든 agents/*.md)
```bash
# agents/ 디렉토리 내 7개 파일 존재 확인
ls agents/*.md | wc -l  # → 7

# 각 파일이 markdown 형식인지 확인
file agents/*.md | grep -v Markdown  # → empty (모두 Markdown)
```

### 4.1 `agents/data-analyst.md`
| 검증 항목 | 방법 | 기대 결과 |
|---------|------|----------|
| 필수 섹션 존재 | `grep -c '^## 역할' agents/data-analyst.md` | 1 |
| 입력 계약 존재 | `grep -c '^## 입력 계약' agents/data-analyst.md` | 1 |
| 출력 계약 존재 | `grep -c '^## 출력 계약' agents/data-analyst.md` | 1 |
| 작업 규칙 존재 | `grep -c '^## 작업 규칙' agents/data-analyst.md` | 1 |
| 금지 사항 존재 | `grep -c '^## 금지 사항' agents/data-analyst.md` | 1 |

### 4.2 `agents/toc-planner.md`
(위와 동일한 검증 항목)

### 4.3 `agents/framework-mapper.md`
(위와 동일한 검증 항목)

### 4.4 `agents/section-writer.md`
(위와 동일한 검증 항목)

### 4.5 `agents/internal-reviewer.md`
(위와 동일한 검증 항목)

### 4.6 `agents/fact-checker.md`
(위와 동일한 검증 항목)

### 4.7 `agents/provenance-builder.md`
(위와 동일한 검증 항목)

---

## Step 5: JSON Schema (8개)

### 공통 검증 (모든 schemas/*.schema.json)
```bash
# schemas/ 디렉토리 내 8개 파일 존재 확인
ls schemas/*.schema.json | wc -l  # → 8
```

### 개별 검증 (각 schema.json)
```bash
uv run python -c "
import json, jsonschema

schema_files = [
    'schemas/writing_blueprint.schema.json',
    'schemas/structure_index.schema.json',
    'schemas/draft_meta.schema.json',
    'schemas/draft_queries.schema.json',
    'schemas/section_bucket.schema.json',
    'schemas/kpi_registry.schema.json',
    'schemas/framework_index.schema.json',
    'schemas/file_registry.schema.json',
]

for f in schema_files:
    with open(f) as fp:
        try:
            json.load(fp)
            print(f'✅ {f} — JSON 유효')
        except json.JSONDecodeError as e:
            print(f'❌ {f} — JSON 오류: {e}')
"
```

### 각 Schema별 필드 존재 검증
```bash
uv run python -c "
import json

checks = {
    'schemas/writing_blueprint.schema.json': ['\$defs', 'properties'],
    'schemas/structure_index.schema.json': ['\$defs', 'properties'],
    'schemas/draft_meta.schema.json': ['properties', 'required'],
    'schemas/draft_queries.schema.json': ['properties', 'required'],
    'schemas/section_bucket.schema.json': ['properties', 'required'],
    'schemas/kpi_registry.schema.json': ['properties', 'required'],
    'schemas/framework_index.schema.json': ['properties', 'required'],
    'schemas/file_registry.schema.json': ['properties', 'required'],
}

for path, required_keys in checks.items():
    with open(path) as f:
        data = json.load(f)
    missing = [k for k in required_keys if k not in data]
    if missing:
        print(f'❌ {path} — 누락: {missing}')
    else:
        print(f'✅ {path} — OK')
"
```

---

## Step 6: LLM 래퍼

### 6.1 `llm/router.py`
| 검증 항목 | 방법 | 기대 결과 |
|---------|------|----------|
| 문법 유효 | `python3.13 -m py_compile llm/router.py` | 오류 없음 |
| Import | `uv run python -c "from llm.router import ModelRouter; print('OK')"` | OK |
| ModelRouter 인스턴스 | `uv run python -c "r=ModelRouter(); print(type(r))"` | `<class 'llm.router.ModelRouter'>` |
| 에이전트 모델 조회 | `uv run python -c "r=ModelRouter(); m=r.get_model_for_agent('section-writer'); assert m == 'claude-sonnet-4-20250514'"` | 통과 |
| 모델 설정 조회 | `uv run python -c "r=ModelRouter(); c=r.get_model_config('section-writer'); assert 'temperature' in c"` | 통과 |

### 6.2 `llm/call_log.py`
| 검증 항목 | 방법 | 기대 결과 |
|---------|------|----------|
| 문법 유효 | `python3.13 -m py_compile llm/call_log.py` | 오류 없음 |
| Import | `uv run python -c "from llm.call_log import CallLogEntry, generate_call_id, calculate_cost; print('OK')"` | OK |
| CallLogEntry 생성 | `uv run python -c "from llm.call_log import CallLogEntry; e=CallLogEntry(run_id='TEST', call_id='C1', agent='a', model='m', provider='p', timestamp='t', latency_ms=1.0, prompt_tokens=10, completion_tokens=5, total_tokens=15, cost_usd=0.001, status='ok', error=None, retry_count=0); print('OK')"` | OK |
| call_id 생성 | `uv run python -c "from llm.call_log import generate_call_id; id=generate_call_id(); assert id.startswith('CALL-')"` | 통과 |
| 비용 계산 | `uv run python -c "from llm.call_log import calculate_cost; c=calculate_cost('claude-sonnet-4-20250514', {'prompt_tokens':1000,'completion_tokens':500}); assert c > 0"` | 통과 |

---

## Step 7: Claude Code 어댑터

### 공통 검증 (모든 .claude/agents/*.md)
```bash
# 7개 어댑터 파일 존재 확인
ls .claude/agents/*.md | wc -l  # → 7
```

### 개별 검증 (각 adapter)
```bash
for f in .claude/agents/*.md; do
  name=$(basename "$f" .md)
  # 첫 H1 검증
  first_h1=$(grep '^# ' "$f" | head -1)
  expected="# $name"
  if [ "$first_h1" = "$expected" ]; then
    echo "✅ $name — 첫 H1 정상"
  else
    echo "❌ $name — 첫 H1 오류: '$first_h1' (기대: '$expected')"
  fi

  # Description 존재
  if grep -q '^## Description' "$f"; then
    echo "   ✅ Description 존재"
  else
    echo "   ❌ Description 누락"
  fi

  # Instructions 존재
  if grep -q '^## Instructions' "$f"; then
    echo "   ✅ Instructions 존재"
  else
    echo "   ❌ Instructions 누락"
  fi
done
```

### adapters 목록
- `.claude/agents/data-analyst.md`
- `.claude/agents/toc-planner.md`
- `.claude/agents/framework-mapper.md`
- `.claude/agents/section-writer.md`
- `.claude/agents/internal-reviewer.md`
- `.claude/agents/fact-checker.md`
- `.claude/agents/provenance-builder.md`

---

## End-to-End 검증 (고급)

### E2E-1: 게이트 판정 E2E
```bash
# 1. 테스트 워크스페이스 생성
WS=/tmp/e2e_test_prj
uv run python scripts/init_workspace.py "$WS"

# 2. P0 상태에서 P1→P2 게이트 확인 (아무 파일 없을 때)
uv run python scripts/check_gate.py "$WS" p1_to_p2  # → exit 1 (blocked)

# 3. project_state.json 확인
test -f "$WS/project_state.json" && echo "✅ project_state.json 존재"
```

### E2E-2: LLM Router + Call Log 연동
```bash
uv run python -c "
from llm.router import ModelRouter
from llm.call_log import CallLogEntry, generate_call_id, calculate_cost

router = ModelRouter()
agents = ['data-analyst', 'toc-planner', 'framework-mapper', 'section-writer',
          'internal-reviewer', 'fact-checker', 'provenance-builder']

for agent in agents:
    model = router.get_model_for_agent(agent)
    config = router.get_model_config(agent)
    print(f'✅ {agent}: {model} (temp={config[\"temperature\"]})')

print('✅ 모든 에이전트 모델 라우팅 정상')
"
```

---

## 발견된 이슈 트래커

| 파일 | 이슈 | 심각도 | 상태 | 발견일 |
|------|------|--------|------|--------|
| (없음) | — | — | — | — |

---

## 검증 완료 기준

**모든 항목 ✅ 통과** 시 구현 완료로 판단:

```
Step 1: 3/3 ✅
Step 2: 5/5 ✅
Step 3: 5/5 ✅
Step 4: 7/7 ✅
Step 5: 8/8 ✅
Step 6: 2/2 ✅
Step 7: 7/7 ✅
E2E:   2/2 ✅
────────────────
TOTAL: 39/39 ✅
```

---

## 실행 방법

```bash
cd /Users/lj_homemac/tools/sustainreport_ai

# 전체 검증 실행
uv sync

# 개별 Step 검증
# Step 1
python3.13 -m py_compile pyproject.toml scripts/init_workspace.py

# Step 2
for f in orchestration/*.json; do python3.13 -c "import json; json.load(open('$f'))"; done

# Step 3
for f in scripts/*.py; do python3.13 -m py_compile "$f"; done

# Step 5
uv run python -c "import json, glob; [json.load(open(f)) for f in glob.glob('schemas/*.schema.json')]"

# Step 6
uv run python -c "from llm.router import ModelRouter; from llm.call_log import CallLogEntry"

# Step 7
ls .claude/agents/*.md | wc -l  # → 7
```
