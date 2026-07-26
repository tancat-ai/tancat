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
