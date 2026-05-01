# FEATURE SPEC: AI-009 Phase B — Authenticated Journey Scraping

**Status:** Design complete — ready for implementation  
**Priority:** Highest — core value driver  
**Depends on:** AI-009 Phase A (already implemented)  
**Created:** 2026-03-29

---

## Problem Statement

The current scraper (`scrape_multiple_pages`) opens a fresh browser for each URL with no
session state. Any page behind a login wall redirects to the login page. The scraper
silently returns login page context for every authenticated URL, and the LLM generates
tests full of invented selectors for pages it never actually saw.

Additionally, many real applications have dynamic URLs (e.g. `/order/78451`,
`/dashboard?session=abc123`) that the user cannot know in advance. Phase A's
user-supplied URL list cannot handle these.

Phase B fixes both problems by navigating a full browser session through a
user-defined journey, capturing page context at each step.

---

## Solution Overview

Replace the per-URL subprocess calls for authenticated flows with a **single subprocess
that receives a full journey definition**, navigates it in one browser session, and
returns all captured page contexts as JSON.

The journey is defined as an ordered list of steps. Each step is one of:

| Step Type | What it does |
|-----------|-------------|
| `goto` | Navigate directly to a URL |
| `click` | Click an element by selector or visible text |
| `fill` | Fill an input field with a value |
| `submit` | Click a submit button |
| `capture` | Capture page context at the current page |
| `wait` | Wait for a selector to appear before continuing |

The user builds this journey in the UI. The scraper executes it and returns context
for every `capture` step.

---

## Auth Redirect Detection (Silent Failure Fix)

After every `goto` and after every `capture`, the scraper must check:

1. Does the current URL match the intended URL?
2. Does the page title or H1 contain any of: `login`, `sign in`, `sign-in`,
   `authenticate`, `log in`, `session expired`?

If either condition is true, the step is marked as `redirected_to_auth` and the
scraper returns a clear error message for that step:

```
"Page redirected to login — add a login step before this page in your journey"
```

This error surfaces in the sidebar as a warning. Scraping continues for any
remaining steps that succeed. The final result contains whatever context was
successfully captured before the auth wall.

---

## Out of Scope (Explicit Errors, Not Silent Failures)

The scraper must detect these conditions and return a clear error message — never
attempt to handle them silently:

| Condition | Detection | Error message |
|-----------|-----------|---------------|
| SSO / OAuth redirect | URL domain changes from base domain mid-journey | "SSO/OAuth redirect detected — automated login not supported for this provider" |
| MFA / 2FA prompt | Page contains inputs with type=tel or labels matching "verification code", "authenticator", "one-time" | "MFA prompt detected — automated login not supported" |
| CAPTCHA | Page contains iframe from known CAPTCHA providers, or element with id/class containing "captcha", "recaptcha", "hcaptcha" | "CAPTCHA detected — automated login not supported" |

In all three cases: stop the journey, return whatever context was captured before
the blocker, surface the error clearly in the UI.

---

## Credential Profiles

Users can define one or more credential profiles. Each profile has:

- `label` — display name (e.g. "Admin user", "Standard user", "Checkout test account")
- `username` — the username or email to fill
- `password` — the password to fill

**Storage:** Session state only (`st.session_state`). Never persisted to disk.
Never committed. Cleared when Streamlit restarts.

Multiple profiles allow testing access control — e.g. verify that an admin
button is visible for "Admin user" but not for "Standard user".

---

## New Data Classes (add to `src/page_context_scraper.py`)

### `JourneyStep`

```python
@dataclass
class JourneyStep:
    step_type: Literal["goto", "click", "fill", "submit", "capture", "wait"]
    url: str | None = None           # for goto steps
    selector: str | None = None      # CSS selector or role locator
    visible_text: str | None = None  # for click steps — alternative to selector
    value: str | None = None         # for fill steps
    label: str | None = None         # display name shown in UI
    capture_label: str | None = None # label for captured context (e.g. "Dashboard")
```

### `JourneyResult`

```python
@dataclass
class JourneyResult:
    success: bool
    captured_pages: list[PageContext]
    failed_steps: list[str]          # human-readable descriptions of failures
    error_message: str | None = None # top-level error (SSO, MFA, CAPTCHA)
    redirected_urls: list[str] = field(default_factory=list)
```

### `CredentialProfile`

```python
@dataclass
class CredentialProfile:
    label: str
    username: str
    password: str
```

---

## New Function: `execute_journey`

Add to `src/page_context_scraper.py`:

```python
def execute_journey(
    journey_steps: list[JourneyStep],
    timeout_ms: int = 10_000,
    progress_callback: Callable[..., Any] | None = None,
) -> JourneyResult:
```

This function runs the journey in a **single subprocess** (same pattern as
`scrape_page_context` — subprocess to avoid Streamlit's ProactorEventLoop issue).

The subprocess receives the journey steps as JSON via stdin or a temp file,
executes them in one Playwright browser session, and returns a `JourneyResult`
as JSON via stdout.

Internally the subprocess uses `_execute_journey_process(steps, timeout_ms)`
which is the actual Playwright implementation — same pattern as
`_run_playwright_scraper_process`.

---

## UI Changes (`streamlit_app.py`)

### Credential Profiles Section

Add a new expander below the existing "Add more pages" expander:

```
🔐 Authentication (optional)
```

Inside:

1. **"Pages require login" toggle** (`st.toggle`) — when off, entire section is
   hidden and scraper behaves as today.

2. **Credential profiles** — when toggle is on, show:
   - List of existing profiles (label, username, password fields inline)
   - "Add profile" button — adds a new empty profile row
   - "Remove" button per profile
   - Profiles stored in `st.session_state.credential_profiles: list[dict]`

3. **Active profile selector** — `st.selectbox` populated from profile labels.
   The selected profile is used for `fill` steps that reference `{{username}}`
   and `{{password}}` placeholders (see Journey Builder below).

### Journey Builder Section

Add a new expander:

```
🗺️ Journey steps (optional — for dynamic or authenticated pages)
```

Inside:

- Instruction text: "Define the steps the scraper will follow. Add a Capture
  step wherever you want page context collected."

- List of steps, each rendered as a row:
  - Step type selector (`st.selectbox`): goto / click / fill / capture / wait
  - Dynamic fields depending on type:
    - `goto` → URL text input
    - `click` → selector or visible text input (two sub-options via radio)
    - `fill` → selector input + value input (value can be `{{username}}` or
      `{{password}}` to pull from active credential profile)
    - `capture` → label input (e.g. "Dashboard page", "Cart page")
    - `wait` → selector input
  - "Remove step" button per row

- "Add step" button — appends a new empty step row

- Steps stored in `st.session_state.journey_steps: list[dict]`

- **Auto-populate button**: "Build from URL list" — converts the existing
  additional URLs textarea into a journey of goto + capture steps. This gives
  users a quick start for non-authenticated multi-page flows.

### Generation Flow Changes

In the generate button handler, the decision tree becomes:

```
if journey_steps defined and non-empty:
    use execute_journey() → JourneyResult → MultiPageContext
elif additional_urls defined:
    use scrape_multiple_pages() → MultiPageContext   (existing Phase A)
else:
    use scrape_page_context() → PageContext          (existing single page)
```

The resulting context is passed to the LLM prompt regardless of which path
was taken — no changes needed to prompt assembly or test generation.

---

## Error Surfacing in the UI

All scraper errors (auth redirect, SSO, MFA, CAPTCHA, timeout) must surface
in the sidebar as `st.warning()` with enough detail for the user to fix their
journey definition. They must never be silently swallowed.

Format:
```
⚠️ Scraper: [step label or URL] — [error message]
```

If some pages succeeded and some failed, show both:
- How many pages were captured successfully
- Which steps failed and why

---

## Implementation Order

Implement in this order. Each step should be independently testable before
moving to the next.

1. **`JourneyStep`, `JourneyResult`, `CredentialProfile` dataclasses** —
   add to `src/page_context_scraper.py`

2. **`_execute_journey_process()`** — the Playwright implementation that runs
   inside the subprocess. Handles: goto, click, fill, submit, capture, wait,
   auth redirect detection, SSO/MFA/CAPTCHA detection.

3. **`execute_journey()`** — the public function that serialises the journey
   to JSON, spawns the subprocess, deserialises the result.

4. **Unit tests** — `tests/test_journey_scraper.py`:
   - Journey with only goto + capture steps (no auth)
   - Auth redirect detection returns correct error
   - CAPTCHA detection returns correct error
   - Failed step doesn't prevent subsequent steps from running
   - `{{username}}` / `{{password}}` placeholders are substituted correctly

5. **UI — Credential profiles section** in `streamlit_app.py`

6. **UI — Journey builder section** in `streamlit_app.py`

7. **UI — Generation flow decision tree** updated in `streamlit_app.py`

---

## Protected Files — Do Not Touch

- `src/llm_client.py`
- `src/test_generator.py`
- `main.py`
- `.github/workflows/ci.yml`

---

## Verification (run before finishing)

```bash
bash fix.sh
pytest tests/test_journey_scraper.py -v
pytest tests/ -v
```

All must pass clean. Stop after that.

---

## Notes for Cline

- The subprocess pattern is already established in `scrape_page_context()` —
  follow the exact same pattern for `execute_journey()`. Do not attempt to run
  Playwright directly in the Streamlit thread.
- Credential values must never appear in log output or error messages.
- `{{username}}` and `{{password}}` are the only template placeholders — do
  not invent others.
- The journey builder UI stores state in `st.session_state` — follow the
  existing session state patterns in `streamlit_app.py`.
- Do not modify the existing `scrape_page_context()` or `scrape_multiple_pages()`
  functions — Phase B is additive only.
