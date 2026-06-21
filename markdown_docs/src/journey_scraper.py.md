# `src/journey_scraper.py`

## High-Level Purpose

`journey_scraper.py` provides a journey-aware Playwright scraping layer. Instead of scraping only static URLs, it follows a sequence of user-like actions such as navigation, clicks, fills, waits, scrapes, and transient captures so that dynamic elements are present before element extraction runs.

The module now acts partly as a compatibility facade. Core journey data models are imported from `src.journey_models`, and authenticated journey execution is re-exported from `src.journey_executor`. The scraper classes and subprocess entry point remain defined here.

Primary responsibilities:

- Execute scripted journeys in sync Playwright while exposing an async public API.
- Avoid Windows and Streamlit nested event loop issues by running sync Playwright scraping in a subprocess.
- Scrape and enrich page elements after initial load, navigation, click-driven navigation, explicit scrape steps, and capture steps.
- Discover selectors from natural-language step descriptions using local DOM extraction, heuristic scoring, robust locator construction, and resolver fallback.
- Track skipped steps and locator failures for diagnostics.
- Provide a cart-seeding convenience scraper for flows that require cart state before scraping cart or checkout pages.

## Public Exports

`__all__` exports:

- `CartSeedingScraper`
- `CredentialProfile`
- `JourneyResult`
- `JourneyScraper`
- `JourneyStep`
- `ScrapedStep`
- `execute_journey`

Compatibility aliases and re-exports:

- `execute_journey` is imported from `src.journey_executor`.
- `CredentialProfile`, `JourneyResult`, `JourneyStep`, `ScrapedStep`, and `substitute_templates` are imported from `src.journey_models`.
- `_substitute_templates = substitute_templates` preserves older imports used by legacy tests.

## Top-Level Helper Functions

### `_capture_element_visibility_sync(page: Any, elements: list[dict[str, Any]]) -> list[dict[str, Any]]`

Checks each scraped element's runtime visibility with Playwright.

Parameters:

- `page: Any` - live Playwright page-like object.
- `elements: list[dict[str, Any]]` - extracted element dictionaries, expected to contain optional `selector` keys.

Returns:

- `list[dict[str, Any]]` - the same element list, with `is_visible` added or updated when selector lookup succeeds.

Behavior:

- Iterates through elements.
- Skips elements without a selector.
- Uses `page.locator(selector).first.is_visible()`.
- Suppresses selector or visibility failures so enrichment remains additive.

### `_capture_a11y_snapshot_sync(context: Any, page: Any) -> dict[str, Any] | None`

Captures a Chromium accessibility tree through Chrome DevTools Protocol.

Parameters:

- `context: Any` - Playwright browser context.
- `page: Any` - live Playwright page.

Returns:

- `dict[str, Any] | None` - `{"nodes": [...]}` when a CDP session can be created, or `None` when CDP is unavailable.

Behavior:

- Opens a CDP session for the page.
- Sends `Accessibility.getFullAXTree`.
- Stores returned `nodes` when the response is a dictionary.
- Detaches the CDP session when possible.
- Returns an empty-node snapshot on CDP command failure, and `None` only when session creation fails.

### `_run_subprocess_entry() -> int`

Subprocess entry point used when the module is executed with `--journey-scrape`.

Parameters:

- None directly. Reads JSON payload from `sys.stdin`.

Returns:

- `int` - process-style status code. Returns `0` after successful scrape output, `1` for invalid payload shape.

Behavior:

- Parses stdin JSON into scraper configuration and serialized steps.
- Reconstructs `JourneyStep` instances from step dictionaries.
- Instantiates `JourneyScraper`.
- Calls private sync scraping method `_scrape_journey_sync`.
- Prints JSON output to stdout.

## Class: `JourneyScraper`

Scrapes pages by following a user journey step-by-step.

### Constructor

```python
def __init__(
    self,
    starting_url: str,
    *,
    timeout_ms: int = 30_000,
    max_retries: int = 2,
    base_backoff_ms: int = 1000,
    headless: bool = True,
    credential_profile: CredentialProfile | None = None,
) -> None:
```

Parameters:

- `starting_url: str` - starting page URL; stripped before storage.
- `timeout_ms: int` - default Playwright timeout in milliseconds.
- `max_retries: int` - number of attempts per journey step.
- `base_backoff_ms: int` - retry backoff base in milliseconds.
- `headless: bool` - whether Chromium launches headless.
- `credential_profile: CredentialProfile | None` - optional profile retained for later journey execution.

Returns:

- `None`

Initialized state:

- `self.starting_url: str`
- `self.timeout_ms: int`
- `self.max_retries: int`
- `self.base_backoff_ms: int`
- `self.headless: bool`
- `self._credential_profile: CredentialProfile | None`
- `self._html_scraper: PageScraper`
- `self._resolver: PlaceholderResolver`
- `self._captured_pages: dict[str, list[dict[str, Any]]]`
- `self._context_log: list[dict[str, Any]]`

### `_debug(self, message: str) -> None`

Prints a debug message to stderr when `PIPELINE_DEBUG=1`.

Parameters:

- `message: str` - debug text.

Returns:

- `None`

### `async scrape_journey(self, steps: list[JourneyStep], *, credential_profile: CredentialProfile | None = None) -> dict[str, list[dict[str, Any]]]`

Public async API for following a journey and returning scraped elements per URL.

Parameters:

- `steps: list[JourneyStep]` - journey steps to execute.
- `credential_profile: CredentialProfile | None` - optional per-call credential profile overriding the instance profile.

Returns:

- `dict[str, list[dict[str, Any]]]` - mapping from URL to scraped element dictionaries.

Behavior:

- Filters steps to supported actions: `navigate`, `click`, `fill`, `wait`, `scrape`, `capture`.
- Returns `{}` if no supported steps remain.
- Resolves the effective credential profile.
- Uses `asyncio.to_thread` to run `_scrape_journey_via_subprocess` without blocking the event loop.

### `_scrape_journey_via_subprocess(self, steps: list[JourneyStep], credential_profile: CredentialProfile | None = None) -> dict[str, list[dict[str, Any]]]`

Runs the sync Playwright journey in a clean subprocess.

Parameters:

- `steps: list[JourneyStep]` - cleaned journey steps.
- `credential_profile: CredentialProfile | None` - optional credential profile serialized into the payload.

Returns:

- `dict[str, list[dict[str, Any]]]` - URL-to-elements mapping, or `{}` on subprocess failure or invalid output.

Behavior:

- Serializes steps and scraper configuration to JSON.
- Invokes the current file with `[sys.executable, subprocess_path, "--journey-scrape"]`.
- Passes payload through stdin.
- Captures stdout and stderr.
- Prints subprocess stderr to the parent stderr for debugging.
- Parses stdout JSON into a typed dictionary.
- Stores successful output in `self._captured_pages`.

### `_scrape_journey_sync(self, steps: list[JourneyStep]) -> dict[str, list[dict[str, Any]]]`

Core synchronous Playwright journey executor used by the subprocess.

Parameters:

- `steps: list[JourneyStep]` - journey steps to run.

Returns:

- `dict[str, list[dict[str, Any]]]` - URL-to-elements mapping captured during the journey.

Behavior:

- Launches Chromium through `sync_playwright`.
- Creates a browser context and page.
- Sets the default timeout.
- Optionally navigates to `starting_url`, dismisses overlays, and scrapes the starting page.
- Iterates steps with retry and exponential backoff plus jitter.
- Handles supported actions:
  - `navigate` - navigate through `_navigate_to`.
  - `click` - dismiss overlays, discover missing selector if possible, then click.
  - `fill` - discover missing selector if possible, then fill with provided text.
  - `wait` - wait for seconds parsed from `description`, defaulting to 1.0.
  - `scrape` - scrape the current page.
  - `capture` - scrape transient page content without visibility enrichment, then optionally add accessibility enrichment.
- Auto-scrapes after explicit navigation.
- Detects click-driven URL changes and auto-scrapes the new page.
- Logs relaxed selector fallback and skipped-step events in `_context_log`.
- Closes browser context and browser in `finally`.
- Stores output in `self._captured_pages`.

### `get_pages_visited(self) -> list[str]`

Returns unique URLs captured during the journey.

Parameters:

- None.

Returns:

- `list[str]` - insertion-ordered unique URLs from `self._captured_pages`.

### `get_skipped_steps(self) -> list[dict]`

Returns logged skipped journey steps.

Parameters:

- None.

Returns:

- `list[dict]` - context log entries where `event == "step_skipped"`.

### `get_locator_warnings(self) -> list[dict]`

Returns locator-not-found warnings.

Parameters:

- None.

Returns:

- `list[dict]` - context log entries where `event == "locator_not_found"`.

### `@staticmethod _list_available_elements(page: Any, limit: int = 10) -> list[dict]`

Collects a small diagnostic sample of clickable/link-like elements.

Parameters:

- `page: Any` - live Playwright page.
- `limit: int` - maximum number of elements to inspect.

Returns:

- `list[dict]` - dictionaries containing `tag`, truncated `text`, `id`, and first CSS class.

### `_discover_selector_relaxed(self, page: Any, action: str, description: str) -> str | None`

Fallback selector discovery using relaxed text matching.

Parameters:

- `page: Any` - live Playwright page.
- `action: str` - intended action, currently not used in the relaxed scoring logic.
- `description: str` - natural-language description to match against element text or labels.

Returns:

- `str | None` - robust locator or existing selector for the first relaxed match; `None` when no match is found.

Behavior:

- Waits briefly for network idle.
- Extracts elements from current HTML through `PageScraper`.
- Normalizes description into keywords.
- Looks for any keyword in each candidate's accessible name, aria label, or text.
- Prefers `build_robust_locator(element)` and falls back to `element["selector"]`.

### `_discover_selector(self, page: Any, action: str, description: str) -> str | None`

Primary selector discovery for natural-language journey steps.

Parameters:

- `page: Any` - live Playwright page.
- `action: str` - action such as `click` or `fill`.
- `description: str` - natural-language target description.

Returns:

- `str | None` - selected robust locator or selector, or `None` when no usable candidate is found.

Behavior:

- Waits briefly for page stability.
- Extracts elements from current page HTML.
- Applies visibility enrichment.
- Scores all candidates with `PlaceholderScorer.compute_element_score`.
- Applies action-specific penalties:
  - `fill` heavily penalizes non-input roles.
  - `click` moderately penalizes non-interactive roles.
- Returns the best robust locator or selector when available.
- Falls back to `PlaceholderResolver.rank_candidates`.
- Logs `locator_not_found` events with a diagnostic sample when no usable candidate exists.

### `_navigate_to(self, page: Any, url: str, timeout_ms: int) -> str`

Navigates to a URL and returns the final page URL.

Parameters:

- `page: Any` - live Playwright page.
- `url: str` - absolute or relative URL.
- `timeout_ms: int` - navigation timeout.

Returns:

- `str` - final `page.url` when navigation returns a response; otherwise the attempted full URL.

Behavior:

- Resolves leading-slash relative URLs with `urljoin(page.url, url)`.
- Calls `page.goto(..., wait_until="networkidle")`.
- Waits for network idle and an additional 1 second for DOM stability.
- Dismisses consent overlays after navigation.

### `_click_selector(self, page: Any, selector: str, timeout_ms: int) -> None`

Clicks an element by selector.

Parameters:

- `page: Any` - live Playwright page.
- `selector: str` - selector or locator string.
- `timeout_ms: int` - timeout budget for scroll and click.

Returns:

- `None`

Behavior:

- Uses the first matching locator.
- Returns without raising when no locator exists.
- Scrolls into view with a capped timeout.
- Clicks with a capped timeout.
- Waits 500 ms after click for page transition.
- Re-raises click exceptions after debug logging.

### `_fill_selector(self, page: Any, selector: str, text: str, timeout_ms: int) -> None`

Fills an input-like element by selector.

Parameters:

- `page: Any` - live Playwright page.
- `selector: str` - selector or locator string.
- `text: str` - value to fill.
- `timeout_ms: int` - accepted for signature consistency; not directly used by `locator.fill`.

Returns:

- `None`

Behavior:

- Uses the first matching locator.
- Returns without raising when no locator exists.
- Calls `locator.fill(text)`.
- Re-raises fill exceptions after debug logging.

### `_scrape_current_page(self, page: Any, url: str, context: Any | None = None) -> list[dict[str, Any]]`

Extracts and enriches elements from the current page state.

Parameters:

- `page: Any` - live Playwright page.
- `url: str` - base URL used during extraction.
- `context: Any | None` - optional browser context for accessibility snapshot capture.

Returns:

- `list[dict[str, Any]]` - extracted elements, enriched when possible.

Behavior:

- Reads `page.content()`.
- Extracts elements through `PageScraper._extract_elements_from_html`.
- Adds runtime visibility through `_capture_element_visibility_sync`.
- Adds accessibility enrichment through `AccessibilityEnricher.enrich` when a context and a CDP snapshot are available.
- Falls back to raw extracted elements if enrichment fails.

### `@staticmethod _dismiss_consent_overlays(page: Any) -> None`

Delegates consent-overlay dismissal to a shared browser utility.

Parameters:

- `page: Any` - live Playwright page.

Returns:

- `None`

Behavior:

- Imports `dismiss_consent_overlays` lazily.
- Calls it with the Playwright page.

## Class: `CartSeedingScraper(JourneyScraper)`

Specialized journey scraper for cart-dependent pages.

Purpose:

- Seed a cart by visiting products, selecting a product, adding it to the cart, capturing the confirmation state, dismissing the modal, then navigating to requested cart or checkout URLs.

Class attributes:

- `PRODUCT_SELECTORS: list[str]`
- `ADD_TO_CART_SELECTORS: list[str]`
- `CONTINUE_SHOPPING_SELECTORS: list[str]`

These constants are assigned from imported selector lists for compatibility.

### Constructor

```python
def __init__(
    self,
    starting_url: str,
    products_url: str | None = None,
    **kwargs: Any,
) -> None:
```

Parameters:

- `starting_url: str` - home page URL used to establish session.
- `products_url: str | None` - optional explicit products page URL.
- `**kwargs: Any` - forwarded to `JourneyScraper.__init__`.

Returns:

- `None`

Behavior:

- Initializes the base `JourneyScraper`.
- Stores `self.products_url`, deriving it from `starting_url` when not provided.

### `@staticmethod _derive_products_url(home_url: str) -> str`

Derives a products URL from a home URL.

Parameters:

- `home_url: str` - base home URL.

Returns:

- `str` - URL joined with `/products`.

### `async scrape_cart_pages(self, cart_urls: list[str]) -> dict[str, list[dict[str, Any]]]`

Seeds cart state and scrapes target cart-related pages.

Parameters:

- `cart_urls: list[str]` - cart or checkout URLs to visit after seeding.

Returns:

- `dict[str, list[dict[str, Any]]]` - output from `scrape_journey`.

Behavior:

- Builds a journey with:
  - navigate to products page,
  - click first product selector,
  - click first add-to-cart selector,
  - capture confirmation popup state,
  - click first continue-shopping selector,
  - wait for modal disappearance,
  - navigate to each requested cart URL.
- Calls `self.scrape_journey(steps)`.

### `@staticmethod _ensure_full_url(url: str) -> str`

Normalizes a target URL for cart scraping.

Parameters:

- `url: str` - absolute or relative URL.

Returns:

- `str` - the input URL unchanged.

Behavior:

- Explicitly returns absolute URLs unchanged.
- Also returns relative URLs unchanged because `JourneyScraper._navigate_to` handles relative navigation.

## Runtime Entry Point

```python
if __name__ == "__main__":
    if "--journey-scrape" in sys.argv:
        raise SystemExit(_run_subprocess_entry())
```

The file can be invoked directly as a subprocess worker. Parent code calls it with `--journey-scrape`, sends JSON payload on stdin, and expects JSON scrape output on stdout.

## Key Architectural Patterns

### Async facade over sync Playwright

The public `scrape_journey` method is async, but browser automation uses Playwright's synchronous API. The code bridges the two with `asyncio.to_thread` and a subprocess so callers can use an async interface without running sync Playwright in a problematic nested event loop.

### Subprocess isolation

The module serializes journey configuration and steps into JSON, invokes itself as a subprocess, and deserializes JSON output. This isolates Playwright execution from Streamlit or Windows event loop constraints.

### Compatibility facade

The module preserves older import paths by re-exporting journey models and `execute_journey` while keeping scraper logic local. This reduces downstream churn after extracting models and executor behavior into separate modules.

### Additive enrichment

Visibility and accessibility enrichment are best-effort. Failures are swallowed and raw extracted elements are returned. This keeps scraping resilient even when selectors are stale, CDP is unavailable, or enrichment encounters unexpected page state.

### Selector discovery pipeline

Selector discovery uses a staged approach:

1. Extract the current DOM with `PageScraper`.
2. Enrich candidate elements with visibility information.
3. Score candidates using `PlaceholderScorer`.
4. Apply action-aware penalties to avoid selecting display-only elements for interactive steps.
5. Build a robust locator from the best candidate.
6. Fall back to `PlaceholderResolver.rank_candidates`.
7. Fall back further to relaxed keyword matching when the main discovery method returns `None` during click or fill execution.

### Journey-state capture

The scraper captures pages at several moments:

- Starting URL load.
- Explicit navigation steps.
- Explicit scrape steps.
- Capture steps for transient states such as popups.
- Click steps that change the current page URL.

Captured data is stored in `self._captured_pages`, allowing later retrieval of visited URLs.

### Diagnostic context log

The private `_context_log` accumulates events such as:

- `locator_relaxed_fallback`
- `step_skipped`
- `locator_not_found`

Public diagnostic accessors expose skipped steps and locator warnings.

### Cart-specific journey composition

`CartSeedingScraper` composes a fixed journey using selector constants and then delegates execution to `JourneyScraper`. It does not override scraping mechanics; it only builds the domain-specific sequence needed to make cart and checkout pages meaningful.

## External Dependencies Used By This Module

- Standard library: `asyncio`, `json`, `os`, `random`, `re`, `sys`, `time`, `dataclasses.asdict`, `pathlib.Path`, `typing.Any`.
- Playwright sync API: `sync_playwright`.
- Project collaborators imported by name:
  - `AccessibilityEnricher`
  - selector constants from `form_detector`
  - `execute_journey`
  - journey model classes and `substitute_templates`
  - `build_robust_locator`
  - `PlaceholderResolver`
  - `PlaceholderScorer`
  - `PageScraper`
  - lazily imported `dismiss_consent_overlays`

## Notable Error-Handling Choices

- Visibility, accessibility, load-state waits, and overlay dismissal paths are generally best-effort.
- Subprocess failures return `{}` rather than raising.
- Invalid subprocess JSON output returns `{}`.
- Missing click or fill locator count logs debug output and returns without raising.
- Click and fill runtime exceptions are re-raised after debug logging.
- Step-level exceptions are retried with exponential backoff and then logged only when debug mode is enabled.

## Data Flow Summary

1. Caller creates `JourneyScraper` or `CartSeedingScraper`.
2. Caller passes `JourneyStep` objects to `scrape_journey`, or cart URLs to `scrape_cart_pages`.
3. Steps are filtered and serialized.
4. The module invokes itself with `--journey-scrape`.
5. The subprocess reconstructs steps and runs sync Playwright.
6. Each page state is scraped through `PageScraper`.
7. Element lists are optionally enriched with visibility and accessibility data.
8. JSON output is returned to the parent process.
9. Parent process stores the captured URL-to-elements mapping and returns it to the caller.
