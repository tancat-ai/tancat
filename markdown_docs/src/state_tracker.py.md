# state_tracker.py

## Purpose
State tracking utilities for detecting DOM changes and URL transitions across page interactions during journey scraping.

## Location
`src/state_tracker.py` (122 lines)

## Dependencies
- `hashlib` (standard library)
- `dataclasses.dataclass, field` (standard library)
- `urllib.parse.urlparse` (standard library)

## Public API

### `DOMState` (dataclass)
Snapshot of page DOM state at a point in time. Fields: `url`, `dom_hash`, `element_count`, `title`.

### `StateChange` (dataclass)
Represents detected changes between two DOM states. Fields: `change_type` ("initial" | "url" | "content" | "navigation" | "none"), `description`, `from_state`, `to_state`.

### `StateTracker` (dataclass)
Track DOM and URL state changes across page interactions.

#### `StateTracker.compute_dom_hash(content: str) -> str`
Return a SHA-256 hash of the page HTML content.

#### `StateTracker.capture_state(url: str, html_content: str, element_count: int = 0, title: str = "") -> DOMState`
Capture and store the current page state.

#### `StateTracker.detect_changes(new_state: DOMState) -> StateChange`
Compare new state against the previous one and return the change.

#### `StateTracker.track_url_transition(from_url: str, to_url: str) -> StateChange | None`
Track a URL transition and classify it.

#### `StateTracker.get_history() -> list[DOMState]`
Return the full state history.

#### `StateTracker.get_changes() -> list[StateChange]`
Return all detected state changes.

#### `StateTracker.urls_are_same_domain(url_a: str, url_b: str) -> bool`
Check if two URLs share the same domain.

## Design Notes
- Uses SHA-256 hashing for DOM content comparison
- Classifies changes into: initial, url, content, navigation, none
- Maintains full history for replay/debugging
- Used by `journey_scraper.py` to detect SPA navigation vs server-side redirects

## Related Files
- `src/journey_scraper.py` — consumes state tracking for journey awareness
- `src/stateful_scraper.py` — sibling stateful scraping module