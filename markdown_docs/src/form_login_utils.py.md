# `src/form_login_utils.py`

## High-Level Purpose

`form_login_utils.py` centralizes best-effort login form detection and filling for stateful Playwright scraping flows. It was extracted from `stateful_scraper.py` so login-specific behavior can live in one small utility module instead of being embedded directly in scraper orchestration code.

The module focuses on common demo-site login shapes:

- Saucedemo-style credential fields using stable IDs or names.
- Generic HTML forms containing a text or email input, a password input, and a submit control.
- Detection-only behavior when no credential profile is available.

All operations use synchronous Playwright-style calls through a dynamically typed `page` object.

## Imports and Dependencies

```python
from typing import Any

from src.journey_models import CredentialProfile
```

- `Any`: used for the `page` parameter because the utility expects a Playwright-like page object without importing or binding to a concrete Playwright type.
- `CredentialProfile`: supplies `username` and `password` values when credentials are available.

## Public API

### `attempt_login(page: Any, credential_profile: CredentialProfile | None) -> None`

Detects and optionally fills a login form on the current page.

Parameters:

- `page: Any` - A Playwright-compatible page object. The function expects it to support `locator(...)` and `wait_for_load_state(...)`.
- `credential_profile: CredentialProfile | None` - Optional credentials. When provided, the profile's `username` and `password` are used for login attempts. When omitted, the module only detects login-like forms and does not fill or submit anything.

Returns:

- `None`

Behavior:

- If `credential_profile` is `None`, delegates to `_detect_login_forms_only(page)` and exits.
- If credentials are provided, reads `credential_profile.username` and `credential_profile.password`.
- Attempts saucedemo-style login selectors first.
- Attempts generic form-based login second.
- Does not report whether login succeeded; the function is intentionally fire-and-forget.

Architectural role:

- This is the module's only public entry point.
- It acts as a thin strategy coordinator over private helper functions.

## Private Helpers

### `_try_saucedemo_login(page: Any, username: str, password: str) -> None`

Attempts login using direct page-level selectors that match common demo and login-page conventions.

Parameters:

- `page: Any` - A Playwright-compatible page object.
- `username: str` - Username or email value to fill.
- `password: str` - Password value to fill.

Returns:

- `None`

Selector strategy:

- User field candidates:
  - `#user-name`
  - `#username`
  - `#email`
  - `[name='username']`
  - `[name='email']`
- Password field candidates:
  - `#password`
  - `[name='password']`
- Submit button candidates:
  - `#login-button`
  - `#login-btn`
  - `button[type='submit']`
  - Buttons containing login, log in, or sign in text.

Behavior:

- Locates the first matching user field, password field, and login button.
- Checks that user and password fields are visible within a 2000 ms timeout.
- Fills both credential fields.
- If the login button is visible, clicks it with a 5000 ms timeout.
- Waits for `networkidle` with a 10000 ms timeout after clicking.
- Suppresses all exceptions.

Architectural role:

- Implements the first, most specific login strategy.
- Optimized for sites with stable IDs and conventional names.

### `_try_generic_form_login(page: Any, username: str, password: str) -> None`

Attempts login by searching inside the first visible HTML form.

Parameters:

- `page: Any` - A Playwright-compatible page object.
- `username: str` - Username or email value to fill.
- `password: str` - Password value to fill.

Returns:

- `None`

Selector strategy:

- Uses the first `form` element on the page.
- Within that form, searches for:
  - `input[type="text"]`
  - `input[type="email"]`
  - `input[type="password"]`
  - `button[type="submit"]`
  - `input[type="submit"]`

Behavior:

- Checks the first form is visible within a 1000 ms timeout.
- Checks text/email and password inputs are visible within 1000 ms.
- Fills username and password values.
- If a submit control is visible, clicks it with a 5000 ms timeout.
- Waits for `networkidle` with a 10000 ms timeout after clicking.
- Suppresses all exceptions.

Architectural role:

- Provides a broader fallback after the saucedemo-specific selector strategy.
- Encapsulates generic form traversal so the public API does not need to know about DOM structure details.

### `_detect_login_forms_only(page: Any) -> None`

Detects login-like forms without filling or submitting credentials.

Parameters:

- `page: Any` - A Playwright-compatible page object.

Returns:

- `None`

Behavior:

- First checks for saucedemo-style user and password fields.
- If both fields are visible, returns immediately.
- Otherwise checks the first visible form for text/email and password inputs.
- If both generic inputs are visible, returns immediately.
- Does not fill fields, click buttons, or expose the detection result.
- Suppresses all exceptions.

Architectural role:

- Supports credential-less scraping flows where login forms may be present but should not be modified.
- Mirrors the two detection strategies used by credentialed login attempts.

## Key Architectural Patterns

### Strategy Pipeline

`attempt_login()` coordinates a simple ordered strategy pipeline:

1. Credential-less path: detect only.
2. Credentialed path: try specific saucedemo-style selectors.
3. Credentialed path: try generic form selectors.

The ordering favors precise, stable selectors before broader DOM heuristics.

### Best-Effort Failure Handling

Each private helper wraps its logic in `try` / `except Exception` and silently ignores failures. This makes login automation non-blocking for scraper flows: missing forms, locator failures, visibility timeouts, navigation timing issues, and selector mismatches do not stop the caller.

Tradeoff:

- Good for resilient scraping and demo-site automation.
- Weak for observability because callers cannot distinguish "no form found", "form found but login failed", and "exception swallowed".

### Playwright Locator-First Style

The module relies on Playwright locator composition:

- `page.locator(...).first`
- `form.locator(...).first`
- `is_visible(timeout=...)`
- `fill(...)`
- `click(timeout=...)`
- `page.wait_for_load_state("networkidle", timeout=...)`

It assumes synchronous Playwright APIs and does not use async Playwright calls.

### Credential Boundary

Credentials enter only through `CredentialProfile`. The module extracts `username` and `password` once in `attempt_login()` and passes plain strings into helper strategies.

### Detection Without State Reporting

The detection-only helper returns `None` regardless of whether a form is found. Its current value is side-effect control rather than result reporting: it proves the page can be probed safely without filling data, but it does not expose a boolean detection outcome.

## Side Effects

When credentials are provided, the module may:

- Fill username/email inputs.
- Fill password inputs.
- Click a login or submit control.
- Wait for page/network activity to settle.

When credentials are not provided, the module should only inspect element visibility.

## Error Handling

All private helper functions suppress broad `Exception`. The public function does not catch exceptions directly around credential extraction, but downstream Playwright interactions are swallowed inside helpers.

Potential uncaught errors:

- `credential_profile` object lacks `username` or `password` attributes despite being non-`None`.

## Type Surface

The module uses full function annotations:

```python
def attempt_login(page: Any, credential_profile: CredentialProfile | None) -> None: ...
def _try_saucedemo_login(page: Any, username: str, password: str) -> None: ...
def _try_generic_form_login(page: Any, username: str, password: str) -> None: ...
def _detect_login_forms_only(page: Any) -> None: ...
```

No classes are defined in this module.
