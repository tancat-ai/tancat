# Phase 1 — Multi-Agent Architecture (LangGraph)

**Created:** 2026-07-26
**Status:** Spec
**Depends on:** Phase 5 Eval Harness (shipped), Phase 3 RAG (shipped), `src/llm_providers/` (shipped)
**Blocks:** AI-034 (Test Table & Pre-Flight)

---

## 1. What This Is

Transform the single-orchestrator pipeline (`TestOrchestrator` → `PlaceholderOrchestrator` → `LLMClient`) into a LangGraph-based multi-agent system with three specialised agents, each configurable with its own model/provider.

Current architecture:

```
User story → TestOrchestrator → [scrape → resolve → generate → postprocess] → test file
                                  └── single LLMClient for everything
```

Target architecture:

```
User story → Ingestion Agent ──→ QA Director ──→ Script Synthesizer ──→ test file
                │                    │                  │
                │ analyses story     │ routes criteria  │ generates code
                │ extracts context   │ to correct agent │ per condition
                │ retrieves RAG      │ assigns priority │ resolves placeholders
                │                    │                  │
                └─ RAG store ────────┴──────────────────┘
                
Each agent: configurable model/provider via env vars or model_config.json
```

---

## 2. Why

**Not about model selection.** Our `src/llm_providers/` already handles swapping models at runtime. This is about:

1. **Separation of concerns** — Ingestion, planning, and generation are distinct reasoning tasks. A single prompt doing all three produces mediocrity at each. Three focused agents with task-specific prompts produce better output.

2. **Cost governance** — Different tasks need different model sizes. Ingestion (text analysis) can use a cheap 3B-active model. Script synthesis (code generation) needs a strong 30B+ model. Splitting agents lets us route work to the right-sized model.

3. **Resilience** — If one agent's model goes down, the others keep working. Fallback chains per agent, not one global fallback.

4. **Human-in-the-loop** — LangGraph's checkpointing lets us pause after QA Director planning, show the test plan to the tester, then resume. Impossible with the current linear pipeline.

5. **Eval gating** — Each agent's output is independently measurable. We can benchmark Ingestion accuracy, Director routing quality, and Synthesizer code correctness separately.

---

## 3. Agent Roles

### 3.1 Ingestion Agent

**Input:** Raw user story text (free-form, Gherkin, Jira AC bullets, numbered criteria)
**Output:** Structured `StoryAnalysis` with extracted business rules, boundary values, assumptions, and enriched context from RAG

**Model profile:** Lightweight. Text analysis and RAG retrieval. 3-8B active parameters sufficient.
**Why:** This is the cheapest operation — reading text and matching patterns. The existing `SpecAnalyzer` already does much of this deterministically; the LLM adds semantic understanding for unstructured input.

**Contract:**
```python
@dataclass
class StoryAnalysis:
    story_text: str
    criteria: list[Criterion]       # extracted + enriched
    domain_terms: list[str]          # from RAG retrieval
    assumptions: list[str]           # inferred gaps
    boundary_values: list[Boundary]  # numeric/date boundaries
    source_format: str               # "gherkin" | "jira" | "free-form" | "numbered"
```

**RAG integration:** Queries the vector store for domain-specific patterns (e.g., insurance terms from ingested PDFs, Playwright best practices). Augments the story analysis, not the user input.

### 3.2 QA Director

**Input:** `StoryAnalysis` from Ingestion Agent
**Output:** `TestPlan` — a list of test conditions with assigned priority, type, and routing

**Model profile:** Medium. Reasoning and classification. 8-30B parameters.
**Why:** Needs to reason about test coverage, spot ambiguities, and decide which conditions need human clarification vs. which can go straight to generation. This is a planning task — benefits from strong reasoning but doesn't need code-generation ability.

**Contract:**
```python
@dataclass
class TestCondition:
    ref: str                        # "TC01.03"
    description: str                # human-readable
    condition_type: ConditionType   # happy_path | boundary | negative | exploratory | ambiguity
    priority: Priority              # high | medium | low
    source_criterion: str           # which criterion from StoryAnalysis spawned this
    needs_clarification: bool       # True → pause for human
    clarification_question: str     # shown to tester if needs_clarification
    prerequisite_refs: list[str]    # TC refs that must run before this one
```

**Human-in-the-loop checkpoint:** After the QA Director produces the TestPlan, the graph pauses. The tester reviews conditions, edits/removes/adds, and confirms. Then the graph resumes with the Script Synthesizer.

### 3.3 Script Synthesizer

**Input:** `TestPlan` (confirmed), scraped page data, RAG golden patterns
**Output:** Pytest test file with resolved placeholders and evidence tracking

**Model profile:** Heavy. Code generation. 30B+ parameters or cloud API.
**Why:** This is the hardest task — generating correct, runnable Python test code with proper Playwright selectors. Benefits from the strongest available model.

**Contract:**
```python
@dataclass
class SynthesisResult:
    test_code: str                  # complete pytest file
    pom_classes: list[PomClass]     # if POM mode
    unresolved_placeholders: list[str]  # for pre-flight reporting (AI-034)
    evidence_hooks: bool            # evidence_tracker integrated
    syntax_valid: bool              # passes ast.parse()
```

---

## 4. LangGraph Graph Design

```
START
  │
  ▼
[Ingestion Agent]
  │  StoryAnalysis
  ▼
[QA Director]
  │  TestPlan
  ▼
[Human Checkpoint]  ←── graph pauses, tester reviews TestPlan
  │  confirmed TestPlan
  ▼
[Script Synthesizer]
  │  per-condition
  ▼
[Code Postprocessor]
  │  final test file
  ▼
END
```

**State object** (flows through all nodes):
```python
class PipelineState(TypedDict):
    # Input
    user_story: str
    base_url: str
    additional_urls: list[str]
    credential_profile: dict | None
    pom_mode: bool
    
    # Intermediate
    story_analysis: StoryAnalysis | None
    test_plan: list[TestCondition] | None
    plan_confirmed: bool
    scraped_pages: dict[str, list[dict]]
    
    # Output
    test_code: str | None
    pom_classes: list[dict] | None
    unresolved: list[str]
    errors: list[str]
```

**Fallback edges:** If any agent fails:
- Ingestion fails → skip to QA Director with raw story text (existing fallback path)
- QA Director fails → use single-condition `happy_path` plan
- Synthesizer fails → emit `pytest.skip()` with error note, don't crash the graph

---

## 5. Per-Agent Configuration

Agents use the existing `LLMProvider` infrastructure. **Default: one model for everything.** Multi-model is an optional optimization — users who want to route cheap tasks to a small model and code generation to a big one can configure that, but they don't have to.

**Default config** (single model — works out of the box):

```json
{
  "agents": {
    "default": {
      "provider": "auto",
      "model": "auto"
    }
  }
}
```

With `"auto"`, the system uses `auto_detect_provider()` and whatever model that provider exposes. All three agents share the same model. This is the zero-config path — same as today.

**Optimised config** (multi-model — optional):

```json
{
  "agents": {
    "ingestion": {
      "provider": "ollama",
      "model": "qwen3.6:3b",
      "timeout": 60
    },
    "qa_director": {
      "provider": "lm-studio",
      "model": "gemma-4-26b-it",
      "timeout": 120
    },
    "script_synthesizer": {
      "provider": "openai-local",
      "model": "gemma-4-31b-it",
      "timeout": 300
    }
  },
  "fallback": {
    "provider": "auto",
    "model": "auto"
  }
}
```

**Resolution order per agent:**
1. Agent-specific config (e.g. `agents.ingestion.provider`)
2. `agents.default`
3. `auto_detect_provider()` (probing localhost ports)
4. `fallback` config

**Model-agnostic guarantee:** Any model from any provider that implements `LLMProvider.complete()` can be assigned to any agent. The framework validates output schemas, not which model produced them.

---

## 6. What Doesn't Change

| Component | Status |
|---|---|
| `src/scraper.py` (PageScraper) | Unchanged — scraping is pre-agent, runs before the graph |
| `src/placeholder_resolver.py` | Unchanged — called by Script Synthesizer as a tool |
| `src/placeholder_orchestrator.py` | Refactored into a tool the Synthesizer calls, not an orchestrator |
| `src/placeholder_scorers.py` | Unchanged — scoring functions are pure, work in any context |
| `src/element_matcher.py` | Unchanged |
| `src/code_postprocessor.py` | Unchanged — runs after Synthesizer |
| `src/evidence_tracker.py` | Unchanged — injected into generated code, not the graph |
| `src/llm_providers/` | Unchanged — already supports per-call model selection |
| `src/rag_store.py` / `src/rag_retriever.py` | Unchanged — called by Ingestion Agent |

---

## 7. Implementation Phases

### Phase 1a — Graph scaffold (0.5 sessions)
- `src/agents/graph.py` — LangGraph `StateGraph` definition
- `src/agents/state.py` — `PipelineState` TypedDict
- `pytest` fixture that builds the graph with mock agents
- No real agent logic yet — just graph structure + state flow

### Phase 1b — Agent contracts (0.5 sessions)
- `src/agents/ingestion.py` — `IngestionAgent` class, prompt template, output parser
- `src/agents/director.py` — `QADirectorAgent` class, prompt template, output parser
- `src/agents/synthesizer.py` — `ScriptSynthesizerAgent` class, prompt template, output parser
- Each agent: `async def run(state: PipelineState) -> PipelineState`
- Unit tests for each agent's output schema validation

### Phase 1c — Wiring (1 session)
- Replace `TestOrchestrator.run_pipeline()` with graph execution
- Per-agent model configuration loading
- Fallback chain implementation
- Streamlit UI: human-in-the-loop checkpoint (TestPlan review panel)
- CLI: `--model-config` flag for `model_config.json` path

### Phase 1d — Eval validation (0.5 sessions)
- Run eval harness against multi-agent pipeline
- Compare accuracy vs. single-orchestrator baseline
- Must not regress on any site (gate: ≥88.1% static accuracy)

### Phase 1e — Cleanup (0.5 sessions)
- Remove dead code: old `TestOrchestrator` paths superseded by graph
- Update `AGENTS.md` protected files list
- Update `docs/ARCHITECTURE.md`

**Total: 3 sessions** (was 4-5 in the roadmap — scope narrowed by reusing existing providers/scrapers/resolvers)

---

## 8. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| LangGraph adds overhead for simple stories | Single-condition fallback path (Phase 1b) — bypasses graph, calls Synthesizer directly |
| Per-agent prompts need tuning | Eval harness gates every change. Can't ship prompt change that regresses accuracy |
| Graph state gets too large | State is TypedDict with clear boundaries. No unbounded accumulation. Serde via JSON for checkpointing |
| Human checkpoint blocks automation | CLI mode skips checkpoint (`--auto-confirm`). Streamlit mode shows the panel |

---

## 9. Document-Driven Input Mode

### 9.1 What This Is

An alternative input path where the pipeline ingests **specification documents** (PDFs, Word docs, Confluence pages, change logs) instead of free-form user stories. The graph extracts structured change deltas, routes analysis by persona role, generates impact-aware test plans, and produces a consolidated report — all within the same `PipelineGraph` framework.

This is **not a separate pipeline**. It extends the existing graph with richer state, an optional parsing front-end node, and persona-aware routing in the QA Director. The text-mode path (`user_story: str`) continues to work unchanged — document mode is additive.

**Use case:** A QA lead receives a 40-page PRD. Instead of manually extracting "what changed" and writing test cases, they drop the PDF into the tool. The pipeline:
1. Parses the PDF into structured Markdown
2. Extracts change deltas (new features, modified schemas, unchanged systems)
3. Routes analysis based on role (QA gets test plans; PM gets business logic validation; Ops gets deployment impact)
4. Generates an impact map showing what's affected and what needs regression testing
5. Produces a consolidated report with HITL checkpoint for review and refinement

### 9.2 State Schema Additions

`PipelineState` gains these fields (all optional — empty in text mode):

```python
@dataclass
class ChangeDelta:
    """A single change extracted from a spec document."""
    category: str          # "new_feature" | "modified" | "removed" | "unchanged"
    name: str              # human-readable name
    description: str       # what changed and why
    affected_systems: list[str]  # downstream systems impacted
    data_schema_changes: list[DataSchemaChange]

@dataclass
class DataSchemaChange:
    field: str             # e.g. "customer_id"
    change_type: str       # "NEW" | "MODIFIED" | "REMOVED"
    old_value: str         # e.g. "VARCHAR(8)"
    new_value: str         # e.g. "VARCHAR(10)"
    migration_notes: str   # breaking change? rollback plan?

@dataclass
class ImpactMap:
    """Cross-reference of changes to affected test areas."""
    change_ref: str               # which ChangeDelta this maps to
    impact_radius: list[str]       # systems/modules in blast radius
    regression_areas: list[str]    # unchanged systems needing sanity checks
    test_scenarios: list[str]      # concrete test ideas
    risk_level: str                # "high" | "medium" | "low"

@dataclass
class ConsolidatedReport:
    """Final output of the document-driven pipeline."""
    executive_summary: str
    change_summary: list[ChangeDelta]
    impact_maps: list[ImpactMap]
    test_plan: list[TestCondition]
    generated_tests: str           # pytest code
    unresolved_items: list[str]    # questions for the human
```

PipelineState additions:

```python
# ── Document Input (all optional, empty in text mode) ──
input_mode: str = "text"                # "text" | "document"
raw_document_text: str = ""             # parsed PDF/Markdown content
document_source: str = ""               # original filename
change_deltas: list[ChangeDelta] = field(default_factory=list)
persona_role: str = ""                  # "qa_lead" | "product_owner" | "developer" | "operations"
impact_maps: list[ImpactMap] = field(default_factory=list)
consolidated_report: ConsolidatedReport | None = None
```

### 9.3 Parsing Front-End

Document mode starts with a parsing step before the graph's `ingest` node. This is a **pre-processing node** — it converts the uploaded document into structured text that the Ingestion Agent can consume.

**Strategy: phased adoption.**

| Phase | Engine | Strengths | Limits |
|---|---|---|---|
| **Now** (AI-030 shipped) | `src/pdf_ingest.py` — PyMuPDF | Heading detection, table extraction as Markdown, chunking. Already wired into `rag_ingest.py`. Zero new dependencies. | No multi-column layout awareness. Table detection quality varies by PDF. |
| **Upgrade path** | Unlimited OCR (arXiv:2606.23050) | Constant KV cache → dozens of pages in one 32K forward pass. R-SWA attention for long-document copying tasks. Open-source (Baidu, Apache 2.0). | Requires GPU infrastructure. June 2026 release — limited community, possible rough edges. |

**Decision:** Start with PyMuPDF (already in the project). The unlimited-OCR paper is a compelling upgrade path but blocked on GPU infra. When GPU becomes available, swap the parsing node's engine — the downstream graph nodes are engine-agnostic (they consume `raw_document_text: str`, not PDF bytes).

**Parsing node contract:**

```python
async def _parse_document(state: PipelineState) -> dict[str, Any]:
    """Pre-processing node: PDF/Markdown → structured text.
    
    Only runs when input_mode == "document".
    Calls src/pdf_ingest.ingest_pdf() or equivalent.
    """
    if state.input_mode != "document" or not state.document_source:
        return {}  # skip — text mode
    
    chunks = ingest_pdf(Path(state.document_source))
    raw_text = "\n\n".join(chunk.text for chunk in chunks)
    
    return {
        "raw_document_text": raw_text,
        # Forward original user_story for the existing IngestionAgent path
        "user_story": raw_text[:500],  # summary for backward compat
    }
```

### 9.4 Extended Graph Design

Document mode extends the existing graph with a pre-processing node and an impact-mapping node. The core three-agent flow is unchanged:

```
                          ┌─ text mode: skip ──────────────────────────┐
                          │                                             │
START ──→ [Parse Document] ──→ [Ingestion Agent] ──→ [QA Director] ──→ [Human Checkpoint]
              │                      │                      │                      │
              │ PDF→Markdown         │ StoryAnalysis        │ TestPlan +          │ confirmed
              │ (PyMuPDF /           │ + ChangeDeltas       │ Persona Route       │ TestPlan
              │  Unlimited OCR)      │                      │                      │
              │                      │                      │              ┌───────┘
              │                      │                      │              ▼
              │                      │                      │       [Impact Mapper]
              │                      │                      │              │
              │                      │                      │              │ ImpactMap
              │                      │                      │              │ per change
              │                      │                      │       ┌──────┘
              │                      │                      │       ▼
              │                      │                      └──→ [Script Synthesizer]
              │                                                       │
              │                                                       │ test_code
              │                                                       ▼
              │                                                [Code Postprocessor]
              │                                                       │
              │                                                       ▼
              └────────────────────────────────────────────────→ [Consolidated Report]
                                                                      │
                                                                      ▼
                                                                     END
```

**New nodes:**

| Node | Runs in | What it does |
|---|---|---|
| `parse_document` | document mode only | PDF/Markdown → `raw_document_text` via PyMuPDF (now) or Unlimited OCR (future) |
| `impact_map` | document mode only | Cross-references `ChangeDelta`s against `persona_role` → `ImpactMap` per change |
| `consolidated_report` | document mode only | Aggregates all outputs into a `ConsolidatedReport` struct for export |

**Modified nodes:**

| Node | Change |
|---|---|
| `ingest` | When `input_mode == "document"`, passes `raw_document_text` through `SpecAnalyzer` **plus** runs change-delta extraction (LLM call: "extract new features, modified schemas, unchanged systems from the following spec text"). Outputs both `StoryAnalysis` and `change_deltas`. |
| `plan` (QA Director) | When `persona_role` is set, routes conditions with role-specific annotations. QA Lead: adds boundary/regression checks. Product Owner: adds business logic validation. Developer: adds API contract tests. Operations: adds deployment/migration checks. Uses LangGraph conditional edges with role-based routing keys. |
| `synthesize` | When `impact_maps` are present, the prompt includes impact context: "Field X changed from 8 to 10 digits — generate tests that verify the ingestion pipeline handles the new format." |

**Unchanged nodes:** `postprocess` (syntax validation, evidence stripping — same logic regardless of input mode).

### 9.5 Persona Routing

The QA Director's `_after_qa_director()` conditional edge already supports routing (`auto_confirm`/`plan_confirmed`). Document mode adds persona-aware routing within the `plan` node itself:

```python
def _route_by_persona(state: PipelineState) -> str:
    """Route the plan node's output based on persona role."""
    if not state.persona_role:
        return "default"  # standard test generation
    
    routes = {
        "qa_lead": "impact_map",        # QA → impact analysis → test generation
        "product_owner": "report",       # PM → business logic validation → report
        "developer": "synthesize",       # Dev → skip impact, straight to code
        "operations": "impact_map",      # Ops → impact analysis (deployment focus)
    }
    return routes.get(state.persona_role, "default")
```

All personas converge on the `ConsolidatedReport` node, which tailors the output format by role.

### 9.6 Relationship to AI-030

AI-030 (shipped) built:
- `src/pdf_ingest.py` — PyMuPDF extraction pipeline
- RAG corpus of LV Insurance PDFs (7 docs, 66 chunks)
- `rag_ingest.py --pdfs` CLI flag

**How document mode builds on it:**

| AI-030 capability | Document mode usage |
|---|---|
| `ingest_pdf()` → `list[DocChunk]` | Used directly in `_parse_document()` node |
| Heading detection + table extraction | Feeds structured text into change-delta extraction |
| RAG store populated with domain PDFs | IngestionAgent queries RAG for domain context during change analysis |
| PyMuPDF dependency | Already installed — zero new dependencies for Phase 1 |

**What's new vs. AI-030:**

| AI-030 | Document mode |
|---|---|
| PDF → vector chunks (RAG) | PDF → structured state (graph pipeline) |
| Improves resolver accuracy | Generates test plans from specs |
| Background ingestion | Interactive user workflow |
| Output: better placeholder resolution | Output: test plan + impact map + generated tests |

### 9.7 Implementation Phases (Document Mode Extension)

These phases are additive to the existing Phase 1a-1e plan. They can run in parallel with or after the core Phase 1 work.

#### Phase 1f — State schema + parsing node (0.5 sessions)
- Add `ChangeDelta`, `DataSchemaChange`, `ImpactMap`, `ConsolidatedReport` dataclasses to `src/agents/pipeline_state.py`
- Add document-mode fields to `PipelineState`
- Implement `_parse_document()` node in `src/agents/pipeline_graph.py` (calls `src/pdf_ingest.ingest_pdf()`)
- Conditional edge: skip `parse_document` when `input_mode == "text"`
- Unit tests: `test_pipeline_graph_document_mode.py`

#### Phase 1g — Change delta extraction (0.5 sessions)
- Extend `IngestionAgent` with `_extract_change_deltas()` method
- LLM prompt: "Given this spec document, extract: new features, modified systems, unchanged systems, data schema changes"
- Output parser: LLM structured output → `list[ChangeDelta]`
- Fallback: if LLM fails, extract headings as feature names (deterministic)
- Unit tests: `test_ingestion_document_mode.py`

#### Phase 1h — Persona routing + impact mapping (1 session)
- Add `persona_role` routing to `QADirectorAgent`
- Implement `ImpactMapper` agent: `ChangeDelta` + `persona_role` → `ImpactMap`
- Add `impact_map` node to `PipelineGraph`
- Implement `_build_consolidated_report()` postprocessor node
- Add persona selector to Streamlit UI sidebar
- CLI: `--persona qa_lead|product_owner|developer|operations`
- Unit tests: `test_director_persona_routing.py`, `test_impact_mapper.py`

#### Phase 1i — Unlimited OCR integration (0.5 sessions, blocked on GPU infra)
- Add `UnlimitedOCRParser` adapter class implementing the same interface as `src/pdf_ingest.ingest_pdf()`
- Feature flag: `PARSER_ENGINE=unlimited-ocr` (default: `pymupdf`)
- A/B comparison harness: same PDF → both engines → diff report
- Decision gate: if Unlimited OCR quality ≥ PyMuPDF, make it the default for documents >10 pages

#### Phase 1j — Eval validation (0.5 sessions)
- Create eval dataset: 3 spec documents (PRD, change log, Jira export) → golden test plans
- Run eval harness in document mode vs. text mode (same document, user story extracted manually)
- Gate: document mode must produce ≥90% of the test conditions that a human would extract

**Document mode total: 3 sessions** (plus 0.5 for Unlimited OCR when GPU available)

### 9.8 Document Mode Risks

| Risk | Mitigation |
|---|---|
| PDF layout complexity (multi-column, scanned docs) | PyMuPDF handles most layouts. Image-only pages logged as warnings, skipped. Unlimited OCR as upgrade path for complex docs. |
| Change delta extraction hallucinates features | Structured output parser validates against document text. Flagged discrepancies shown at HITL checkpoint. |
| Persona routing scope creep | Roles are predefined (4 roles). Adding a role requires code change — prevents unbounded branching. |
| Large documents (50+ pages) blow up state | Documents chunked before graph ingestion (PyMuPDF already does this). Change delta extraction runs on summary, not full text. |
| Unlimited OCR requires GPU that doesn't exist | Feature-flagged behind `PARSER_ENGINE`. PyMuPDF remains the default. No GPU dependency for the pipeline to work. |
