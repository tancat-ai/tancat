# `src/credential_redaction.py`

## High-Level Purpose

Credential redaction for evidence artifacts (AI-045 §8.4 item 5). Ensures typed
secrets (passwords, API keys, tokens) never persist in the clear in either
evidence channel: the per-test sidecar JSON (`<test>.evidence.json`) or the
full-page PNG screenshots captured during test execution.

Consumed by `src.evidence_tracker.EvidenceTracker`:
- `fill()` classifies the target field before filling; sensitive fields get
  their value replaced by `***REDACTED***` in the recorded step (both success
  and failure paths) and in any label embedding the raw value.
- `_record_step()` wraps every evidence screenshot in
  `masked_screenshot_page()`, which temporarily blanks filled sensitive inputs
  for the capture and restores the originals afterwards.
- `navigate()` records URLs with basic-auth userinfo stripped
  (`https://user:pass@host` → `https://host`).

## Module Metadata

- **Lines:** ~230
- **Imports:** `json`, `re`, `collections.abc.Iterator`, `contextlib.contextmanager`, `typing.Any`

## Constants

- `REDACTED = "***REDACTED***"` — marker written into evidence.
- `_SENSITIVE_TOKEN_RE` — broad credential-ish token regex with explicit
  lookaround boundaries (NOT `\b`, which misses snake_case like
  `user_password`): password/passwd/pwd, secret, token, api key variants,
  client/private/access key/secret, credential, cvv/cvc/csc, ssn, otp,
  one-time-pin. Case-insensitive.
- `_CAMEL_BOUNDARY_RE` — splits camelCase compounds (`accessToken`) before a
  second matching pass.
- `_PROBED_ATTRIBUTES` — live element attributes probed: id, name,
  placeholder, aria-label, data-testid.

## Functions

### `looks_sensitive(text: str) -> bool`
Purely lexical check for credential-ish tokens. camelCase-aware: splits at
case boundaries then re-matches, so `accessToken` and `apiKeyField` are caught.

### `is_sensitive_field(page: Any, locator: str) -> bool`
Three-layer field classification, cheapest first:
1. The locator string itself (`#password`, `[name='api-key']`).
2. Live element attributes — `type="password"` is always sensitive; the
   probed attributes go through `looks_sensitive`.
3. The element's associated `<label>` text (via `evaluate`).

Defensive by design: every Playwright probe is wrapped so missing elements
(e.g. a fill about to fail) or MagicMock pages degrade to layer 1 only.

### `redact_value(value: str) -> str`
Returns the fixed `REDACTED` marker.

### `redact_text(text: str, secret: str, replacement: str = REDACTED) -> str`
Replaces occurrences of `secret` inside `text`; no-op when secret is empty or
absent (explicit labels that never quoted the value pass through untouched).

### `redact_url_credentials(url: str) -> str`
Strips `user:password@` userinfo from a URL string; returns input unchanged
when no userinfo present or parsing fails.

### `masked_screenshot_page(page)` (context manager)
Temporarily blanks every filled sensitive input on the page via JS
(`_MASK_JS`: matches `type="password"` OR attribute haystack against the same
token pattern embedded as a JS RegExp, with the same camelCase pre-split),
yields for the screenshot call, then restores original values (`_RESTORE_JS`)
in `finally`. Stash lives on `window.__evidenceRedactionStash`. Best-effort:
evaluation failures (about:blank, closed context, mock pages) skip masking
silently — evidence collection must never break test execution.

## Tests

`tests/test_credential_redaction.py` — 51 unit tests + 1 real-browser
integration test (`integration`-marked, run explicitly):
classification positives/negatives, layer degradation on mocks, redaction
primitives, mask/restore lifecycle ordering, EvidenceTracker wiring
(sensitive/non-sensitive fill, failure path, URL userinfo), pixel-level
roundtrip against Chromium.
