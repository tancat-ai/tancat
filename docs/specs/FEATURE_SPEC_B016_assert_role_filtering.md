# Feature Spec — B-016 ASSERT Role Filtering (Soft)

**Created:** 2026-06-25
**Status:** Ready for implementation
**Priority:** Medium — 2 of 6 saucedemo ASSERTs still wrong after B-014
**Depends on:** B-014 (step-context exclusion already implemented)
**Design:** Grilling session 2026-06-25 (see `CONTEXT.md` §Decisions)

---

## 1. Problem Statement

After B-014 (step-context exclusion), ASSERT placeholders still resolve to wrong
interactive elements (buttons, links) when the wrong element is NOT the immediately
preceding interactive step.

### Concrete Failures (saucedemo UAT, 2026-06-25, post B-014)

| ASSERT Description | Resolved To | Why Wrong |
|---|---|---|
| `"cart badge with count 1"` | `.shopping_cart_link[data-test="shopping-cart-link"]` | Cart **link** wins because `data-test` contains "cart" |
| `"Sauce Labs Backpack item in cart"` | `#remove-sauce-labs-backpack` | REMOVE **button** wins because `id` contains "backpack" |

**Pattern:** ASSERT resolves to an interactive element (button, link) whose
structural attributes (`id`, `data-test`) contain keywords from the description,
even though the intended target is a display element (badge text, product name).

### Why scoring cannot fix this

The scoring pipeline ranks by keyword overlap in `id`, `data-test`, and structural
attributes. An interactive element with "cart" in its `data-test` attribute will
always score well for "cart badge" — the scoring logic doesn't know that a badge
should be a display element, not a clickable link.

### Out of scope (spun off as B-019)

`"Thank You page message"` → SKIP. This is a scraper gap (BeautifulSoup doesn't
capture heading text from SVG/JS-rendered pages), not a resolver quality issue.

---

## 2. Root Cause

`_pass2_structural_match()` and Pass 3 scoring have **no awareness of element role**.
They return the first element whose structural attributes overlap with the
description, regardless of whether it's a button, link, or heading.

`_pass1_assert_text_match()` DOES filter by `text_bearing_roles` — but only for
exact text containment. When no display element's text matches the description,
Pass 1 returns `None` and falls through to Pass 2 (unfiltered) and Pass 3
(unfiltered), where interactive elements win.

Additionally, the resolver uses the raw `role` field from BeautifulSoup
(HTML `role` attribute or tag-name fallback) and ignores `computed_role` from the
CDP AX tree enrichment (AI-024).

---

## 3. Solution Design

### Core Rule

> **For ASSERT actions, prefer elements with display roles (heading, paragraph,
> text, status, etc.) over interactive elements (button, link, textbox). Fall back
> to all elements if no display-role candidate scores competitively.**

This is **soft filtering** — we prefer display elements but never skip solely due
to role. If the best match is an interactive element and no display element is
close enough, we log a low-confidence warning and return the interactive element.

### Display Roles

```python
DISPLAY_ROLES = frozenset({
    "heading",      # page/section titles
    "paragraph",    # body text
    "text",         # standalone text nodes
    "status",       # live announcements
    "alert",        # error/warning messages
    "listitem",     # list entries
    "cell",         # table data cells
    "columnheader", # table column headers
    "rowheader",    # table row headers
    "image",        # images (assert visibility)
    "strong",       # emphasized text
    "em",           # italicized text
    "caption",      # table/figure captions
    "figure",       # figures with captions
})
```

**Notably excluded:** `link` and `textbox` are leaf ARIA roles but are interactive.
ASSERT descriptions like "cart badge" should not match cart links by keyword overlap.

### Role Resolution

```python
def _get_effective_role(element: dict[str, str]) -> str:
    """Resolve ARIA role: computed_role (CDP AX tree) → raw role (HTML attr/tag)."""
    return str(element.get("computed_role") or element.get("role", "")).strip().lower()
```

`computed_role` is set by the CDP AX tree enrichment (AI-024) but currently
ignored by the resolver. This is the first pass to use it.

### Implementation — Per-Pass Filtering (Option A)

Role filtering is added inside each pass function for ASSERT. This keeps the
existing structure intact — each pass is independently correctable.

#### Pass 1 ASSERT text match (existing — already filtered)

No change needed. `_pass1_assert_text_match()` already filters by `text_bearing_roles`.
Update it to also check `computed_role` alongside the raw `role`.

#### Pass 2 structural match (new filter)

For ASSERT, skip elements whose effective role is NOT in `DISPLAY_ROLES` AND
is interactive (button, link, textbox, etc.):

```python
def _pass2_structural_match(self, action, description, pages_data):
    if action not in {"CLICK", "FILL", "ASSERT"}:
        return None
    # ... existing logic ...
    for element in elements:
        if action == "ASSERT" and not self._is_display_role(element):
            continue
        # ... structural matching ...
```

#### Pass 3 scoring (new soft filter)

For ASSERT, split candidates into display-role and non-display-role groups:

```python
# After collecting all_ranked from all pages...
display_ranked = [(s, e) for s, e in all_ranked if self._is_display_role(e)]
other_ranked = [(s, e) for s, e in all_ranked if not self._is_display_role(e)]

if display_ranked:
    best_display = display_ranked[0]
    global_top = all_ranked[0][0]
    gap = global_top - best_display[0]

    if gap <= ROLE_FALLBACK_GAP:  # 3 points
        return best_display[1]
    else:
        logger.warning("[RESOLVE] low-confidence fallback: no display element "
                       "within %d of top score %s for '%s'", ROLE_FALLBACK_GAP, global_top, description)
        # Fall through to return global best (may be interactive)

return all_ranked[0][1] if all_ranked else None
```

### Helper Method

```python
DISPLAY_ROLES = frozenset({
    "heading", "paragraph", "text", "status", "alert",
    "listitem", "cell", "columnheader", "rowheader",
    "image", "strong", "em", "caption", "figure",
})

ROLE_FALLBACK_GAP = 3  # points — tunable after UAT


def _get_effective_role(self, element: dict[str, str]) -> str:
    return str(element.get("computed_role") or element.get("role", "")).strip().lower()


def _is_display_role(self, element: dict[str, str]) -> bool:
    """Check if an element's effective role is a display (non-interactive) role."""
    role = self._get_effective_role(element)
    if role in self.DISPLAY_ROLES:
        return True
    # Also check raw tag for elements without computed_role
    tag = str(element.get("tag", "")).strip().lower()
    if tag in {"h1", "h2", "h3", "h4", "h5", "h6", "p", "span", "label", "li", "td", "th"}:
        return True
    return False
```

---

## 4. Files to Modify

| File | Change |
|------|--------|
| `src/placeholder_orchestrator.py` | Add `DISPLAY_ROLES`, `ROLE_FALLBACK_GAP`, `_get_effective_role()`, `_is_display_role()`. Update `_pass1_assert_text_match()` to check `computed_role`. Add role filter to `_pass2_structural_match()` for ASSERT. Add soft filter to Pass 3 scoring for ASSERT. |

### Files NOT changed

| File | Reason |
|------|--------|
| `src/placeholder_resolver.py` | No changes — role filtering is at orchestrator level |
| `src/accessibility_enricher.py` | No changes — `computed_role` is already written, resolver just reads it |
| `src/scraper.py` | No changes — scraper gap is B-019 |

---

## 5. Testing Strategy

### Unit tests (new: `tests/test_b016_role_filtering.py`)

| Test | Description |
|------|-------------|
| `test_get_effective_role_prefers_computed` | `computed_role=heading` + `role=h1` → returns `heading` |
| `test_get_effective_role_falls_back_to_raw` | No `computed_role`, `role=button` → returns `button` |
| `test_is_display_role_true_for_heading` | `computed_role=heading` → True |
| `test_is_display_role_true_for_paragraph` | `computed_role=paragraph` → True |
| `test_is_display_role_false_for_button` | `computed_role=button` → False |
| `test_is_display_role_false_for_link` | `computed_role=link` → False |
| `test_is_display_role_tag_fallback` | No `computed_role`, `tag=h1` → True |
| `test_is_display_role_tag_fallback_span` | No `computed_role`, `tag=span` → True |
| `test_pass2_structural_skip_interactive_for_assert` | ASSERT on page with button and heading → heading returned, not button |
| `test_pass2_structural_allows_all_for_click` | CLICK on page → no role filtering applied |
| `test_pass3_soft_filter_returns_display` | Best display score within gap → display element returned |
| `test_pass3_soft_filter_fallback_to_interactive` | Best display score exceeds gap → interactive returned with warning |
| `test_pass3_soft_filter_no_display_elements` | Zero display elements → fallback to all |

### UAT

Run `scripts/uat/uat_automationexercise.py --site saucedemo` and verify:
- `"cart badge with count 1"` → NOT `.shopping_cart_link`
- `"Sauce Labs Backpack item in cart"` → NOT `#remove-sauce-labs-backpack`

---

## 6. Success Criteria

- [ ] Pass 2 structural match skips interactive elements for ASSERT
- [ ] Pass 3 scoring applies soft role filtering for ASSERT
- [ ] CLICK/FILL resolution unchanged (no role filtering for interactive actions)
- [ ] Low-confidence warning logged on soft-fallback
- [ ] `ruff`, `mypy`, `pytest` pass
- [ ] UAT against saucedemo shows improved ASSERT resolution for the 2 remaining failures

---

## 7. Risk Assessment

| Risk | Mitigation |
|------|------------|
| Soft-fallback gap too aggressive (3 points) | Log low-confidence warning; tune after UAT |
| `computed_role` not on all elements | Fallback to raw `role` + tag check |
| Legitimate ASSERT on interactive element (e.g. "button is disabled") | Soft fallback returns interactive element if no display element is competitive |
| Role filtering + step-context exclusion compose incorrectly | Follow-up: review pipeline ordering in orchestrator |

---

## 8. Design Decisions (from grilling session)

| Decision | Rationale |
|----------|-----------|
| Use `computed_role` over raw `role` | CDP AX tree gives proper ARIA roles; raw role is just HTML attr or tag name |
| Define `DISPLAY_ROLES` as positive set | Easier to reason about than a negative "interactive roles" exclusion list |
| Keep resolver self-contained | No import from `AccessibilityEnricher` needed |
| Exclude `link`/`textbox` from display | Cart links shouldn't match "cart badge" by keyword overlap |
| Soft filtering, not hard | Never produce more SKIPs than before; warn instead |
| Per-pass filtering (Option A) | Keeps existing structure intact; each pass independently testable |
| No description scope awareness | Skeleton doesn't encode scope; role filtering + scoring covers the problem |
| Scraper gap spun off as B-019 | Separate concern — wrong matches vs missing data |

---

*Last updated: 2026-06-25*
