# `src/intent_matcher.py`

## High-Level Purpose

`intent_matcher.py` provides intent-based filtering for DOM elements during placeholder resolution. It decides whether a scraped element is a plausible match for an action and natural-language description such as clicking a cart button, filling an email field, asserting a popup, or rejecting newsletter elements for unrelated checkout flows.

The module uses a strategy-registry architecture. Each intent category is implemented as an `IntentStrategy`, and `IntentMatcher` dispatches through the registered strategies until one returns a definitive accept or reject decision. If no strategy has an opinion, matching defaults to accepting the element for backwards-compatible behavior.

## Dependencies

- `ABC`, `abstractmethod` from `abc` for the strategy base class.
- `Any` from `typing` for loosely shaped scraped element dictionaries.
- `SemanticMatcher` from `src.semantic_matcher` for token extraction and semantic similarity checks.

## Element Data Contract

Strategies expect `element` to be a `dict[str, Any]` containing scraped DOM metadata. Commonly inspected keys include:

- `selector`
- `text`
- `href`
- `classes`
- `icon_classes`
- `visual_description`
- `parent_text`
- `aria_icon_label`
- `value`
- `data_test`
- `name`
- `placeholder`
- `aria_label`
- `accessible_name`
- `role`
- `id`
- `tag`

Missing keys are handled defensively with `element.get(..., "")`.

## Module Helpers

### `_all_element_text(element: dict[str, Any]) -> str`

Concatenates searchable text-bearing fields from a scraped element into one lowercase string. This helper creates a broad haystack for intent strategies that match against visible text, selectors, labels, accessibility names, parent text, IDs, and test attributes.

Parameters:

- `element: dict[str, Any]` - Scraped DOM element metadata.

Returns:

- `str` - Lowercase concatenated text from the recognized element fields.

### `_is_fillable(element: dict[str, Any]) -> bool`

Determines whether an element supports text entry or selection. Hidden fields and CSRF/token/authenticity fields are rejected. Inputs, textareas, selects, textbox-like roles, and elements with a `name` or `placeholder` are accepted.

Parameters:

- `element: dict[str, Any]` - Scraped DOM element metadata.

Returns:

- `bool` - `True` if the element is treated as fillable, otherwise `False`.

### `_description_words(description: str) -> set[str]`

Tokenizes a natural-language description through `SemanticMatcher.get_words`.

Parameters:

- `description: str` - Natural-language action description.

Returns:

- `set[str]` - Significant description words as produced by `SemanticMatcher`.

## Base Class

### `class IntentStrategy(ABC)`

Abstract base class for all intent-matching strategies. Strategies use tri-state results:

- `True` - Accept the element.
- `False` - Reject the element.
- `None` - Strategy is indifferent and dispatch should continue.

#### `match(self, action: str, description: str, element: dict[str, Any]) -> bool | None`

Abstract method implemented by every concrete strategy.

Parameters:

- `action: str` - Placeholder action type such as `CLICK`, `FILL`, or `ASSERT`.
- `description: str` - Natural-language placeholder description.
- `element: dict[str, Any]` - Scraped DOM element metadata.

Returns:

- `bool | None` - Accept, reject, or no opinion.

## Strategy Implementations

### `class ExactIdStrategy(IntentStrategy)`

Matches elements when description tokens appear in element identifiers.

#### `match(self, action: str, description: str, element: dict[str, Any]) -> bool | None`

Builds an ID haystack from `id` and `data_test`, then checks for description words longer than three characters.

Returns:

- `True` if any significant description word appears in the identifier haystack.
- `None` otherwise.

### `class SemanticFillStrategy(IntentStrategy)`

Handles semantic matching for `FILL` actions against fillable form elements.

Class attributes:

- `FORM_FIELD_MAP: dict[str, set[str]]` - Maps common field descriptions such as `first name`, `zip code`, `email address`, and `phone number` to likely element IDs, names, or test identifiers.

#### `match(self, action: str, description: str, element: dict[str, Any]) -> bool | None`

Only applies when `action == "FILL"` and `_is_fillable(element)` is true. It uses semantic similarity against element IDs, data-test attributes, names, placeholders, aria labels, and accessible names. It also includes explicit handling for username, password, and mapped form-field terms.

Returns:

- `True` for high-confidence semantic or explicit form-field matches.
- `None` when the action is not fill-related, the element is not fillable, or no fill match is found.

### `class LoginIntentStrategy(IntentStrategy)`

Matches login, logout, sign-in, sign-out, and submit-oriented intents.

Class attributes:

- `_LOGIN_TERMS`
- `_LOGIN_DESCRIPTION`
- `_LOGIN_BUTTON_DESCRIPTION`
- `_LOGIN_BUTTON_TEXT`

#### `match(self, action: str, description: str, element: dict[str, Any]) -> bool | None`

Checks general login/logout descriptions against broad element text. For `CLICK` actions, it also recognizes login button descriptions and known button terms.

Returns:

- `True` for matching login/logout/sign-in elements.
- `None` otherwise. General login descriptions intentionally do not reject when no login element signal is found.

### `class SubscribeGuardStrategy(IntentStrategy)`

Prevents newsletter or subscribe elements from matching unrelated intents.

#### `_is_subscribe_element(self, element: dict[str, Any]) -> bool`

Detects subscribe/newsletter elements using broad element text and specific IDs.

Parameters:

- `element: dict[str, Any]` - Scraped DOM element metadata.

Returns:

- `bool` - `True` if the element appears to be a subscribe/newsletter element.

#### `match(self, action: str, description: str, element: dict[str, Any]) -> bool | None`

Rejects subscribe elements for cart, checkout, payment, dismissive, popup, modal, confirmation, and textless click intents.

Returns:

- `False` for subscribe elements that should not satisfy the requested intent.
- `None` when the element is not a subscribe element or no guard applies.

### `class PageStateAssertStrategy(IntentStrategy)`

Rejects element-level matches for page-state assertions.

Class attributes:

- `_PAGE_STATE_TERMS`

#### `match(self, action: str, description: str, element: dict[str, Any]) -> bool | None`

Only applies to `ASSERT` actions. Descriptions such as `home page`, `checkout page`, `cart page`, or `confirmation page` are treated as page-level assertions rather than element-level matches.

Returns:

- `False` for page-state assertion descriptions.
- `None` otherwise.

### `class ProductCardStrategy(IntentStrategy)`

Matches product card click intents.

#### `match(self, action: str, description: str, element: dict[str, Any]) -> bool | None`

Only applies to `CLICK` actions whose description includes `product card`. It checks broad element text for card-related signals.

Returns:

- `bool` for product-card click descriptions, based on card text signals.
- `None` for non-click or non-product-card descriptions.

### `class CartIntentStrategy(IntentStrategy)`

Handles cart-related click matching.

#### `match(self, action: str, description: str, element: dict[str, Any]) -> bool | None`

Only applies to `CLICK` actions. It distinguishes cart navigation, add-to-cart buttons, text-based add-to-cart matches, and cart links/icons. It explicitly rejects cart navigation links for add-to-cart intents.

Returns:

- `True` for recognized cart action matches.
- `False` for add-to-cart descriptions matched against cart navigation or elements without add-to-cart signals.
- `None` when no cart-specific rule applies.

### `class CheckoutIntentStrategy(IntentStrategy)`

Handles checkout navigation and order-completion click intents.

#### `match(self, action: str, description: str, element: dict[str, Any]) -> bool | None`

Only applies to `CLICK` actions. It matches finish/complete/place/confirm order actions, checkout navigation descriptions, and general checkout clicks. It rejects payment elements when the description asks for checkout rather than payment.

Returns:

- `True` for recognized checkout or order-completion matches.
- `False` for checkout descriptions that point at payment elements or fail required signals.
- `None` when no checkout-specific rule applies.

### `class CartAssertStrategy(IntentStrategy)`

Matches cart, checkout, and item assertions against content elements.

#### `match(self, action: str, description: str, element: dict[str, Any]) -> bool | None`

Only applies to `ASSERT` actions containing `cart`, `item`, or `checkout`. It looks for content-oriented signals such as cart descriptions, quantities, prices, summaries, products, orders, and payments. Search-only elements and cart navigation links are rejected.

Returns:

- `True` when the element appears to be relevant cart/checkout/item content.
- `False` for search-only non-cart elements or navigation-only cart links.
- `None` when the assertion is outside this strategy's scope.

### `class PopupAssertStrategy(IntentStrategy)`

Matches assertions for confirmation popups, modals, alerts, and notifications.

Class attributes:

- `_POPUP_KEYWORDS`
- `_POPUP_ELEMENT_SIGNALS`

#### `match(self, action: str, description: str, element: dict[str, Any]) -> bool | None`

Only applies to `ASSERT` actions with popup-related keywords. It accepts dialog/alert/status roles, modal-like classes or selectors, and content elements inside modal-like contexts with confirmation or success text.

Returns:

- `True` for popup/modal/alert-like elements.
- `None` when the description is not popup-related or no popup signal is found.

### `class GenericAssertStrategy(IntentStrategy)`

Fallback matching for high-level content-display assertions.

Class attributes:

- `_CONTENT_DISPLAY_TERMS`
- `_CONTENT_ROLES`
- `_CONTENT_TAGS`

#### `match(self, action: str, description: str, element: dict[str, Any]) -> bool | None`

Only applies to `ASSERT` actions whose description includes content-display terms such as `listed`, `displayed`, `appears`, `visible`, or `summary`. It accepts elements with content roles or tags when visible text is present.

Returns:

- `True` for text-bearing content display elements.
- `None` otherwise.

### `class SuccessAssertStrategy(IntentStrategy)`

Matches thank-you, order-confirmed, order-complete, and success message assertions.

Class attributes:

- `_SUCCESS_KEYWORDS`
- `_MESSAGE_KEYWORDS`
- `_SUCCESS_ELEMENT_TEXT`

#### `match(self, action: str, description: str, element: dict[str, Any]) -> bool | None`

Only applies to `ASSERT` actions. It requires both a success keyword and a message-like keyword in the description before checking element text for success or confirmation content.

Returns:

- `True` for matching success/confirmation message elements.
- `False` when both description gates pass but element text lacks required success signals.
- `None` when the assertion does not meet the success-message gates.

### `class ContinueShoppingStrategy(IntentStrategy)`

Matches continue shopping and continue checkout click intents.

#### `match(self, action: str, description: str, element: dict[str, Any]) -> bool | None`

Only applies to `CLICK` actions. It recognizes `continue shopping`, `continue button`, and `continue checkout` descriptions.

Returns:

- `True` when broad element text contains appropriate continue/shopping terms.
- `False` when a continue-related description is in scope but element text lacks required terms.
- `None` for non-click or unrelated descriptions.

### `class ProductNameStrategy(IntentStrategy)`

Fallback matching based on product-name word overlap.

Class attributes:

- `_PRODUCT_INDICATORS`

#### `match(self, action: str, description: str, element: dict[str, Any]) -> bool | None`

Applies to `CLICK` and `ASSERT` actions. It removes generic action words from the description, requires at least two remaining product words, and matches those words against element text, data-test attributes, IDs, names, and aria labels.

Returns:

- `True` when at least half the inferred product words are found in element content.
- `None` otherwise.

## Dispatcher

### `class IntentMatcher`

Thin public dispatcher over registered `IntentStrategy` instances. It centralizes the default strategy order and keeps backwards-compatible static helpers.

Class attributes:

- `FORM_FIELD_MAP: dict[str, set[str]]` - Alias to `SemanticFillStrategy.FORM_FIELD_MAP` for compatibility with external callers.
- `_all_element_text` - Static alias for module helper `_all_element_text`.
- `_is_fillable` - Static alias for module helper `_is_fillable`.

#### `__init__(self, strategies: list[IntentStrategy] | None = None) -> None`

Initializes the matcher with either a caller-supplied strategy list or the default strategy registry.

Parameters:

- `strategies: list[IntentStrategy] | None = None` - Optional explicit registry.

Returns:

- `None`

Default strategy order:

1. `ExactIdStrategy`
2. `SemanticFillStrategy`
3. `LoginIntentStrategy`
4. `SubscribeGuardStrategy`
5. `PageStateAssertStrategy`
6. `ProductCardStrategy`
7. `CartIntentStrategy`
8. `CheckoutIntentStrategy`
9. `CartAssertStrategy`
10. `PopupAssertStrategy`
11. `GenericAssertStrategy`
12. `SuccessAssertStrategy`
13. `ContinueShoppingStrategy`
14. `ProductNameStrategy`

#### `matches(action: str, description: str, element: dict[str, Any]) -> bool`

Backwards-compatible static API. It creates a default `IntentMatcher` instance and delegates to `match`.

Parameters:

- `action: str` - Placeholder action type.
- `description: str` - Natural-language placeholder description.
- `element: dict[str, Any]` - Scraped DOM element metadata.

Returns:

- `bool` - Final accept/reject result.

#### `match(self, action: str, description: str, element: dict[str, Any]) -> bool`

Iterates through the configured strategies until one returns `True` or `False`. If all strategies return `None`, it accepts by default to preserve legacy behavior.

Parameters:

- `action: str` - Placeholder action type.
- `description: str` - Natural-language placeholder description.
- `element: dict[str, Any]` - Scraped DOM element metadata.

Returns:

- `bool` - Final accept/reject result.

## Key Architectural Patterns

### Strategy Registry

Each intent family is isolated in a small `IntentStrategy` implementation. `IntentMatcher` owns the strategy ordering and dispatches without embedding category-specific logic directly in the dispatcher.

### Tri-State Matching

Strategies return `True`, `False`, or `None`. This allows high-confidence strategies and guard strategies to make definitive decisions while unrelated strategies can stay indifferent.

### Guard Strategies

Some strategies are intentionally protective rather than affirmative. Examples include rejecting subscribe/newsletter elements for cart or checkout tasks and rejecting page-level assertions from element-level matching.

### Semantic Plus Heuristic Matching

The module combines semantic similarity, exact identifier matching, explicit keyword maps, role/tag checks, and broad text haystacks. This gives the resolver multiple ways to recognize intent without relying on a single matching technique.

### Backwards Compatibility

The dispatcher preserves older call shapes through `IntentMatcher.matches(...)`, `IntentMatcher.FORM_FIELD_MAP`, and static aliases for `_all_element_text` and `_is_fillable`. The final fallback also accepts elements when no strategy has an opinion, matching legacy behavior.

### Ordered Specificity

The default strategy list starts with exact and fill-specific matches, then applies domain-specific login, subscribe, cart, checkout, assertion, popup, success, continue, and product-name fallbacks. Because the first definitive result wins, ordering is part of the matching contract.
