"""Credential redaction for evidence artifacts (AI-045 §8.4 item 5).

Generated tests type real credentials (username/password/API keys) into forms
during execution. Two evidence channels previously captured those values in
the clear:

1. **Sidecar JSON** — ``EvidenceTracker.fill()`` recorded ``value=<secret>``
   and a default label ``"Fill <locator> with '<secret>'"`` into
   ``<test>.evidence.json``.
2. **Screenshots** — full-page evidence screenshots show any filled field
   whose content is not rendered masked by the browser (native
   ``<input type="password">`` paints dots, but API-key/token fields typed
   into plain ``<input type="text">`` elements leak verbatim).

This module provides the detection + redaction primitives used by
``EvidenceTracker`` so neither channel ever persists a secret:

- :func:`looks_sensitive` / :func:`is_sensitive_field` — heuristic field
  classification (locator text + live element attributes + label text).
- :func:`redact_value` / :func:`redact_text` — value/label redaction.
- :func:`redact_url_credentials` — strip ``user:password@`` userinfo from URLs.
- :func:`masked_screenshot_page` — context manager that temporarily blanks
  every filled sensitive input on the page for the duration of a screenshot,
  then restores the original values.

Detection is deliberately defensive: every live-DOM probe is wrapped so a
missing element or a MagicMock page degrades to locator-string matching only.
False positives cost nothing (a benign value is masked in evidence); false
negatives leak credentials, so the token list errs on the broad side.
"""

import json
import re
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

__all__ = [
    "REDACTED",
    "looks_sensitive",
    "is_sensitive_field",
    "redact_value",
    "redact_text",
    "redact_url_credentials",
    "masked_screenshot_page",
]

#: Marker written into evidence in place of a detected secret.
REDACTED = "***REDACTED***"

# Broad credential-ish tokens. Word-boundary anchored on the left so e.g.
# "author" does not match "auth"; right side stays open so "tokens",
# "password_hint", "apiKeyField" all match.
# Broad credential-ish tokens. Boundaries are explicit lookarounds rather
# than ``\b`` so snake_case names ("user_password", "card_cvv") still match
# — underscore is a word character and would defeat ``\b``.
_SENSITIVE_TOKEN_RE = re.compile(
    r"(?i)(?<![a-z0-9])(passwo?r?d|passwd|pwd|secret|token|api[\s\-_]?key|"
    r"client[-_]?secret|private[-_]?key|access[-_]?key|credential|"
    r"cv[vc]|csc|ssn|one[-_]?time[-_]?pin|otp)(?![a-z0-9])"
)

#: Attributes probed on the live element (in addition to ``type``) when
#: classifying a field as sensitive.
_PROBED_ATTRIBUTES = ("id", "name", "placeholder", "aria-label", "data-testid")


_CAMEL_BOUNDARY_RE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def looks_sensitive(text: str) -> bool:
    """Return True when *text* contains a credential-ish token.

    Used on locator strings, element attributes and label text. Purely
    lexical — never touches the DOM. camelCase compounds ("accessToken",
    "apiKeyField") are split at case boundaries before matching.
    """
    s = str(text or "")
    if _SENSITIVE_TOKEN_RE.search(s):
        return True
    if _CAMEL_BOUNDARY_RE.search(s):
        return bool(_SENSITIVE_TOKEN_RE.search(_CAMEL_BOUNDARY_RE.sub("_", s)))
    return False


def is_sensitive_field(page: Any, locator: str) -> bool:
    """Classify whether the target of *locator* holds (or will hold) a secret.

    Three layers, cheapest first:
      1. The locator string itself (``#password``, ``[name='api-key']`` …).
      2. Live element attributes — ``type="password"`` is always sensitive;
         id/name/placeholder/aria-label/data-testid go through
         :func:`looks_sensitive`.
      3. The element's associated ``<label>`` text.

    Any Playwright error (element missing — e.g. the fill is about to fail —
    or a mock page returning MagicMocks) degrades gracefully: non-string
    results are ignored, so classification falls back to layer 1.
    """
    # Layer 1: the locator string alone.
    if looks_sensitive(locator):
        return True

    try:
        loc = page.locator(locator).first
    except Exception:
        return False

    # Layer 2: element attributes.
    for attr in _PROBED_ATTRIBUTES:
        value: Any = None
        try:
            value = loc.get_attribute(attr)
        except Exception:
            value = None
        if isinstance(value, str) and looks_sensitive(value):
            return True

    try:
        input_type = loc.get_attribute("type")
    except Exception:
        input_type = None
    if isinstance(input_type, str) and input_type.strip().lower() == "password":
        return True

    # Layer 3: associated <label> text.
    try:
        label_text = loc.evaluate(
            "el => { const l = el.labels && el.labels[0];"
            " const d = el.closest('label');"
            " return (l ? l.textContent : '') || (d ? d.textContent : ''); }"
        )
        if isinstance(label_text, str) and looks_sensitive(label_text):
            return True
    except Exception:
        pass

    return False


def redact_value(value: str) -> str:
    """Return the fixed redaction marker for a detected secret."""
    return REDACTED


def redact_text(text: str, secret: str, replacement: str = REDACTED) -> str:
    """Replace occurrences of *secret* inside *text* with *replacement*.

    No-op when *secret* is empty or not present, so explicitly supplied
    labels that never contained the value pass through untouched.
    """
    if not secret or not text:
        return text
    return text.replace(secret, replacement)


def redact_url_credentials(url: str) -> str:
    """Strip ``user:password@`` userinfo from a URL string.

    Basic-auth credentials sometimes appear in navigation URLs
    (``https://admin:s3cret@host/``). Returns the URL unchanged when no
    userinfo is present or the string does not parse.
    """
    try:
        parts = url.split("://", 1)
        if len(parts) != 2 or "@" not in parts[1]:
            return url
        scheme, rest = parts
        authority, _, remainder = rest.partition("/")
        if "@" not in authority:
            return url
        host = authority.rsplit("@", 1)[1]
        return f"{scheme}://{host}/{remainder}"
    except Exception:
        return url


# ── Screenshot masking ────────────────────────────────────────────────────

# Embed the same token pattern (without the Python-only inline flag) as a JS
# RegExp so browser-side detection matches the Python-side heuristics exactly.
_JS_TOKEN_PATTERN = _SENSITIVE_TOKEN_RE.pattern.replace("(?i)", "")
_MASK_JS = """() => {
    const rx = new RegExp(__TOKEN_PATTERN__, 'i');
    const fields = Array.from(document.querySelectorAll('input, textarea'));
    const stash = [];
    for (const el of fields) {
        const val = el.value || '';
        if (!val) continue;
        const t = (el.getAttribute('type') || '').toLowerCase();
        // Split camelCase so 'accessToken' matches the same tokens as Python.
        const hay = [
            el.id, el.name, el.getAttribute('placeholder'),
            el.getAttribute('aria-label'), el.getAttribute('data-testid'),
        ].filter(Boolean).join(' ').replace(/([a-z0-9])([A-Z])/g, '$1_$2');
        if (t === 'password' || rx.test(hay)) {
            stash.push([el, val]);
            el.value = '';
        }
    }
    window.__evidenceRedactionStash = stash;
    return stash.length;
}""".replace("__TOKEN_PATTERN__", json.dumps(_JS_TOKEN_PATTERN))

_RESTORE_JS = """() => {
    const stash = window.__evidenceRedactionStash || [];
    for (const pair of stash) {
        try { pair[0].value = pair[1]; } catch (err) { /* detached node */ }
    }
    window.__evidenceRedactionStash = [];
    return stash.length;
}"""


@contextmanager
def masked_screenshot_page(page: Any) -> Iterator[None]:
    """Temporarily blank filled sensitive inputs while *page* is screenshotted.

    Usage::

        with masked_screenshot_page(page):
            page.screenshot(path=..., full_page=True)

    Best-effort by design: if evaluation fails (about:blank, closed context,
    mock page) masking is skipped silently and the screenshot proceeds —
    evidence collection must never break test execution. Values are restored
    in the ``finally`` block whenever masking was applied.
    """
    masked = False
    try:
        result = page.evaluate(_MASK_JS)
        masked = isinstance(result, int) and result > 0
    except Exception:
        masked = False
    try:
        yield
    finally:
        if masked:
            try:
                page.evaluate(_RESTORE_JS)
            except Exception:
                pass
