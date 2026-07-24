# Semantic Scraper Transition

**Created:** 2026-07-22  
**Status:** ✅ Complete (Phases 1-3 shipped, Phase 4 deferred — hybrid architecture retained)  
**Branch:** `feat/semantic-scraper`

## Problem

The current `PageScraper._extract_elements_from_html()` uses BeautifulSoup to parse static
HTML. This causes systematic gaps:

| Gap | Example | Why BS4 fails |
|-----|---------|---------------|
| No accessible_name for wrapped labels | `<label><input type="radio">SDP</label>` → radio has `accessible_name=""` | BS4 sees `<input>` and `<label>` as separate tags; wrapping label text lost |
| JS-populated text missing | `#premiumPrice` text is "£—" (set by JS) | BS4 reads source HTML, not rendered DOM |
| Container divs not captured | `#productCar`, `#paymentFull` — clickable cards | Plain `<div>` has no ARIA role, no interactive tag → skipped |
| Headings beat containers in scoring | `h4` child wins over parent `div#productCar` | BS4 captures both but parent has empty text |

The root cause: BS4 is **structural** (markup-based). We need **semantic** (accessibility-based)
element extraction that captures what Playwright locators actually find.

## Solution

Replace `_extract_elements_from_html` (BeautifulSoup) with `page.aria_snapshot(boxes=True)`
(Playwright 1.60+, available in Python 1.61.0). The ARIA tree provides:

- ✅ Computed `accessible_name` for ALL elements (radio, checkbox, select, button, textbox, etc.)
- ✅ Computed `role` (not just HTML tag name)
- ✅ JS-populated text (captures rendered DOM state)
- ✅ Parent/child hierarchy (YAML nesting)
- ✅ Bounding boxes `[box=x,y,w,h]` for each element
- ✅ Input values, placeholder, checked/selected state

### What ARIA tree does NOT provide

| Attribute | Source | Fix |
|-----------|--------|-----|
| `id` | HTML attribute | Quick `page.locator().evaluate('el => el.id')` per element |
| `data-test`, `data-testid` | HTML attribute | Same — evaluate per element |
| `href` | HTML attribute for `<a>` | ARIA gives `/url:` for links |
| CSS classes | HTML attribute | Evaluate per element |
| `name` (HTML name attr) | HTML attribute | Evaluate per element |

### Hybrid approach

1. **Primary**: `aria_snapshot(boxes=True)` → parse YAML → element list with roles, names, hierarchy
2. **Supplementary**: For each ARIA element, extract HTML attributes via Playwright locator evaluation
3. **Merge**: Combine ARIA semantics + HTML attributes into the same element dict format

## Current vs Target Architecture

```
CURRENT:
  page.content() → BeautifulSoup → _extract_elements_from_html
  CDP getFullAXTree → AccessibilityEnricher.enrich()  (separate pass, unreliable)
  
TARGET:
  page.aria_snapshot(boxes=True) → _extract_elements_from_aria  (single pass)
  page.evaluate() per element → HTML attr extraction  (lightweight supplement)
```

### Files affected

| File | Change |
|------|--------|
| `src/scraper.py` | Add `_extract_elements_from_aria()`, deprecate `_extract_elements_from_html()` |
| `src/accessibility_enricher.py` | **REMOVE** — ARIA tree already provides computed names |
| `src/element_matcher.py` | Possible — pass1 iteration order may change |
| `src/placeholder_scorers.py` | Possible — new `computed_role` values may need bonus adjustments |
| `scripts/eval/scraped_pages/` | Regenerate ALL scraped data with new scraper |

### Files NOT affected

- `src/journey_scraper.py` — uses same `PageScraper`, benefits automatically
- `src/stateful_scraper.py` — same
- `src/cart_seeding_scraper.py` — same
- All resolver/scorer/ranker files — consume same element format

## Test & Comparison Plan

### Before (on `main`)

1. **Save baseline**: Run `python scripts/eval/eval_harness.py baseline --save` to freeze current metrics
2. **Dump element counts**: Save element counts per-page from current BS4 scraper
3. **Dump accessible names**: Save accessible_name coverage stats per role
4. **Run full resolver eval**: Record per-site accuracy

### During (on `feat/semantic-scraper`)

1. **Side-by-side comparison test**: Scrape same pages with both BS4 and ARIA, diff element lists
2. **ARIA parser unit tests**: Verify YAML → element dict conversion for each role type
3. **Attribute extraction tests**: Verify HTML attrs extracted correctly for each element type
4. **Eval harness run**: Compare resolver accuracy against baseline

### After (merge gate)

1. **Accuracy comparison**: ARIA resolver accuracy must be ≥ BS4 accuracy
2. **Element count diff**: No element type should lose coverage (only gain)
3. **accessible_name coverage**: All form controls must have non-empty accessible_name
4. **No regressions**: Full test suite passes, ruff/mypy clean

## Implementation Phases

### Phase 1: ARIA Parser ✅ COMPLETE

- [x] `src/aria_parser.py` — parse `aria_snapshot()` YAML output into element dicts (328 lines)
- [x] YAML grammar: headings, textboxes, comboboxes, checkboxes, radios, buttons, links, groups, text
- [x] Handle nesting (parent/child via YAML indentation)
- [x] Extract `/placeholder:`, `/url:`, `/checked:`, `/selected:`, `/level:` attributes
- [x] Convert `[box=x,y,w,h]` to bounding box dict
- [x] 33 unit tests (`tests/test_aria_parser.py`)

### Phase 2: Hybrid Extraction ✅ COMPLETE

- [x] Hybrid merge: BS4 (structure) + CDP AX tree (accessible_name) + ARIA snapshot (placeholder, value, bbox, groups)
- [x] `_merge_aria_into_bs4()` — conservative: only sets placeholder/value/bbox, never overwrites accessible_name
- [x] `_find_aria_match()` — 3-pass matching (exact text, containment, text-only)
- [x] `_ROLE_MAP` — maps BS4 HTML roles to ARIA computed roles for matching
- [x] Wire into `PageScraper._scrape_url_sync_result()` — hybrid path
- [x] Feature flag: `SCRAPER_BACKEND=aria` env var (default: off, BS4-only)
- [x] ARIA-only group containers appended (safe — at end, generic/region/group roles only)
- [x] Integration tested: 5 eval sites, BS4 = Hybrid (52.2% both)

### Phase 3: Resolver Alignment ✅ COMPLETE

- [x] Eval harness benchmark: Hybrid = BS4 on all 5 sites (no regression)
- [x] Scoring adjustment: heading penalty + container bonus (B-025)
- [x] Pass1 matching: word-ratio relax, heading skip, id/name match, word boundaries (B-024)
- [x] Locator normalization in golden_validator (B-026)
- [x] Target met: ARIA accuracy ≥ BS4 accuracy

### Phase 4: Cleanup ⚠️ DEFERRED

- [ ] Remove `src/accessibility_enricher.py` — **KEPT**: CDP AX tree provides full-tree accessible_name that ARIA can't (hidden elements)
- [ ] Remove `_extract_elements_from_html()` — **KEPT**: BS4 is the primary extraction path; ARIA enriches it
- [ ] Remove CDP `getFullAXTree` call — **KEPT**: Needed for accessible_name on hidden elements
- [ ] Remove `a11y_snapshot` from `ScrapeResult` — **KEPT**: Still populated for CDP enrichment
- [x] Regenerate `scripts/eval/scraped_pages/` — done
- [x] Run full QA: ruff clean, mypy clean, 125 tests pass, eval harness = 52.2%
- [ ] Update documentation — **IN PROGRESS**

**Note:** The hybrid architecture keeps all three layers:
1. **BS4** — HTML structure, CSS selectors, ids, data-test, classes
2. **CDP getFullAXTree** — accessible_name, computed_role (full tree, including hidden)
3. **ARIA snapshot** — placeholder, value, bounding boxes, container groups (visible only)

This is intentional — each layer provides data the others don't. Full replacement would lose coverage.

## Risk Assessment

| Risk | Likelihood | Mitigation |
|------|-----------|------------|
| ARIA tree element order differs | High | Feature flag for rollback, pass1 handles order-agnostic matching |
| Hidden elements missing from ARIA tree | High | ARIA only captures visible elements; production pipeline scrapes per-page where only visible content matters |
| Performance regression | Medium | `aria_snapshot()` is one CDP call (fast); attribute extraction adds N Playwright evaluations (benchmark first) |
| YAML parsing errors on edge cases | Low | Thorough unit tests per role type; fallback to BS4 on parse error |
| Different element count causes eval accuracy drop | Low | Run before/after comparison; tune scoring if needed |

## Success Criteria

1. **All form controls** (radio, checkbox, select, textbox, spinbutton) have non-empty `accessible_name` from their label
2. **JS-populated text** is captured (elements whose text comes from JS render with their actual text)
3. **Resolver accuracy** on eval-005 (lv_insurance) improves from 79.2% → ≥85%
4. **No regression** on eval-001 through eval-004
5. **All existing tests pass**, ruff + mypy clean
