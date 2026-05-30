# page_context_tracker.py

## Purpose
Page context tracking for journey-aware placeholder resolution. Tracks which page the resolver is operating on as it processes journey steps sequentially, using both URL inference from element hrefs and action-based heuristics to maintain accurate page state.

## Location
`src/page_context_tracker.py` (218 lines)

## Dependencies
- `__future__.annotations` (standard library)
- `logging` (standard library)
- `urllib.parse.urljoin, urlparse` (standard library)

## Module Constants
- `NAVIGATION_ACTIONS: set[str]` — Action words implying page transitions (login, sign in, submit, checkout, etc.)
- `TRANSITION_URL_PATTERNS: dict[str, tuple[str, ...]]` — Keyword-to-URL-pattern mappings for inferring page transitions

## Public API

### `PageContextTracker`

#### `__init__(self, scraped_urls: list[str]) -> None`
Initialize with list of all discovered/scraped URLs.

#### `current_url` (property)
The currently active page URL.

#### `set_initial_url(self, url: str | None) -> None`
Set the initial page URL before processing begins.

#### `track_url_transition(self, from_url: str, to_url: str) -> None`
Track a URL transition.

#### `infer_next_url(self, action_description: str, current_element: dict | None = None) -> str | None`
Infer the next page URL based on action description and current element context. Uses element hrefs when available, falls back to action-based URL pattern matching.

#### `get_history(self) -> list[str]`
Return the URL navigation history.

#### `on_page_navigate(self, url: str) -> None`
Record that a page navigation occurred (called after `page.goto()` or navigation click).

#### `on_action_complete(self) -> None`
Record that a non-navigation action completed on the current page.

## Design Notes
- Maintains URL history for diagnostics
- Infers URL transitions from action verbs and element hrefs
- Used by `placeholder_orchestrator.py` for page-context validation

## Related Files
- `src/placeholder_orchestrator.py` — consumes page context tracking
- `src/url_inference.py` — sibling URL inference module