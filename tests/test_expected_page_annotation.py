"""AI-067: the emitted tracker call carries the page its locator was resolved for.

The evidence tracker flags a step that runs on a different page than the one it
was resolved against. That only works if the generated test passes the
expectation through — these tests pin the emit side, including the safety
property that we never emit a keyword a tracker method does not accept (which
would raise TypeError in the generated test).
"""

from __future__ import annotations

from src.code_postprocessor import replace_token_in_line


def _emit(
    action: str,
    resolved: str,
    *,
    expected_page: str = "",
    assertion_type: str = "toBeVisible",
) -> str:
    token = f"{{{{{action}:x}}}}"
    return replace_token_in_line(
        token,
        action,
        token,
        resolved,
        set(),
        "x",
        fill_value="v",
        assertion_type=assertion_type,
        expected_page=expected_page,
    )


def test_click_carries_expected_page() -> None:
    emitted = _emit("CLICK", "#login-button", expected_page="http://a/index.html")
    assert "evidence_tracker.click(" in emitted
    assert "expected_page='http://a/index.html'" in emitted


def test_fill_carries_expected_page() -> None:
    emitted = _emit("FILL", "#user-name", expected_page="http://a/index.html")
    assert "evidence_tracker.fill(" in emitted
    assert "expected_page='http://a/index.html'" in emitted


def test_visible_assert_carries_expected_page() -> None:
    emitted = _emit("ASSERT", "#accounts-list", expected_page="http://a/dashboard.html")
    assert "evidence_tracker.assert_visible(" in emitted
    assert "expected_page='http://a/dashboard.html'" in emitted


def test_hidden_assert_carries_expected_page() -> None:
    emitted = _emit("ASSERT", "#modal", expected_page="http://a/cart.html", assertion_type="toBeHidden")
    assert "evidence_tracker.assert_hidden(" in emitted
    assert "expected_page='http://a/cart.html'" in emitted


def test_no_expected_page_emits_unchanged_call() -> None:
    emitted = _emit("CLICK", "#login-button")
    assert emitted.strip() == "evidence_tracker.click('#login-button', label='x')"


def test_only_supported_methods_are_annotated() -> None:
    """``assert_count`` does not accept ``expected_page`` — emitting it would be
    a TypeError in the generated test, so the annotation must be skipped."""
    emitted = _emit("ASSERT", "#rows", expected_page="http://a/cart.html", assertion_type="toHaveCount")
    assert "evidence_tracker.assert_count(" in emitted
    assert "expected_page" not in emitted


def test_skip_lines_are_not_annotated() -> None:
    emitted = _emit("CLICK", 'pytest.skip("unresolved")', expected_page="http://a/index.html")
    assert emitted.strip().startswith("pytest.skip(")
    assert "expected_page" not in emitted


def test_url_assertions_are_not_annotated() -> None:
    emitted = _emit("ASSERT", 'expect(page).to_have_url("http://a/x")', expected_page="http://a/index.html")
    assert emitted.strip().startswith("expect(")
    assert "expected_page" not in emitted
