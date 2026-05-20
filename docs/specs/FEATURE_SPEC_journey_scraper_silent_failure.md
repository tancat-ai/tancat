# FEATURE SPEC: Fix _discover_selector() Silent Failure in Journey Scraper

**Status:** Implemented  
**Priority:** High  
**Depends on:** `FEATURE_SPEC_remove_pages_needed.md` (must be implemented first)  
**Issue:** When the journey scraper can't find an element to click, it silently skips the step without warning, causing downstream pages to never be visited  
**Solution:** Emit diagnostics when a locator isn't found, implement retry-with-relaxed-criteria fallback, and track skipped steps in evidence  
**Target files:** `src/journey_scraper.py`, `src/locator_builder.py`, `tests/test_journey_scraper_silent_failure_fix.py`  
**Estimated effort:** 2 days  
**Created:** 2026-05-20  
**Completed:** 2026-05-20

---

## Problem Statement

After the PAGES_NEEDED fix (where the journey scraper detects page changes inline), the scraper's ability to actually navigate becomes critical. Currently, `_discover_selector()` has a silent failure mode:

**Current behavior:**
1. Scraper tries to find an element matching the placeholder description (e.g., "cart link")
2. `_discover_selector()` returns `None` when no match is found
3. The caller silently continues to the next step without any warning
4. The page never navigates, so the destination page is never scraped
5. Placeholders for that page remain unresolved
6. The generated test has `pytest.skip()` for those steps

**Symptom:** Tests for pages like cart or checkout are skipped, with no indication of *why* — the failure happened silently during the scraping phase, not the test phase.

**Root cause:** `_discover_selector()` uses a best-effort selector building strategy. When the DOM doesn't contain an element that matches the placeholder description with sufficient confidence, it returns `None`. The caller doesn't distinguish between "element not found" and "element found but not clickable" — both are silent.

---

## Proposed Solution

### Three improvements

| Improvement | What it does | Why |
|-------------|-------------|-----|
| **1. Warn on not found** | Log a warning with context when `_discover_selector()` returns `None` | Makes the problem visible in debug output |
| **2. Track skipped steps** | Record each skipped step in the evidence/context log with the description, page URL, and available elements | Provides data for post-hoc diagnosis |
| 3. **Retry with relaxed criteria** | On first failure, re-scan the DOM with relaxed matching (e.g., partial text match, broader attribute search) | Reduces false negatives without sacrificing quality |

---

### Implementation details

#### 1. Warn on not found

**File:** `src/journey_scraper.py` — `_discover_selector()` method

When the method returns `None`, emit a structured warning:

```python
self._context_log.append({
    "event": "locator_not_found",
    "step": step_index,
    "action": action,  # "CLICK"
    "description": description,  # "cart link"
    "page_url": page.url,
    "best_candidate_score": best_score if best_candidate else 0,
    "available_elements": self._list_available_elements(page, limit=10),
})
```

`_list_available_elements()` returns a summary of clickable elements on the page (up to a limit) to help diagnose why the match failed.

#### 2. Track skipped steps

**File:** `src/journey_scraper.py` — main execution loop

In the step execution loop, when `_discover_selector()` returns `None`:

```python
selector = self._discover_selector(description, action)
if selector is None:
    self._context_log.append({
        "event": "step_skipped",
        "step": step_index,
        "reason": "locator_not_found",
        "description": description,
        "page_url": page.url,
    })
    continue  # Don't silently fall through — explicit skip
```

After the journey completes, expose a summary:

```python
def get_skipped_steps(self) -> list[dict]:
    """Return steps that were skipped during the journey."""
    return [e for e in self._context_log if e.get("event") == "step_skipped"]
```

#### 3. Retry with relaxed criteria

**File:** `src/locator_builder.py` — New method

Add a relaxed mode to the locator builder:

```python
def build_selector_relaxed(self, description: str, page_elements: list[Element]) -> Selector | None:
    """Build a selector with relaxed matching criteria.
    
    Used as a fallback when the strict selector build fails.
    Relaxes: exact text match → partial match, requires all attributes → any attribute.
    """
```

**File:** `src/journey_scraper.py` — Retry logic

```python
selector = self._discover_selector(description, action)
if selector is None:
    # Retry with relaxed criteria
    selector = self._discover_selector_relaxed(description, action)
    if selector is not None:
        self._context_log.append({
            "event": "locator_relaxed_fallback",
            "step": step_index,
            "description": description,
            "selector": selector,
        })
    else:
        self._context_log.append({
            "event": "step_skipped",
            "step": step_index,
            "reason": "locator_not_found_even_relaxed",
            "description": description,
            "page_url": page.url,
        })
```

---

### What Changed (Implementation Summary)

| Component | Before | After |
|-----------|--------|-------|
| `src/journey_scraper.py` | No diagnostic helpers | Added `_list_available_elements()`, `get_skipped_steps()`, `get_locator_warnings()` |
| `src/locator_builder.py` | Strict matching only | Added `build_selector_relaxed()` with partial text match and lower threshold (0.2) |
| Context log | No skip tracking | Full skip tracking with `step_skipped`, `locator_not_found`, `locator_relaxed_fallback` events |
| `tests/test_journey_scraper_silent_failure_fix.py` | Did not exist | 10 tests covering all new functionality |

---

## Implementation Steps Completed

### Step 1: Added `_list_available_elements()` helper ✅

**File:** `src/journey_scraper.py`

New method that enumerates clickable elements (`a, button, input, [role=button], [role=link]`) up to a limit, returning tag, text (truncated to 50 chars), id, and first CSS class for each element.

### Step 2: Added relaxed selector builder ✅

**File:** `src/locator_builder.py`

New `build_selector_relaxed()` method with relaxed rules:
- Partial text match instead of exact/contains
- Any attribute match instead of all attributes  
- Lower confidence threshold (0.2 instead of 0.3)

### Step 3: Wired retry logic in journey scraper ✅

**File:** `src/journey_scraper.py`

Retry logic pattern implemented:
1. Try strict selector first via `_discover_selector()`
2. On failure, try relaxed selector via `_discover_selector_relaxed()`
3. On double failure, log `step_skipped` event with `locator_not_found_even_relaxed` reason

### Step 4: Exposed diagnostics ✅

**File:** `src/journey_scraper.py`

- `get_skipped_steps()` — Returns list of skipped steps from context log
- `get_locator_warnings()` — Returns list of locator-not-found events
- Context log populated with all new event types during execution

### Step 5: Created tests ✅

**File:** `tests/test_journey_scraper_silent_failure_fix.py`

- 10 tests covering: `_list_available_elements()`, `build_selector_relaxed()`, skip tracking, retry logic
- All tests use mock objects (no browser required)
- All tests pass with full type annotation coverage

---

## Acceptance Criteria

- [x] `_discover_selector()` logs a warning event when it returns `None`
- [x] Skipped steps are tracked in context log with full context
- [x] Relaxed selector fallback succeeds for at least some previously-failing cases
- [x] `get_skipped_steps()` exposes all skipped steps after journey
- [x] All existing tests pass (45 original journey scraper tests + 10 new tests = 55 total)
- [x] New tests cover relaxed fallback and skip tracking

---

## Verification Results

| Check | Result |
|-------|--------|
| `ruff check` | Pass — 0 issues (10 auto-fixed annotations) |
| `mypy` | Pass — no issues found in 3 source files |
| `pytest test_journey_scraper.py` | **45 passed** |
| `pytest test_journey_scraper_silent_failure_fix.py` | **10 passed** |

---

## When This Becomes Visible

This fix is **only** relevant after the PAGES_NEEDED fix is in place. Before that, the orchestrator pre-declares pages (even if wrong), so the scraper visits pages regardless of navigation. After the PAGES_NEEDED fix, the scraper relies on actual navigation — making the silent failure a real problem.

**Order of implementation:**
1. `FEATURE_SPEC_remove_pages_needed.md` — Make scraper rely on inline page detection
2. This spec — Make the scraper robust when it can't find elements

---

## Known Limitations

- Relaxed matching may produce less precise selectors (e.g., matching any link with "cart" in the text, including "Remove from cart")
- The scraper can't distinguish between "element not on this page" and "element exists but doesn't match description"
- For SPAs with dynamic content, the element may not be visible yet when the scraper arrives (timing issue, not a matching issue)

---

*Last updated: 2026-05-20*