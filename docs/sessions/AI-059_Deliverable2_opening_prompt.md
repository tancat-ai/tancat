# AI-059 Deliverable 2 — Opening Message (paste into fresh context)

> Copy everything below the line into a new Pi session to continue Deliverable 2.

---

You are continuing **AI-059 Deliverable 2** in the `AI-Playwright-Test-Generator` repo (working dir `C:/Users/l_a_c/code/AI-Playwright-Test-Generator`). The repo is clean on top of commit **`f2f0b60`** (`feat(ai-059): learning-impact isolation harness — sentinel identity + controlled baseline`), which already shipped Deliverable 1 (lab sentinel identity, cold/warm baseline runner, `AI059_DISABLE_AUTO_LEARN` gate, opt-in `rag_diagnostics.jsonl`). The handoff doc is at `docs/sessions/2026-08-27_ai059_session2_resolver_usage_trace_handoff.md` — read it first.

## Task (Deliverable 2 — "resolver usage trace")
Today we can see RAG patterns are **retrieved** (logged to `rag_diagnostics.jsonl` via `AI059_RAG_DIAGNOSTICS_PATH`), but NOT whether a retrieved pattern was actually **applied** as a scoring bonus to the winning element. Make usage observable: for each retrieved pattern, emit `eligible` (site gate passed?), `matched` (selector hit the winning element?), and `bonus` (points contributed).

## Design (implement cleanly — do NOT reintroduce the previous broken state)
1. **`src/rag_retriever.py`**: add `RAGRetriever.pattern_usage(self, patterns, site_hash, element_selector) -> list[dict]` returning one record per pattern: `{description, source, site_hash, eligible, matched, bonus}`. Mirror the existing bonus logic:
   - `PlaceholderScorer.GOLDEN_PATTERN_BONUS = 20`, `SAME_SITE_LEARNED_BONUS = 5`.
   - golden `eligible = not (pattern.site_hash and pattern.site_hash != site_hash)` (empty `site_hash` = legacy, site-agnostic).
   - learned `eligible = bool(site_hash) and pattern.site_hash == site_hash`.
   - direct match `bonus = int(bonus_full * pattern.confidence)`; substring match `bonus = int(bonus_full * 0.5 * pattern.confidence)`.
   - Refactor `scoring_bonus_for` to delegate: `for rec in self.pattern_usage(...): if rec["bonus"] > 0: return float(rec["bonus"])` (preserves first-match-wins). Do NOT modify `PlaceholderScorer._golden_pattern_bonus`/`_learned_pattern_bonus` (the applied path) — keep it untouched for zero risk.
2. **`src/placeholder_orchestrator.py`**:
   - In `if matched_element is not None:`, compute `winner_selector = str(matched_element.get("selector", "") or "").strip()` (raw candidate selector — NOT the repr'd emitted locator), call `self._rag_retriever.pattern_usage(golden_patterns, site or "", winner_selector)`, and append via a NEW staticmethod `_write_rag_usage_diagnostic(action, description, usage)` (opt-in `AI059_RAG_DIAGNOSTICS_PATH`, `try/except (OSError, TypeError, ValueError)` like the existing `_write_rag_diagnostic`).
   - Optionally add `eligible` to the existing retrieval diagnostic (`_write_rag_diagnostic`, called from `_retrieve_golden_patterns`) — if you add a `site` param to that staticmethod, keep the 3-arg call in test `test_rag_diagnostics_are_opt_in_and_jsonl` valid.
3. **`tests/test_learning_impact.py`**: add `test_pattern_usage_reports_eligible_match_and_bonus` (import `RAGRetriever` from `src.rag_retriever`; build `RetrievedPattern`s with `source="learned"`/`"golden"` + `site_hash`; assert `eligible`/`matched`/`bonus` for same-site, cross-site, and empty-site-hash cases).

## Gotchas
- `_write_rag_diagnostic` is a `@staticmethod` with signature `(action, description, patterns)` — it currently has NO `site` param. A prior attempt added a 4-arg call `site=site` without adding the param → `TypeError`. Don't repeat that.
- Match against the winner's **raw** `matched_element.get("selector", "")`, not the repr'd robust selector.
- Keep the diagnostic writes inside `try/except` so they never affect resolution.

## Verification (all must pass before any commit)
- `python scripts/smoke.py --json`
- `python -m ruff check .` and `python -m ruff format --check .` (format any new/changed files)
- `python -m mypy src/ cli/` (+ mypy on staged test files; pre-commit checks tests too)
- `python -m pytest tests/ -q`
- `python scripts/eval/eval_harness.py run --mode static --min-accuracy 79` (baseline ~97.9%, must stay ≥ 79)
- Confirm `tests/test_learning_impact.py::test_rag_diagnostics_are_opt_in_and_jsonl` still passes.

## When done
Run the ship-it skill to commit + push. Do NOT commit the handoff doc (`docs/sessions/2026-08-27_ai059_session2_resolver_usage_trace_handoff.md` / this file) unless continuing into a follow-up — they are handoff artifacts.
