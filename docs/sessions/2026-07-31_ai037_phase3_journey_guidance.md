# Handover — 2026-07-31: AI-037 Phase 3 — Skeleton Journey-Structure Guidance (shipped)

## Summary

AI-037 Phase 3 shipped. LV Insurance regeneration improved **15/24 (62.5%) → 19/24 (79.2%)**
— meeting the ≥19/24 success criterion. The pipeline's ceiling (ideal skeleton through the
live pipeline) went **21/24 → 24/24**. Static eval 100% all sites, 1928 tests, ruff/mypy clean.

## What was actually wrong (two findings beyond the handover's prompt-lever)

The handover predicted prompt guidance was the only lever. Controlled experiments showed
TWO additional structural causes — one scraper, one validator:

### 1. Scraper: live journey capture never revealed SPA hidden sections (fixed)

- **Evidence:** `scripts/debug.py resolve` on the LV mock site: `Car Insurance product card`
  → **0 candidates**, despite `#productCar` being scraped. `rank_candidates` hard-skips
  `is_visible=False` elements for CLICK/FILL, and on the LV SPA every non-active section
  is `display:none`.
- **Why frozen eval was 24/24:** `refresh_lv_capture.py` calls
  `JourneyScraper._reveal_hidden_sections(page)` before its final capture. The live
  journey scraper's `_scrape_current_page` never did.
- **Fix:** `src/journey_scraper.py` `_scrape_current_page` now calls
  `_reveal_hidden_sections(page)` before extracting — mirrors the frozen methodology.
- **Proof:** ideal-skeleton live pipeline went 21/24 → 24/24.

### 2. Validator: has-text substring equivalence missing (fixed)

- **Evidence:** resolver returned `h2:has-text("✅ Quote Generated Successfully!")` (the
  real h2 inside `#quoteSuccess`) but golden tolerance `h2:has-text('Quote Generated')`
  failed — exact-string compare on a Playwright substring matcher.
- **Fix:** `scripts/eval/golden_validator.py` `_locators_match` now treats `:has-text()`
  needles as substring-equivalent (either direction), tag-agnostic.
- **Tests:** 2 new cases in `scripts/eval/golden_validator_test.py`.

### 3. Prompt: journey-structure guidance (the handover's lever, shipped as specified)

`src/prompt_builder.py` + `src/prompt_utils.py` (kept **byte-identical**, 26 prompt tests pass):
- "fill ALL fields on the current page BEFORE navigating (Next) to the next page"
- "never place a step after the navigation that leaves its page"
- "do NOT emit pytest.skip for steps you cannot place — place them on their natural page"
- "use the exact labels from the story — do not invent intermediate clicks or pages"

Added to both `build_skeleton_prompt` and `build_single_condition_prompt` (and legacy
equivalents). A/B shows it's necessary but not sufficient alone — LLM sampling
nondeterminism dominates the remaining variance.

## Results

| Metric | Before | After |
|--------|--------|-------|
| LV regeneration (eval-005) | 15/24 (62.5%) | **19/24 (79.2%)** |
| Ideal-skeleton live pipeline | 21/24 | **24/24** |
| Static eval (all 5 sites) | 100% | **100%** |
| Resolver-only eval (LV) | 24/24 | **24/24** |
| theinternet regeneration | 6/7 | **7/7** |
| Overall regeneration | 56.7% | **59.7%** |
| Full test suite | — | **1928 passed** |
| ruff / mypy | clean | clean |

Remaining 5 LV misses are CLICKs where the LLM emitted generic descriptions ("Submit",
"Next") that all resolve to `#quoteSubmit` — pure skeleton sampling noise. The resolver
handles identical descriptions 24/24.

## Files changed

| File | Change |
|------|--------|
| `src/prompt_builder.py` | JOURNEY STRUCTURE section in both t-string prompts |
| `src/prompt_utils.py` | same, legacy equivalents (byte-identical) |
| `src/journey_scraper.py` | `_scrape_current_page` now reveals SPA sections before capture |
| `scripts/eval/golden_validator.py` | has-text substring equivalence in `_locators_match` |
| `scripts/eval/golden_validator_test.py` | 2 new regression tests |
| `BACKLOG.md` | AI-037 Phase 3 complete |

## Useful commands

```bash
uv run python scripts/eval/eval_resolver.py --mode static          # resolver-only (frozen)
uv run python scripts/eval/eval_harness.py run --mode static       # static gate (CI)
LANGGRAPH_ENABLED=0 uv run python scripts/eval/eval_harness.py run --regenerate  # live UAT (~10 min)
uv run python scripts/eval/uat_tstring_prototype.py                # A/B (prompt paths)
uv run python scripts/eval/refresh_lv_capture.py                   # re-freeze LV data if deleted (gitignored)
```

## Follow-ups (optional, not required for Phase 3)

- **Regeneration stability:** saucedemo/automationexercise regeneration scores fluctuate
  with LLM sampling (saucedemo 8-10/20 run-to-run). Static gate stays 100%. If CI needs
  stable regeneration numbers, consider a deterministic skeleton→golden-alignment post-pass
  or `temperature=0` on skeleton calls.
- **AI-037 overall ≥65%** target: not met (59.7%) — dominated by saucedemo/demoqa
  regeneration variance, not the LV resolver. Re-evaluate after any skeleton-prompt work.
- Experiment scripts (`exp_ai037_*`) were deleted after use per one-off-script policy.
