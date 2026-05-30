# `src/form_detector.py`

## Purpose
Form detection and element classification utilities. Detects form fields, classifies input types, identifies submit buttons, and discovers selectors from element descriptions.

## Metadata
- **Lines:** 129
- **Imports:** dataclasses.dataclass, typing.Any

## Constants
| Constant | Description |
|----------|-------------|
| `PRODUCT_SELECTORS` | CSS selectors for product links/items (data-product-id, /product/ paths, .product-item, etc.) |
| `ADD_TO_CART_SELECTORS` | Submit/add-to-cart button selectors |
| `CONTINUE_SHOPPING_SELECTORS` | Continue shopping/close modal selectors |

## Classes/Dataclasses
| Class | Description |
|-------|-------------|
| `FormField` | Dataclass: tag, field_type, selector, name, placeholder |
| `FormDetector` | Detects and classifies form elements on a page |

## Methods
| Method | Description |
|--------|-------------|
| `classify_input(raw_type, element)` | Maps input type attribute to canonical category (email, password, phone, text, etc.) |
| `identify_submit_button(elements)` | Returns best submit button selector — checks ADD_TO_CART_SELECTORS then fallback text match |
| `detect_forms(elements)` | Groups scraped elements into form structures (returns list of FormField lists) |
| `discover_selector(elements, description)` | Scores elements by description match — text match (+10), name match (+8), has_id (+5), has_name (+3) |

## Key Logic
- Input type mapping: 11 explicit types fall through to "text" default
- Submit button detection: selector-based match first, then text keyword fallback ("submit", "add", "buy", "checkout", "proceed")
- `discover_selector` returns None when best_score <= 0 (no meaningful match)
- Form detection groups all input/select/textarea elements into a single form (simple heuristic)