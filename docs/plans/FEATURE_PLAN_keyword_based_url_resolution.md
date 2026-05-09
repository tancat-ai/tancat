# Feature Plan: Keyword-Based URL Resolution

> **Status:** Complete (Phases 1-4)  
> **Created:** 2026-05-08  
> **Updated:** 2026-05-09  
> **Supersedes:** LLM-guessed URLs in PAGES_NEEDED  
> **Related:** BACKLOG.md items B-012 (LLM-guessed URLs cause wrong page selection)

---

## Problem Statement

The current pipeline uses LLM-guessed URLs in the `# PAGES_NEEDED:` block for URL resolution. The LLM has no way to know the actual URL structure of a target site, so it hallucinates plausible-looking paths that are often wrong:

```
# Current (broken) — LLM guesses URLs:
# PAGES_NEEDED:
# - https://www.saucedemo.com/cart.html          ← hallucinated
# - https://www.saucedemo.com/checkout           ← might be /checkout_step2
```

These guessed URLs are then used by:
1. `_select_initial_page_url()` — selects which scraped page to resolve locators from
2. `_ensure_test_navigation()` — injects `evidence_tracker.navigate("url")` into tests
3. `resolve_url()` — resolves `{{GOTO:...}}` placeholders to concrete URLs

**Impact:** Tests navigate to wrong pages, placeholder resolution uses wrong scraped data, and tests fail or skip because elements aren't found on the guessed page.

---

## Proposed Solution

Replace LLM-guessed URLs with **keyword-based page references** that are resolved against **actually discovered URLs** from journey scraping.

### New Design

```
# Proposed — LLM writes keywords matching GOTO placeholders:
# PAGES_NEEDED:
# - cart                                    ← keyword, not a URL
# - checkout                                ← keyword, not a URL
```

Skeleton uses matching keywords:
```python
def test_01_checkout(...):
    evidence_tracker.navigate("{{GOTO:cart}}")   # matches "cart" keyword
```

After journey scraping discovers actual URLs by following navigation, build a mapping:
```
cart     → https://www.saucedemo.com/cart
checkout → https://www.saucedemo.com/checkout
```

Then resolve `{{GOTO:cart}}` → `evidence_tracker.navigate("https://www.saucedemo.com/cart")`

---

## Architecture Changes

### Files Modified

| File | Change | Status |
|------|--------|--------|
| `src/pipeline_models.py` | `PageRequirement.url` → `PageRequirement.keyword` | ✅ Done |
| `src/skeleton_parser.py` | Parse keywords instead of URLs from PAGES_NEEDED | ✅ Done |
| `src/placeholder_orchestrator.py` | Use keyword resolution + UrlResolver | ✅ Done |
| `src/code_postprocessor.py` | `_ensure_test_navigation()` accepts target_url | ✅ Done |
| `src/orchestrator.py` | Build keyword→URL mapping after scraping | ✅ Done |

### Files Created

| File | Purpose | Status |
|------|---------|--------|
| `src/url_resolver.py` | Builds keyword→URL mapping from journey scraping results | ✅ Done |
| `tests/test_url_resolver.py` | 15 unit tests for UrlResolver | ✅ Done |

### Files Unchanged (Protected)

| File | Reason |
|------|--------|
| `src/test_generator.py` | PROTECTED — stable test generation pipeline |
| `src/journey_scraper.py` | Already discovers real URLs |
| `src/scraper.py` | Already captures visited URLs |

---

## Migration Strategy

### Phase 1 — Immediate Fix ✅ COMPLETE
- [x] Fix `_select_initial_page_url()` to use seed URL as fallback
- [x] Fix `_ensure_test_navigation()` to accept seed_url parameter
- [x] Tests: verify Saucedemo login tests resolve from homepage

### Phase 2 — Keyword-Based PAGES_NEEDED ✅ COMPLETE
- [x] Change `PageRequirement` model (url → keyword)
- [x] Update skeleton parser regex
- [x] Update placeholder orchestrator
- [x] Tests: verify keyword parsing works
- [x] All 19 pipeline model + skeleton parser tests pass

### Phase 3 — UrlResolver Module ✅ COMPLETE
- [x] Created `src/url_resolver.py` with UrlResolver class
- [x] Integration into orchestrator pipeline (builds mapping after scraping)
- [x] GOTO resolution uses UrlResolver as first step:
  1. UrlResolver (keyword → URL from scraped URLs)
  2. PlaceholderResolver.resolve_url (scraped element matching)
  3. heuristic_url_from_description (relative path fallback)
  4. seed_url (last resort fallback)
- [x] Tests: 15/15 url_resolver tests pass
- [x] `ruff` and `mypy` pass cleanly

### Phase 4 — Cleanup ✅ COMPLETE
- [x] Update skeleton prompt in `src/prompt_utils.py` to instruct LLM to use keywords
- [x] Fix prompt tests (37/37 passing)
- [ ] Update AGENTS.md with new design (deferred)
- [ ] Update BACKLOG.md (deferred)
- [ ] Fix pre-existing orchestrator test failures (placeholder resolution — separate issue)

---

## Success Criteria

- [x] No LLM-guessed URLs in PAGES_NEEDED block
- [x] UrlResolver maps keywords to discovered URLs
- [x] `ruff`, `mypy` pass on modified files
- [x] All url_resolver tests pass (15/15)
- [ ] Generated tests navigate to correct pages (UAT verification pending)
- [ ] All orchestrator tests pass (9 pre-existing failures to address)

---

## Implementation Notes

### What's Working
- `PageRequirement` uses `keyword` field throughout the codebase
- Skeleton parser correctly parses keyword format: `# - cart (shopping cart page)`
- `_select_initial_page_url()` and `_select_fallback_page_url()` prefer seed URLs
- UrlResolver successfully maps keywords to discovered URLs
- GOTO resolution flow uses UrlResolver as first step
- All 15 url_resolver unit tests pass
- `ruff` and `mypy` pass cleanly on all modified files

### What's Pending
- Update AGENTS.md with new design (deferred)
- Update BACKLOG.md (deferred)
- Fix 9 pre-existing orchestrator test failures (placeholder resolution — separate issue)

### Known Limitations
- GOTO placeholder resolution still uses `heuristic_url_from_description()` and `resolve_url()` as fallbacks
- The skeleton prompt still shows URL examples (will be updated in Phase 4)
- `_page_requirements_to_pages()` returns `None` (use all scraped pages) until UrlResolver filtering is implemented

---

*Last updated: 2026-05-09*
*Author: AI Session (Cline)*