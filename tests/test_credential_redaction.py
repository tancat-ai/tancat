"""Tests for src/credential_redaction.py (AI-045 §8.4 item 5).

Evidence artifacts (sidecar JSON + full-page screenshots) must never persist
typed credentials in the clear. Covers: field classification heuristics,
value/label/URL redaction primitives, the screenshot mask/restore lifecycle,
and the EvidenceTracker.fill() wiring (sensitive vs non-sensitive).
"""

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from src.credential_redaction import (
    _MASK_JS,
    _RESTORE_JS,
    REDACTED,
    is_sensitive_field,
    looks_sensitive,
    masked_screenshot_page,
    redact_text,
    redact_url_credentials,
    redact_value,
)
from src.evidence_tracker import EvidenceTracker

# ── looks_sensitive ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "text",
    [
        "password",
        "Password",
        "user_password",
        "confirm-password",
        "passwd",
        "pwd",
        "secret",
        "client_secret",
        "api_key",
        "apiKey",
        "api-key",
        "token",
        "accessToken",
        "credential",
        "cvv",
        "cvc",
        "ssn",
        "otp",
        "one-time-pin",
    ],
)
def test_looks_sensitive_positive(text: str) -> None:
    assert looks_sensitive(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "",
        "author",  # 'auth' prefix must not match
        "username",
        "first_name",
        "email",
        "search",
        "quantity",
        "street address",
    ],
)
def test_looks_sensitive_negative(text: str) -> None:
    assert looks_sensitive(text) is False


# ── is_sensitive_field ────────────────────────────────────────────────────


def _mock_page_with_attributes(attributes: dict[str, str], label_text: str = "") -> MagicMock:
    """A mock page whose locator resolves to an element with *attributes*."""
    page = MagicMock()
    loc = page.locator.return_value.first

    def get_attribute(name: str) -> Any:
        return attributes.get(name)

    loc.get_attribute.side_effect = get_attribute
    loc.evaluate.return_value = label_text
    return page


def test_is_sensitive_field_locator_string_alone() -> None:
    # Layer 1 fires before any DOM access — even a broken page object.
    assert is_sensitive_field(None, "#password") is True
    assert is_sensitive_field(None, "[name='api-key']") is True
    assert is_sensitive_field(MagicMock(), "input#user-password") is True


def test_is_sensitive_field_type_attribute() -> None:
    page = _mock_page_with_attributes({"type": "password"})
    # Locator string clean; classification must come from the live attribute.
    assert is_sensitive_field(page, "#login-field") is True


def test_is_sensitive_field_named_attribute() -> None:
    page = _mock_page_with_attributes({"name": "card_cvv"})
    assert is_sensitive_field(page, ".checkout-input") is True


def test_is_sensitive_field_label_text() -> None:
    page = _mock_page_with_attributes({}, label_text="API Key")
    assert is_sensitive_field(page, ".form-control") is True


def test_is_sensitive_field_benign() -> None:
    page = _mock_page_with_attributes(
        {"type": "text", "id": "first-name", "name": "fname"},
        label_text="First Name",
    )
    assert is_sensitive_field(page, "#first-name") is False


def test_is_sensitive_field_mock_degrades_to_layer1() -> None:
    # Raw MagicMock: every probe returns a MagicMock (not a str) — must not
    # raise, must fall through to False when the locator itself is clean.
    assert is_sensitive_field(MagicMock(), "#checkout-btn") is False


# ── redaction primitives ──────────────────────────────────────────────────


def test_redact_value_hides_secret() -> None:
    secret = "secret_sauce"
    result = redact_value(secret)
    assert secret not in result
    assert result == REDACTED


def test_redact_text_replaces_occurrences() -> None:
    assert redact_text("Fill #pw with 'hunter2'", "hunter2") == f"Fill #pw with '{REDACTED}'"


def test_redact_text_noop_when_absent() -> None:
    label = "Password"
    assert redact_text(label, "hunter2") == label


def test_redact_text_empty_secret() -> None:
    assert redact_text("some label", "") == "some label"


def test_redact_url_credentials_strips_userinfo() -> None:
    url = "https://admin:s3cret@example.com/dashboard?x=1"
    result = redact_url_credentials(url)
    assert "s3cret" not in result
    assert "admin" not in result
    assert result == "https://example.com/dashboard?x=1"


def test_redact_url_credentials_unchanged_without_userinfo() -> None:
    assert redact_url_credentials("https://example.com/a?b=c") == "https://example.com/a?b=c"


def test_redact_url_credentials_at_in_path_not_userinfo() -> None:
    url = "https://example.com/users/@me/settings"
    assert redact_url_credentials(url) == url


# ── masked_screenshot_page ────────────────────────────────────────────────


def test_masked_screenshot_masks_and_restores() -> None:
    page = MagicMock()
    page.evaluate.side_effect = [2, 0]  # mask found 2 fields, restore reports 0
    with masked_screenshot_page(page):
        page.screenshot(path="x.png")
    calls = [c.args[0] for c in page.evaluate.call_args_list]
    assert len(calls) == 2
    assert "__evidenceRedactionStash" in calls[0]  # MASK JS stashes originals
    assert "__evidenceRedactionStash" in calls[1]  # RESTORE JS replays stash
    assert "el.value = ''" in calls[0]
    assert "pair[0].value = pair[1]" in calls[1]


def test_masked_screenshot_no_restore_when_nothing_masked() -> None:
    page = MagicMock()
    page.evaluate.return_value = 0  # no sensitive fields filled
    with masked_screenshot_page(page):
        pass
    assert page.evaluate.call_count == 1  # restore never runs


def test_masked_screenshot_silent_on_evaluate_failure() -> None:
    page = MagicMock()
    page.evaluate.side_effect = Exception("about:blank")
    with masked_screenshot_page(page):  # must not raise
        pass
    assert page.evaluate.call_count == 1  # no restore attempt either


def test_masked_screenshot_restores_even_when_body_raises() -> None:
    page = MagicMock()
    page.evaluate.side_effect = [3, 0]
    with pytest.raises(RuntimeError), masked_screenshot_page(page):
        raise RuntimeError("boom")
    assert page.evaluate.call_count == 2  # restore still ran


def test_mask_and_restore_js_share_stash_key() -> None:
    """The two JS snippets must operate on the same window key."""
    assert "__evidenceRedactionStash" in _MASK_JS
    assert "__evidenceRedactionStash" in _RESTORE_JS
    # Browser-side detection mirrors the Python heuristic tokens.
    assert "password" in _MASK_JS
    assert "RegExp(" in _MASK_JS


# ── EvidenceTracker wiring ────────────────────────────────────────────────


def test_tracker_fill_sensitive_value_redacted(tmp_path: Path) -> None:
    """Sidecar JSON channel: '#password' fill records REDACTED, not the secret."""
    tracker = EvidenceTracker(MagicMock(), "test_redact", evidence_root=tmp_path)
    tracker.fill("#password", "secret_sauce")

    step = tracker.steps[-1]
    assert step["value"] == REDACTED
    assert "secret_sauce" not in str(step)
    # Default label built from the SAFE value.
    assert f"Fill #password with '{REDACTED}'" == step["label"]


def test_tracker_fill_explicit_label_quoting_secret_scrubbed(tmp_path: Path) -> None:
    tracker = EvidenceTracker(MagicMock(), "test_redact2", evidence_root=tmp_path)
    tracker.fill("#password", "hunter2", label="Type hunter2 into password box")

    step = tracker.steps[-1]
    assert "hunter2" not in step["label"]
    assert step["label"] == f"Type {REDACTED} into password box"


def test_tracker_fill_non_sensitive_keeps_value(tmp_path: Path) -> None:
    """Benign fields keep their real value — evidence stays useful."""
    tracker = EvidenceTracker(MagicMock(), "test_keep", evidence_root=tmp_path)
    tracker.fill("#first-name", "John")

    step = tracker.steps[-1]
    assert step["value"] == "John"
    assert step["label"] == "Fill #first-name with 'John'"


def test_tracker_fill_sensitive_failure_path_redacted(tmp_path: Path) -> None:
    """The failure path must redact too — that's exactly when screenshots fire."""
    page = MagicMock()
    tracker = EvidenceTracker(page, "test_fail_fill", evidence_root=tmp_path)

    # Make the actual fill blow up after detection succeeded.
    page.locator.return_value.fill.side_effect = Exception("not fillable")
    with pytest.raises(Exception, match="not fillable"):
        tracker.fill("#password", "secret_sauce")

    step = tracker.steps[-1]
    assert step["result"]["status"] == "failed"
    assert step["value"] == REDACTED
    assert "secret_sauce" not in str(step)


def test_tracker_navigate_redacts_url_userinfo(tmp_path: Path) -> None:
    page = MagicMock()
    tracker = EvidenceTracker(page, "test_nav", evidence_root=tmp_path)
    tracker.navigate("https://admin:s3cret@example.com/")

    step = tracker.steps[-1]
    assert "s3cret" not in str(step)
    assert step["value"] == "https://example.com/"


def test_tracker_screenshot_wrapped_in_masking(tmp_path: Path) -> None:
    """Every evidence screenshot goes through the mask/restore lifecycle."""
    page = MagicMock()
    # First evaluate (mask) reports 1 masked field; second (restore) 0.
    # Any earlier evaluates come from consent-overlay dismissal.
    page.evaluate.side_effect = lambda js, *a, **k: (
        1 if "__evidenceRedactionStash" in js and "el.value = ''" in js else 0
    )
    tracker = EvidenceTracker(page, "test_shot", evidence_root=tmp_path)
    tracker.navigate("https://example.com")

    calls = page.method_calls
    shot_index = next(i for i, c in enumerate(calls) if c[0] == "screenshot")
    mask_index = next(
        i for i, c in enumerate(calls) if c[0] == "evaluate" and "el.value = ''" in str(c.args[0] if c.args else "")
    )
    restore_index = next(
        i
        for i, c in enumerate(calls)
        if c[0] == "evaluate" and "pair[0].value = pair[1]" in str(c.args[0] if c.args else "") and i > shot_index
    )
    assert mask_index < shot_index < restore_index


# ── Real-browser integration (marked integration; excluded from default run) ──


@pytest.mark.integration
def test_masked_screenshot_roundtrip_real_browser(tmp_path: Path) -> None:
    """Against real Chromium: sensitive values are blanked for the capture and
    restored afterwards; benign values are never touched."""
    pytest.importorskip("playwright")
    from playwright.sync_api import sync_playwright

    html = """
    <html><body>
      <input id="api_key" type="text" value="sk-live-abc123"/>
      <input id="session_token" type="text" value="tok-xyz"/>
      <input id="first_name" type="text" value="Jane"/>
    </body></html>
    """
    shot = tmp_path / "masked.png"
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        page.set_content(html)
        with masked_screenshot_page(page):
            # Masking applies at context entry: secrets are blanked in the DOM
            # for the whole capture window.
            assert page.locator("#api_key").input_value() == ""
            page.screenshot(path=str(shot), full_page=True)
            assert page.locator("#session_token").input_value() == ""
        # After the context: originals restored.
        assert page.locator("#api_key").input_value() == "sk-live-abc123"
        assert page.locator("#session_token").input_value() == "tok-xyz"
        assert page.locator("#first_name").input_value() == "Jane"
        browser.close()
    assert shot.exists() and shot.stat().st_size > 0
