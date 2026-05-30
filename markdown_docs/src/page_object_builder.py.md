---
purpose: >
  Generates Page Object Model (POM) classes from resolved journey data.
  Creates reusable locator methods for each page, producing clean, maintainable test code.
lines: ~300
created: "2026-05-30"
---

# `src/page_object_builder.py`

## High-Level Purpose

Converts resolved TestJourney data into Page Object Model classes. Each unique page URL gets a class with typed locator properties and action methods.

## Output Format

Generates Python classes like:
```python
class LoginPage:
    def __init__(self, page: Page):
        self.page = page

    @property
    def username(self) -> Locator:
        return self.page.locator("#username")

    @property
    def password(self) -> Locator:
        return self.page.locator("#password")

    def click_login(self):
        self.page.locator("#login-btn").click()
```

## Key Methods

| Method | Returns | Description |
|--------|---------|-------------|
| `build_pom_code(journeys, page_urls)` | `str` | Generate full POM class code |
| `_extract_unique_locators(journey)` | `dict[str, str]` | Deduplicated locator map per page |
| `_generate_class_name(url)` | `str` | URL → PascalCase class name |

## Dependencies

- `src.pipeline_models` — `TestJourney`, `TestStep`

## Depended On By

- `src/orchestrator.py` — writes POM code to generated test file