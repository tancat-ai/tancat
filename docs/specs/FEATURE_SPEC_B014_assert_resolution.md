# FEATURE SPEC — B-014 ASSERT Tokens Resolving to Wrong Elements

**Status:** In Progress
**Created:** 2026-06-04
**Depends on:** `src/placeholder_scorers.py`, `src/intent_matcher.py`, `src/placeholder_resolver.py`
**Priority:** High — False green tests are a demo blocker

---

## Problem Statement

ASSERT placeholders for "confirmation message" resolve to interactive elements
like `.cart_quantity_delete` (delete button) instead of the actual confirmation
popup. The resolver matches on shared attributes (e.g., `data-product-id`)
rather than assertion intent.

### Concrete Failure

On automationexercise.com, test_04 and test_06 generate ASSERT placeholders for
"confirmation message". The resolver ranks `.cart_quantity_delete` as the best
match because:

1. `_product_id_bonus` gives +20 when product words match `data-product-id` on the delete button
2. `_assertion_candidate_bonus` gives +2 for div/p/span with text (too permissive)
3. No penalty exists for interactive elements (buttons) being used as ASSERT targets

### Why This is Critical

A silently wrong assertion is worse than a skipped test. It gives false
confidence — the core value proposition of this tool.

---

## Root Cause Analysis

### Scoring Chain for ASSERT Tokens

When resolving `{{ASSERT:confirmation message}}` against scraped elements:

| Score Component | Current Behavior | Impact |
|-----------------|------------------|--------|
| `_product_id_bonus` | +20 for product word overlap in `data-product-id` | Buttons with `data-product-id` get inflated scores |
| `_assertion_candidate_bonus` | +2 for any div/p/span with text | Too permissive — doesn't check assertion intent |
| `_assert_visibility_penalty` | -40 for hidden elements | Only catches truly hidden elements |
| `_click_role_bonus` | +3 for button/link roles | **Wrong** — applies to ASSERT too (no action guard in current code) |

### The Missing Filter

`IntentMatcher` has `SuccessAssertStrategy` for "thank you" messages and
`CartAssertStrategy` for cart assertions, but neither handles the generic case:
**ASSERT for a confirmation message should prefer non-interactive display elements**.

The scoring system has no concept of "assertion intent" — it treats all ASSERT
tokens equally regardless of whether they target a message, a page state, or
a form field.

---

## Solution Design

### Approach: Composite Scoring Adjustment for ASSERT Actions

Add assertion-aware scoring adjustments to `PlaceholderScorer` that penalize
interactive elements and reward display elements when the token is an ASSERT
targeting a message-like description.

**Changes:**

1. **`_assert_action_penalty()`** — Penalize interactive elements (buttons, links with action hrefs) when action is ASSERT and description contains message-like terms
2. **`_assert_message_bonus()`** — Reward display elements (div/p/span with confirmation-like text) when action is ASSERT and description contains message-like terms
3. **Fix `_click_role_bonus`** — Already guarded by `action != "CLICK"` return, but verify it doesn't leak to ASSERT
4. **Update `SuccessAssertStrategy`** — Expand to cover "confirmation message" patterns

### Implementation Details

#### 1. `_assert_action_penalty()` in `PlaceholderScorer`

```python
@staticmethod
def _assert_action_penalty(action: str, description: str, element: dict[str, Any]) -> int:
    """Penalize interactive elements for ASSERT targeting message-like descriptions."""
    if action != "ASSERT":
        return 0

    lowered = description.lower()
    if not any(term in lowered for term in ("message", "confirmation", "success", "alert", "notification", "popup")):
        return 0

    role = str(element.get("role", "")).strip().lower()
    tag = str(element.get("tag", "")).strip().lower()
    href = str(element.get("href", "")).strip()

    # Buttons are poor assertion targets for messages
    if role in {"button", "submit"} or tag == "button":
        return -15

    # Links with action-oriented hrefs are poor targets
    if (role == "link" or tag == "a") and href:
        if any(term in href.lower() for term in ("delete", "remove", "cart", "action")):
            return -10

    return 0
```

#### 2. `_assert_message_bonus()` in `PlaceholderScorer`

```python
@staticmethod
def _assert_message_bonus(action: str, description: str, element: dict[str, Any]) -> int:
    """Reward display elements for ASSERT targeting message-like descriptions."""
    if action != "ASSERT":
        return 0

    lowered = description.lower()
    if not any(term in lowered for term in ("message", "confirmation", "success", "alert", "notification", "popup")):
        return 0

    role = str(element.get("role", "")).strip().lower()
    tag = str(element.get("tag", "")).strip().lower()
    text = str(element.get("text", "")).strip().lower()
    aria_label = str(element.get("aria_label", "")).strip().lower()
    aria_role = str(element.get("aria_role", "")).strip().lower()

    # Dialog/alert roles are ideal for confirmation messages
    if role in {"dialog", "alertdialog", "alert", "status"}:
        return 15

    # ARIA-based alert roles
    if aria_role in {"dialog", "alertdialog", "alert", "status"}:
        return 12

    # Content elements with confirmation-like text
    if tag in {"div", "p", "span"} and text:
        if any(term in text for term in ("confirm", "success", "thank", "order", "complete", "done")):
            return 10

    # ARIA label with confirmation-like content
    if aria_label and any(term in aria_label for term in ("confirm", "success", "thank", "complete")):
        return 8

    return 0
```

#### 3. Expand `SuccessAssertStrategy` in `IntentMatcher`

Add "confirmation message" patterns to the success/assertion terms:

```python
class SuccessAssertStrategy(IntentStrategy):
    """Thank-you / order-confirmed / success / confirmation message ASSERT matching."""

    _SUCCESS_TERMS = (
        "thank you",
        "thankyou",
        "success",
        "order confirmed",
        "order complete",
        "confirmation message",
        "confirmation",
        "success message",
        "alert message",
        "notification",
    )
    _SUCCESS_ELEMENT_TEXT = (
        "thank you",
        "thankyou",
        "order confirmed",
        "order complete",
        "order summary",
        "confirmation",
        "success",
        "confirmed",
        "completed",
        "done",
    )
```

#### 4. Integration in `compute_element_score()`

Add the two new scoring functions to the adjustment chain:

```python
score += PlaceholderScorer._assert_action_penalty(action, description, element)
score += PlaceholderScorer._assert_message_bonus(action, description, element)
```

---

## Files to Modify

| File | Change |
|------|--------|
| `src/placeholder_scorers.py` | Add `_assert_action_penalty()` and `_assert_message_bonus()` methods; integrate into `compute_element_score()` |
| `src/intent_matcher.py` | Expand `SuccessAssertStrategy._SUCCESS_TERMS` and `_SUCCESS_ELEMENT_TEXT` |

---

## Testing Strategy

| Test | Type | Description |
|------|------|-------------|
| `test_assert_action_penalty_rejects_buttons` | Unit | ASSERT for "confirmation message" penalizes button elements |
| `test_assert_action_penalty_allows_display` | Unit | ASSERT for "confirmation message" does not penalize div/p/span |
| `test_assert_message_bonus_rewards_dialog` | Unit | ASSERT for "confirmation message" rewards dialog/alert roles |
| `test_assert_message_bonus_rewards_confirmation_text` | Unit | ASSERT rewards div/p with confirmation-like text |
| `test_assert_message_bonus_ignored_for_click` | Unit | Message bonus is 0 for non-ASSERT actions |
| `test_success_assert_expanded_terms` | Unit | SuccessAssertStrategy matches "confirmation message" |
| `test_product_id_bonus_does_not_override_assert_penalty` | Integration | Full scoring: penalty + bonus outweigh product_id bonus for ASSERT |
| UAT test_04, test_06 | E2E | Verify fix against automationexercise.com |

---

## Success Criteria

- [ ] ASSERT tokens for "confirmation message" no longer resolve to `.cart_quantity_delete` or similar interactive elements
- [ ] ASSERT tokens resolve to dialog/alert/status elements or divs with confirmation-like text
- [ ] UAT test_04 and test_06 pass (or show improved resolution)
- [ ] Existing tests continue to pass (no regression in FILL/CLICK resolution)
- [ ] `ruff`, `mypy`, `pytest` pass

---

## Risk Assessment

| Risk | Mitigation |
|------|-----------|
| Over-penalizing legitimate ASSERT on buttons | Only penalize when description contains message-like terms |
| Breaking existing ASSERT patterns | Narrow scope: only affects ASSERT + message-like descriptions |
| UAT still fails after fix | May indicate need for deeper resolver redesign; document as known limitation |

---

## Session Tracking

| Date | Activity | Notes |
|------|----------|-------|
| 2026-06-04 | Spec created | Root cause: product_id_bonus + missing assert intent filter |

---

*Last updated: 2026-06-04*