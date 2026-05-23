# Session 1: Data Models + Core Journey Execution

**AI-009 Phase B — Authenticated Journey Scraping**  
**Created:** 2026-05-12  
**Depends on:** AI-009 Phase A (complete)  
**Original spec:** `docs/specs/FEATURE_SPEC_AI009_phase_b.md`

---

## Goal

Add `JourneyResult` and `CredentialProfile` dataclasses, implement `execute_journey()`
with subprocess pattern, and add auth redirect / SSO / MFA / CAPTCHA detection.

---

## Current State of Relevant Files

### src/journey_scraper.py (630 lines)
- **Already has:** `JourneyStep` dataclass (uses `action` field, NOT `step_type`),
  `ScrapedStep` dataclass (defined but unused), subprocess pattern via
  `_scrape_journey_via_subprocess()`, sync Playwright logic via
  `_scrape_journey_sync()`, `CartSeedingScraper`, consent overlay dismissal,
  selector discovery (`_discover_selector`), scroll-into-view click helper
- **Missing:** `JourneyResult`, `CredentialProfile`, `execute_journey()`,
  auth redirect detection, SSO/MFA/CAPTCHA detection

### src/stateful_scraper.py (268 lines)
- **Already has:** `_attempt_login()` with hardcoded `standard_user`/`secret_sauce`,
  `_seed_cart_session()`, `_dismiss_consent_overlays()`
- **Will be modified in Session 2** (not this session)

### tests/test_journey_scraper.py (104 lines)
- **Already has:** Basic initialization tests for `JourneyStep`, `JourneyScraper`,
  `CartSeedingScraper`, selector constants
- **Needs:** Tests for new dataclasses, execute_journey, detection logic

---

## Rules (from AGENTS.md)

- **Package manager:** `uv add` / `uv sync` — NEVER use `pip`
- **Test format:** pytest sync + playwright fixtures — NEVER async def
- **Type hints:** All functions must have full type annotations
- **Helper functions:** Go in `src/`, NOT in `streamlit_app.py`
- **Quality gates:** ruff → mypy → pytest before declaring done
- **Protected files — DO NOT TOUCH:**
  - `src/llm_client.py`
  - `src/test_generator.py`
  - `src/llm_providers/`
  - `.github/workflows/ci.yml`

---

## Tasks in Order

### Task 1: Add dataclasses to src/journey_scraper.py

Add AFTER existing `JourneyStep` and `ScrapedStep` dataclasses:

```python
@dataclass
class CredentialProfile:
    """User-defined credentials for authenticated journey scraping.
    
    Stored in session state only — never persisted to disk.
    """
    label: str
    username: str
    password: str


@dataclass
class JourneyResult:
    """Result of executing a journey through authenticated pages."""
    success: bool
    captured_pages: dict[str, list[dict[str, Any]]]  # url -> elements
    failed_steps: list[str]                          # human-readable descriptions
    error_message: str | None = None                 # top-level error (SSO, MFA, CAPTCHA)
    redirected_urls: list[str] = field(default_factory=list)
```

**Important:** Keep `JourneyStep.action` field as-is (do NOT rename to `step_type`).

---

### Task 2: Implement _execute_journey_sync() in src/journey_scraper.py

Sync Playwright implementation that runs inside a subprocess.

```python
def _execute_journey_sync(
    journey_steps: list[JourneyStep],
    credential_profile: CredentialProfile | None = None,
    timeout_ms: int = 30_000,
    starting_url: str | None = None,
) -> JourneyResult:
    """Execute journey steps in a single Playwright browser session.
    
    Checks for auth redirects, SSO, MFA, and CAPTCHA — returns explicit errors.
    """
```

**Required behavior:**

1. **Step execution:** Iterate through journey_steps, execute each by `action`:
   - `goto` → `page.goto(url)` with timeout
   - `click` → Click element by `selector` or `text` (use existing `_click_selector`)
   - `fill` → Fill input by `selector` with `text` value (use existing `_fill_selector`)
   - `submit` → Click submit button (reuse click logic)
   - `capture` → Capture page context using existing scrape logic
   - `wait` → Wait for `selector` to appear

2. **Template substitution:** In `fill` steps, replace `{{username}}` and `{{password}}`
   from `credential_profile` if provided.

3. **Auth redirect detection** — After every `goto` and `capture`:
   - Check if current URL matches intended URL
   - Check page title and H1 text for: `login`, `sign in`, `sign-in`, `authenticate`,
     `log in`, `session expired`
   - If detected: mark step as `redirected_to_auth`, add to `redirected_urls`,
     add to `failed_steps`: `"Page redirected to login — add a login step before this page"`

4. **SSO detection** — After every navigation:
   - If URL domain changes from base domain (derived from first goto or starting_url)
   - Stop journey, set `error_message`:
     `"SSO/OAuth redirect detected — automated login not supported for this provider"`

5. **MFA detection** — After every navigation:
   - Check for inputs with `type="tel"` or labels matching
     `"verification code"`, `"authenticator"`, `"one-time"`
   - Stop journey, set `error_message`:
     `"MFA prompt detected — automated login not supported"`

6. **CAPTCHA detection** — After every navigation:
   - Check for iframe from known CAPTCHA providers (google.recaptcha.net, hcaptcha.com)
   - Check for element id/class containing `"captcha"`, `"recaptcha"`, `"hcaptcha"`
   - Stop journey, set `error_message`:
     `"CAPTCHA detected — automated login not supported"`

7. **Consent overlay dismissal:** Reuse existing consent dismissal logic from
   `_scrape_journey_sync()` before each capture.

8. **Return:** `JourneyResult` with all captured pages, failed steps, and any top-level error.

---

### Task 3: Implement execute_journey() public function

```python
def execute_journey(
    journey_steps: list[JourneyStep],
    credential_profile: CredentialProfile | None = None,
    timeout_ms: int = 30_000,
    starting_url: str | None = None,
) -> JourneyResult:
    """Execute a journey in a subprocess (avoids ProactorEventLoop on Windows).
    
    Serialises steps to JSON, spawns subprocess, deserialises JourneyResult.
    """
```

**Pattern:** Follow `_scrape_journey_via_subprocess()` exactly:
1. Serialize `journey_steps` + `credential_profile` + params to JSON
2. Spawn subprocess with `sys.executable` + script that calls `_execute_journey_sync`
3. Send JSON via stdin, read JSON from stdout
4. Deserialize to `JourneyResult`
5. Handle subprocess errors gracefully

---

### Task 4: Unit tests — tests/test_journey_scraper.py

Add tests for new functionality. Since Playwright can't run in unit tests easily,
mock the subprocess or test data model logic:

```
- test_journey_result_creation
- test_journey_result_serialization
- test_credential_profile_creation
- test_auth_redirect_detection_url_mismatch
- test_auth_redirect_detection_login_keywords
- test_sso_detection_domain_change
- test_mfa_detection_tel_input
- test_mfa_detection_verification_label
- test_captcha_detection_recaptcha_iframe
- test_captcha_detection_hcaptcha_class
- test_template_substitution_username_password
- test_failed_step_does_not_stop_journey
- test_journey_result_from_dict (deserialization)
```

Focus on the detection logic and data model. The subprocess pattern can be tested
with a simple integration test if needed.

---

## Acceptance Criteria

- [x] `ruff check src/journey_scraper.py` → clean
- [x] `mypy src/journey_scraper.py` → clean
- [x] `pytest tests/test_journey_scraper.py -v` → 45 tests pass
- [x] `JourneyResult` and `CredentialProfile` dataclasses exist and are fully typed
- [x] `execute_journey()` works with goto + capture steps (subprocess pattern)
- [x] Auth redirect detection returns correct error messages (7 test cases)
- [x] SSO / MFA / CAPTCHA detection stops journey with explicit errors (14 test cases)
- [x] Template substitution replaces `{{username}}` / `{{password}}` (5 test cases)
- [x] No protected files were modified

## Verification

```bash
ruff check src/journey_scraper.py        # clean
mypy src/journey_scraper.py              # clean
pytest tests/test_journey_scraper.py -v  # 45 passed
pytest tests/ -v                         # 576 passed
```

All pass clean. Completed 2026-05-12.

---

## Session Outcome

| Item | Status | Details |
|------|--------|---------|
| `src/journey_scraper.py` | ✅ Modified | +~440 lines: `CredentialProfile`, `JourneyResult`, `_execute_journey_sync()`, `execute_journey()`, detection helpers, subprocess entry point |
| `tests/test_journey_scraper.py` | ✅ Modified | +291 lines: 31 new tests covering data models, detection logic, template substitution |
| `src/llm_client.py` | ✅ Untouched | Protected |
| `src/test_generator.py` | ✅ Untouched | Protected |
| `src/llm_providers/` | ✅ Untouched | Protected |
| `.github/workflows/ci.yml` | ✅ Untouched | Protected |
| `streamlit_app.py` | ✅ Untouched | Session 3 scope |
| `orchestrator.py` | ✅ Untouched | Session 4 scope |
| `src/stateful_scraper.py` | ✅ Untouched | Session 2 scope |

---

## DO NOT

- Touch `streamlit_app.py` (Session 3)
- Touch `orchestrator.py` (Session 4)
- Modify existing `JourneyStep` (keep `action` field)
- Remove `ScrapedStep` (may be used later)
- Touch `src/stateful_scraper.py` (Session 2)
- Touch protected files listed above