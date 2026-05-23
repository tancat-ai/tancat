# FEATURE_SPEC_AI024_accessibility_tree_enrichment.md

## AI-024 — Accessibility Tree Enrichment

**Status:** ✅ Implemented — 2026-05-17
**Last updated:** 2026-05-17
**Depends on:** Nothing — standalone improvement to scraper pipeline
**Blocks:** Nothing — but reduces frequency of locator failures that trigger AI-023 repair loop
**Priority:** Medium — single-session improvement with measurable impact

---

## Problem Statement

The current scraper in `src/scraper.py` extracts elements from raw HTML using BeautifulSoup. It parses static attributes (id, class, name, aria-label) but misses computed accessible names that browsers derive from:

1. **ARIA relationships** — `aria-labelledby`, `aria-describedby`, `aria-controls` reference other elements whose text content becomes the accessible name
2. **Parent element context** — a `<span>` inside a `<label for="...">` inherits the label's text as its accessible name
3. **SVG child elements** — icon buttons with embedded `<svg><title>Cart</title></svg>` expose "Cart" as the accessible name but not in raw HTML attributes
4. **Implicit roles** — `<a href="...">` has role=link automatically, `<button>` has role=button — the a11y tree computes these explicitly
5. **Image alternatives** — `<img alt="...">` and `<img>` with adjacent text get computed names from surrounding context

These are exactly the attributes a tester would see in Chrome DevTools → Accessibility panel — but our scraper doesn't capture them. When `PlaceholderResolver` tries to match `{{CLICK:View Cart}}` against an icon-only button whose accessible name is "View Cart" (from an SVG title or aria-labelledby), it fails because the raw HTML has no text to match.

---

## Design Principle

**Enrich, don't replace.**

The accessibility snapshot supplements existing DOM data — it does not replace BeautifulSoup extraction. The two sources have different strengths:

| Source | Strengths | Weaknesses |
|--------|-----------|------------|
| BeautifulSoup HTML parse | All attributes, full DOM structure, href values, classes | No computed names, no ARIA resolution |
| Accessibility snapshot | Computed accessible names, implicit roles, browser-computed state | Less detailed selectors, may miss non-interactive elements |

Merging both gives the placeholder resolver more text signals without losing attribute-level precision.

---

## Scope Constraints

**Only during scraping, not at test runtime.** The a11y snapshot is captured once when scraping pages for context. It enriches the element data that feeds into skeleton generation and placeholder resolution. Tests themselves continue to use Playwright locators directly — no a11y tree access at runtime.

**Merge at element level, not page level.** Each scraped element record gets enriched with computed accessible name if available from the a11y tree. We do not replace the element list — we add fields.

**No new dependencies.** Playwright's `page.accessibility.snapshot()` is built-in. No external libraries needed.

---

## Implementation Plan

Single Cline session. Do not split.

---

### What This Session Does

Adds `page.accessibility.snapshot()` to the scraping pipeline and merges computed accessible names back into element records.

**Files created:**
- `src/accessibility_enricher.py` — merge logic, a11y tree traversal
- `tests/test_accessibility_enricher.py` — unit tests for merge function

**Files touched:**
- `src/scraper.py` — add a11y snapshot call in `_scrape_url_sync()`, pass data to enricher

---

### Accessibility Snapshot API

```python
a11y_tree = page.accessibility.snapshot()
# Returns structure like:
# {
#   "role": "WebPage",
#   "name": "",
#   "properties": [...],
#   "childProperties": [...],
#   "children": [
#     {
#       "role": "button",
#       "name": "View Cart",  # ← computed from SVG title or aria-labelledby
#       "properties": [{"name": "controls", "value": "cart-dropdown"}],
#       "children": []
#     },
#     {
#       "role": "link",
#       "name": "",           # ← empty name — match by position or href
#       "childProperties": [{"name": "alt", "value": "Logo"}],
#       "children": [...]
#     }
#   ]
# }
```

**Key fields:**
- `role` — computed role (explicit or implicit)
- `name` — computed accessible name (from aria-label, aria-labelledby, text content, alt, title)
- `properties` — ARIA attributes as key-value pairs
- `childProperties` — properties from child elements (e.g., `<img alt>` inside `<a>`)

---

### `src/accessibility_enricher.py`

**`AccessibilityEnricher` class:**

```python
class AccessibilityEnricher:
    @staticmethod
    def enrich(elements: list[dict[str, Any]], a11y_tree: dict[str, Any]) -> list[dict[str, Any]]:
        """Merge computed accessible names from a11y tree into scraped elements.

        For each element, try to find a matching node in the accessibility tree
        and add the computed name if it provides additional information.
        """
```

**Matching strategy:**

Since the a11y tree doesn't include DOM selectors directly, matching is done by cross-referencing:

1. **By role + name** — if an element has text "View Cart" and an a11y node has name="View Cart" with role="button", match them
2. **By position in the DOM** — traverse both trees in document order, match Nth interactive element to Nth a11y node
3. **By href** — link elements can be matched by their href value appearing in a11y properties

**Fallback:** If matching fails for an element, leave it unchanged. The enricher never removes data — it only adds.

**New fields added to each element:**

```python
{
    "accessible_name": "View Cart",     # computed from a11y tree if available
    "computed_role": "button",          # explicit role from a11y (may differ from raw 'role' attr)
    "aria_describedby": "...",          # resolved text from aria-describedby reference
}
```

---

### Changes to `src/scraper.py`

In `_scrape_url_sync()`, after `page.content()` and before browser close:

```python
# Existing: extract elements from HTML
html_content = page.content()
elements = self._extract_elements_from_html(html_content, base_url=final_url)

# NEW: capture accessibility snapshot (production: CDP getFullAXTree — see scraper.py)
a11y_tree = page.accessibility.snapshot()

# NEW: enrich elements with computed accessible names
from src.accessibility_enricher import AccessibilityEnricher
elements = AccessibilityEnricher.enrich(elements, a11y_tree)
```

---

### Impact on Placeholder Resolution

The enriched element data flows through the existing pipeline:

1. `PlaceholderOrchestrator` receives elements with `accessible_name` field
2. `SemanticCandidateRanker` ranks candidates — now includes accessible name as a text signal alongside `text`, `aria_label`, and `placeholder`
3. `PlaceholderResolver.text_matches_description()` can match against computed names

**No changes needed to placeholder_resolver.py or locator_scorer.py** — they already accept the element dict and search available text fields. The new `accessible_name` field is automatically available as a matching target if we add it to the ranker's text comparison list.

---

### Unit Tests Required (minimum 6)

- `test_enrich_adds_accessible_name_when_present`
- `test_enrich_preserves_element_without_a11y_match`
- `test_enrich_matches_by_role_and_name`
- `test_enrich_handles_empty_a11y_tree`
- `test_enrich_resolves_aria_labelledby_text`
- `test_enrich_does_not_overwrite_existing_aria_label`

---

## File Summary

| File | Session | New / Modified |
|------|---------|----------------|
| `src/accessibility_enricher.py` | 1 | New |
| `tests/test_accessibility_enricher.py` | 1 | New |
| `src/scraper.py` | 1 | Modified — add a11y snapshot call |

---

## What This Does Not Do

**No changes to placeholder resolver logic.** The enricher provides better data; the resolver uses it through existing mechanisms. If the resolver needs a minor update to include `accessible_name` in text comparison, that's a one-line addition to `semantic_candidate_ranker.py`.

**No runtime a11y access.** Tests continue to use standard Playwright locators. The a11y tree is only used during the scraping phase to build better context data.

**No visual analysis.** This feature uses DOM-computed accessibility names, not image-based OCR or screenshot analysis. Visual matching is out of scope (see AI-025 for future visual regression work).

---

## Backlog Entry (copy into BACKLOG.md)

```
### AI-024 — Accessibility Tree Enrichment
**What:** Add `page.accessibility.snapshot()` to the scraping pipeline to capture
computed accessible names from ARIA relationships, parent context, and SVG children.
Merge these names back into scraped element records so the placeholder resolver has
more text signals when matching placeholders like `{{CLICK:View Cart}}`.

**Why:** Current scraper extracts raw HTML attributes only. It misses computed names
that browsers derive from aria-labelledby, label-for relationships, and embedded SVG
titles. These are precisely the names a tester would see in DevTools — but our
resolver cannot match against them because they don't exist in raw HTML.

**Spec:** docs/specs/FEATURE_SPEC_AI024_accessibility_tree_enrichment.md

**New files:**
- src/accessibility_enricher.py — merge a11y tree data with scraped elements
- tests/test_accessibility_enricher.py

**Modified files:**
- src/scraper.py — add a11y snapshot call, pass to enricher

**Impact:** Reduces locator failures by catching cases where an element has no good
attributes but has a clear accessible name. Fewer failures = fewer times AI-023
repair loop needs to trigger.

**Priority:** Medium
**Design session:** Complete — 2026-05-01
```

---

## Related Work

- **AI-023 (Interactive Locator Repair)** — AI-024 reduces the frequency of locator
  failures, meaning the repair loop is invoked less often. They are independent but
  complementary: AI-024 prevents failures; AI-023 fixes them when they occur.
- **AI-025 (Visual Regression Detection)** — Separate concern. Uses screenshot
  comparison post-run to detect UI changes. Not related to accessibility enrichment.