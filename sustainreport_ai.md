{\rtf1\ansi\ansicpg949\cocoartf2868
\cocoatextscaling0\cocoaplatform0{\fonttbl\f0\fnil\fcharset0 HelveticaNeue;\f1\fnil\fcharset0 .AppleSystemUIFontMonospaced-Regular;}
{\colortbl;\red255\green255\blue255;\red0\green0\blue0;\red255\green255\blue255;\red139\green137\blue127;
\red249\green248\blue242;}
{\*\expandedcolortbl;;\cssrgb\c0\c1\c1;\cssrgb\c100000\c100000\c99985;\cssrgb\c61274\c60483\c57193;
\cssrgb\c98236\c97841\c96027;}
\paperw11900\paperh16840\margl1440\margr1440\vieww11520\viewh8400\viewkind0
\deftab720
\pard\pardeftab720\partightenfactor0

\f0\fs26 \cf2 \cb3 \expnd0\expndtw0\kerning0
\outl0\strokewidth0 \strokec4 Agent\
\pard\pardeftab720\partightenfactor0

\f1\fs22 \cf2 \cb3 \strokec4 Design ESG system architecture\
\pard\pardeftab720\partightenfactor0

\f0 \cf2 \cb3 \strokec4 I now have a thorough understanding of the predecessor project's architecture, strengths, and gaps. Let me produce the comprehensive architecture plan.\
\
---\
\pard\pardeftab720\partightenfactor0

\fs18 \cf2 \cb3 \strokec4 \uc0\u44036 \u47029 \u55176  \u48372 \u44592 
\f1\fs26 \cf2 \cb3 \strokec5 \
\pard\pardeftab720\partightenfactor0

\f0\fs22 \cf2 \cb3 \strokec4 \
# sustainreport_ai -- System Architecture and Project Plan\
\
## 1. System Architecture Overview\
\
### 1.1 Fundamental Design Principle\
\
The system is organized around three orthogonal axes:\
\
- **Vertical axis (Phases):** P0 through P7, representing the lifecycle from project definition through evidence pack delivery\
- **Horizontal axis (Agents):** Specialist agents, each owning a bounded domain of competence\
- **Depth axis (Provenance):** Every artifact links backward to its source, forming an unbroken chain from final report sentence to raw file byte\
\
The predecessor `esgreport_writing` proved that contract-first design (Pydantic schemas, state machines, ID systems) works. It also revealed three critical weaknesses that this new architecture must fix:\
\
1. **The chain breaks in the middle.** Raw intake and final gates are strong, but content analysis, segment-to-section routing, and review separation are weak connective tissue.\
2. **The orchestrator is too passive.** The current `project-next-step` is a read-only status reporter. The new system needs an active orchestrator that sequences work, holds ambiguous decisions, and guides the operator.\
3. **No pre-writing structure decision layer.** The user's core requirement -- "\uc0\u47785 \u52264 \u44396 \u49457 \u48512 \u53552  \u49548 \u51452 \u51228 \u50640  \u45824 \u54620  \u49436 \u49696  \u45953 \u49828 \u47484  \u49324 \u51204 \u50640  \u51221 \u54616 \u44256  \u44536  \u44396 \u51312 \u50640  \u46384 \u46972  \u49436 \u49696 " -- has no explicit system support. TOC depth, writing approach per section, and evidence-routing targets must be decided before any drafting begins.\
\
### 1.2 Top-Level Architecture\
\
```\
                         \uc0\u9484 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9488 \
                         \uc0\u9474    Human Operator     \u9474 \
                         \uc0\u9474    (Natural Language   \u9474 \
                         \uc0\u9474     Interface)         \u9474 \
                         \uc0\u9492 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9516 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9496 \
                                  \uc0\u9474 \
                         \uc0\u9484 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9660 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9488 \
                         \uc0\u9474    MAIN ORCHESTRATOR   \u9474 \
                         \uc0\u9474    (Project Master)    \u9474 \
                         \uc0\u9474                        \u9474 \
                         \uc0\u9474   - Phase sequencing   \u9474 \
                         \uc0\u9474   - Gate management    \u9474 \
                         \uc0\u9474   - State explanation  \u9474 \
                         \uc0\u9474   - Agent dispatch     \u9474 \
                         \uc0\u9474   - Budget control     \u9474 \
                         \uc0\u9492 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9516 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9496 \
                                  \uc0\u9474 \
              \uc0\u9484 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9532 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9488 \
              \uc0\u9474                    \u9474                    \u9474 \
     \uc0\u9484 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9660 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9488  \u9484 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9660 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9488  \u9484 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9660 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9488 \
     \uc0\u9474   DATA LAYER    \u9474  \u9474  PLANNING LAYER \u9474  \u9474  WRITING LAYER  \u9474 \
     \uc0\u9474                 \u9474  \u9474                 \u9474  \u9474                 \u9474 \
     \uc0\u9474  Data Analyst   \u9474  \u9474  TOC/Structure  \u9474  \u9474  Writer Agents  \u9474 \
     \uc0\u9474  Agent          \u9474  \u9474  Agent          \u9474  \u9474  (by domain)    \u9474 \
     \uc0\u9474                 \u9474  \u9474  Framework      \u9474  \u9474                 \u9474 \
     \uc0\u9474                 \u9474  \u9474  Agent          \u9474  \u9474  Review Agent   \u9474 \
     \uc0\u9474                 \u9474  \u9474                 \u9474  \u9474  Fact-Check     \u9474 \
     \uc0\u9474                 \u9474  \u9474                 \u9474  \u9474  Agent          \u9474 \
     \uc0\u9492 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9516 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9496  \u9492 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9516 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9496  \u9474  Provenance     \u9474 \
              \uc0\u9474                   \u9474          \u9474  Agent          \u9474 \
              \uc0\u9492 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9524 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9524 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9516 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9496 \
                                                    \uc0\u9474 \
                         \uc0\u9484 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9660 \u9472 \u9472 \u9488 \
                         \uc0\u9474      FILE-BASED STATE STORE   \u9474 \
                         \uc0\u9474      (Project Workspace)      \u9474 \
                         \uc0\u9474                               \u9474 \
                         \uc0\u9474   JSON registries, MD content, \u9474 \
                         \uc0\u9474   context bus, event log       \u9474 \
                         \uc0\u9492 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9472 \u9496 \
```\
\
### 1.3 Communication Model\
\
All agent communication happens through the file-based workspace. Agents never call each other directly. This is a deliberate choice carried forward from the predecessor and reinforced by the Paperclip pattern:\
\
- **Agents read artifacts produced by prior phases** (input contracts)\
- **Agents write artifacts for downstream phases** (output contracts)\
- **The Orchestrator dispatches agents** and checks gate conditions\
- **The Context Bus** (`context_bus/events.jsonl`) records all significant state transitions\
- **Heartbeat files** signal agent liveness during long operations\
\
This means debugging, auditing, and human override are always possible by inspecting the workspace directory.\
\
### 1.4 State Management\
\
State is managed at two levels:\
\
**Object-level state machines** (carried forward from v1.5, proven by 958 tests):\
- File: received -> registered -> candidate_version -> pending_human_gate -> active -> superseded -> archived_inactive\
- Segment: extracted -> validated -> version_relinked -> deprecated  \
- Draft section: not_started -> drafted -> review_issue_open / needs_redraft -> approved_for_edit -> final_locked\
- Calculation: generated -> recomputed -> verified -> invalidated\
- Guideline: active -> breaking_change_announced -> propagated -> rescan_required\
\
**Phase-level project state** (new, managed by Orchestrator):\
- P0_DEFINITION -> P1_INGESTION -> P2_PLANNING -> P3_BUCKET_BUILDING -> P4_DRAFTING -> P5_REVIEW -> P6_EDITORIAL -> P7_EVIDENCE_PACK\
- Phase transitions require gate checks (not all sections must be at the same phase -- sections advance independently, but the project phase reflects the "leading edge")\
\
---\
\
## 2. Agent Design\
\
### 2.1 Main Orchestrator (Project Master)\
\
**Role:** The single point of control for the entire project lifecycle. Does not do domain work. Dispatches agents, enforces gates, explains state, and guides the human operator.\
\
**Inputs:** All workspace artifacts (reads registries, manifests, gate statuses)  \
**Outputs:** Dispatch commands, gate decisions, natural-language status reports, next-action recommendations\
\
**LLM model choice:** Small/fast model for status explanation and action guidance (Haiku-class). No LLM needed for gate enforcement (pure deterministic logic).\
\
**Autonomy level:** HIGH for read operations and status reporting. MEDIUM for dispatching deterministic phases. LOW for gate overrides (requires human approval).\
\
**Key behaviors:**\
- On startup: scans workspace, builds project state snapshot, identifies blockers\
- On operator query: explains current state in natural Korean/English, lists blockers with reasons, suggests specific next CLI commands\
- On agent completion: validates output artifacts, updates context bus, checks downstream gates\
- Budget tracking: tracks token usage per agent per phase, warns when approaching limits\
\
**Improvement over predecessor:** The v1.7b `project-next-step` is read-only. The new Orchestrator actively sequences work: "Data Analyst has finished normalization for 47 of 52 files. 5 files need manual conversion. Would you like to proceed with planning using the 47 available files, or wait until all files are ready?"\
\
### 2.2 Data Analyst Agent\
\
**Role:** File ingestion, format conversion, normalization, 3-layer deduplication, segment extraction, content analysis, topic tagging.\
\
**Inputs:** Raw files from source directory (PDF, Excel, HWP, images, etc.)  \
**Outputs:** \
- `file_registry/F-NNNN.json` per file\
- `01_raw/` raw copies\
- `03_normalized_md/F-NNNN.md` normalized markdown\
- `segment_registry.json` with extracted segments\
- `duplicate_summary.json`\
- Content analysis tags per segment (topic, content type, language, confidence)\
\
**LLM model choice:**\
- No LLM for format conversion (MarkItDown, OCR tools)\
- Small model for content type classification and topic tagging\
- Medium model for semantic signature computation (dedup layer 3)\
\
**Autonomy level:**\
- FULL AUTO: Binary hash dedup, format conversion, segment extraction\
- SEMI-AUTO: Structural fingerprint dedup (auto-flag, human-confirm for near-matches)\
- HUMAN REQUIRED: Cross-format equivalence decisions, HWP/scan manual review\
\
### 2.3 TOC/Structure Agent\
\
**Role:** This is the NEW agent that addresses the user's core requirement. Before any writing begins, this agent designs the report structure: TOC hierarchy, depth of each subtopic, writing approach (narrative vs. data table vs. mixed), expected length, framework alignment per section.\
\
**Inputs:**\
- `report_basis.json` (reporting period, boundary, frameworks)\
- `framework_outline_matrix.json` (framework disclosure requirements)\
- `section_manifest.json` (initial TOC from framework mapping)\
- `evidence_catalog.json` (available evidence inventory)\
- `kpi_definition_registry.json`\
- Industry peer reports (reference structure)\
- Client preferences (from P0 project definition)\
\
**Outputs:**\
- **`writing_blueprint.json`** (NEW artifact): Per-section writing specification\
  ```\
  section_id: SEC-3.1\
  title: "\uc0\u50728 \u49892 \u44032 \u49828  \u48176 \u52636 \u47049 "\
  depth_level: 3 (1=overview, 2=standard, 3=detailed, 4=comprehensive)\
  writing_approach: "data_table_with_narrative"\
  expected_length_words: 800-1200\
  required_subsections: ["Scope 1", "Scope 2", "Scope 3 (relevant categories)"]\
  framework_disclosures: ["GRI 305-1", "GRI 305-2", "TCFD Metrics-a"]\
  evidence_requirements: ["emission data by scope", "calculation methodology", "YoY comparison"]\
  writing_constraints: ["must include base year", "must show intensity metrics"]\
  flexibility_mode: "rigid"\
  ```\
- **`section_depth_map.json`**: Visual hierarchy of the report with depth assignments\
- Updated `section_manifest.json` with refined TOC\
\
**LLM model choice:** Medium model (Sonnet-class) for structure reasoning, with deterministic rules for framework mapping.\
\
**Autonomy level:**\
- SEMI-AUTO: Proposes structure, human reviews and approves\
- The writing blueprint is a GATE artifact: no drafting proceeds without an approved blueprint\
\
### 2.4 Framework Agent\
\
**Role:** Framework mapping specialist. Maps disclosure requirements across GRI, TCFD, KSSB/IFRS S2, ESRS, SASB, UNGC, ISO 26000, UN SDGs, EcoVadis, Hyundai KAP, RMAP to report sections.\
\
**Inputs:**\
- `report_basis.json` (which frameworks apply)\
- `section_manifest.json` (report structure)\
- Framework reference database (built-in, deterministic)\
\
**Outputs:**\
- `framework_outline_matrix.json` (section-to-disclosure mapping)\
- `framework_applicability_matrix.json` (company-specific applicability)\
- `framework_gap_report.json` (disclosures required but not yet addressed)\
- Cross-mapping validation (e.g., GRI 305-1 and TCFD Metrics-a both require emission data)\
\
**LLM model choice:** Minimal LLM use. Framework mapping is predominantly deterministic (rule-based lookup). LLM only for edge cases where disclosure requirements are ambiguous.\
\
**Autonomy level:** FULL AUTO for standard framework mapping. HUMAN REQUIRED for materiality assessment and framework scope decisions.\
\
### 2.5 Writer Agents (Domain-Specialized, Multiple Instances)\
\
**Role:** Evidence-based section drafting. Each writer specializes in a domain: Environment, Social, Governance, Overview/Strategy, Appendix/Data Tables.\
\
**Inputs:**\
- `writing_blueprint.json` entry for this section (structure, depth, approach, constraints)\
- `section_bucket/SEC-X.Y.json` (routed evidence for this section)\
- `03_normalized_md/` source content (the actual evidence text)\
- `style_guide.json`, `terminology_dictionary.json`\
- Upstream section summaries (for continuity, read-only)\
\
**Outputs:**\
- `05_drafts/SEC-X.Y.md` (draft markdown with embedded provenance tags)\
- `05_drafts/SEC-X.Y_meta.json` (draft metadata, state, provenance refs)\
- Every sentence must contain `<!-- src:SEG-XXXXX@vN -->` or `<!-- src:CALC-XXXX -->` tags\
\
**LLM model choice:** Large model (Opus-class) for strategy/narrative sections. Medium model (Sonnet-class) for data-heavy sections. Small model (Haiku-class) for boilerplate/appendix sections.\
\
**Autonomy level:**\
- RIGID sections (quantitative data): Fully templated, LLM fills values only\
- FLEX sections (narrative with data): LLM drafts within blueprint constraints\
- MANUAL sections (CEO message, forward-looking statements): Human writes, system only provides evidence summary\
\
**Key constraint from predecessor:** The `SectionFlexibilityMode` (rigid/flex/manual) pattern works well. Carry it forward.\
\
**Key improvement:** The predecessor's writer agents lack the `writing_blueprint` input. They receive evidence but not explicit instructions on depth, structure, or writing approach. The new system gives writers a precise specification before they start.\
\
### 2.6 Review Agent (Internal Fact-Check)\
\
**Role:** Cross-references drafted content against source evidence. Checks: numbers match sources, provenance tags are present and valid, no unsupported claims, no internal inconsistencies across sections.\
\
**Inputs:**\
- Drafted sections (`05_drafts/`)\
- Source segments and files\
- `calculation_registry.json`\
- `provenance_index.json`\
\
**Outputs:**\
- `07_review/internal_fact_check_report.json`\
- Review findings with severity (error/warning/info)\
- Specific line references with linked source evidence\
\
**LLM model choice:** Deterministic-first (regex, cross-reference lookup). LLM only for semantic consistency checks (e.g., "this paragraph says emissions decreased but the table shows an increase").\
\
**Autonomy level:** FULL AUTO for generation. Human reviews findings and decides actions.\
\
### 2.7 Fact-Check Agent (External Validation)\
\
**Role:** Validates claims against external sources. Checks: industry benchmark claims, public data references, regulatory compliance assertions, comparative/leadership claims.\
\
**Inputs:**\
- Drafted sections\
- `_RISKY_EXTERNAL_PATTERNS` (regex patterns for claims requiring verification, from predecessor)\
- External data sources (industry databases, public filings)\
\
**Outputs:**\
- `07_review/external_fact_check_report.json`\
- Flagged claims with verification status and source\
\
**LLM model choice:** Medium model for claim extraction. External API calls for verification.\
\
**Autonomy level:** SEMI-AUTO. Flags claims, human verifies.\
\
### 2.8 Provenance Agent\
\
**Role:** Builds and maintains the complete evidence chain from final report back to source files.\
\
**Inputs:** All workspace artifacts\
**Outputs:**\
- `provenance_index.json` (section-to-source mapping)\
- `kpi_registry.json` (KPI values with full calculation trace)\
- `numeric_trace_view.json` (every number in the report traced to its source)\
- `evidence_pack/` (complete audit-ready package)\
\
**LLM model choice:** No LLM. Purely deterministic artifact assembly.\
\
**Autonomy level:** FULL AUTO. Produces evidence pack from existing artifacts.\
\
---\
\
## 3. Data Architecture\
\
### 3.1 Workspace Directory Structure\
\
```\
PF-2025-001/                              # Portfolio\
  project_relationship_map.json\
  report_output_map.json\
  shared_asset_scope.json\
  \
  PRJ-2025-COMP-001/                      # Project\
    project.json                           # Project metadata\
    \
    00_definition/                         # P0: Project definition\
      project_charter.json                 # Scope, boundary, frameworks, automation levels\
      stakeholder_matrix.json              # Who approves what\
      \
    01_raw/                                # P1: Raw file storage (immutable)\
      F-0001_original_name.pdf\
      F-0002_original_name.xlsx\
      \
    02_file_registry/                      # File tracking\
      F-0001.json\
      F-0002.json\
      _index.json\
      duplicate_summary.json\
      version_groups.json\
      \
    03_normalized_md/                      # Normalized content\
      F-0001.md\
      F-0001_meta.json                    # Conversion quality metrics\
      F-0002.md\
      \
    04_segments/                           # Extracted segments\
      segment_registry.json\
      SEG-00001.json                      # Segment with topic tags, content type\
      SEG-00002.json\
      \
    05_planning/                           # P2: Planning artifacts\
      report_basis.json\
      framework_outline_matrix.json\
      framework_applicability_matrix.json\
      kpi_definition_registry.json\
      evidence_catalog.json\
      section_manifest.json               # TOC\
      writing_blueprint.json              # NEW: per-section writing specification\
      section_depth_map.json              # NEW: hierarchical depth assignments\
      section_boundary_matrix.json\
      workflow_readiness_report.json\
      \
    06_buckets/                            # P3: Evidence routing\
      SEC-1.0.json                        # Section bucket with routed evidence\
      SEC-2.1.json\
      section_gap_report.json             # Sections with insufficient evidence\
      \
    07_drafts/                             # P4: Section drafts\
      SEC-1.0.md                          # Draft with provenance tags\
      SEC-1.0_meta.json                   # Draft state, provenance refs\
      SEC-2.1.md\
      SEC-2.1_meta.json\
      \
    08_review/                             # P5: Review artifacts\
      internal_fact_check_report.json\
      framework_review_report.json\
      external_fact_check_report.json\
      review_issues.json\
      assurance_qna_log.json\
      \
    09_editorial/                          # P6: Editorial\
      final_report.md\
      final_report_state.json\
      revision_freeze_log.json\
      \
    10_evidence_pack/                      # P7: Audit-ready package\
      evidence_pack_manifest.json\
      provenance_index.json\
      kpi_registry.json\
      numeric_trace_view.json\
      \
    guidance/                              # Cross-phase guidelines\
      style_guide.json\
      terminology_dictionary.json\
      section_flexibility_matrix.json\
      \
    context_bus/                            # Event log\
      events.jsonl\
      \
    approval_gates.json                    # Gate tracking\
```\
\
### 3.2 The Provenance Chain\
\
This is the single most important data relationship in the system:\
\
```\
Final Report Sentence\
  \uc0\u9474 \
  \uc0\u9500 \u9472 \u9472  provenance tag: <!-- src:SEG-00014@v2 -->\
  \uc0\u9474      \u9474 \
  \uc0\u9474      \u9492 \u9472 \u9472  Segment SEG-00014\
  \uc0\u9474            \u9474 \
  \uc0\u9474            \u9500 \u9472 \u9472  source_file: F-0001\
  \uc0\u9474            \u9474      \u9474 \
  \uc0\u9474            \u9474      \u9492 \u9472 \u9472  Raw file: 01_raw/F-0001_GHG_data.xlsx\
  \uc0\u9474            \u9474 \
  \uc0\u9474            \u9500 \u9472 \u9472  heading_path: ["3. \u54872 \u44221 ", "3.1 \u50728 \u49892 \u44032 \u49828 ", "Scope 1"]\
  \uc0\u9474            \u9492 \u9472 \u9472  text_excerpt: "Scope 1 \u51649 \u51217 \u48176 \u52636 : 12,345 tCO2e"\
  \uc0\u9474 \
  \uc0\u9500 \u9472 \u9472  provenance tag: <!-- src:CALC-0021 -->\
  \uc0\u9474      \u9474 \
  \uc0\u9474      \u9492 \u9472 \u9472  Calculation CALC-0021\
  \uc0\u9474            \u9474 \
  \uc0\u9474            \u9500 \u9472 \u9472  inputs: [SEG-00014@v2, SEG-00045@v1]\
  \uc0\u9474            \u9500 \u9472 \u9472  formula: "scope1 + scope2"\
  \uc0\u9474            \u9492 \u9472 \u9472  result: 45,678 tCO2e\
  \uc0\u9474 \
  \uc0\u9492 \u9472 \u9472  section_bucket: SEC-3.1\
        \uc0\u9474 \
        \uc0\u9500 \u9472 \u9472  source_file_refs: [F-0001, F-0003]\
        \uc0\u9492 \u9472 \u9472  source_segment_refs: [SEG-00014, SEG-00015, SEG-00045]\
```\
\
### 3.3 Key Schema Contracts\
\
All JSON artifacts follow the common envelope pattern from the predecessor:\
\
```json\
\{\
  "schema_name": "writing_blueprint",\
  "schema_version": "1.0.0",\
  "generated_at": "2026-04-01T10:00:00Z",\
  "project_id": "PRJ-2025-COMP-001"\
\}\
```\
\
The `writing_blueprint.json` is the most important NEW schema. It bridges the gap between planning and writing that the predecessor never filled:\
\
```\
writing_blueprint.json\
  entries:\
    - section_id: str\
      title: str\
      depth_level: int (1-4)\
      writing_approach: enum (narrative | data_table | data_table_with_narrative | mixed | template_only)\
      expected_length_range: \{min_words: int, max_words: int\}\
      required_subsections: list[str]\
      framework_disclosures: list[str]  (e.g., ["GRI 305-1", "TCFD Metrics-a"])\
      evidence_requirements: list[str]  (natural language descriptions of what evidence is needed)\
      writing_constraints: list[str]    (specific rules for this section)\
      tone: enum (formal_technical | formal_narrative | factual_concise)\
      flexibility_mode: enum (rigid | flex | manual)\
      model_recommendation: str        (which LLM model to use for this section)\
      parent_section_id: str | null\
      order: int\
      approved: bool\
      approved_by: str | null\
      approved_at: datetime | null\
```\
\
---\
\
## 4. Workflow Pipeline\
\
### 4.0 Phase 0: Project Definition\
\
**Gate in:** None  \
**Gate out:** Project charter approved (frameworks, boundary, scope, stakeholder matrix defined)\
\
1. Operator creates project via CLI: `sr init-project --portfolio-id PF-2025-001 --project-id PRJ-2025-COMP-001`\
2. System creates workspace directory structure\
3. Operator fills project charter: reporting period, organizational boundary, applicable frameworks, automation level preferences per section type\
4. Operator defines stakeholder matrix: who approves what (ESG team approves data sections, CEO office approves strategy, legal approves compliance)\
5. Orchestrator validates charter completeness\
\
### 4.1 Phase 1: Data Ingestion & Normalization\
\
**Gate in:** Project charter approved  \
**Gate out:** All files registered, normalization exceptions resolved or acknowledged\
\
1. Operator provides source directory\
2. Data Analyst Agent ingests files:\
   - Copies to `01_raw/` (immutable)\
   - Assigns file IDs (`F-0001`, `F-0002`, ...)\
   - Creates file registry entries (state: `received`)\
3. Format conversion via MarkItDown/OCR:\
   - PDF -> MD, Excel -> MD, images -> MD (OCR)\
   - HWP: flag as `manual_required`\
   - Store in `03_normalized_md/` with conversion quality metadata\
4. 3-layer deduplication:\
   - Layer 1: Binary hash (exact duplicate auto-reject)\
   - Layer 2: Structural fingerprint (near-duplicate flagged for human review)\
   - Layer 3: Semantic signature (cross-format equivalence flagged for human review)\
5. Segment extraction:\
   - Split normalized documents into content segments\
   - Each segment gets topic tags, content type classification, language\
   - Store in `04_segments/`\
6. Orchestrator reports status: "52 files ingested, 47 normalized, 5 need manual conversion. 3 duplicate groups found."\
\
### 4.2 Phase 2: Planning\
\
**Gate in:** Normalization complete (or exceptions acknowledged)  \
**Gate out:** Writing blueprint approved by operator\
\
1. Framework Agent maps applicable frameworks to disclosure requirements\
2. Framework Agent produces `framework_outline_matrix.json` and gap report\
3. TOC/Structure Agent proposes initial TOC based on:\
   - Framework disclosure requirements\
   - Available evidence inventory\
   - Industry best practices for report structure\
   - Client preferences\
4. TOC/Structure Agent assigns depth and writing approach per section\
5. **Human review loop:** Operator reviews proposed TOC and writing blueprint\
   - Adjusts section depth\
   - Modifies writing approaches\
   - Adds/removes sections\
   - Sets flexibility modes (rigid/flex/manual)\
6. Operator approves writing blueprint -- this is a hard gate\
7. Workflow readiness check: validates that all planning artifacts are consistent and complete\
\
### 4.3 Phase 3: Section Bucket Building\
\
**Gate in:** Writing blueprint approved  \
**Gate out:** All sections have routed evidence (or explicit gap acknowledgment)\
\
1. Deterministic routing (95% of cases):\
   - Match segments to sections by heading path, topic tags, framework alignment\
   - Use section-signature matching, keyphrase overlap, terminology dictionary\
   - Use the extensive alias and routing rules proven in v1.7b\
2. LLM-assisted routing (5% of cases):\
   - Ambiguous segments where deterministic rules produce ties\
   - Cross-domain segments that could belong to multiple sections\
3. Gap report generation:\
   - Sections with no evidence\
   - Sections with insufficient evidence for their depth level\
   - Evidence that doesn't route to any section (orphaned evidence)\
4. Human review of gap report: operator may request additional data collection or reduce section depth\
\
### 4.4 Phase 4: Evidence-Based Drafting\
\
**Gate in:** Section buckets populated, gap report reviewed  \
**Gate out:** All sections drafted (or manual sections marked as human-pending)\
\
1. Orchestrator builds dependency graph (parent sections before children)\
2. Orchestrator dispatches writers in batches:\
   - Batch 1: Overview/strategy sections (provide framing for detail sections)\
   - Batch 2: Data-heavy sections (quantitative, rigid mode)\
   - Batch 3: Narrative sections (flex mode)\
   - Manual sections: skipped, human writes\
3. Each writer receives:\
   - Writing blueprint entry (structure, depth, constraints)\
   - Section bucket (routed evidence)\
   - Source content (normalized markdown)\
   - Style guide and terminology\
   - Upstream section summaries (read-only, for consistency)\
4. Writer produces draft with embedded provenance tags\
5. Orchestrator validates: every claim has a provenance tag, word count within range, required subsections present\
\
### 4.5 Phase 5: Multi-Layer Review\
\
**Gate in:** Section drafted  \
**Gate out:** All review issues resolved or accepted\
\
Three independent review passes (can run in parallel):\
\
**Internal Fact-Check (Review Agent):**\
- Numbers match source data\
- Provenance tags are valid and point to correct sources\
- No internal contradictions across sections\
- Year-over-year comparisons are consistent\
- Unit consistency (tCO2e everywhere, not sometimes "tons")\
\
**Framework Review (Framework Agent):**\
- All required disclosures are addressed\
- Disclosure content meets framework requirements\
- Cross-framework consistency (same emission number in GRI and TCFD sections)\
\
**External Validation (Fact-Check Agent):**\
- Risky claims flagged (industry-leading, world-class, etc.)\
- Public data references verified\
- Industry benchmark comparisons validated\
- Regulatory compliance assertions checked\
\
Each review produces findings. Findings flow into `review_issues.json`. Section state transitions to `review_issue_open` until resolved.\
\
### 4.6 Phase 6: Editorial & Finalization\
\
**Gate in:** All review issues resolved for a section  \
**Gate out:** Section final-locked\
\
1. Tone harmonization across sections\
2. Cross-section consistency check (terminology, number formatting, date formats)\
3. Appendix generation (GRI index, TCFD index, data tables)\
4. Final assembly into `final_report.md`\
5. Section-by-section final lock (state: `final_locked`)\
6. `final_report_state.json` tracks overall lock status\
\
### 4.7 Phase 7: Evidence Pack Generation\
\
**Gate in:** All sections final-locked  \
**Gate out:** Evidence pack passes integrity check\
\
1. Provenance Agent builds `provenance_index.json`: every section mapped to its sources\
2. KPI registry: every KPI value with calculation chain\
3. Numeric trace view: every number in the final report traced to source\
4. Evidence pack manifest: lists all artifacts, their hashes, and relationships\
5. Integrity check: validates all cross-references, no broken links, no orphaned artifacts\
6. Evidence pack: the complete audit-ready package\
\
---\
\
## 5. TOC/Structure Planning System\
\
This is the critical gap in the predecessor and the core differentiator of the new system.\
\
### 5.1 The Problem\
\
The predecessor jumps from "we have a section manifest (list of sections)" directly to "write section drafts." There is no intermediate step where the system and operator collaboratively decide: How deep should section 3.1 go? Should it be a data table or a narrative? What subsections are needed? What writing constraints apply?\
\
### 5.2 The Solution: Writing Blueprint\
\
The `writing_blueprint.json` is a contract between the planning phase and the writing phase. It specifies, for each section:\
\
**Depth Level (1-4):**\
- Level 1 (Overview): 100-300 words. High-level summary. Example: "Our company is committed to reducing GHG emissions."\
- Level 2 (Standard): 300-800 words. Key facts and figures with brief explanation. Example: Scope 1/2 totals with methodology note.\
- Level 3 (Detailed): 800-1500 words. Full analysis with context, trends, targets. Example: Scope 1/2/3 breakdown with YoY comparison, intensity metrics, reduction targets, methodology.\
- Level 4 (Comprehensive): 1500+ words. Exhaustive treatment. Example: Full GHG inventory with category-level Scope 3, detailed methodology, verification statement, scenario analysis.\
\
**Writing Approach:**\
- `data_table`: Primarily tables and figures with minimal narrative\
- `narrative`: Primarily text with embedded data points\
- `data_table_with_narrative`: Tables followed by explanatory narrative\
- `mixed`: Combination determined by content\
- `template_only`: Fill-in-the-blank template (for boilerplate sections)\
\
**Framework Alignment:**\
- Which specific disclosure requirements this section must address\
- Cross-mapping to show when one section serves multiple frameworks\
\
### 5.3 Blueprint Creation Process\
\
1. **Auto-propose:** TOC/Structure Agent analyzes framework requirements and evidence inventory to propose initial blueprint\
2. **Human review:** Operator reviews each section's depth, approach, and constraints\
3. **Iterative refinement:** Agent adjusts based on operator feedback\
4. **Approval gate:** Operator explicitly approves the blueprint\
5. **Blueprint lock:** Once approved, the blueprint becomes the binding contract for writers\
\
### 5.4 Blueprint Enforcement During Drafting\
\
Writers receive their section's blueprint entry as a hard constraint:\
- Word count outside the specified range triggers a warning\
- Missing required subsections trigger a warning\
- Writing approach mismatch (e.g., pure narrative when data_table was specified) triggers redraft\
- Framework disclosures not addressed trigger a review finding\
\
---\
\
## 6. Quality & Verification System\
\
### 6.1 The Three Review Layers\
\
| Layer | Agent | Focus | Method | Autonomy |\
|-------|-------|-------|--------|----------|\
| Internal fact-check | Review Agent | Numbers, sources, internal consistency | Deterministic + LLM semantic check | Full auto |\
| Framework review | Framework Agent | Disclosure completeness, framework compliance | Deterministic rule matching | Full auto |\
| External validation | Fact-Check Agent | External claims, benchmarks, public data | LLM claim extraction + external API | Semi-auto |\
\
### 6.2 Review Finding Lifecycle\
\
```\
Finding created (severity: error/warning/info)\
  \uc0\u8594  Assigned to section owner\
    \uc0\u8594  Resolution:\
      \uc0\u9500 \u9472 \u9472  Fix: redraft section (state \u8594  needs_redraft \u8594  drafted)\
      \uc0\u9500 \u9472 \u9472  Accept: human acknowledges with rationale\
      \uc0\u9492 \u9472 \u9472  Dismiss: finding is incorrect (with justification)\
    \uc0\u8594  All findings resolved \u8594  section eligible for editorial\
```\
\
### 6.3 Provenance Verification Chain\
\
The system enforces an unbroken provenance chain. At the evidence pack gate, the following checks must ALL pass:\
\
1. Every section in the final report has a provenance index entry\
2. Every provenance tag in draft text resolves to a valid segment or calculation\
3. Every segment traces to a registered, non-superseded file\
4. Every calculation's inputs trace to valid segments\
5. No section contains text without provenance tags (the "no speculation" rule)\
6. The evidence pack SHA-256 hashes match actual file contents\
\
### 6.4 Hallucination Detection\
\
This is a core user concern. The system addresses it at multiple levels:\
\
1. **Prevention:** Writers only receive evidence from section buckets. The prompt explicitly forbids speculation.\
2. **Detection (structural):** Every sentence must have a provenance tag. Untagged sentences are automatically flagged.\
3. **Detection (semantic):** Review Agent compares claimed values against source segment values.\
4. **Detection (external):** Fact-Check Agent validates quantitative claims against public data.\
5. **Human verification:** The provenance index makes it easy for humans to trace any sentence back to its source.\
\
---\
\
## 7. Project Management UX\
\
### 7.1 Natural Language Interface\
\
The Orchestrator communicates with the operator in natural language (Korean or English based on project settings). This is NOT a chatbot -- it is a structured status reporter and action guide.\
\
**Status query example:**\
```\
Operator: \uc0\u54788 \u51116  \u49345 \u53468 ?\
\
System: \uc0\u54532 \u47196 \u51229 \u53944  PRJ-2025-COMP-001 \u54788 \u54889 :\
\
Phase 1 (\uc0\u51088 \u47308  \u53804 \u51077 ): \u50756 \u47308 \
  - 52\uc0\u44060  \u54028 \u51068  \u46321 \u47197 , 47\u44060  \u51221 \u44508 \u54868  \u50756 \u47308 \
  - 5\uc0\u44060  \u54028 \u51068  \u49688 \u46041  \u48320 \u54872  \u54596 \u50836  (F-0048~F-0052: HWP \u54805 \u49885 )\
  - 3\uc0\u44060  \u51473 \u48373  \u44536 \u47353  \u48156 \u44204 , 2\u44060  \u51088 \u46041  \u52376 \u47532 , 1\u44060  \u51064 \u44036  \u54869 \u51064  \u54596 \u50836 \
\
Phase 2 (\uc0\u44592 \u54925 ): \u51652 \u54665  \u51473 \
  - \uc0\u47785 \u52264  \u52488 \u50504  \u49373 \u49457  \u50756 \u47308  (42\u44060  \u49465 \u49496 )\
  - writing_blueprint \uc0\u49849 \u51064  \u45824 \u44592  \u51473 \
  \
\uc0\u52264 \u45800  \u50836 \u51064 :\
  1. F-0048~F-0052: HWP \uc0\u54028 \u51068  \u49688 \u46041  \u48320 \u54872  \u54596 \u50836 \
  2. VG-003: \uc0\u51473 \u48373  \u44536 \u47353  \u51221 \u48376  \u54869 \u51064  \u54596 \u50836  (\u54872 \u44221 \u45936 \u51060 \u53552 _v2.xlsx vs \u54872 \u44221 \u45936 \u51060 \u53552 _final.xlsx)\
  3. writing_blueprint: \uc0\u50868 \u50689 \u51088  \u49849 \u51064  \u54596 \u50836 \
\
\uc0\u44428 \u51109  \u45796 \u51020  \u51312 \u52824 :\
  1. `sr resolve-duplicate VG-003 --keep F-0015` (\uc0\u51473 \u48373  \u54644 \u44208 )\
  2. `sr approve-blueprint` (writing blueprint \uc0\u44160 \u53664  \u48143  \u49849 \u51064 )\
  3. HWP \uc0\u54028 \u51068 \u51008  \u49688 \u46041  \u48320 \u54872  \u54980  `sr import-manual F-0048 --source converted.md`\
```\
\
### 7.2 Operator Commands\
\
The CLI provides structured commands for each phase:\
\
```\
# Project lifecycle\
sr init-project          # P0: Create project\
sr import-files          # P1: Ingest files\
sr status                # Any: Current state overview\
sr next-step             # Any: Specific next action guidance\
\
# Planning\
sr propose-toc           # P2: Generate TOC proposal\
sr approve-blueprint     # P2: Approve writing blueprint\
sr check-readiness       # P2: Workflow readiness check\
\
# Writing\
sr build-buckets         # P3: Route evidence to sections\
sr write-drafts          # P4: Generate drafts for ready sections\
sr write-section SEC-3.1 # P4: Write specific section\
\
# Review\
sr review-internal       # P5: Run internal fact-check\
sr review-framework      # P5: Run framework compliance check\
sr review-external       # P5: Run external validation\
sr resolve-issue ISS-001 # P5: Resolve review finding\
\
# Finalization\
sr lock-section SEC-3.1  # P6: Final-lock a section\
sr build-evidence-pack   # P7: Generate evidence pack\
sr integrity-check       # P7: Validate evidence pack\
\
# Utility\
sr resolve-duplicate VG-003  # Resolve duplicate group\
sr import-manual F-0048      # Import manually converted file\
sr export-docx               # Export to Word format\
```\
\
### 7.3 Dashboard\
\
A terminal-based dashboard (using Rich or similar) showing:\
- Project phase progress bar\
- Section-by-section status grid (color-coded by state)\
- Active blockers list\
- Recent context bus events\
- Agent activity (which agent is running, token usage)\
\
---\
\
## 8. Multi-Project Support\
\
### 8.1 Project Topology Types\
\
Carried forward from the predecessor's proven 5-type taxonomy:\
\
| Type | Code | Description | Output |\
|------|------|-------------|--------|\
| Single company | SINGLE | One company, one report | 1 report |\
| Group unified (full) | GROUP_UNIFIED_FULL | N companies, 1 integrated report | 1 report |\
| Group unified (partial) | GROUP_UNIFIED_PARTIAL | Some chapters shared, some per-entity | 1 report |\
| Group parallel | GROUP_PARALLEL | Same standards, separate reports | N reports |\
| Hybrid matrix | HYBRID_MATRIX | Mix of unified and parallel | M reports |\
\
### 8.2 Portfolio-Level Coordination\
\
The portfolio level manages:\
- `project_relationship_map.json`: parent-child relationships between projects\
- `report_output_map.json`: which projects contribute to which output reports\
- `shared_asset_scope.json`: which assets (guidelines, framework DB, terminology) are shared\
\
### 8.3 Cross-Project Data Flow\
\
For group projects:\
- **Shared guidelines** propagate from parent to children (guideline state machine handles breaking changes)\
- **Shared framework DB** is read-only for child projects\
- **Cross-company files** are split into per-entity segments before routing (never route a cross-company file directly to a section)\
- **Shared sections** (e.g., group governance overview) are managed at the parent level with references from child reports\
- **KPI aggregation** flows upward: child entity KPIs aggregate to parent group KPIs\
\
---\
\
## 9. Implementation Phases (Prioritized Roadmap)\
\
### Phase I: Foundation (Weeks 1-3)\
\
**Goal:** Reproduce the predecessor's core contracts and add the new planning layer.\
\
Build order:\
1. **Core contracts** (carry forward from esgreport_writing, refactored):\
   - `core/ids.py` -- ID system\
   - `core/states.py` -- State machines\
   - `core/files.py` -- Atomic file operations\
   - `core/exceptions.py` -- Exception hierarchy\
   - `models/common.py` -- Base Pydantic models with registry document envelope\
2. **Workspace initialization:**\
   - `services/project_init_service.py` -- Directory structure creation\
   - New `00_definition/` directory for project charter\
3. **File ingestion pipeline:**\
   - `services/import_service.py` -- File intake\
   - `services/normalizer_service.py` -- Format conversion\
   - `services/duplicate_service.py` -- 3-layer dedup\
4. **NEW: Writing blueprint model and TOC planning:**\
   - `models/writing_blueprint.py` -- The new core artifact\
   - `models/section_depth_map.py`\
   - `services/toc_planning_service.py`\
\
**Deliverable:** `init-project -> import-files -> propose-toc -> approve-blueprint -> status` flow works end-to-end.\
\
### Phase II: Evidence Routing & Drafting (Weeks 4-6)\
\
**Goal:** Close the data-to-draft chain.\
\
Build order:\
1. **Segment extraction:**\
   - `services/segment_service.py` -- Extract segments from normalized docs\
   - Content analysis and topic tagging\
2. **Section bucket building:**\
   - `services/section_bucket_service.py` -- Deterministic routing\
   - Gap report generation\
3. **Blueprint-guided drafting:**\
   - `services/section_writer_service.py` -- Writer agents\
   - Provenance tag embedding\
   - Blueprint constraint enforcement\
4. **Orchestrator MVP:**\
   - `services/orchestrator_service.py` -- Phase sequencing, batch dispatch, status reporting\
\
**Deliverable:** `build-buckets -> write-drafts -> status` flow works. Drafts have provenance tags and follow blueprint specifications.\
\
### Phase III: Review & Verification (Weeks 7-9)\
\
**Goal:** Close the draft-to-verified chain.\
\
Build order:\
1. **Internal fact-check:**\
   - `services/review_report_service.py` -- Deterministic review\
   - Number verification, provenance validation\
2. **Framework review:**\
   - `services/framework_review_service.py` -- Disclosure completeness check\
3. **External validation:**\
   - `services/external_fact_check_service.py` -- Claim flagging\
4. **Review issue lifecycle:**\
   - Issue creation, assignment, resolution tracking\
   - State machine integration (drafted -> review_issue_open -> needs_redraft -> drafted)\
\
**Deliverable:** Three-layer review produces actionable findings. Review-to-redraft loop works.\
\
### Phase IV: Finalization & Evidence Pack (Weeks 10-11)\
\
**Goal:** Close the verified-to-delivered chain.\
\
Build order:\
1. **Editorial workflow:**\
   - Tone harmonization, cross-section consistency\
   - Final assembly, appendix generation\
2. **Evidence pack:**\
   - `services/provenance_index_service.py`\
   - `services/evidence_pack_service.py`\
   - Integrity check\
3. **Export:**\
   - Markdown to DOCX export\
\
**Deliverable:** Complete end-to-end flow from raw files to evidence pack.\
\
### Phase V: Multi-Project & Polish (Weeks 12-14)\
\
**Goal:** Production readiness for real client projects.\
\
Build order:\
1. **Portfolio management:**\
   - Multi-project topology\
   - Shared asset propagation\
   - Cross-company segment splitting\
2. **Dashboard and UX:**\
   - Terminal dashboard\
   - Natural language status reports\
   - Improved error messages\
3. **Agent budget management:**\
   - Token tracking per agent\
   - Cost reporting\
4. **Testing:**\
   - Port relevant patterns from the predecessor's 958-test suite\
   - Integration tests for end-to-end flows\
   - Property-based tests for state machine transitions\
\
---\
\
## Key Architectural Decisions Summary\
\
1. **File-based workspace over database:** All state lives in JSON files in a project directory. This makes the system debuggable, portable, and auditable without any infrastructure dependency.\
\
2. **Contract-first, still:** Pydantic models define every artifact shape before any service code is written. The predecessor proved this works.\
\
3. **Writing blueprint as a gate:** No drafting without an approved writing blueprint. This is the single biggest improvement over the predecessor.\
\
4. **Deterministic-first routing:** Rules handle 95% of segment-to-section routing. The predecessor's 100+ routing aliases and topic-signature systems are carried forward.\
\
5. **Three-layer review, always separated:** Internal fact-check, framework review, and external validation are independent agents producing independent reports. Never combine them.\
\
6. **Provenance is not optional:** Every sentence in the final report must trace back to source evidence. This is enforced by structure (provenance tags), not by policy.\
\
7. **Control over automation:** The system proposes, the human decides. Gates at every phase transition. Manual sections are explicitly marked and never auto-drafted.\
\
8. **Multi-project from day one in the data model:** Even if Phase V implementation is deferred, the portfolio/project/output ID system supports multi-project from the start.\
\
---\
\
### Critical Files for Implementation\
\
- `/Users/lj_homemac/tools/esgreport_writing/app/core/states.py` -- The state machine definitions to carry forward (proven by 958 tests)\
- `/Users/lj_homemac/tools/esgreport_writing/app/core/ids.py` -- The global ID system to carry forward\
- `/Users/lj_homemac/tools/esgreport_writing/app/models/section_flexibility_matrix.py` -- The rigid/flex/manual pattern that the new writing blueprint extends\
- `/Users/lj_homemac/tools/esgreport_writing/esg_multi_agent_system_design_v_1.md` -- The v1.5 design contract (sections 3-7 on multi-project, state machines, schema governance, provenance)\
- `/Users/lj_homemac/tools/esgreport_writing/WHOLE_FLOW_EXECUTION_PLAN.md` -- The spine analysis identifying where the predecessor's chains break (the exact problems this new architecture must solve)\
}