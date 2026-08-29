# AI-059 Session 2 — Resolver Usage-Trace Handoff

**Date:** 2026-08-27
**Branch / commit:** `main` @ `f2f0b60` (`feat(ai-059): learning-impact isolation harness — sentinel identity + controlled baseline`)
**Status:** Deliverable 1 shipped. Deliverable 2 (this doc's subject) reverted to a clean checkpoint and handed to a fresh context.

---

## 1. TL;DR

- **Deliverable 1 (shipped, committed, pushed):** the AI-059 controlled-isolation harness — lab sentinel identity, cold/warm baseline runner, `AI059_DISABLE_AUTO_LEARN` gate, opt-in `rag_diagnostics.jsonl`. This is the "previous changes" the user asked to commit first.
- **Deliverable 2 (in progress, NOT committed):** make RAG *usage* observable. Today we can see patterns are **retrieved** (`rag_diagnostics.jsonl`), but not whether a retrieved pattern was actually **applied** as a scoring bonus to the winning element. Deliverable 2 adds `eligible` / `matched` / `bonus` per retrieved pattern.
- This session's Deliverable-2 edits were started, left the tree **broken** (a failed edit), and were **reverted** so the clean Deliverable-1 state could be committed. This doc + the companion opening prompt continue Deliverable 2 from a fresh context on top of `f2f0b60`.

## 2. Why the working tree was reverted (lesson)

The Deliverable-2 attempt modified three shared files and one failed edit left the tree non-runnable:

- `src/rag_retriever.py` — added `pattern_usage()` + refactored `scoring_bonus_for` to delegate to it.
- `src/placeholder_orchestrator.py` — added `self._write_rag_diagnostic(..., site=site)` (4-arg call) **but the method signature is 3-arg** → `TypeError`; and added `self._write_rag_usage_diagnostic(...)` **with no such method defined** → `AttributeError`.
- `tests/test_learning_impact.py` — added a `test_pattern_usage_*` test + `RAGRetriever` import.

All of the above were reverted. The committed tree (`f2f0b60`) is the clean Deliverable-1 state. **Re-implement Deliverable 2 cleanly on top of `f2f0b60`.**

## 3. Deliverable 2 — design

### Goal
For each placeholder resolution, emit per-retrieved-pattern records answering:
- `eligible` — did the **site gate** pass for this run's site identity?
- `matched` — did the pattern selector hit the **winning element**?
- `bonus` — how many points did it contribute to the winner's score?

### Single source of truth
`PlaceholderScorer` already applies the bonus in `_golden_pattern_bonus` / `_learned_pattern_bonus`. `RAGRetriever.scoring_bonus_for` is a *parallel* implementation of the same gate+match+bonus logic. Add `RAGRetriever.pattern_usage(patterns, site_hash, element_selector) -> list[dict]` that returns **all** per-pattern records (not just the first match), and have `scoring_bonus_for` delegate to it (`for rec in self.pattern_usage(...): if rec["bonus"] > 0: return float(rec["bonus"])`). This keeps the *applied* path (`PlaceholderScorer`) untouched (zero risk) and makes the reported bonus identical to the applied one.

### Logic (mirror of the scorer / `scoring_bonus_for`)
Constants (from `src/placeholder_scorers.py`):
- `PlaceholderScorer.GOLDEN_PATTERN_BONUS = 20`
- `PlaceholderScorer.SAME_SITE_LEARNED_BONUS = 5`

Per pattern:
- golden: `eligible = not (pattern.site_hash and pattern.site_hash != site_hash)` (empty `site_hash` = legacy, site-agnostic → eligible).
- learned: `eligible = bool(site_hash) and pattern.site_hash == site_hash`.
- If eligible and direct selector match (`pattern.selector == element_selector`): `bonus = int(bonus_full * pattern.confidence)`.
- Else if eligible and substring match (`element_selector in pattern.selector or pattern.selector in element_selector`): `bonus = int(bonus_full * 0.5 * pattern.confidence)`.
- `matched` is True iff a bonus was produced.

### Instrumentation points (in `src/placeholder_orchestrator.py`)
1. **Retrieval diagnostic** (existing `_write_rag_diagnostic`, called from `_retrieve_golden_patterns`): keep as-is, OR add an `eligible` field per pattern using `RAGRetriever.pattern_usage(patterns, site, "")` (empty selector → eligibility only, no match/bonus). Passing `site` requires adding a `site` param to the staticmethod (today it has none) — do this carefully so the existing test `test_rag_diagnostics_are_opt_in_and_jsonl` (3-arg call) still passes.
2. **Usage diagnostic** (new, after resolution): in `if matched_element is not None:`, compute `winner_selector = str(matched_element.get("selector", "") or "").strip()` and call `self._rag_retriever.pattern_usage(golden_patterns, site or "", winner_selector)`, then write via a new `_write_rag_usage_diagnostic(action, description, usage)` staticmethod (same opt-in `AI059_RAG_DIAGNOSTICS_PATH`, `try/except` like `_write_rag_diagnostic`).

> **Gotcha — raw vs repr selector:** the scorer compares against the candidate's *raw* `element["selector"]`. The orchestrator emits `repr(robust_selector)` for the test, but for usage matching use `matched_element.get("selector", "")` (the raw candidate selector), NOT the repr'd value.

### Diagnostic output shape
- Retrieval line: `{"action", "description", "results":[{description, selector, action_type, confidence, source, page, site_hash, eligible?}]}`
- Usage line: `{"action", "description", "usage":[{description, source, site_hash, eligible, matched, bonus}]}`

Both append to `AI059_RAG_DIAGNOSTICS_PATH`; correlate by `action` + `description`.

## 4. Files to touch
| File | Change |
|------|--------|
| `src/rag_retriever.py` | add `pattern_usage()`; refactor `scoring_bonus_for` to delegate |
| `src/placeholder_orchestrator.py` | (optional) `eligible` in `_write_rag_diagnostic`; add `_write_rag_usage_diagnostic`; call it after resolution |
| `tests/test_learning_impact.py` | add `test_pattern_usage_reports_eligible_match_and_bonus` (need `from src.rag_retriever import RAGRetriever`) |

## 5. Verification gates (must all pass before commit)
- `python scripts/smoke.py --json`
- `python -m ruff check .` and `ruff format --check .`
- `python -m mypy src/ cli/` (and mypy on staged test files — pre-commit is broader)
- `python -m pytest tests/ -q`
- `python scripts/eval/eval_harness.py run --mode static --min-accuracy 79` (baseline 97.9%, must stay ≥ 79)
- Keep `test_rag_diagnostics_are_opt_in_and_jsonl` passing (3-arg `_write_rag_diagnostic` call).

## 6. Companion
- `docs/sessions/AI-059_Deliverable2_opening_prompt.md` — paste-ready opening message for the fresh context.
