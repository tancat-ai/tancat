# Session - make the message-polarity floor negation-aware (2026-10-15, t-0825, B-102)

**Question:** the 2026-10-13 held-out re-measure (t-0759) stayed at 94/113, 0 hollow passes. Of the
19 misses, which are real resolver bugs that can be fixed cheaply, and which fix first?

**Answer:** the polarity floor shipped in t-0754 was negation-blind. The `#order-error` trap in
`mock_sites/ambiguous` ("Your order **could not be completed**...") carried the positive word
"completed", which cancelled the negative polarity of its own id/class, so the floor let it win
"order success message" (eval-010 c3) in both the 2026-10-12 and 2026-10-13 runs. This session makes
element-text polarity token-aware with a bounded negation window. Structural identity fields
(selector/id/class/aria-label) stay flat substring scans.

## 1. Triage of the 2026-10-13 misses (19 total)

| Class | Count | Misses |
|---|---|---|
| Polarity floor negation bug (B-102) | 1 | eval-010 c3 "order success message" -> `#order-error` (the trap) |
| `target_never_captured` | 3 | eval-008 GOTOs (2), eval-010 quantity field |
| lv wrong picks | 2 | `#dob` for the postcode criterion; Add Vehicle button |
| Page-arrival instead of element | 3 | eval-001 (saucedemo) criteria answered with URL-level evidence |
| Modal-title vs confirmation-line picks | several | `h4:has-text(...)` modal titles chosen over the confirmation line, and vice versa |
| Harness string-strict artifacts | 2 | `h4:has-text("🚗 Car Insurance")` vs tolerance `h4:has-text('Car Insurance')`; `h4:has-text("Result:")` vs tolerance `h4:has-text("Result")` |

Notes:

- The two string-strict artifacts are **gate-measurement decisions, not resolver bugs** - the
  emitted locators are correct, the comparison is stricter than the golden's own tolerance.
  Deliberately not touched here; they belong to the **B-101** golden-quality audit (a tolerance
  change moves gate-1 numbers and needs a stated reason, per B-101).
- The lv wrong picks and modal-title picks are the next resolver classes after B-102; they need
  their own triage sessions, not a blind re-run.

## 2. The bug

`PlaceholderScorer._message_outcome_conflict` (t-0754) built one identity string from the element
text **and** its structural fields, then did flat substring scans for positive/negative outcome
terms. For the trap:

- wants: positive ("success message")
- id/class: `order-error` / `error-message` -> negative signal present
- body text: "Your order could not be **completed**" -> "completed" matched as a positive signal
- result: element is both positive and negative -> no conflict -> floor lets it through

The old logic is reproduced in `test_success_message_rejects_error_sibling_with_negated_positive_text`
(the test fails on the pre-fix code: flat scan finds "completed" and reports no conflict).

## 3. The fix (`src/placeholder_scorers.py`)

- New `PlaceholderScorer._polarity_term_in_text(text, terms)`: tokenizes the text and, for each
  polarity term, looks back `_NEGATION_WINDOW = 4` tokens. A term is negated when:
  - the **immediately previous** token is `"no"` (so "Order no 123 confirmed" stays positive), or
  - any other negator in the window: `not, no, never, cannot, can't, couldn't, won't, wouldn't,
    without, failed, unable, avoid, prevent`.
- `_message_outcome_conflict` now computes element polarity as **text-polarity (negation-aware) OR
  structural-polarity (flat)** per outcome sign, and keeps the existing conflict rule
  (wants positive + element only negative, or the reverse). Absence-prefix criteria remain exempt.
- Rationale for the split: body text is phrased in sentences, so "could not be completed" is
  meaningful; a name like `error-message` is not a sentence, so token windows would only add noise.

## 4. Tests (`tests/test_t0754_accuracy_classes.py`, +3)

- `test_success_message_rejects_error_sibling_with_negated_positive_text` - the exact trap element
  from `mock_sites/ambiguous/index.html` is now rejected for "order success message"
  (`compute_element_score` returns None; `_message_outcome_conflict` True).
- `test_order_number_is_not_a_negation` - "Order no 123 confirmed" still verifies as positive
  ("no" must not open an order number).
- `test_error_criterion_rejects_element_that_negates_its_error` - "No error found. Transfer
  confirmed." rejects a "transfer error message" criterion (symmetry check).

All 10 tests in the file pass.

## 5. Gates (local, pre-push)

- smoke: pass; ruff check + format: clean; mypy `src/ cli/`: clean (164 files).
- `pytest tests/ -q`: 3901 passed, 7 skipped, **1 failed - pre-existing, not this change**:
  `tests/test_streamlit_widgets.py::TestProviderSelector::test_azure_provider_is_selectable_and_asks_for_its_key`
  fails identically on the clean `e2885d5` tree (environment-dependent warning set; verified by
  stashing the change and re-running).
- Eval static gate (`eval_harness.py run --mode static --min-accuracy 79`): **91/96 = 94.8%, exit 0** -
  identical to the pre-fix run (91/96). Static mode does not cover eval-008/eval-010 (0/0
  placeholders), so it is blind to this fix by design; the fix is verified by unit tests against
  the exact trap element.

## 6. What this does NOT change

- No held-out re-measure in this session (a full run is ~47 min and needs the local LLM; the fix
  is covered by unit tests, and the next re-measure will show whether eval-010 c3 flips).
- No harness/tolerance changes (the two string-strict artifacts stay with B-101).
- Gate 1 stays 94/113 on the last committed evidence; expected to move to 95/113 on a fresh run
  if the trap is the only miss in its class.

## 7. Next

1. Fresh held-out re-measure on the branch once merged (same settings as t-0759) - confirm
   eval-010 c3 resolves to the success element.
2. Next resolver classes from §1: the 3 `target_never_captured` (GOTO capture) and the 2 lv wrong
   picks (`#dob` for postcode; Add Vehicle).
3. B-101 for the two string-strict artifacts, with a stated reason per tolerance change.
