# `src/evidence_tracker.py`

## High-Level Purpose

Runtime evidence tracker — records each test step (navigate, click, fill, assert) with screenshots, element metadata, timing, and failure diagnostics. Writes per-test sidecar JSON files for evidence-based reporting.

## Module Metadata

- **Lines:** 426
- **Imports:** `re`, `time`, `pathlib.Path`, `typing.Any`, `playwright.sync_api.Page`, `src.config`, `src.evidence_serializer`, `src.failure_reporter`, `src.hover_click_utils`, `src.locator_fallback`

## Class: `EvidenceTracker`

### `__init__(page, test_name, condition_ref="unknown", story_ref="unknown", evidence_root=None, test_package_dir=None)`
- `test_package_dir` takes precedence over `evidence_root` for evidence directory
- Evidence written to `<test_package_dir>/evidence/`
- Sidecar: `{test_name}.evidence.json`
- Loads previous run history and step data for incremental run counts

### `_clean_label(label) -> str`
Converts `{{ACTION:description}}` tokens to human-readable `"Action: description"`.

### `_dismiss_consent_overlays()` / `_dismiss_ad_overlays()`
Delegates to `src.browser_utils.dismiss_consent_overlays`.

### `_dismiss_confirmation_modals()`
Dismisses added-to-cart confirmation modals before clicks. **B-015 lesson (2026-08-03):** text-based dismissal (`Continue Shopping`, `.close`, …) is scoped to modal/dialog containers (`#cartModal, .modal, [role='dialog'], …`) — a visible "Continue Shopping" button on the cart page itself (saucedemo) must never be clicked here.

### `_is_modal_close_target(locator) -> bool`
True when a locator is a confirmation-modal close control (close-modal, Continue Shopping, btn-success).

### `_load_previous_history() -> dict` / `_load_previous_steps() -> list`
Loads run history and step data from sidecar JSON for incremental counters.

### `_get_element_metadata(locator) -> dict`
Captures tag, id, data-testid, bounding box, and viewport percentages for an element. Uses full-document size for coordinates.

### `_record_step(step_type, label, locator, value, take_screenshot, error, matched_text, fallback_used, fallback_chain, elapsed_ms)`
Core recording method. Builds step dict with:
- Incremental `step_run_count` from previous runs
- Full-page screenshot when requested, captured in the configured evidence image format — lossless WebP by default (`src.config.evidence_image_extension()` / `evidence_image_format()`, override with `AITEST_EVIDENCE_IMAGE_FORMAT=png`). Credential fields are masked for the duration of the capture.
- Element metadata (bbox, tag, attributes)
- Failure diagnosis via `FailureReporter.diagnose_failure()` on error
- Status: `"passed"`, `"partial_pass"` (when fallback used), `"failed"`

### `navigate(url, label="")` — Navigate + dismiss overlays + screenshot
### `fill(locator, value, label="")` — Fill form field
### `click(locator, label="")` — Click with layered fallback:
1. Scroll into view + direct click (`.first` to avoid strict-mode)
2. Fast-fail: missing/hidden elements raise `_LocatorNotFoundError` immediately (no fallback marathon)
3. **Modal-close no-op (2026-08-03):** if the target is a modal-close control and the modal is already dismissed (element hidden), the click's intent is satisfied — record a no-op instead of failing (generated "close popup / OK" steps collide with the tracker's pre-click auto-dismiss)
4. On visibility/timeout error: dismiss ads → hover-reveal → locator scoring fallback
5. Fallback success → `"partial_pass"` status with audit trail
### `assert_visible(locator, label="")` — Wait for visible + screenshot + capture text
### `write(status="passed") -> str` — Serialize sidecar JSON, update run history counters, return path

## Dependencies

- `src.evidence_serializer.EvidenceSerializer`
- `src.failure_reporter.FailureReporter`
- `src.hover_click_utils.try_hover_and_click`
- `src.locator_fallback.LocatorFallback`
- `src.browser_utils.dismiss_consent_overlays`

## Depended On By

Generated test code (runtime), `evidence_loader.py`, report builders

## Public API Additions

Refreshed 2026-10-02: public symbols present in the source and not listed above.

- `PageMismatchError` (class): Raised when a step ran on a page other than the one its locator was resolved against (the gate-2 false-green class). A step that "succeeds" on the wrong page has not verified its condition - a flow divergence that use...
- `EvidenceTracker.assert_hidden` (method of `EvidenceTracker`): `EvidenceTracker.assert_hidden(locator: str, label: str = '', expected_page: str = '') -> None` - Assert the element is hidden or detached - a state-ABSENCE check. For polarity ASSERTs like "popup closed" / "item removed": Playwright's wait_for(state="hidden") passes for hidden OR detached nodes, which is exac...
- `EvidenceTracker.assert_text` (method of `EvidenceTracker`): `EvidenceTracker.assert_text(locator: str, expected: str, label: str = '') -> None` - Assert the element's text content matches the expected string exactly.
- `EvidenceTracker.assert_text_contains` (method of `EvidenceTracker`): `EvidenceTracker.assert_text_contains(locator: str, expected: str, label: str = '') -> None` - Assert the element's text content contains the expected substring.
- `EvidenceTracker.assert_disabled` (method of `EvidenceTracker`): `EvidenceTracker.assert_disabled(locator: str, label: str = '') -> None` - Assert the element is disabled.
- `EvidenceTracker.assert_enabled` (method of `EvidenceTracker`): `EvidenceTracker.assert_enabled(locator: str, label: str = '') -> None` - Assert the element is enabled.
- `EvidenceTracker.assert_checked` (method of `EvidenceTracker`): `EvidenceTracker.assert_checked(locator: str, label: str = '') -> None` - Assert a checkbox or radio button is checked.
- `EvidenceTracker.assert_count` (method of `EvidenceTracker`): `EvidenceTracker.assert_count(locator: str, expected: int, label: str = '') -> None` - Assert the number of elements matching the locator equals expected.
- `EvidenceTracker.assert_count_at_least` (method of `EvidenceTracker`): `EvidenceTracker.assert_count_at_least(locator: str, minimum: int, label: str = '') -> None` - Assert at least minimum elements match the locator (B-090). A criterion like "shows at least four capability cards" must count the matching elements, not assert one element's visibility. assert_count is an exa...
- `EvidenceTracker.assert_value` (method of `EvidenceTracker`): `EvidenceTracker.assert_value(locator: str, expected: str, label: str = '') -> None` - Assert an input/textarea/select has the expected value attribute.
- `EvidenceTracker.assert_attribute` (method of `EvidenceTracker`): `EvidenceTracker.assert_attribute(locator: str, attribute: str, label: str = '', *, forbidden: tuple[str, ...] = (), must_be_url: bool = False, required_scheme: str = '') -> None` - Assert an element's attribute is present and non-empty (B-069 part b). When forbidden is given, the value must not contain any of those substrings (case-insensitive) - a "live" href that still says TBD or YO...
- `EvidenceTracker.assert_no_forbidden` (method of `EvidenceTracker`): `EvidenceTracker.assert_no_forbidden(selector: str, forbidden: str | tuple[str, ...], label: str = '', attribute: str | None = None, *, also_text: bool = False) -> None` - Assert NO element matching selector contains forbidden (B-069 part b). Page-level integrity check that needs no element resolution - "no TBD in links" inspects every <a> href, "no TBD in buttons" inspects...
- `EvidenceTracker.assert_attribute_all` (method of `EvidenceTracker`): `EvidenceTracker.assert_attribute_all(selector: str, attribute: str, label: str = '', *, forbidden: tuple[str, ...] = (), must_be_url: bool = False) -> None` - Assert EVERY element matching selector has a non-empty attribute (B-069 part b). "all images have alt" -> every <img> must carry a non-empty alt. Zero matching elements FAILS - the condition expects the ele...
- `EvidenceTracker.assert_contains` (method of `EvidenceTracker`): `EvidenceTracker.assert_contains(section: str, child: str, label: str = '') -> None` - Assert a named section contains a child element (B-088). section is the section heading's text and child is a CSS selector. The check finds the innermost element that has a heading with that text AND contains...
- `EvidenceTracker.assert_no_broken_images` (method of `EvidenceTracker`): `EvidenceTracker.assert_no_broken_images(label: str = '') -> None` - Assert every <img> on the page finished loading (B-090). A page-fact criterion ("no image on the page is broken - every image element has a non-zero natural width") must inspect every image, not assert one hero di...
- `EvidenceTracker.assert_natural_width` (method of `EvidenceTracker`): `EvidenceTracker.assert_natural_width(locator: str, label: str = '') -> None` - Assert the first element matching locator is a loaded image (B-090). "The hero product screenshot has finished loading (natural width > 0)" must read the image's naturalWidth; assert_visible passes even fo...
- `EvidenceTracker.assert_no_horizontal_scroll` (method of `EvidenceTracker`): `EvidenceTracker.assert_no_horizontal_scroll(width: int = 375, label: str = '') -> None` - Assert the page does not scroll horizontally at width px (B-090). "At a viewport width of 375 pixels the page does not scroll horizontally" must resize the viewport and measure scrollWidth - a visibility asser...
- `EvidenceTracker.assert_anchor_targets_exist` (method of `EvidenceTracker`): `EvidenceTracker.assert_anchor_targets_exist(selector: str = 'a[href^="#"]', label: str = '') -> None` - Assert every in-page anchor points at an element that exists (B-092). "Every same-page anchor link points at an element that exists" is a page-wide scan, not a check of one link. Anchors with a bare # fragment poi...
- `EvidenceTracker.assert_section_has_price` (method of `EvidenceTracker`): `EvidenceTracker.assert_section_has_price(section: str, label: str = '') -> None` - Assert a named section shows a price (B-092). "The Pro Deployment tier is shown with a price" must find the section whose heading names the tier and check it contains a currency amount - asserting the heading's visibi...
- `EvidenceTracker.assert_empty` (method of `EvidenceTracker`): `EvidenceTracker.assert_empty(locator: str, label: str = '') -> None` - Assert an element has no text and no child elements.


## How It Works (Internals)

Private `_`-helpers - the module's real logic (21 items). Grouped under the public function that calls them.

### `EvidenceTracker.navigate(url: str, label: str = '') -> None` - method of `EvidenceTracker`

- `_dismiss_consent_overlays() -> None` (method of `EvidenceTracker`): Delegate to central consent dismissal utility.
- `_dismiss_ad_overlays() -> None` (method of `EvidenceTracker`): Delegate to central consent dismissal utility (includes ad overlay handling).
- `_record_step(step_type: str, label: str, locator: str | None = None, value: str | None = None, take_screenshot: bool = False, error: str | None = None, matched_text: str | None = None, fallback_used: bool = False, fallback_chain: list[dict[str, Any]] | None = None, elapsed_ms: int | None = None, fast_fail: bool = False, element_metadata: dict[str, Any] | None = None, expected_page: str = '') -> None` (method of `EvidenceTracker`): Record one evidence step. Args: expected_page: The page this step's locator was resolved against. When the step actually runs somewhere else the mismatch is recorded on the step result (page_mismatch) so a wrong-p...

### `EvidenceTracker.click(locator: str, label: str = '', expected_page: str = '') -> None` - method of `EvidenceTracker`

- `_is_modal_close_target(locator: str) -> bool` (method of `EvidenceTracker`): True when the locator is a confirmation-modal close control. Generated tests emit explicit "close popup / OK / Continue Shopping" steps for added-to-cart modals; the tracker auto-dismisses those same modals before eve...
- `_dismiss_confirmation_modals() -> None` (method of `EvidenceTracker`): Dismiss confirmation modals/popups that block pointer events. E-commerce sites show an "added to cart" modal (#cartModal) that intercepts clicks on navigation links. Best-effort and non-destructive: if no modal is vis...
- `_get_element_metadata(locator: str | None = None) -> dict[str, Any]` (method of `EvidenceTracker`): Calculates bbox and viewport percentages for the element.
- `_verify_click_navigation(locator: str, label: str, el_metadata: dict[str, Any], original_url: str, pages_before: tuple[Page, ...] = ()) -> None` (method of `EvidenceTracker`): Ensure a "successful" click on a link actually navigated. Google's ad stack (FreeCmp consent dialog, #google_vignette) can swallow link clicks: Playwright reports the click as successful (even the JS el.click()'...

### `EvidenceTracker.__init__(page: Page, test_name: str, condition_ref: str = 'unknown', story_ref: str = 'unknown', *, evidence_root: Path | None = None, test_package_dir: Path | None = None) -> None` - method of `EvidenceTracker`

- `_load_previous_history() -> dict[str, int]` (method of `EvidenceTracker`): Load previous history; calls `load_run_history`; returns dict[str, int].
- `_load_previous_steps() -> list[dict[str, Any]]` (method of `EvidenceTracker`): Load previous steps; calls `load_steps`; returns list[dict[str, Any]].

### `EvidenceTracker.fill(locator: str, value: str, label: str = '', expected_page: str = '') -> None` - method of `EvidenceTracker`

- `_safe_page_url() -> str` (method of `EvidenceTracker`): Safe page url; returns str.
- `_select_option(locator: str, value: str) -> None` (method of `EvidenceTracker`): Select an option on a native <select>, robust to value/label mismatch. LLM fill values are nondeterministic ("Electric Company") and rarely equal the option's value attribute ("electric") or its exact label ("City...
- `_locator_tag(locator: str) -> str` (method of `EvidenceTracker`): Return the resolved element's tag name for a locator, or empty. Uses Playwright's own engine to inspect the first matching element - cheap, and avoids a CSS tag parse that would misread compound selectors. Empty on an...

### `EvidenceTracker.write(status: str = 'passed') -> str` - method of `EvidenceTracker`

- `_persist_sidecar(status: str) -> None` (method of `EvidenceTracker`): Write the current steps + run history to the sidecar JSON. Called incrementally by _record_step (B-035) and finally by write() with the definitive status.

### `EvidenceTracker.assert_attribute(locator: str, attribute: str, label: str = '', *, forbidden: tuple[str, ...] = (), must_be_url: bool = False, required_scheme: str = '') -> None` - method of `EvidenceTracker`

- `_attribute_violations(value: str, *, forbidden: tuple[str, ...] = (), must_be_url: bool = False, required_scheme: str = '') -> list[str]` (method of `EvidenceTracker`): B-069 part b: predicate violations for an attribute value. A value violates the condition when it contains any forbidden substring (case-insensitive), when must_be_url and it is not an http(s) URL, or when requi...

### Internal utilities

- `_same_page(expected: str, actual: str) -> bool` (function): Return True when two URLs address the same page. Compares scheme + host + path only, ignoring query and fragment: SPA mocks encode state in the query (success.html?item=blue-top) and a differing query is not evide...
- `_clean_label(label: str) -> str` (method of `EvidenceTracker`): Convert raw placeholder tokens into cleaner user-facing labels.
- `_find_new_tab(pages_before: tuple[Page, ...]) -> Page | None` (method of `EvidenceTracker`): B-072: return the most recent page opened after the click, if any.
- `_wait_for_navigation(original_url: str, pages_before: tuple[Page, ...], timeout: float) -> str | Page` (method of `EvidenceTracker`): B-072: poll up to *timeout* seconds for a navigation event. Returns "url" when the original page navigated, the new Page when a new tab appeared, or "none" when neither happened in the window.
- `_record_new_tab_navigation(new_tab: Page, label: str, el_metadata: dict[str, Any], original_url: str) -> None` (method of `EvidenceTracker`): B-072: the click opened a new tab - the navigation went there. Wait for the new tab to load, record its final URL on the click step (plus whether it matches the link's href), then close the tab so the suite continues...
- `_url_changed(original_url: str, timeout: float) -> bool` (method of `EvidenceTracker`): Poll for a URL change within *timeout* seconds.
- `_amend_last_click_to_failure(label: str, locator: str, original_url: str, detail: str | None = None) -> None` (method of `EvidenceTracker`): Flip the last recorded passed/partial click step to a truthful failure.
