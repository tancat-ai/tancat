# AI-052 — Observed Transitions — Session 4

> **Session 4 of 6** — delete the keyword-URL guessing; GOTO hygiene.
> Plan: `docs/plans/AI-052_observed_transitions_plan.md` (read §0 + this session).
> Date: 2026-08-23

---

## What was built

**No code path turns a description keyword into a URL any more.**

### `src/url_inference.py` — rewritten as evidence-only

- `infer_next_page_url` now derives transitions **only from the clicked
  element's own `href`** (absolute, or relative resolved against
  `current_url`). Fragments (`#`), `javascript:`, `mailto:` return None.
- **Deleted**: `_infer_click_transition_url` (login/checkout/continue/finish/
  transfer/pay description keywords → `_find_discovered_url`) and the
  navigation-wording block that looked up scraped URLs from descriptions.
  `_find_discovered_url` deleted with them.
- Module docstring states the no-guessing principle. Trail-driven callers
  never consult this module at all; non-trail callers get `None` for
  href-less elements ("no observed transition").

### `src/journey_scraper.py` — discovery fallback is evidence-bounded

- Deleted `_infer_url_from_description` (keyword → fabricated path candidates
  + outbound `httpx.head` probes — the last text→URL fabrication site).
- Replaced with `_match_discovered_url(description, known_urls)`: navigates
  only to pages the journey has ALREADY scraped, matching description
  keywords against real path words (best match wins). No match ⇒ the step is
  honestly recorded as `step_skipped`. Side benefit: one fewer outbound-HTTP
  call site for the egress audit.

### Call-site audit (plan deliverable 2)

- `placeholder_orchestrator.py:1296` — the sole remaining caller, non-trail
  path only (strict trail path ignores inference entirely since S3).
- GOTO/URL paths use `resolver.resolve_url`, which returns only URLs already
  in scraped data / seed list — evidence-based, kept.
- `scripts/archive/debug_scripts/replay_saucedemo_checkout.py` — archived,
  untouched.

## Open question #3 answered

**Does deleting the keyword branch drop eval static below 97.9%? — No.**
Eval static measures **97.9% before AND after** S4 (baseline held exactly).
One unit test DID depend on the old fabrication:
`test_run_pipeline_advances_after_login…` asserted a cart-link CLICK that was
only possible because the "login" keyword branch advanced `current_url`
without evidence. Post-S4 the resolver honestly cannot know where login lands
without an observation, so the navigation-intent fallback emits
`navigate('https://www.saucedemo.com/cart.html')` (a verified page) instead.
Test updated to pin the new contract.

## Gate results

| Gate | Result |
|---|---|
| `scripts/smoke.py --json` | ✅ 39/39 (egress audit still clean, one fewer call site) |
| `ruff check .` / `format --check .` | ✅ |
| `mypy src/ cli/` | ✅ |
| `pytest tests/ -n 3` | ✅ 2726 passed, 1 skipped |
| eval static | ✅ **97.9% — unchanged** (open question #3: no regression) |
| `verify_production saucedemo --keep` | ✅ same profile as post-S3: 0 different-page errors; 4 passed / 1 failed (**AI-051**, out of scope) / 1 honest skip |
| `verify_production automationexercise --keep` | ✅ same profile as post-S3: 0 different-page errors; 6 passed / 1 failed (login-gated checkout modal — skeleton omits login, not a locator bug) |

## Files changed

| File | Change |
|---|---|
| `src/url_inference.py` | Rewritten evidence-only; keyword branches + helpers deleted (~90 lines removed) |
| `src/journey_scraper.py` | `_infer_url_from_description` → `_match_discovered_url`; call site updated |
| `tests/test_url_inference.py` | Rewritten: pins the no-guessing contract (keyword-rich clicks without href → None) |
| `tests/test_journey_observed_trail.py` | Stub updated to `_match_discovered_url` |
| `tests/test_orchestrator.py` | One assertion updated to the post-S4 honest behaviour |

## Next

**Session 5 (optional)** — ARIA role-aware candidate collection; only if
residual cross-page risk or role-mismatch false picks show up. Otherwise
**Session 6** — regression sweep, docs sync, ship.
