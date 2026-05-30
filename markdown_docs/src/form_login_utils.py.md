# `src/form_login_utils.py`

## Purpose
Login form detection and filling utilities. Handles common demo-site login patterns (saucedemo.com, generic forms) for stateful scraping.

## Metadata
- **Lines:** 104
- **Imports:** typing.Any, src.journey_scraper.CredentialProfile

## Public API
| Function | Description |
|----------|-------------|
| `attempt_login(page, credential_profile)` | Detects and fills login forms. Uses credential_profile if provided, otherwise detects forms only |

## Private Helpers
| Function | Description |
|----------|-------------|
| `_try_saucedemo_login(page, username, password)` | Strategy 1: id-based selectors (#user-name, #password, #login-button) with visibility checks |
| `_try_generic_form_login(page, username, password)` | Strategy 2: generic form detection (form > input[type=text] + input[type=password] + button[type=submit]) |
| `_detect_login_forms_only(page)` | Detects login forms without filling — for anonymous/pre-filled access |

## Key Logic
- Two-strategy approach: saucedemo-style first, then generic form fallback
- All strategies wrapped in try/except with silent pass on failure
- Visibility checks with short timeouts (2000ms for saucedemo, 1000ms for generic) before filling
- After clicking login, waits for `networkidle` (10s timeout)
- CredentialProfile from `src.journey_scraper` provides username/password
- If credential_profile is None, only detects forms without filling