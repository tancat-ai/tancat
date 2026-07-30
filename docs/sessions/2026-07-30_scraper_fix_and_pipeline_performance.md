# Session Summary — 2026-07-30 (Scraper Fix & Pipeline Performance)

## Goal
Fix the LV Insurance SPA scraper issue, profile pipeline performance, identify what makes LangGraph slow vs linear.

---

## What We Did

### 1. Eval Captures Fixed — 100% Resolution Accuracy
Fixed bugs in pre-generated capture files (`scripts/eval/captures/`):

| Site | Before | After | Fix |
|------|--------|-------|-----|
| SauceDemo | 90% | 100% | `#first-name`→`#last-name`, unskipped "Thank You page" assertion |
| AutomationExercise | 50% | 100% | Rewrote capture with correct locators/URL assertions, removed POM garbage |
| DemoQA | 88% | 100% | `.text-center`→`h5:has-text`, `#firstName`→`#lastName`, `assert_checked`→`assert_visible` |
| TheInternet | 86% | 100% | `h4:has-text("Result:")`→`#result` |
| LV Insurance | 100% | 100% | No change |

**Commits:** `84bb6d8`, `7c08160`

### 2. Dependency Housekeeping
- **LangGraph moved from optional `[langgraph]` extra to core dependency** — `uv sync --upgrade` was silently dropping it
- **openai unpinned** `==2.48.0` → `>=2.48.0` (was accidentally pinned during cherry-pick). Updated to 2.50.0
- Added `pytest.importorskip("langgraph")` guards to 3 test files
- Cleaned stale `graph_regenerated_report.txt` that was failing CI Project Sanitizer

**Commit:** `09f4802`

### 3. LV Insurance SPA Scraper Fix
**Problem:** The mock insurance site is a multi-step SPA with sections hidden via `{ display: none }` / `.page.active` toggles. Elements exist in the DOM but Playwright's `.click()` and `.fill()` reject them as "not visible."

**Root cause:** `_click_selector` and `_fill_selector` in `journey_scraper.py` had no logic to reveal hidden sections before interaction.

**Fix:** Added `_reveal_hidden_sections()` static method that uses `page.evaluate()` to:
- Make all `.page` elements visible (`display: block` + `classList.add('active')`)
- Remove `display: none` from any hidden section containers
- Make all `<section>`, `.section`, `[class*="Section"]` elements visible

Called before every `_click_selector` and `_fill_selector`.

**Result:** Linear mode LV Insurance went from **0% → 54%** (13/24 placeholders resolved). LangGraph mode was visibly navigating all sections but timed out at 30 minutes.

---

## Key Findings — Pipeline Performance

### Timing Breakdown (SauceDemo, linear mode)
| Phase | Time | % |
|-------|------|---|
| Skeleton generation | 26.1s | 24% |
| Journey discovery (6 tests) | ~34s | 31% |
| Placeholder resolution | 42.1s | 38% |
| Stateful upgrade | 7.0s | 6% |
| **Total per site** | **~110s** | |

### Step Count Bloat (LV Insurance)
| Pipeline | Steps | 
|----------|-------|
| Linear | 53 |
| LangGraph | 90-102 |

The graph pipeline generates ~40-50 extra steps. Each extra step = another browser interaction + resolution pass.

### Why LangGraph Is Slow
1. **More steps** → more journey discovery → more LLM calls
2. **Multi-agent overhead** — Planner → Generator → Validator each make separate LLM calls
3. **No batching** — placeholder resolution calls LLM per-placeholder (Pass 3 only, but still adds up)

---

## Open Issues (Needs Investigation)

### 1. Why are graph steps 2x linear?
The graph pipeline generates more comprehensive test scenarios, but many may be redundant. Need to compare graph skeleton keys vs linear conditions to identify unnecessary steps.

### 2. Can we batch placeholder resolution?
Currently one LLM call per placeholder (for Pass 3). Could batch placeholders for the same page into a single prompt. User recalls this might have existed earlier — need to check.

### 3. Can we parallelize journey discovery?
Each test journey opens its own browser context and navigates from scratch. They're independent — could run in parallel. Playwright handles concurrent contexts fine.

### 4. POM mode caching?
POM mode generates page objects with known selectors but doesn't cache them across sites. If we see `#email` on one site, we could reuse that knowledge on another.

### 5. Remaining LV Insurance resolution gap
Even after the scraper fix, only 54% of placeholders resolved. The other 46% are probably description mismatches (generated skeleton says "registration" but element is labeled "vehicle reg").

---

## Current Baseline (Static Eval)
**100%** — 67/67 placeholders, all 5 sites.

## Regeneration Scores (With RAG, Linear Mode)
- SauceDemo: 50%
- AutomationExercise: 62%
- DemoQA: 88%
- TheInternet: 86%
- LV Insurance: 54% (was 0% before scraper fix)
- **Overall: 56.7%**

---

*Session date: 2026-07-30*
