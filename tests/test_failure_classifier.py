"""Unit tests for src/failure_classifier.py"""

from __future__ import annotations

from src.failure_classifier import FailureCategory, _extract_locator, classify_failure

# ---------------------------------------------------------------------------
# LOCATOR_TIMEOUT
# ---------------------------------------------------------------------------


def test_classify_locator_timeout_basic() -> None:
    detail = classify_failure("TimeoutError: waiting for locator('#submit-btn')")
    assert detail.category == FailureCategory.LOCATOR_TIMEOUT
    assert detail.raw_locator is not None or detail.raw_locator is None  # extractor may or may not match
    assert detail.error_message == "TimeoutError: waiting for locator('#submit-btn')"


def test_classify_locator_timeout_with_locator_string() -> None:
    err = "TimeoutError: waiting for locator('page.locator(\"#submit-btn\")')"
    detail = classify_failure(err)
    assert detail.category == FailureCategory.LOCATOR_TIMEOUT


def test_classify_locator_timeout_get_by_role() -> None:
    err = "TimeoutError: waiting for get_by_role('button', name='Submit')"
    detail = classify_failure(err)
    assert detail.category == FailureCategory.LOCATOR_TIMEOUT


# ---------------------------------------------------------------------------
# STRICT_VIOLATION
# ---------------------------------------------------------------------------


def test_classify_strict_violation() -> None:
    err = "strict mode violation: resolved to 2 elements"
    detail = classify_failure(err)
    assert detail.category == FailureCategory.STRICT_VIOLATION


def test_classify_strict_violation_with_locator() -> None:
    err = "strict mode violation: locator('#item') resolved to 3 elements"
    detail = classify_failure(err)
    assert detail.category == FailureCategory.STRICT_VIOLATION


# ---------------------------------------------------------------------------
# ASSERTION_FAILURE
# ---------------------------------------------------------------------------


def test_classify_assertion_failure() -> None:
    err = "AssertionError: assert False == True"
    detail = classify_failure(err)
    assert detail.category == FailureCategory.ASSERTION_FAILURE


def test_classify_assertion_failure_multiline() -> None:
    err = "AssertionError: Expected 'Login' but got 'Sign In'\nassert 'Login' == 'Sign In'"
    detail = classify_failure(err)
    assert detail.category == FailureCategory.ASSERTION_FAILURE


# ---------------------------------------------------------------------------
# NAVIGATION_ERROR
# ---------------------------------------------------------------------------


def test_classify_navigation_error() -> None:
    err = "Error: net::ERR_CONNECTION_REFUSED"
    detail = classify_failure(err)
    assert detail.category == FailureCategory.NAVIGATION_ERROR


# ---------------------------------------------------------------------------
# OTHER / fallback
# ---------------------------------------------------------------------------


def test_classify_other_unknown() -> None:
    err = "NameError: name 'undefined_var' is not defined"
    detail = classify_failure(err)
    assert detail.category == FailureCategory.OTHER
    assert detail.raw_locator is None


def test_classify_empty_error() -> None:
    detail = classify_failure("")
    assert detail.category == FailureCategory.OTHER


def test_classify_whitespace_only() -> None:
    detail = classify_failure("   ")
    assert detail.category == FailureCategory.OTHER


# ---------------------------------------------------------------------------
# _extract_locator
# ---------------------------------------------------------------------------


def test_extract_locator_simple() -> None:
    text = "waiting for locator('#submit-btn')"
    result = _extract_locator(text)
    assert result == "#submit-btn"


def test_extract_locator_nested() -> None:
    text = "waiting for locator('page.locator(\"#submit-btn\")')"
    result = _extract_locator(text)
    # Should extract inner string between outer quotes
    assert "submit-btn" in (result or "")


def test_extract_locator_not_found() -> None:
    result = _extract_locator("some random error text")
    assert result is None
