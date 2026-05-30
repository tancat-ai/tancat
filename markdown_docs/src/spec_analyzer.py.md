# spec_analyzer.py

## Purpose
Derives `TestCondition` objects from a test specification by analyzing feature specs. Supports two modes: deterministic parsing of explicit numbered acceptance criteria, and LLM-driven spec analysis for free-form specifications.

## Location
`src/spec_analyzer.py`

## Dependencies
- `src.llm_client` — LLMClient for spec analysis when no explicit criteria exist

## Module Constants
- `ConditionType` — Literal type: `"happy_path" | "boundary" | "negative" | "exploratory" | "regression" | "ambiguity"`
- `ConditionSrc` — Literal type: `"ai" | "manual" | "automation"`
- `ConditionIntent` — Literal type: `"element_presence" | "element_behavior" | "state_assertion" | "journey_step" | "journey_outcome"`

## Public API

### `infer_condition_intent(text: str) -> ConditionIntent`
Heuristic function that infers the best-fit intent category from condition text using keyword phrase matching. Priority order: journey_step phrases → journey_outcome phrases → state_assertion phrases → element_presence → element_behavior → defaults to journey_step.

### `TestCondition` (dataclass)
A single verifiable condition derived from spec analysis.
- `id: str` — Unique identifier (e.g., "BC01.02")
- `type: ConditionType` — Category of condition
- `text: str` — Plain English description
- `expected: str` — Expected result
- `source: str` — Spec clause that drove this condition
- `flagged: bool` — True if type is "ambiguity"
- `src: ConditionSrc` — Origin ("ai", "manual", "automation")
- `intent: ConditionIntent` — Inferred intent category
- `to_dict() -> dict` — Returns dict representation

### `SpecAnalyzer.__init__(llm_client: LLMClient | None = None)`
Initialize with an LLM client (creates default if not provided).

### `SpecAnalyzer.analyze(spec_text: str) -> list[TestCondition]`
Analyze spec text and return list of test conditions. Prefers deterministic parsing of explicit numbered acceptance criteria over LLM analysis. Falls back to LLM-driven analysis for free-form specs.

### `SpecAnalyzer._extract_numbered_criteria(spec_text: str) -> list[str]`
Extract numbered acceptance criteria lines from spec text. Handles common headings ("## Acceptance Criteria", "Acceptance Criteria:") and parses `N. criterion` format.

## Design Notes
- Two-mode design: explicit criteria → deterministic mapping, free-form spec → LLM analysis
- LLM output parsing includes JSON repair for common mistakes (trailing commas, unquoted keys, single quotes, raw newlines)
- Fallback parsing extracts individual `{...}` objects when the overall JSON array is malformed
- `__test__ = False` on TestCondition prevents pytest from collecting it as a test
- System prompt enforces strict JSON output with no markdown fences

## Related Files
- `src/test_plan.py` — consumes TestCondition objects for test planning
- `src/llm_client.py` — LLM interface used for spec analysis
- `src/orchestrator.py` — orchestrator may use spec analysis results