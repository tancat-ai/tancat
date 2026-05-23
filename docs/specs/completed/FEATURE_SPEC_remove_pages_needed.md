# FEATURE SPEC: Remove PAGES_NEEDED Pre-declaration

**Status:** Complete  
**Priority:** High  
**Issue:** PAGES_NEEDED is unreliably emitted by the LLM (60% of runs miss cart/checkout pages per variability analysis)  
**Solution:** Remove pre-declaration requirement, rely on journey scraper's inline page-change detection  
**Target files:** `src/orchestrator.py`, `src/skeleton_parser.py`, `src/prompt_utils.py`, `src/placeholder_orchestrator.py`  
**Estimated effort:** 1 day  
**Created:** 2026-05-20  
**Completed:** 2026-05-22  
**Commit:** 83695e91668b0fd1fea5b5fe6a2a0cc88c8a6682

---

## Problem Statement

The skeleton-first pipeline requires the LLM to pre-declare which pages are visited via a `# PAGES_NEEDED:` comment. The variability analysis (see `scripts/debug/skeleton_variability_report.md`) proved this is inherently fragile:

- **60% of skeleton generations** omit critical pages (cart, checkout) from PAGES_NEEDED
- The LLM generates the same skeleton steps but declares different pages across runs
- Missing pages → journey scraper doesn't scrape them → placeholders remain unresolved → tests fail

**Root cause:** Asking the LLM to pre-declare pages is a prediction task. The LLM doesn't know the site structure, so it guesses based on the skeleton text alone. Different runs produce different guesses.

---

## Key Insight

**The journey scraper already detects page changes inline.** After each skeleton step execution, it checks if the URL changed and triggers a fresh scrape on the new page. This mechanism is already in `src/journey_scraper.py` lines 650-660:

```python
# After each step execution:
if page_url != new_url:
    page_url = new_url
    self._context_log.append({"event": "navigation", "url": page_url})
    # Re-scans the page
```

The scraper already follows actual browser navigation. It doesn't need to be told where to go — it just needs to scrape the current page whenever it lands somewhere new.

**PAGES_NEEDED is the problem, not the solution.** It's a pre-declaration step that conflicts with the journey scraper's organic page discovery.

---

## Proposed Solution

### Remove PAGES_NEEDED as a pre-declaration requirement

Make the journey scraper's inline page-change detection the **sole** mechanism for page discovery. The scraper already tracks all visited pages in its context log — expose that as the authoritative list.

### What changes

| Component | Current behavior | New behavior |
|-----------|-----------------|--------------|
| Skeleton prompt | Instructs LLM to emit `# PAGES_NEEDED:` comment | Remove this instruction |
| `skeleton_parser.py` | `parse_pages_needed()` extracts pages from LLM output | Keep for backward compatibility (mark deprecated), don't error if missing |
| `orchestrator.py` | Extracts `pages_needed` from skeleton, passes to scraper | Stop extracting; pass `None` to scraper |
| `journey_scraper.py` | Receives `pages_needed` but uses its own page-change detection | Continue using inline detection (no change needed) |
| `placeholder_orchestrator.py` | Fallback scraper path uses `pages_needed` for static scraping | Remove fallback path; use journey scraper only |
| Post-scraping | Pages visited not tracked | Extract from `context_log` navigation events |

### Implementation steps

#### Step 1: Update skeleton prompt

**File:** `src/prompt_utils.py`

Remove the section that instructs the LLM to emit `# PAGES_NEEDED:` comments. Search for the prompt template that includes:

```
# PAGES_NEEDED:
- page_name, https://url
```

Remove this instruction entirely. The LLM no longer needs to declare pages.

#### Step 2: Update orchestrator

**File:** `src/orchestrator.py`

In `run_pipeline()` and `_generate_combined_skeleton_for_conditions()`:

- Remove calls to `self.parser.parse_pages_needed(raw_skeleton)`
- Pass `pages_needed=None` to `_scrape_journeys_statefully()`
- After scraping completes, extract actual pages visited from the scraper's context log

#### Step 3: Update placeholder orchestrator

**File:** `src/placeholder_orchestrator.py`

The fallback scraper path (when journey scraper isn't used) currently relies on `pages_needed` to know which URLs to scrape statically. Remove this fallback path — the journey scraper with inline page detection is the only path now.

#### Step 4: Expose pages visited from journey scraper

**File:** `src/journey_scraper.py`

Add a method to extract the list of unique pages visited from the context log:

```python
def get_pages_visited(self) -> list[str]:
    """Return unique URLs visited during the journey."""
    pages = []
    seen = set()
    for entry in self._context_log:
        if entry.get("event") == "navigation":
            url = entry.get("url")
            if url and url not in seen:
                pages.append(url)
                seen.add(url)
    return pages
```

#### Step 5: Update skeleton_parser

**File:** `src/skeleton_parser.py`

Keep `parse_pages_needed()` but mark as deprecated. Don't fail if the comment is missing:

```python
@deprecated("Pages are now discovered organically by the journey scraper")
def parse_pages_needed(self, skeleton: str) -> list[tuple[str, str]]:
    ...
```

#### Step 6: Update tests

- Update any tests that expect `pages_needed` in the pipeline output
- Add a test that verifies page discovery works without PAGES_NEEDED comment in skeleton
- Add a test that verifies the journey scraper's `get_pages_visited()` returns correct pages

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Existing skeletons in `generated_tests/` still have PAGES_NEEDED | High | Low | Parser handles both with and without comment |
| UI depends on pages_needed for progress display | Medium | Medium | Extract from scraper context log instead |
| CLI reports reference pages_needed | Low | Low | Use `get_pages_visited()` output |

---

## Acceptance Criteria

- [x] Skeleton prompt no longer instructs LLM to emit PAGES_NEEDED
- [x] Pipeline runs successfully without PAGES_NEEDED in skeleton output
- [x] All pages are still scraped correctly (verified by context_log navigation events)
- [x] Placeholder resolution works correctly (same or better than before)
- [x] Existing tests pass (backward compatible) — 776 tests passed
- [x] New test added: page discovery without PAGES_NEEDED
- [x] Variability script shows no regression in page coverage

## Implementation Summary

### Files Modified

| File | Change |
|------|--------|
| `src/prompt_utils.py` | Removed PAGES_NEEDED section from skeleton prompt template |
| `src/orchestrator.py` | Removed `pages_needed` extraction from pipeline; added `get_pages_visited()` from scraper context log; updated UI progress and test file output |
| `src/placeholder_orchestrator.py` | Removed `build_static_scraper_path()` and `resolve_all_from_static_path()`; added `build_journey_scraper_path()`, `resolve_all_from_journey_path()`; made `page_requirements` optional in `run_placeholder_resolution()` |
| `src/journey_scraper.py` | Added `get_pages_visited()` method to extract unique URLs from context log |
| `src/skeleton_parser.py` | Marked `parse_pages_needed()` as deprecated with warning |
| `tests/test_prompt_utils.py` | Updated test to assert PAGES_NEEDED is **not** in skeleton prompt |
| `tests/test_orchestrator.py` | Added `test_orchestrator_extract_pages_visited` and `test_orchestrator_pages_visited_deduplicates` |
| `docs/specs/FEATURE_SPEC_remove_pages_needed.md` | Updated status to Complete |

### Key Design Decisions
1. **Journey scraper as sole path:** Replaced static fallback scraper with journey scraper path, as inline page-change detection is more reliable than pre-declared page lists
2. **Backward compatible:** `parse_pages_needed()` retained (deprecated) for any existing skeletons that still include the comment
3. **Optional page_requirements:** `run_placeholder_resolution()` accepts `page_requirements=None`, falling back to journey scraper's organic page discovery

---

## Related Issues

- **Variability analysis**: `scripts/debug/skeleton_variability_report.md` — Shows 60% of runs miss pages
- **Related but separate**: `_discover_selector()` silent failure (see `FEATURE_SPEC_journey_scraper_silent_failure.md`) — Even after this fix, if the scraper can't find an element to click, it won't navigate. That's a separate issue to fix.

---

## Known Limitations

This fix **only** solves the PAGES_NEEDED reliability problem. It does NOT solve the case where the journey scraper fails to find a clickable element and therefore never navigates to the next page. That requires the companion fix: `_discover_selector()` silent failure handling.

---

*Last updated: 2026-05-22 (completed)*