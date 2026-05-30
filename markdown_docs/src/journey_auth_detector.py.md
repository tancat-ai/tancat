# journey_auth_detector.py

## Purpose
Authentication detection helpers for journey scraping. Extracted from `journey_scraper.py` to keep the scraper focused on its core responsibility (following user journeys). These functions detect unexpected auth redirects, SSO gateways, MFA prompts, and CAPTCHAs so the pipeline can surface meaningful errors instead of silently failing.

## Location
`src/journey_auth_detector.py` (69 lines)

## Dependencies
- **Standard library only**: `re`, `urllib.parse`

## Public API

### `detect_auth_redirect(page_url: str, intended_url: str, page_title: str, h1_text: str) -> bool`
Returns `True` if the current page appears to be an unexpected auth redirect. Checks:
- URL/domain mismatch after navigation
- Page title or H1 contains auth keywords (login, sign in, authenticate, session expired, etc.)

### `detect_sso(base_domain: str, current_url: str) -> bool`
Returns `True` if navigation left the base domain (likely SSO redirect).

### `detect_mfa(page_html: str) -> bool`
Returns `True` if the page contains MFA-related inputs. Detects:
- `type="tel"` inputs (phone code entry)
- Labels containing MFA keywords (verification code, authenticator, one-time, 2fa, two-factor)

### `detect_captcha(page_html: str) -> bool`
Returns `True` if the page contains CAPTCHA iframes or elements. Detects:
- Known CAPTCHA domains: `google.recaptcha.net`, `hcaptcha.com`, `captcha.`
- CAPTCHA-related element text (captcha, recaptcha, hcaptcha)

## Detection Patterns
| Pattern | Purpose |
|---------|---------|
| `_AUTH_REDIRECT_KEYWORDS` | Login/sign-in/authenticate/session expired keywords |
| `_MFA_LABEL_PATTERN` | MFA verification keywords |
| `_CAPTCHA_DOMAINS` | Known CAPTCHA service domains |
| `_CAPTCHA_ELEMENT_PATTERN` | CAPTCHA element text patterns |

## Design Notes
- All functions are pure (no side effects) — easy to test in isolation
- Regex patterns are pre-compiled at module level for performance
- Extracted from `journey_scraper.py` during refactoring to separate auth detection concerns from DOM scraping

## Related Files
- `src/journey_scraper.py` — consumer of these detection helpers
- `src/state_tracker.py` — DOM state tracking used during journey scraping