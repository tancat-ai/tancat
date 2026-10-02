# `src/verification_strength.py`

## Purpose

B-100: what each generated test proved, decided where the resolver knows it. The eval harness (B-093 gate 2) has to *infer* verification strength from the emitted code alone, because that is all it sees. The emitter k...

## Module Metadata

- **Lines:** ~225
- **Imports:** `__future__.annotations`, `collections.abc.Mapping`, `collections.abc.Sequence`, `dataclasses.dataclass`, `src.pipeline_models.TestJourney`, `src.pipeline_models.TestResolutionCounts`, `src.pipeline_models.TestVerificationVerdict`, `src.pipeline_models.VerificationStatus`

## Classes

| Class | Description |
|-------|-------------|
| `ResolvedAssertion` | One ASSERT placeholder and what the emitter wrote for it. resolved_value is the emitted expression (a selector, a to_have_url call, or a skip), ass... |

## Functions

| Function | Description |
|----------|-------------|
| `is_global_container(locator: str) -> bool` | True when a locator targets a page-level container (B-093 gate 2). body, main, #content and friends pass on any page of a broken app, so an asser... |
| `ResolvedAssertion.is_skip() -> bool` | True when the emitted replacement is a pytest.skip (no check). |
| `ResolvedAssertion.is_page_arrival() -> bool` | True when the check proves arrival at a page (a URL assertion). |
| `ResolvedAssertion.is_global_container_check() -> bool` | True when the emitted check targets a page-level container. The page-level families (count/document/section) are real structural checks and are exempt -- onl... |
| `ResolvedAssertion.is_element_check() -> bool` | True when the emitter wrote a real check against a specific element. |
| `compute_test_verification_verdicts(journeys: Sequence[TestJourney], assertions_by_test: Mapping[str, Sequence[ResolvedAssertion]], unresolved_descriptions: Mapping[str, Sequence[str]], counts_by_test: Mapping[str, TestResolutionCounts]) -> list[TestVerificationVerdict]` | Return one verdict per journey, in journey order. Args: journeys: Parsed test functions, one per criterion. assertions_by_test: Test name -> resolved ASSERT... |

## How It Works (Internals)

Private `_`-helpers - the module's real logic (1 item). Grouped under the public function that calls them.

### `compute_test_verification_verdicts(journeys: Sequence[TestJourney], assertions_by_test: Mapping[str, Sequence[ResolvedAssertion]], unresolved_descriptions: Mapping[str, Sequence[str]], counts_by_test: Mapping[str, TestResolutionCounts]) -> list[TestVerificationVerdict]` - function

- `_unresolved_reason(descriptions: Sequence[str], unresolved: int, total: int) -> str` (function): Name the unresolved placeholders and the count -- never return silence.
