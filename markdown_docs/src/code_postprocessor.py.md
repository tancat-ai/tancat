# `src/code_postprocessor.py`

## High-Level Purpose

Orchestrates pure code-string transformations by delegating to specialized sub-modules. Acts as the main pipeline entry point for post-processing LLM-generated test code, applying a cascade of deterministic fixes to common skeleton-generation mistakes.

## Module Metadata

- **Lines:** 438
- **Imports:** `re`, `src.code_normalizer`, `src.llm_reasoning_filter`

## Functions

### `normalise_generated_code(code: str, consent_mode: str = "auto-dismiss", target_url: str = "") -> str`
**Main pipeline function.** Applies transformations in this order:
1. Strip LLM reasoning text (`strip_llm_reasoning`)
2. Convert standalone placeholders (`convert_standalone_placeholders`)
3. Fix malformed `@pytest.mark.evidence` decorators
4. Inject `import pytest` and `from playwright.sync_api` when needed
5. Replace hallucinated `evidence_launcher` → `evidence_tracker`
6. Ensure `evidence_tracker` fixture on all test functions (`_ensure_evidence_tracker_fixture`)
7. Rewrite `page.goto(` → `evidence_tracker.navigate(`
8. Fix hallucinated marker syntax, constructor names, invalid kwargs
9. Strip invalid decorator assignments
10. Fix type hint typos (Plan/Payable/Note → Page)
11. Inject consent helper when `consent_mode == "auto-dismiss"`
12. Rewrite `page.` → `self.page.` in class methods
13. Strip hallucinated `record_condition(...)` calls
14. Fix misplaced parentheses in evidence_tracker calls
15. Ensure test navigation (`ensure_test_navigation`)
16. Fix module-scope indentation (`fix_module_scope_indentation`)
17. Replace unresolved placeholders with `pytest.skip()` (`replace_remaining_placeholders`)
18. Strip `# PAGES_NEEDED:` block (`strip_pages_needed_block`)
19. Dedent indented test blocks (`dedent_indented_test_blocks`)
20. Fix indentation (`fix_indentation`)
21. Deduplicate skip calls (`deduplicate_skip_calls`)
22. Replace bare ellipsis (`replace_bare_ellipsis`)

### `replace_token_in_line(line, action, token, resolved_value, duplicate_selectors, description, fill_value) -> str`
Replaces a single `{{ACTION:description}}` placeholder token within a code line. Handles CLICK, ASSERT, FILL, GOTO, and URL action types by wrapping resolved selectors in appropriate `evidence_tracker.*` calls.

### `flatten_inner_functions(code: str) -> str`
Removes nested `def inner():` style wrappers and moves their decorators up to the parent test function.

### `inject_import(code: str, import_line: str) -> str`
Inserts an import at the top of the generated file, after `from __future__` lines.

### `rewrite_page_references_in_class_methods(code: str) -> str`
Replaces bare `page.` → `self.page.` and `evidence_tracker.` → `self.evidence_tracker.` inside class instance methods.

## Private Helpers

| Function | Purpose |
|----------|---------|
| `_ensure_evidence_tracker_fixture(code)` | Adds `evidence_tracker` fixture argument to tests that use it |
| `_inject_consent_helper(code)` | Injects `dismiss_consent_overlays` import and calls after navigation |

## Key Design Decisions
- **Cascade pattern** — `normalise_generated_code` applies transforms sequentially; each function receives output of the previous
- **Hallucination guardrails** — targets known LLM failure modes: wrong fixture names, hallucinated methods, type hint typos
- **Delegation** — all heavy lifting delegated to `code_normalizer` and `llm_reasoning_filter`; this module orchestrates order

## Dependencies
- `src.code_normalizer` — all normalization transforms
- `src.llm_reasoning_filter` — LLM reasoning text detection/stripping