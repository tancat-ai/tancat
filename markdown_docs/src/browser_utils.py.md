# `src/browser_utils.py`

## High-Level Purpose

`src/browser_utils.py` contains synchronous Playwright browser utilities for clearing UI elements that can interfere with automated page interaction. Its public entry point, `dismiss_consent_overlays`, performs best-effort dismissal or removal of consent banners, cookie dialogs, ad overlays, and some overlay-like blockers.

The module is intentionally defensive: every interaction path catches broad exceptions and returns `None`, allowing callers to continue even when a page does not contain the expected overlay structures or when a dismissal attempt fails.

## Module Structure

- Imports `Page` from `playwright.sync_api`.
- Defines no classes.
- Exposes one public function.
- Keeps the implementation decomposed into four private helper functions, each responsible for one dismissal strategy.

## Public Function

### `dismiss_consent_overlays(page: Page) -> None`

Best-effort orchestration function for removing browser overlays before or during Playwright test execution.

Parameters:

- `page: Page` - A synchronous Playwright `Page` object representing the browser tab under automation.

Returns:

- `None`

Behavior:

- Calls `_dismiss_google_consent_tvm(page)`.
- Calls `_dismiss_structural_consent_banners(page)`.
- Calls `_dismiss_position_overlays(page)`.
- Calls `_remove_ad_overlays_js(page)`.

Architectural role:

- Acts as a facade over multiple overlay-dismissal strategies.
- Keeps caller-facing behavior simple: invoke once, ignore failures, and proceed.
- Uses synchronous Playwright APIs only.

## Private Helper Functions

### `_dismiss_google_consent_tvm(page: Page) -> None`

Handles Google consent UI patterns associated with `.fc-consent-root`.

Parameters:

- `page: Page` - A synchronous Playwright page.

Returns:

- `None`

Behavior:

- Looks for `.fc-consent-root button:has-text('Consent')` and clicks the first visible match.
- Looks for `.fc-consent-root button:has-text('Manage options')` and clicks the first visible match.
- Sends the `Escape` key.
- Uses `page.evaluate()` to remove `.fc-consent-root` and `.fc-dialog-overlay` elements from the DOM.
- Waits briefly after successful interactions to allow the page state to settle.

Failure handling:

- Each action is isolated in its own `try`/`except Exception` block.
- Exceptions are swallowed.

### `_dismiss_structural_consent_banners(page: Page) -> None`

Finds known consent or cookie banner containers and clicks dismissal controls inside those containers.

Parameters:

- `page: Page` - A synchronous Playwright page.

Returns:

- `None`

Behavior:

- Defines `container_selectors`, a list of known consent-provider, cookie-banner, modal, overlay, and ARIA dialog selectors.
- Defines `consent_button_patterns`, a list of button selectors for text and ARIA-label patterns such as consent, accept, agree, allow, close, dismiss, and X.
- Iterates through the container selectors.
- For the first visible matching container, searches only within that container for dismissal buttons.
- Clicks the first visible matching dismissal button and returns immediately.

Architectural pattern:

- Uses scoped selector matching to reduce false positives.
- Avoids matching generic dismissal text against the entire page.
- Treats known structural containers as the boundary for safe button matching.

Failure handling:

- Container lookup failures skip to the next container selector.
- Button lookup or click failures skip to the next button pattern.

### `_dismiss_position_overlays(page: Page) -> None`

Detects and dismisses overlay-like UI by layout and viewport position rather than by known provider selectors.

Parameters:

- `page: Page` - A synchronous Playwright page.

Returns:

- `None`

Behavior:

- Defines `dismiss_texts`, a list of accepted dismissal labels.
- Runs JavaScript through `page.evaluate()` to inspect `div`, `section`, `[role="dialog"]`, and `[role="alertdialog"]` elements.
- Filters out elements that are too small or off-screen.
- Computes CSS positioning and bounding rectangles for candidate overlay containers.
- Identifies fixed-position bottom banners and centered overlays.
- Searches candidate containers for `button`, `[role="button"]`, and `a[role="button"]` controls.
- Records matching button center coordinates when their visible text includes one of the dismissal labels.
- Clicks the first returned coordinate using `page.mouse.click(x, y)`.
- Expands collapsed Bootstrap-style panels by adding the `in` class and setting `display = 'block'` on `.panel-collapse.collapse` elements.

Implementation notes:

- The JavaScript computes `isSticky` and `hasBackdrop`, but the final overlay predicates use fixed-position bottom and centered overlay checks.
- The evaluated JavaScript returns an array of button metadata; the Python code stores it in `result: dict` and then treats it as a truthy sequence.

Failure handling:

- JavaScript evaluation, mouse click, and panel-expansion errors are swallowed.

### `_remove_ad_overlays_js(page: Page) -> None`

Removes known advertising overlay elements and ad containers using specific selectors.

Parameters:

- `page: Page` - A synchronous Playwright page.

Returns:

- `None`

Behavior:

- Sends the `Escape` key.
- Defines `ad_overlay_selectors` for Google vignette, Google ad iframes, ASWIFT iframes, and advertisement iframes.
- Checks each known selector and sends `Escape` again when a matching element exists.
- Runs JavaScript through `page.evaluate()` to hide and remove known consent, vignette, AdSense, ASWIFT, iframe, and ad container elements.
- Waits briefly after JavaScript cleanup.

Architectural pattern:

- Uses specific ad selectors instead of broad layout or z-index heuristics.
- Mutates the DOM directly only for known overlay and ad patterns.

Failure handling:

- Keyboard, selector lookup, and JavaScript evaluation failures are swallowed.

## Key Architectural Patterns

### Best-Effort Idempotent Cleanup

All functions return `None` and are written to tolerate absent elements, changed markup, hidden overlays, Playwright timing errors, and JavaScript failures. This makes the utilities suitable for repeated calls during browser automation.

### Public Facade With Private Strategies

`dismiss_consent_overlays` is the sole public facade. The concrete strategies are private helpers:

- Google consent-specific handling.
- Structural consent banner handling.
- Position-based overlay detection.
- Specific ad-overlay DOM cleanup.

### Scoped Matching Before Broad Detection

The module first attempts provider-specific and structural dismissal before using position-based detection. Structural dismissal scopes button text matching to candidate containers, reducing the chance of clicking ordinary page controls.

### Synchronous Playwright API

Every function accepts `playwright.sync_api.Page` and uses sync Playwright methods such as `locator()`, `click()`, `is_visible()`, `wait_for_timeout()`, `keyboard.press()`, `mouse.click()`, and `evaluate()`.

### DOM Mutation For Known Blockers

The module uses `page.evaluate()` to remove or hide specific overlay and ad elements when normal clicks or Escape-key dismissal may not be enough. The selectors are explicit and targeted rather than based on broad visual properties.

### Defensive Exception Suppression

Each dismissal attempt is wrapped in broad exception handling. The design favors forward progress in generated or automated tests over surfacing overlay-cleanup failures to callers.

## External Side Effects

- May click buttons on the current page.
- May press the `Escape` key.
- May move through short Playwright timeouts.
- May mutate the DOM by removing or hiding consent and ad elements.
- May expand collapsed Bootstrap panel elements.

## Dependencies

- `playwright.sync_api.Page`
