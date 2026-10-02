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

## Recent API Additions

Symbols present in the source but not covered above (refresh pass, 1 items):

### `PageObjectBuilder` (class)

Convert scraped pages into deterministic Playwright page object modules.

## Public API Additions

Refreshed 2026-10-02: public symbols present in the source and not listed above.

- `PageObjectBuilder.build_page_object` (method of `PageObjectBuilder`): `PageObjectBuilder.build_page_object(scraped_page: ScrapedPage, *, file_path: str = '', class_name: str | None = None, use_evidence_tracker: bool = False) -> GeneratedPageObject` - Return metadata plus source code for a page object module. Args: scraped_page: Scraped page metadata to build from. file_path: Override default file path. class_name: Override auto-derived class name. use_evidence_tra...
- `PageObjectBuilder.get_default_file_path` (method of `PageObjectBuilder`): `PageObjectBuilder.get_default_file_path(url: str, *, base_dir: str = 'generated_tests/pages') -> str` - Return the default file path for a page object generated from a URL.


## How It Works (Internals)

Private `_`-helpers - the module's real logic (10 items). Grouped under the public function that calls them.

### `PageObjectBuilder.get_default_file_path(url: str, *, base_dir: str = 'generated_tests/pages') -> str` - method of `PageObjectBuilder`

- `_derive_class_name(url: str) -> str` (method of `PageObjectBuilder`): Return a deterministic page object class name from a URL.
- `_to_module_name(class_name: str) -> str` (method of `PageObjectBuilder`): Convert a class name into a snake_case module name.

### `PageObjectBuilder.build_page_object(scraped_page: ScrapedPage, *, file_path: str = '', class_name: str | None = None, use_evidence_tracker: bool = False) -> GeneratedPageObject` - method of `PageObjectBuilder`

- `_build_methods(scraped_page: ScrapedPage, *, use_evidence_tracker: bool = False) -> list[tuple[str, str]]` (method of `PageObjectBuilder`): Return generated method names and source snippets for one page.
- `_build_module_source(*, class_name: str, url: str, methods: list[tuple[str, str]], element_count: int, use_evidence_tracker: bool = False, elements: list[dict[str, Any]] | None = None) -> str` (method of `PageObjectBuilder`): Return the final Python module source. Args: class_name: Page object class name. url: Page URL. methods: List of (method_name, source) tuples. element_count: Number of scraped elements. use_evidence_tracker: Generate...

### Internal utilities

- `_is_hidden_element(element: dict[str, Any]) -> bool` (method of `PageObjectBuilder`): True when the element is hidden / non-interactive and must not be a POM method. Hidden CSRF/token inputs (role="hidden") and csrf/token/authenticity named fields are never valid click or fill targets.
- `_derive_method_name(element: dict[str, object]) -> str` (method of `PageObjectBuilder`): Return a reusable method name for a scraped element.
- `_build_method_source(method_name: str, selector: str, role: str, *, prefer_first: bool = False, use_evidence_tracker: bool = False) -> str` (method of `PageObjectBuilder`): Return one page object method source block. Args: method_name: The generated method name. selector: The locator selector string. role: The ARIA role of the element. prefer_first: Use .first when duplicate selector...
- `_build_evidence_method_source(method_name: str, selector: str, role: str) -> str` (method of `PageObjectBuilder`): Return an evidence-aware method source block delegating to EvidenceTracker. The generated methods use self.tracker.click(), self.tracker.fill(), etc., so that every interaction is captured in the sidecar evide...
- `_build_element_index_source(elements: list[dict[str, Any]]) -> str` (method of `PageObjectBuilder`): Build a _ELEMENTS tuple literal mapping label words -> scraped selector. B-028: the generic POM click() fallback must only click selectors that actually exist in the scraped data - it must never emit text=<d...
- `_normalize_label_words(text: str) -> str` (method of `PageObjectBuilder`): Normalize element labels into a deduplicated lowercase word string.
