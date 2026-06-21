# Feature Spec — B-014 Step-Context ASSERT Resolution

**Supersedes:** `FEATURE_SPEC_B014_assert_resolution.md` (scoring-based approach, incomplete)
**Created:** 2026-06-24
**Status:** Draft
**Priority:** High — silent wrong assertions are worse than skips
**Depends on:** `src/placeholder_orchestrator.py`, `src/placeholder_resolver.py`

---

## 1. Problem Statement

ASSERT placeholders resolve to the wrong elements because resolution is done in
isolation — each placeholder is matched against scraped elements with no knowledge
of the surrounding test steps. The resolver scores elements by keyword overlap and
structural attributes, which means an interactive element whose `id` or `data-test`
contains description keywords can beat the correct display element.

### Concrete Failures (saucedemo UAT, 2026-06-22)

| ASSERT Description | Resolved To | Correct Target | Why Wrong |
|---|---|---|---|
| `"inventory page title"` | `#login-button` | Page heading | Previous step CLICK resolved to `#login-button` — same element reused |
| `"cart badge shows 1"` | `.shopping_cart_link` | Cart badge element | Previous step CLICK resolved to `.shopping_cart_link` — same element reused |
| `"shopping cart header"` | `.shopping_cart_link` | Cart page heading | Previous step CLICK resolved to `.shopping_cart_link` — same element reused |
| `"sauce labs backpack in cart"` | `#remove-sauce-labs-backpack` | Product name in cart | Previous step CLICK resolved to `#remove-sauce-labs-backpack` — same element reused |
| `"checkout information form"` | `#checkout` | Checkout page heading | Previous step CLICK resolved to `#checkout` — same element reused |
| `"thank you message"` | `#user-name` | Confirmation text | Previous step FILL resolved to `#user-name` — same element reused |

**Pattern:** Every failure is "ASSERT resolves to the element from the immediately
preceding interactive step."

### Why scoring cannot fix this

The current spec (`FEATURE_SPEC_B014_assert_resolution.md`) adds scoring penalties
and bonuses. This only works for message-like assertions (containing "message",
"confirmation", "success", etc.) and requires tuning magic numbers (`+2`, `-15`).
It does not address the core problem: the wrong element wins the score because it
has keyword overlap in its `id` attribute, regardless of whether it's the right
semantic target.

---

## 2. Root Cause

`PlaceholderOrchestrator._replace_placeholders_sequentially()` iterates journey steps
and calls `_resolve_placeholder_for_page()` for each placeholder. The resolver
receives only:

- `action` (ASSERT/CLICK/FILL)
- `description` ("inventory page title")
- `current_url` (page being searched)
- `scraped_data` (all elements on page)

It does NOT receive:

- The **previous step's** resolved selector or description
- The **step sequence** (position in the flow)
- The **sibling placeholders** on the same step

Without this context, the resolver cannot know that `#login-button` was just clicked
and should not also be the target of a different ASSERT.

---

## 3. Solution Design

### Core Rule

> **When resolving an ASSERT, exclude any element whose selector was used by the
> immediately preceding interactive step (CLICK/FILL), unless the ASSERT's
> description semantically references the same element as the previous step.**

This is a **deterministic rule**, not a scoring heuristic. It does not depend on
tuning thresholds or magic numbers.

### Three-Part Implementation

#### Part A: Thread step context through the resolution loop

In `_replace_placeholders_sequentially()`, track the last resolved selector and
description. Pass them into `_resolve_placeholder_for_page()`.

```
Current signature:
  _resolve_placeholder_for_page(action, description, current_url,
                                scraped_data, scraped_errors)

New signature:
  _resolve_placeholder_for_page(action, description, current_url,
                                scraped_data, scraped_errors,
                                previous_selector: str | None = None,
                                previous_description: str | None = None)
```

Tracking logic in the loop:

```python
last_selector: str | None = None
last_description: str | None = None

for step in journey.steps:
    for placeholder in step.placeholders:
        resolved_value, next_url = await self._resolve_placeholder_for_page(
            action=action,
            description=description,
            current_url=current_url,
            scraped_data=scraped_data,
            scraped_errors=errors,
            previous_selector=last_selector,
            previous_description=last_description,
        )

        # Track for next iteration — only CLICK/FILL set the bar for exclusion
        if "pytest.skip" not in resolved_value and action in {"CLICK", "FILL"}:
            last_selector = resolved_value
            last_description = description
```

**Key decisions:**

- Only CLICK/FILL update the tracked selector — ASSERT steps don't set the
  exclusion bar (you can ASSERT the same element multiple times in a row).
- GOTO/URL don't set the bar either (navigation doesn't interact with elements).

#### Part B: Build excluded selectors in `_resolve_placeholder_for_page()`

When `action == "ASSERT"` and `previous_selector` is set, determine if the
selector should be excluded:

1. **Same description check:** If the ASSERT description semantically matches the
   previous description (using `PlaceholderResolver.text_matches_description()`),
   allow reuse — the test is asserting the same element's state.

2. **Different description:** Build `excluded_selectors = {previous_selector}`
   and pass to `_find_best_element_for_current_page()`.

The excluded selectors set is built from the robust locator string (e.g.
`"#login-button"`) AND the raw element `selector` field (e.g.
`"input#login-button"`). Both forms are excluded to handle cases where
`build_robust_locator()` produces different strings for the same element.

```python
def _build_excluded_selectors(
    self,
    action: str,
    description: str,
    previous_selector: str | None,
    previous_description: str | None,
    pages_data: dict[str, list[dict[str, str]]],
) -> set[str]:
    """Build a set of selectors to exclude for this resolution.

    For ASSERT: excludes the previous step's selector unless descriptions match.
    For CLICK/FILL: returns empty set (no exclusion).
    """
    if action != "ASSERT" or not previous_selector:
        return set()

    # Allow reuse if descriptions reference the same element
    if previous_description and self.resolver.text_matches_description(
        previous_description, description
    ):
        return set()

    # Find all selector forms for the previous element
    excluded: set[str] = {previous_selector}
    for elements in pages_data.values():
        for element in elements:
            raw_selector = str(element.get("selector", "")).strip()
            robust = build_robust_locator(element)
            # Match against both robust locator and raw selector
            if robust == previous_selector or raw_selector == previous_selector:
                excluded.add(robust or "")
                excluded.add(raw_selector)

    return {s for s in excluded if s}  # Remove empty strings
```

#### Part C: Filter excluded selectors in `_find_best_element_for_current_page()`

Add `excluded_selectors: set[str] | None = None` parameter. Filter at each pass:

- **Pass 1 (text match):** Skip elements whose selector is in excluded set.
- **Pass 1 ASSERT (text-bearing):** Same filter.
- **Pass 2 (structural):** Same filter.
- **Pass 3 (scoring):** Remove excluded candidates from `all_ranked` before
  sorting. If all candidates are excluded, return `None` (skip with message).

```python
async def _find_best_element_for_current_page(
    self,
    action: str,
    description: str,
    current_url: str | None,
    pages_data: dict[str, list[dict[str, str]]],
    excluded_selectors: set[str] | None = None,
) -> dict[str, str] | None:
```

Filter helper:

```python
@staticmethod
def _is_excluded(element: dict[str, str], excluded_selectors: set[str]) -> bool:
    """Check if an element should be excluded from consideration."""
    raw = str(element.get("selector", "")).strip()
    if raw in excluded_selectors:
        return True
    robust = build_robust_locator(element)
    if robust and robust in excluded_selectors:
        return True
    return False
```

---

## 4. Files to Modify

| File | Change |
|------|--------|
| `src/placeholder_orchestrator.py` | Thread `previous_selector`/`previous_description` through loop; add `_build_excluded_selectors()`; add `excluded_selectors` param to `_find_best_element_for_current_page()`; filter at each pass |

### Files NOT changed

| File | Reason |
|------|--------|
| `src/placeholder_scorers.py` | No scoring changes needed — exclusion is a gate, not a score |
| `src/placeholder_resolver.py` | No resolver changes — exclusion happens at orchestrator level |
| `src/intent_matcher.py` | No intent strategy changes |

---

## 5. Testing Strategy

### Unit tests (in `tests/test_b014_assert_resolution.py`)

| Test | Description |
|------|-------------|
| `test_assert_excludes_previous_click_selector` | CLICK resolves to `#x`, then ASSERT with different description → `#x` not returned |
| `test_assert_allows_same_selector_when_description_matches` | CLICK "login button", ASSERT "login button is disabled" → `#login-button` allowed |
| `test_assert_not_excluded_when_first_step` | Journey starts with ASSERT → no exclusion applied |
| `test_assert_not_excluded_for_click_after_click` | CLICK → CLICK → no exclusion (rule only applies to ASSERT) |
| `test_fill_sets_exclusion_bar` | FILL → ASSERT → previous FILL selector is excluded |
| `test_goto_does_not_set_exclusion_bar` | GOTO → ASSERT → no exclusion (navigation doesn't interact with elements) |
| `test_excluded_selectors_built_from_raw_and_robust` | Both raw selector and robust locator forms are excluded |

### Integration tests (new file: `tests/test_orchestrator_step_context.py`)

| Test | Description |
|------|-------------|
| `test_saucedemo_login_then_assert_inventory` | CLICK login-button → ASSERT "inventory page title" → login-button excluded |
| `test_saucedemo_add_to_cart_then_assert_badge` | CLICK add-to-cart → ASSERT "cart badge" → add-to-cart selector excluded |
| `test_saucedemo_checkout_then_assert_form` | CLICK checkout → ASSERT "checkout form" → checkout button excluded |

### Regression

Run full test suite to ensure no regressions in CLICK/FILL resolution.

---

## 6. Success Criteria

- [ ] All 6 B-014 saucedemo examples resolve to different elements than the previous step's selector (or skip)
- [ ] ASSERT descriptions that reference the same element as the previous step (e.g. "login button is disabled") still resolve correctly
- [ ] No regressions in existing test suite
- [ ] `ruff`, `mypy`, `pytest` pass
- [ ] UAT against saucedemo shows improved ASSERT resolution

---

## 7. What This Does NOT Fix

- ASSERT descriptions that have no overlap with previous steps but still match the
  wrong element via scoring (e.g., two completely unrelated elements where both
  have keyword overlap). This is a separate matching quality issue that the existing
  scoring penalties partially address.
- Page-level assertions like "home page is loaded" where there is no specific
  element to assert (these remain as skips, which is correct).

---

## 8. Risk Assessment

| Risk | Mitigation |
|------|------------|
| False exclusion — legitimate ASSERT on same element | Allow reuse when descriptions semantically match (`text_matches_description()`) |
| Selector form mismatch — `build_robust_locator()` produces different strings | Exclude both raw `selector` and robust locator forms |
| ASSERT chains — multiple ASSERTs on same element | Only CLICK/FILL set the exclusion bar, not ASSERT |
| Over-aggressive exclusion leaves no candidates | Returns `None` → test skips with clear message (correct behavior, better than wrong assertion) |

---

## 9. Session Plan

| Session | Scope | Deliverable |
|---------|-------|-------------|
| Session 1 | Parts A + B: thread context through loop, build excluded selectors | `_resolve_placeholder_for_page()` accepts previous context; `_build_excluded_selectors()` implemented; unit tests for exclusion logic |
| Session 2 | Part C: filter in `_find_best_element_for_current_page()` + integration tests | Exclusion applied across all passes; saucedemo scenario tests; UAT verification |

---

*Last updated: 2026-06-24*
