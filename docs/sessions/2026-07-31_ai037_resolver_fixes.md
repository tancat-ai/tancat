# Handover — 2026-07-31: AI-037 Resolver Fixes (shipped) + Phase 3 Next

## Shipped this session (commit: see git log for `feat(ai037)` batch — 2026-07-31)

### 1. AI-037 Resolver Fixes — LV Insurance 54% → 62.5% regeneration, 100% resolver

All structural fixes (NO vocabulary list — the DOM provides labels):

| Fix | File | Why |
|-----|------|-----|
| Radio/checkbox label capture | `src/scraper.py` | Radios wrapped in `<label>` get accessible_name (e.g. "Social, Domestic & Pleasure") |
| Clickable div capture | `src/scraper.py` | Divs with explicit id kept even without direct text (`#productCar`, `#paymentFull`) — B-025's click-target premise |
| `<strong>` in display_tags | `src/scraper.py` | `#quoteRef` was never captured (tag not in any pass) |
| Synthetic ARIA marker | `src/scraper.py` | Pass-2 containers flagged `synthetic_id=True` |
| Radio locator format | `src/locator_builder.py` + `scripts/eval/eval_resolver.py` | `input[name][value]` disambiguates radio groups |
| Quote-agnostic locator normalization | `scripts/eval/golden_validator.py` | `input[name='x']` ≡ `input[name="x"]` |
| camelCase in `get_words()` | `src/semantic_matcher.py` | `#vehicleReg` → "vehicle Reg" → matches "registration" |
| Pass 1 synthetic skip | `src/element_matcher.py` | Synthetic groups ("Vehicle Usage") no longer win fast-text over real radios |
| Radio CLICK bonus + synthetic exclusion | `src/placeholder_scorers.py` | Container +10 no longer applies to fake ids |
| Proportional text bonus + punctuation | `src/placeholder_scorers.py` | "compulsory excess" (2 tokens) > "voluntary excess" (1); "excess:" ≡ "excess" |

**Supporting files:**
- `scripts/eval/refresh_lv_capture.py` (new) — drives the mock quote flow, then captures — faithful post-journey eval data (excessInfo etc.)
- `tests/test_scraper_ai037.py`, `tests/test_ai037_resolver_fixes.py` (new, 15 tests)
- Frozen eval data refreshed: `scripts/eval/scraped_pages/http_localhost_8781_...json` (gitignored — regenerate with `refresh_lv_capture.py` if deleted)

**Results (2026-07-31):**
- Resolver-only eval (frozen data): LV **24/24 (100%)**, overall **59.7%** (was 58.2%), no other site regressed
- Full regeneration UAT (live LLM, 5 stories): LV **15/24 (62.5%)** (spec baseline 54%), overall 56.7%
- Official static eval: 100% all sites · full suite 1928 passed · ruff/mypy clean

---

## ⚠️ NEXT SESSION — AI-037 Phase 3: Skeleton Journey-Structure Guidance

**The remaining LV gap is NOT the resolver.** Resolver-only is 24/24 (100%) on the same
descriptions. The regeneration gap (62.5%) is **LLM skeleton journey structure**: the LLM
places steps on the wrong page, so resolution targets the wrong page's elements.

**Evidence — 9 LV misses from the 2026-07-31 regeneration (DB: eval_runs, eval-005, generation_mode=regenerated):**
```
[FILL] 'first name'   → #paymentFull   (expected #firstName)    ← account field resolved on quote page
[FILL] 'last name'    → #paymentFull   (expected #lastName)
[FILL] 'postcode'     → #paymentFull   (expected #postcode)
[CLICK] 'Car Insurance product card' → #quoteSubmit (expected #productCar)
[FILL] 'vehicle registration number' → #paymentFull (expected #vehicleReg)
[CLICK] 'usage type'  → #quoteSubmit   (expected input[name='usageType'][value='SDP'])
[FILL] 'overnight location' → #paymentFull (expected #overnightLocation)
[CLICK] 'Add Vehicle button' → #quoteSubmit (expected #addVehicleBtn)
[CLICK] 'Pay in Full payment option' → #quoteSubmit (expected #paymentFull)
```
Pattern: account-page FILLs resolve to `#paymentFull`; quote-page CLICKs resolve to `#quoteSubmit`.
The LLM's skeleton puts `first name`/`postcode` after a GOTO/CLICK that lands on the quote page,
or the resolver's page-scoping picks the wrong page. Descriptions match golden keys word-for-word.

**Proposed levers (in priority order):**
1. **Skeleton prompt journey guidance** (`src/prompt_utils.py` / `src/prompt_builder.py` —
   now t-string structured, so this is auditable):
   - "Each step must appear on the page it belongs to. Follow the story order: fill all
     fields on the current page before navigating (Next) to the next page."
   - "A test that fills `first name` must do so directly after navigating to the account
     page — never after reaching the quote page."
   - "Do not emit `pytest.skip` for steps you can't place — place them on their natural page."
2. **Verify against the UAT:** `uv run python scripts/eval/uat_tstring_prototype.py` (A/B)
   or full: `LANGGRAPH_ENABLED=0 uv run python scripts/eval/eval_harness.py run --regenerate`
3. **Success criteria:** LV regeneration ≥80% (19/24), overall ≥65%.

**Warning:** the frozen LV eval data (`refresh_lv_capture.py`) is gitignored — if you see
the resolver eval drop suddenly, re-run `uv run python scripts/eval/refresh_lv_capture.py`.

---

## Useful commands

```bash
uv run python scripts/eval/eval_resolver.py --mode static          # resolver-only (frozen data)
uv run python scripts/eval/refresh_lv_capture.py                   # regenerate LV frozen data (journey state)
uv run python scripts/eval/eval_harness.py run --mode static       # captured-code gate
LANGGRAPH_ENABLED=0 uv run python scripts/eval/eval_harness.py run --regenerate   # live regeneration UAT (~10 min)
uv run python scripts/eval/uat_tstring_prototype.py                # t-string prompt A/B (legacy vs t-string)
```

## Context: recent session history

- 2026-07-31 earlier: t-string PromptBuilder (PEP 750) shipped — prompt assembly structured + auditable (`src/prompt_builder.py`, wired into `test_generator.py` + `orchestrator.py`). AI-033 resolved.
- 2026-07-30: SPA scraper fix (`_reveal_hidden_sections`) — LV 0% → 54%. Pipeline perf (batching + parallelization). Phase 1d temperature=0.
- AI-037 spec: `docs/specs/FEATURE_SPEC_AI037_lv_insurance_resolution_gap.md` (updated with 2026-07-31 diagnostic — no vocab list).
