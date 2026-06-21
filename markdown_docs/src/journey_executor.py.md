# `src/journey_executor.py`

## High-Level Purpose

`journey_executor.py` executes user-defined browser journeys through Playwright's synchronous Python API, with explicit detection for authentication-related blockers such as login redirects, SSO/OAuth redirects, CAPTCHA, and MFA prompts.

The module exposes `execute_journey()` as the public entry point. That public API serializes the journey into JSON, launches this same file as a subprocess, and parses the child process output back into a `JourneyResult`. The actual browser automation happens inside `_execute_journey_sync()`, which runs in the subprocess and owns the Playwright browser lifecycle.

This subprocess pattern isolates Playwright execution from the caller and is documented in the module as a Windows `ProactorEventLoop` avoidance strategy.

## External Dependencies

- `json`, `sys`, `Path`, `asdict`, `Any`, and `urlparse` from the standard library.
- `sync_playwright` from `playwright.sync_api` for synchronous Chromium automation.
- `AccessibilityEnricher` for enriching scraped elements with accessibility tree data.
- Auth detection helpers: `detect_auth_redirect`, `detect_captcha`, `detect_mfa`, and `detect_sso`.
- Journey model types: `CredentialProfile`, `JourneyResult`, `JourneyStep`, and `substitute_templates`.
- `PageScraper` for extracting elements from captured HTML.
- `src.browser_utils.dismiss_consent_overlays`, imported lazily inside `_dismiss_consent_overlays()`.

## Public API

### `execute_journey(...) -> JourneyResult`

```python
def execute_journey(
    journey_steps: list[JourneyStep],
    credential_profile: CredentialProfile | None = None,
    timeout_ms: int = 30_000,
    starting_url: str | None = None,
) -> JourneyResult:
```

Runs a journey through the subprocess-backed execution path.

Parameters:

- `journey_steps`: ordered list of `JourneyStep` objects to execute.
- `credential_profile`: optional credentials used for template substitution during `fill` steps.
- `timeout_ms`: default timeout for Playwright operations and subprocess scaling.
- `starting_url`: optional initial URL loaded before executing the journey steps.

Returns:

- `JourneyResult`: parsed result from the subprocess, including success state, captured pages, failed steps, error message, and redirected URLs.

Behavior:

- Converts each `JourneyStep` and optional `CredentialProfile` to dictionaries with `asdict()`.
- Builds a JSON payload containing steps, credentials, timeout, and starting URL.
- Resolves the subprocess target to this module's own `journey_executor.py` path.
- Calls `subprocess_run(...)` with the `--execute-journey` flag.
- Delegates result interpretation to `_parse_execute_result(...)`.

## Internal Execution Functions

### `_execute_journey_sync(...) -> JourneyResult`

```python
def _execute_journey_sync(
    journey_steps: list[JourneyStep],
    credential_profile: CredentialProfile | None = None,
    timeout_ms: int = 30_000,
    starting_url: str | None = None,
) -> JourneyResult:
```

Executes all journey steps inside a single Playwright browser session.

Parameters:

- `journey_steps`: ordered `JourneyStep` list to run.
- `credential_profile`: optional credentials for placeholder substitution.
- `timeout_ms`: default page timeout and scraper timeout.
- `starting_url`: optional URL visited before the first step.

Returns:

- `JourneyResult`: aggregate outcome of the journey.

State tracked during execution:

- `captured_pages: dict[str, list[dict[str, Any]]]`: scraped element data keyed by URL.
- `failed_steps: list[str]`: human-readable failures collected per step.
- `redirected_urls: list[str]`: detected login redirect destinations.
- `error_message: str | None`: terminal auth-blocking condition, such as SSO, CAPTCHA, or MFA.
- `base_domain: str`: domain used for SSO redirect detection.

Step handling:

- `goto` / `navigate`: requires `step.url`, navigates with `networkidle`, dismisses consent overlays, updates `base_domain`, detects auth redirects, detects SSO, checks page HTML for CAPTCHA and MFA.
- `click`: clicks by `step.selector` through `_click_with_locator()`, or by `step.text` with Playwright text lookup when no selector is provided.
- `fill`: requires `step.selector`, resolves credential templates in `step.text`, and fills through `_fill_with_locator()`.
- `submit`: tries a small ordered set of common submit button selectors and records a failure if none are found.
- `capture`: extracts elements from current HTML with `PageScraper._extract_elements_from_html(...)`, optionally enriches them with a CDP accessibility snapshot, and stores them under the current URL.
- `wait`: waits for a numeric duration from `step.description` with a default of `1.0` second, then optionally waits for `step.selector`.

Failure handling:

- Per-step exceptions are caught and appended to `failed_steps`.
- Once `error_message` is set by SSO, CAPTCHA, or MFA detection, later steps are skipped and recorded as stopped.
- Browser context and browser are closed in a `finally` block.
- `success` is true only when there is no `error_message` and no failed steps.

### `_parse_execute_result(completed: Any) -> JourneyResult`

```python
def _parse_execute_result(completed: Any) -> JourneyResult:
```

Converts a subprocess completion object into a `JourneyResult`.

Parameters:

- `completed`: expected to behave like `subprocess.CompletedProcess`, with `stderr`, `stdout`, and `returncode` attributes.

Returns:

- `JourneyResult`: parsed successful output, or a failure result for subprocess errors, invalid JSON, or unexpected payload shape.

Behavior:

- Prints subprocess stderr to the parent's stderr when present.
- Returns a failure result if the child process exit code is nonzero.
- Parses `completed.stdout` as JSON.
- Requires the parsed JSON to be a dictionary.
- Calls `JourneyResult.from_dict(data)` for valid dictionary output.

### `subprocess_run(...) -> Any`

```python
def subprocess_run(
    subprocess_path: str,
    flag: str,
    payload: dict,
    timeout_ms: int,
    step_count: int,
) -> Any:
```

Runs the child process that performs journey execution.

Parameters:

- `subprocess_path`: path to the Python file to execute.
- `flag`: command-line flag passed to the child process, currently `--execute-journey`.
- `payload`: JSON-serializable execution payload.
- `timeout_ms`: base timeout in milliseconds.
- `step_count`: number of journey steps, used to scale subprocess timeout.

Returns:

- `Any`: the result of `subprocess.run(...)`, typically a `subprocess.CompletedProcess[str]`.

Behavior:

- Imports `subprocess` lazily.
- Invokes `[sys.executable, subprocess_path, flag]`.
- Sends the JSON payload on standard input.
- Captures stdout and stderr as text.
- Uses `check=False`.
- Sets the subprocess timeout to `max(120, timeout_ms // 1000 * max(1, step_count))`.

## Browser Helper Functions

### `_dismiss_consent_overlays(page: Any) -> None`

```python
def _dismiss_consent_overlays(page: Any) -> None:
```

Dismisses cookie consent and ad overlays through a lazily imported browser utility.

Parameters:

- `page`: Playwright page-like object.

Returns:

- `None`.

### `_click_with_locator(page: Any, selector: str, timeout_ms: int) -> None`

```python
def _click_with_locator(page: Any, selector: str, timeout_ms: int) -> None:
```

Clicks the first element matching a selector.

Parameters:

- `page`: Playwright page-like object.
- `selector`: Playwright selector string.
- `timeout_ms`: operation timeout used with upper bounds for scroll and click.

Returns:

- `None`.

Behavior:

- Uses `page.locator(selector).first`.
- Returns without failure if no matching element exists.
- Attempts `scroll_into_view_if_needed(...)`, swallowing scroll errors.
- Clicks with `timeout=min(5000, timeout_ms)`.
- Waits 500 ms after the click.

### `_fill_with_locator(page: Any, selector: str, text: str, timeout_ms: int) -> None`

```python
def _fill_with_locator(page: Any, selector: str, text: str, timeout_ms: int) -> None:
```

Fills the first element matching a selector.

Parameters:

- `page`: Playwright page-like object.
- `selector`: Playwright selector string.
- `text`: text to enter.
- `timeout_ms`: accepted for signature consistency, but not used directly.

Returns:

- `None`.

Behavior:

- Uses `page.locator(selector).first`.
- Returns without failure if no matching element exists.
- Calls `locator.fill(text)`.

### `_capture_a11y_snapshot_sync(context: Any, page: Any) -> dict[str, Any] | None`

```python
def _capture_a11y_snapshot_sync(context: Any, page: Any) -> dict[str, Any] | None:
```

Captures a Chromium accessibility tree through a CDP session.

Parameters:

- `context`: Playwright browser context-like object.
- `page`: Playwright page-like object.

Returns:

- `dict[str, Any] | None`: an accessibility snapshot shaped as `{"nodes": [...]}`, or `None` if a CDP session cannot be created.

Behavior:

- Creates a CDP session with `context.new_cdp_session(page)`.
- Sends `Accessibility.getFullAXTree`.
- Stores `nodes` from the response when the response is a dictionary.
- Attempts to detach the CDP session before returning.
- Swallows accessibility capture and detach errors, returning the best available snapshot.

## Subprocess Entrypoint

### `_run_execute_journey_entry() -> int`

```python
def _run_execute_journey_entry() -> int:
```

Child-process entrypoint for `execute_journey()`.

Parameters:

- None.

Returns:

- `int`: process-style exit code, with `0` for successful execution and `1` for invalid payload shape.

Behavior:

- Reads JSON from `sys.stdin`.
- Validates that the payload is a dictionary.
- Reconstructs `JourneyStep` objects from `payload["journey_steps"]`, skipping non-dictionary entries.
- Reconstructs an optional `CredentialProfile` from `payload["credential_profile"]`.
- Reads `timeout_ms` and `starting_url`.
- Calls `_execute_journey_sync(...)`.
- Prints `result.to_dict()` as JSON to stdout.

### Module Main Guard

```python
if __name__ == "__main__":
    if "--execute-journey" in sys.argv:
        raise SystemExit(_run_execute_journey_entry())
```

When run as a script with `--execute-journey`, the module executes the child-process entrypoint and exits with its return code.

## Architectural Patterns

### Subprocess Boundary for Browser Automation

The public API is intentionally separate from direct Playwright execution. `execute_journey()` serializes dataclass-backed inputs and delegates to a subprocess. This creates a process boundary around browser automation and lets the parent process handle only orchestration and result parsing.

### JSON Serialization Contract

The parent and child communicate through JSON over standard input and standard output:

1. Parent converts `JourneyStep` and `CredentialProfile` instances to dictionaries.
2. Child reconstructs model objects from primitive dictionaries.
3. Child serializes `JourneyResult.to_dict()` to stdout.
4. Parent parses stdout and calls `JourneyResult.from_dict(...)`.

### Linear Step Interpreter

`_execute_journey_sync()` behaves as a compact interpreter over `JourneyStep.action`. Each supported action maps to a branch with specific validation, Playwright behavior, and failure recording.

### Explicit Auth Blocker Detection

Navigation steps are also guard checkpoints. After navigation, the executor inspects URL, page title, `h1` text, and HTML content to detect:

- login redirects,
- SSO/OAuth redirects,
- CAPTCHA pages,
- MFA prompts.

SSO, CAPTCHA, and MFA set a terminal `error_message`, causing subsequent steps to be recorded as stopped.

### Best-Effort Interaction Helpers

The click, fill, consent-dismissal, and accessibility helpers favor best-effort behavior:

- Missing click/fill locators return quietly at helper level.
- Scroll, accessibility, consent, and selector-wait failures are generally swallowed where they are nonessential.
- User-visible failure messages are collected at the journey-step level rather than raised directly.

### Capture With Optional Accessibility Enrichment

The `capture` step extracts DOM-derived element data from the current HTML, then attempts to capture the Chromium accessibility tree through CDP. If the snapshot succeeds, `AccessibilityEnricher.enrich(...)` augments the extracted elements. If accessibility capture fails, the module still preserves the HTML-derived capture.

### Resource Cleanup

The Playwright browser context and browser are closed in a `finally` block after journey execution, ensuring cleanup even when steps fail or auth detection stops progress.

## Error and Result Semantics

- A journey is successful only when no failed steps were recorded and no terminal `error_message` was set.
- Non-terminal step failures are accumulated in `failed_steps` and allow later steps to continue.
- Terminal auth blockers set `error_message` and cause remaining steps to be marked as stopped.
- Subprocess failures, invalid subprocess JSON, and unexpected subprocess output are converted into failure `JourneyResult` objects by the parent process.

## Classes

This module defines no classes. It coordinates imported model classes and dataclasses from other modules.
