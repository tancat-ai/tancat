---
purpose: >
  State-aware DOM scraper used as fallback in placeholder_orchestrator.py.
  Tracks form state, visible elements, and DOM mutations across interactions.
lines: ~350
created: "2026-05-30"
---

# `src/stateful_scraper.py`

## High-Level Purpose

Fallback scraper that maintains DOM state awareness across page interactions. Tracks which forms are visible, which elements changed after actions, and provides context-rich element data for placeholder resolution.

## Key Features

- **Form state tracking:** Records form field values before/after interactions
- **Visibility detection:** Only considers visible elements for candidate matching
- **DOM mutation awareness:** Detects elements added/removed after user actions
- **Context preservation:** Carries page URL, title, and visible text for LLM reasoning

## Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `scrape_page(url)` | `ScrapeResult` | Navigate and scrape with state awareness |
| `record_interaction(action, selector)` | `dict` | Record DOM state after click/fill |
| `get_visible_elements()` | `list[dict]` | Only visible, interactable elements |

## Dependencies

- `src.scraper.PageScraper` — base scraping
- `src.state_tracker.StateTracker` — state persistence

## Depended On By

- `src/placeholder_orchestrator.py` — fallback when journey_scraper unavailable

## Recent API Additions

Symbols present in the source but not covered above (refresh pass, 1 items):

### `StatefulPageScraper` (class)

Scrape pages using a Playwright browser context with a cart session.

## How It Works (Internals)

Private `_`-helpers — the module's real logic (1 item). Grouped under the public function that uses them:

### Internal utilities
- `_run_subprocess_entry() -> int` (function) — Entry point for the subprocess-backed stateful scrape.
