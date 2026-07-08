# Reliability Diagnostic Report

**Date:** 2026-07-05
**Scope:** Test generation engine output consistency analysis

---

## Summary of Findings

Analyzed 18 runs of the same user story (automationexercise browse + cart) across Jul 1-4, 2026.

### Key Metrics

| Metric | Range | Target |
|--------|-------|--------|
| Tests generated | 8 (consistent) | ✅ |
| pytest.skip lines | **1 to 9** | ≤ 2 |
| Unresolved placeholders | **1 to 9** | ≤ 2 |
| Pages scraped | 3-4 | ✅ |
| Test execution | Variable | Needs fix |

### Root Causes Identified

#### R-001: Skeleton description variance (HIGH IMPACT)
The LLM generates wildly different placeholder descriptions across runs:
- **Good:** `{{CLICK:Dress category link}}` → resolves to `a[href="/category_products/1"]`
- **Bad:** `{{CLICK:Dress category link in the left sidebar}}` → may or may not resolve
- **Bad:** `{{ASSERT:product categories section containing category links like Dress, Jackets, T-Shirts}}` → never resolves

**Problem:** Longer, more verbose descriptions have lower match probability. The resolver uses text containment and keyword overlap. Descriptions like "product categories section containing category links like Dress, Jackets, T-Shirts" are too long and specific for Pass 1 text matching.

**Fix:** Strengthen Pass 1 text matching with a "key phrase extraction" step that identifies the core entity from verbose descriptions.

#### R-002: Raw placeholder tokens surviving into output (HIGH IMPACT)
Some generated tests contain raw `{{ASSERT:...}}` tokens that weren't replaced by the orchestrator. The `_remove_raw_placeholder_lines` regex catches lines that are ONLY a placeholder, but misses:
- Placeholders wrapped in `pytest.skip('Unresolved placeholder in this step. {{ASSERT:...}}')` 
- Placeholders inside prose comments

**Fix:** Strengthen cleanup in `_insert_consolidated_skips` and `_remove_raw_placeholder_lines`.

#### R-003: Wrong URL patterns in skeleton (MEDIUM IMPACT)
LLM sometimes generates `category-product/1` instead of `category_products/1`. The journey scraper tries to navigate to this URL but gets a 404, so no elements are captured for that page.

**Fix:** URL normalization in `_scrape_journeys_statefully` to handle common path variations.

#### R-004: `GeneratedPage` catch-all page object (LOW IMPACT)
When the scraper encounters URLs that don't match a known page pattern, it generates a generic `GeneratedPage` class. These add noise to imports and instantiations.

**Fix:** Filter out catch-all page objects that have fewer than N meaningful elements.

#### R-005: ASSERT descriptions too vague for resolution (MEDIUM IMPACT)
Descriptions like "cart page table is visible with at least one product row" or "user is either logged in or prompted to login" are too abstract for keyword-based matching.

**Fix:** Improve `_pass1_assert_text_match` and scoring to handle abstract descriptions via intent-based matching.

---

## Fix Priority

1. **R-001** (Skeleton description variance) — Add key phrase extraction in resolver
2. **R-002** (Raw tokens surviving) — Strengthen cleanup passes
3. **R-005** (Vague ASSERT descriptions) — Improve intent matching
4. **R-003** (URL patterns) — URL normalization
5. **R-004** (Catch-all POM) — Filter generic pages
