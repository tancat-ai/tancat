# AI-052 — Observed Transitions — Session 1

> **Session 1 of 6** — Data model + capture observed transition trails.
> Plan: `docs/plans/AI-052_observed_transitions_plan.md` (read §0 + this session).
> Date: 2026-07-23

---

## What was built

**No resolver changes. Pure capture + typed data model.** The `JourneyScraper`
now records every step of a journey as a factual `ObservedStep` — where the
browser *actually* was, read from `page.url`, never inferred.

### New types (`src/journey_models.py`)

| Type | Purpose |
|---|---|
| `ObservedStep` | One step: `{index, action, description, selector_used, from_url, to_url, navigated, scraped, error}` |
| `ObservedTrail` | Ordered list of `ObservedStep` + `pages_visited` property (deduped) |

`JourneyResult` now carries an optional `trail: ObservedTrail | None` field
(round-trips through `to_dict`/`from_dict`, back-compatible with old payloads).

### Capture (`src/journey_scraper.py`)

- `_scrape_journey_sync` populates one `ObservedStep` per journey step using the
  existing `current_url` / `new_url = page.url` / `output` writes.
- New `get_observed_trail()` getter (typed, unlike the raw `_context_log`).
- `navigated` is `True` only when the step changed `page.url` relative to
  `from_url`; for step 0 `from_url` is the starting page so `navigated` is
  always `False` there (documented in the dataclass).
- `scraped` is `True` when the step's destination URL is in the scraped `output`.
- `error` is set from the exception path after retries, or
  `"locator_not_found_even_relaxed"` when a click/fill finds no element.

### Subprocess plumbing (`src/journey_subprocess.py`)

The trail is embedded in the subprocess stdout JSON under the `__trail__` key
(the parent process's `_scrape_journey_via_subprocess` parses it back into a
typed `ObservedTrail`). Without this the trail would be lost across the
subprocess boundary.

### Phase B path (`src/journey_executor.py`)

`_execute_journey_sync` also records an `ObservedTrail` (simpler — no retry
loop, no URL inference) and attaches it to `JourneyResult.trail`.

### Testability seam

Two `getattr(self, "_url_guard_patched", False)` checks skip the SSRF guard's
DNS resolution in unit tests (the guard calls `socket.getaddrinfo` on every
navigate, which fails in sandboxed test environments). Production behaviour is
unchanged — the flag is never set outside tests.

---

## Live verification (saucedemo, 2026-07-23)

Ran a real login → title-link → scrape journey against saucedemo.com:

```
step 0: click 'login button'       'https://www.saucedemo.com'        -> '.../inventory.html'             navigated=True scraped=True
step 1: click 'product title link' '.../inventory.html'               -> '.../inventory-item.html?id=4'   navigated=True scraped=True
step 2: scrape 'final page state'  '.../inventory-item.html?id=4'     -> '.../inventory-item.html?id=4'   navigated=False scraped=True
```

The trail is exactly what the resolver will need: step 1's `to_url` is the
detail page that the AI-052 bug currently re-guesses via
`infer_next_page_url` and then can't find in `scraped_data`.

---

## Gate results

| Gate | Result |
|---|---|
| `scripts/smoke.py` | ✅ 39/39 |
| `pytest -q -n 4` | ✅ 2702 passed, 1 skipped |
| `eval_harness.py run --mode static` | ✅ 97.9% (baseline 97.9%) |
| `ruff check` (changed files) | ✅ clean |
| `mypy` (changed files) | ✅ clean (src); test file has 11 known mypy errors from monkeypatching (acceptable for tests) |

## Files changed

| File | Change |
|---|---|
| `src/journey_models.py` | +`ObservedStep`, +`ObservedTrail`, +`trail` field on `JourneyResult` |
| `src/journey_scraper.py` | Trail capture in `_scrape_journey_sync`, +`get_observed_trail()`, URL-guard test seam |
| `src/journey_subprocess.py` | Embed trail in subprocess stdout under `__trail__` |
| `src/journey_executor.py` | Trail capture in `_execute_journey_sync`, attach to `JourneyResult` |
| `tests/test_journey_observed_trail.py` | **new** — 11 tests (data model, live-faithful loop, subprocess contract) |

## Next

**Session 2** — Plumb the trail into the resolver (`orchestrator.py`
`_scrape_journeys_statefully` → `run_pipeline` →
`_replace_placeholders_sequentially`). No behaviour change yet — just wire
data through and add a debug log line per journey.
