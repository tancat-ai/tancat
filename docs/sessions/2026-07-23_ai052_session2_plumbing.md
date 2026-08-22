# AI-052 — Observed Transitions — Session 2

> **Session 2 of 6** — Plumb the trail into the resolver (no behaviour change).
> Plan: `docs/plans/AI-052_observed_transitions_plan.md` (read §0 + this session).
> Date: 2026-07-23

---

## What was built

**The observed trail now reaches the resolver and is logged per journey. No
resolution behaviour changed** — this is pure plumbing, deliberately low-risk.

### `src/orchestrator.py`

- `_scrape_journeys_statefully` now returns a 3-tuple
  `(scraped_data, pages_visited, observed_trails)` where `observed_trails` maps
  each journey's `test_name` → its `ObservedTrail` (read from the per-journey
  `JourneyScraper.get_observed_trail()`). The `zip(..., strict=True)` keeps the
  journey→result pairing honest.
- `run_pipeline` captures `observed_trails` from that call, passes
  `observed_trails=...` into `_replace_placeholders_sequentially`, and stores it
  on `PipelineRunResult.observed_trails` (new field, default `{}`).

### `src/placeholder_orchestrator.py`

- `_replace_placeholders_sequentially` accepts
  `observed_trails: dict[str, ObservedTrail] | None = None` (default → `{}` for
  back-compat with tests/CLI callers).
- For each journey it logs the factual trail, **gated on `PIPELINE_DEBUG=1`**:
  ```
  [resolve] <test_name> observed trail: [url0 -> url1 -> url2]
  ```
  > Implementation note: the plan said "at debug level" via the module `logger`,
  > but the Streamlit app never configures Python logging, so `logger.debug` is
  > invisible in a normal run. I used the same `PIPELINE_DEBUG` + stderr
  > convention the rest of the pipeline already uses (`orchestrator._debug`),
  > which is also exactly what the DoD names.

### Back-compat fix (`tests/test_orchestrator.py`)

Two existing tests mocked `_scrape_journeys_statefully` to return a 2-tuple;
updated both to the new 3-tuple (added `{}` for trails).

---

## Definition of Done — proven with a REAL live trail

Captured an actual saucedemo trail (login → title-link → scrape) and fed it
through the new `observed_trails` parameter. Under `PIPELINE_DEBUG=1`:

```
[resolve] test_saucedemo_add_flow observed trail:
  [https://www.saucedemo.com/inventory.html -> https://www.saucedemo.com/inventory-item.html?id=4]
```

The real observed transition is visible at the resolver — the exact URL the
resolver currently re-guesses (and can't find). S3 will make it *consume* this.

---

## Gate results

| Gate | Result |
|---|---|
| `scripts/smoke.py` | ✅ 39/39 |
| `pytest -q -n 3` | ✅ 2707 passed, 1 skipped (was 2702; +5 new S2 tests) |
| `eval_harness.py run --mode static` | ✅ 97.9% (unchanged — expected, see S1 note) |
| `ruff check` (changed) | ✅ clean |
| `mypy` (changed) | ✅ clean |

## Files changed

| File | Change |
|---|---|
| `src/orchestrator.py` | `_scrape_journeys_statefully` returns trails; `run_pipeline` passes + stores them; `PipelineRunResult.observed_trails` |
| `src/placeholder_orchestrator.py` | `_replace_placeholders_sequentially` accepts `observed_trails`; PIPELINE_DEBUG-gated trail log |
| `tests/test_orchestrator_trail_plumbing.py` | **new** — 5 tests (trail returns, log present/absent, back-compat, result field) |
| `tests/test_orchestrator.py` | 2 mock sites: 2-tuple → 3-tuple |

(S1 files — `journey_models.py`, `journey_scraper.py`, `journey_subprocess.py`,
`journey_executor.py`, `test_journey_observed_trail.py` — are part of the same
uncommitted changeset; commit together or separately, both are self-contained.)

## Next

**Session 3** — the core fix. The resolver derives `current_url` from the
observed trail (a fact) instead of `infer_next_page_url` (a guess); unobserved
steps → honest `pytest.skip`, never a cross-page locator. Gates include
`verify_production saucedemo --keep`.
