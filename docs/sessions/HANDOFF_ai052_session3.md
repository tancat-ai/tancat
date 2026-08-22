# HANDOFF → AI-052 Session 3 (fresh context)

You are starting **Session 3 of 6** for AI-052 (Observed Transitions). Read this
first, then read ONLY plan §0 + Session 3 (do not re-derive S1/S2).

## Read in this order (fresh context)
1. This file.
2. `docs/plans/AI-052_observed_transitions_plan.md` → §0 (shared context) **and** the **Session 3** section only. It has the goal, the 3 deliverables, the tricky index-mapping note, the four test fixtures, the gates, and the DoD.
3. `docs/sessions/2026-07-23_ai052_session1_observed_trail.md` + `docs/sessions/2026-07-23_ai052_session2_plumbing.md` (what S1/S2 already built — so you don't redo it).

## Where things stand
- **S1 ✅ done** — `JourneyScraper` captures a typed `ObservedTrail` (one `ObservedStep` per step: `index, action, description, selector_used, from_url, to_url, navigated, scraped, error`). Live saucedemo check passed.
- **S2 ✅ done** — the trail is plumbed: `_scrape_journeys_statefully` → `run_pipeline` → `_replace_placeholders_sequentially(observed_trails=...)`. It's debug-logged under `PIPELINE_DEBUG=1`. **No resolution behaviour changed yet.**
- **S3 = YOUR SESSION — the core fix.** Make the resolver *consume* the trail.

## S3 in one paragraph (full detail in the plan)
Stop guessing next-page URLs. In `_replace_placeholders_sequentially`
(`src/placeholder_orchestrator.py:480`), derive `current_url` from the **observed
trail** (a fact) instead of `infer_next_page_url` (a guess). Three states:
- **verified** — the step's `to_url` is in `scraped_data` → scope resolution to it.
- **evidenced** — real `href` target, page not scraped → advance, but next step unresolvable → skip.
- **unknown** — no observation, no href → stay on last verified page; if the element isn't there → **honest `pytest.skip`**, never a cross-page locator.

The specific line that currently produces AI-052 is the all-pages fallback in
`_build_scoped_pages` (`src/placeholder_orchestrator.py:1200`) /
`element_matcher.find_best_element_for_current_page:743` ("Collects candidates
from ALL pages first"). When `current_url` is verified, scope to it; when
evidenced/unknown, scope to the **from-page** (last verified) — do NOT fall back
to all pages.

## The one genuinely tricky part (plan's open question #1)
**Index alignment**: the skeleton's placeholder order must line up with the
observed trail's step order. The trail was built from the *same* journey steps,
so it *should* hold — but **ASSERTs map to `scrape` steps and GOTOs to
`navigate`**. Verify against the four captured failure fixtures before trusting
it; build an explicit index map if it doesn't hold.

## The four fixtures (use these as S3 test data — `tests/test_resolver_observed_scope.py`)
- **A** (saucedemo 2026-08-20): trail shows title-link → `?id=4`; the following add-to-cart must resolve to `pytest.skip`, NOT `#add-to-cart-sauce-labs-fleece-jacket`.
- **B** (automationexercise 2026-08-03): `.btn.check_out` while on `/products` → now skips instead of cross-page click.
- **C** (happy path): every step lands on a scraped page → all resolve as before (no regression).
- **evidenced** case: real href to unscraped page → next step skips honestly.
(The raw repro: `generated_tests/verify_saucedemo_20260820_234225/test_saucedemo.py`.)

## S3 gates (run in order before accepting)
`scripts/smoke.py` → `pytest -q --tb=short -n 3` (use -n 3; -n 4/8 can OOM on this box) → **eval static** (`scripts/eval/eval_harness.py run --mode static`, baseline 97.9%) → `ruff check` + `mypy` → **`scripts/verify_production.py saucedemo --keep`** (~10 min, **needs llama.cpp running on :8080**).
S3 DoD: **zero `_LocatorNotFoundError: ... different page`** across saucedemo + automationexercise verify runs; the affected step now skips; no new false passes. (Gate count may drop slightly — correct, a step is honestly skipped instead of failing.)

## Housekeeping rules (do NOT break)
- **Do not flip BACKLOG/ROADMAP status to `✅`** — that only happens at **S6 (ship-it)**, after commit+push+CI green. BACKLOG AI-052 currently says "S1✅ S2✅ S3 next (uncommitted)".
- **Never commit untracked `generated_tests/test_*.py`** (gitignore rule). `verify_production --keep` writes generated tests — leave them untracked.
- **Commit S1+S2+S3 together** (or at least before S3 ship) — 7 src files changed + 2 new test files are currently uncommitted. `git status --short` will show them.
- `verify_production` needs the local LLM on `:8080` (llama.cpp, per `.env`). If it isn't up, S3's heavy gate can't run — flag it, don't fake it.

## Quick orientation (touch points)
- `src/placeholder_orchestrator.py:482` `_replace_placeholders_sequentially` — consume the trail here (already receives `observed_trails`).
- `src/placeholder_orchestrator.py:1200` `_build_scoped_pages` — honest scoping (no all-pages fallback).
- `src/element_matcher.py:743,963` — candidate collection (role-aware gate is S5, optional — NOT S3).
- `src/url_inference.py` — keyword branch stays for now (deleted in S4).
- `src/journey_models.py` — `ObservedStep`/`ObservedTrail` definitions (read the `navigated` docstring: step 0 is always `navigated=False` by construction; use `from_url != to_url` for the first step).

Out of scope for S3: AI-051 (post-login `to_have_url`), AI-046 (thinking A/B), S5 ARIA role gate (optional, separate).
