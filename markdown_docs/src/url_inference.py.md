# `src/url_inference.py`

## Purpose
URL transition resolution for journey-aware placeholder resolution. Returns where
a resolved CLICK actually goes — derived **only from evidence** (the clicked
element's own `href`).

## AI-052 Update (2026-08-23, S4 — no-guessing)

This module was rewritten in AI-052 Session 4. The previous version inferred
transitions from description keywords ("description says inventory, so probably
`/inventory.html`") via `_infer_click_transition_url` (login→inventory,
checkout→step-two, … branches) and `_find_discovered_url`. **Both functions are
deleted.** The no-guessing principle: a URL transition is derived ONLY from the
clicked element's own `href` — a fact about where the click goes. Anything else
is a guess and is intentionally not implemented.

Where a step lands is now the **observed trail** (`ObservedTrail` captured by
`src/journey_scraper.py`, consumed by `src/placeholder_orchestrator.py`) — the
source of truth. Trail-driven callers never consult this module at all;
non-trail callers get `None` for elements without a real href, which the caller
treats as "no observed transition" (never a fabricated one).

## Public API

| Function | Description |
|----------|-------------|
| `infer_next_page_url(action, description, matched_element, scraped_data, current_url) -> str \| None` | Main (and only) entry: returns the transition target of a resolved CLICK — its own `href` only |

### `infer_next_page_url` rules

- `action != "CLICK"` → `None`
- empty `href`, or `href` starting with `#`, `javascript:`, `mailto:`, `tel:` → `None`
- absolute `http://` / `https://` href → returned as-is
- relative href with `current_url` → resolved via `urljoin(current_url, href)`
- relative href without `current_url` → returned as-is

Note the `description` and `scraped_data` parameters are retained for
signature compatibility with existing call sites; they are not used for
inference (keyword matching on them was the deleted guessing behaviour).

## How It Works (internals)

No private `_`-prefixed helpers remain — the module is a single ~30-line
function. All the intelligence moved out: transition observation to
`src/journey_scraper.py` (`ObservedTrail`) and consumption to
`src/placeholder_orchestrator.py` (`_replace_placeholders_sequentially`).

## Dependencies

- `logging`, `urllib.parse.urljoin` (stdlib only)
- Consumers: `src/placeholder_orchestrator.py` (non-trail fallback path), `src/placeholder_resolver.py`
- Related: `src/journey_scraper.py` (`ObservedTrail` / `ObservedStep`), `src/placeholder_orchestrator.py` (trail consumption, S2/S3)

## Metadata
- **Lines:** 49 (at refresh, 2026-08-23)
