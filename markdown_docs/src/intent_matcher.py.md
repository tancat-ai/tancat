# `src/intent_matcher.py`

## High-Level Purpose

Intent-based element filtering for placeholder resolution. Uses a strategy-registry architecture where each intent category is a standalone `IntentStrategy` implementation. `IntentMatcher.matches()` is a thin dispatcher that iterates registered strategies until one returns a definitive `True` or `False`. Prevents the resolver from latching onto irrelevant elements (e.g., newsletter subscribe inputs when the user story says "add to cart").

## Module Metadata

- **Lines:** 561
- **Imports:** `abc.ABC`, `abc.abstractmethod`, `typing.Any`, `src.semantic_matcher.SemanticMatcher`

## Architecture

Strategy-registry pattern: `IntentMatcher` dispatches over a list of `IntentStrategy` instances. Each strategy returns `True` (accept), `False` (reject), or `None` (indifferent — pass to next strategy). Default: accept if no strategy claims the intent.

## Shared Helpers

### `_all_element_text(element: dict) -> str`
Concatenate all searchable text fields of element (selector, text, href, classes, icon_classes, visual_description, parent_text, aria_icon_label, value, data_test, name, placeholder, aria_label, accessible_name).

### `_is_fillable(element: dict) -> bool`
Return `True` when the scraped element supports text entry. Checks role, selector prefix, and presence of name/placeholder. Excludes hidden fields and CSRF/token fields.

### `_description_words(description: str) -> set[str]`
Tokenized words longer than 3 characters.

## Strategy Implementations

| Strategy | Action Scope | Purpose |
|----------|-------------|---------|
| `ExactIdStrategy` | All | Match when element id/data-test contains description tokens |
| `SemanticFillStrategy` | FILL | Semantic similarity for fillable elements; FORM_FIELD_MAP for common field names |
| `LoginIntentStrategy` | All | Login/logout/sign-in intent matching |
| `SubscribeGuardStrategy` | All | Prevent subscribe/newsletter elements matching unrelated intents |
| `PageStateAssertStrategy` | ASSERT | Reject element-level matches for page-state assertions |
| `ProductCardStrategy` | CLICK | Match product card elements |
| `CartIntentStrategy` | CLICK | Cart navigation and add-to-cart matching |
| `CheckoutIntentStrategy` | CLICK | Checkout navigation and order completion |
| `CartAssertStrategy` | ASSERT | Cart/checkout/item ASSERT matching |
| `SuccessAssertStrategy` | ASSERT | Thank-you/order-confirmed ASSERT matching |
| `ContinueShoppingStrategy` | CLICK | Continue shopping/checkout button matching |
| `ProductNameStrategy` | CLICK, ASSERT | Product-name word overlap (fallback) |

## Class: `IntentMatcher`

### `__init__(strategies: list[IntentStrategy] | None = None)`
Use default strategy registry unless explicit list supplied.

### `matches(action, description, element) -> bool` (static)
Backwards-compatible static entry point. Creates default registry instance and dispatches.

### `match(action, description, element) -> bool`
Instance method — iterate strategies until one returns a definitive answer. Default: `True` (accept).

## Dependencies

`src.semantic_matcher` (SemanticMatcher.get_words, SemanticMatcher.semantic_similarity)

## Depended On By

`placeholder_resolver.py` — intent filtering during candidate ranking