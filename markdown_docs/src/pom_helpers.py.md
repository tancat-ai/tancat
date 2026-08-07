# `src/pom_helpers.py` — POM-Mode Code Generation Helpers

## Purpose
Page Object Model artifact generation. Extracted from `placeholder_orchestrator.py`. Handles import statements, instantiation lines, and converting placeholder tokens into POM method calls.

## Functions
- `build_page_object_artifacts(...) -> list[dict]` — generate POM classes from scraped pages
- `build_pom_url_map(...) -> dict[str, str]` — URL → class name mapping
- `build_pom_imports(pom_classes: list[dict]) -> str` — import statements
- `build_pom_instantiation(pom_classes: list[dict]) -> str` — instantiation code
- `get_pom_instance_name(url: str, url_map: dict) -> str` — URL → instance variable name
- `get_pom_method_call(placeholder, url_map, ...) -> str` — placeholder → method call

## Related
- `src/placeholder_orchestrator.py` — consumer
- `src/page_object_builder.py` — `PageObjectBuilder` class


## Recent API Additions

Symbols present in the source but not covered above (refresh pass, 1 items):

### `deduplicate_pom_lines(code: str) -> str` (function)

Remove duplicated POM imports and per-test page-object instantiations.

## How It Works (Internals)

Private `_`-helpers — the module's real logic (1 item). Grouped under the public function that uses them:

### `get_pom_method_call`
- `_selector_literal(value: str) -> str` (function) — Return *value* as a Python string literal.
