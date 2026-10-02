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

## Public API Additions

Refreshed 2026-10-02: public symbols present in the source and not listed above.

- `single_condition_warning` (function): `single_condition_warning(spec_text: str, conditions: list[TestCondition]) -> str | None` - B-062 option C: warn when a long story collapses to a single condition. Returns a short user-facing warning so a "one test for a whole page" result is not mistaken for a correct one, or None when no warning is warrant...
- `SpecAnalyzer.__init__` (method of `SpecAnalyzer`): `SpecAnalyzer.__init__(llm_client: LLMClient | None = None) -> None` - Initialize with an LLM client.
- `SpecAnalyzer.analyze` (method of `SpecAnalyzer`): `SpecAnalyzer.analyze(spec_text: str) -> list[TestCondition]` - Analyze spec text and return list of test conditions.
- `MULTI_CONCERN_MIN_CHARS` (constant): `MULTI_CONCERN_MIN_CHARS = 200`
- `MULTI_CONCERN_TEST_VERBS` (constant): `MULTI_CONCERN_TEST_VERBS = ('check', 'verify', 'should', 'shows', 'links', 'can be')`
- `NUMBERED_LIST_BREAK_STREAK` (constant): `NUMBERED_LIST_BREAK_STREAK = 3`


## How It Works (Internals)

Private `_`-helpers - the module's real logic (10 items). Grouped under the public function that calls them.

### `SpecAnalyzer.analyze(spec_text: str) -> list[TestCondition]` - method of `SpecAnalyzer`

- `_has_multi_concern_signal(text: str) -> bool` (method of `SpecAnalyzer`): Return True when the text hints at multiple distinct test concerns.
- `_conservative_sentence_split(text: str) -> list[str] | None` (method of `SpecAnalyzer`): Split a single-blob requirement into distinct concern sentences. Conservative by design: splits on sentence boundaries only (never mid-sentence commas), so narrative journeys stay whole. Returns None when the text is...
- `_fallback_conditions(sentences: list[str]) -> list[TestCondition]` (method of `SpecAnalyzer`): Build conditions from a conservative sentence split.
- `_extract_numbered_criteria(spec_text: str) -> tuple[list[str], str]` (method of `SpecAnalyzer`): Extract numbered acceptance criteria lines from spec_text. Returns (items, source) where source is "numbered" (explicit list), "unstructured" (split from vague input), or "none" (no items found).
- `_parse_response(response: str) -> list[TestCondition]` (method of `SpecAnalyzer`): Parse LLM JSON response into TestCondition objects.

### Internal utilities

- `_extract_json_array_text(raw: str) -> str` (method of `SpecAnalyzer`): Return the best-effort JSON array substring from the LLM response.
- `_repair_common_json_issues(text: str) -> str` (method of `SpecAnalyzer`): Attempt to repair common JSON mistakes from LLM output. Repairs: - Trailing commas before } or ] - Unquoted object keys: { id: "TC01" } -> { "id": "TC01" } - Single quotes in simple cases - Raw newlines inside quoted...
- `_escape_newlines_inside_strings(text: str) -> str` (method of `SpecAnalyzer`): Escape newlines inside strings; returns str.
- `_normalise_intent(raw_intent: Any, text: str) -> ConditionIntent` (method of `SpecAnalyzer`): Return a validated condition intent, falling back to heuristic inference.
- `_try_parse_objects_from_array(array_text: str) -> list[TestCondition]` (method of `SpecAnalyzer`): Best-effort parse when the overall JSON array is malformed. Extract '{...}' blocks and parse them individually.
