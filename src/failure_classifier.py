"""
failure_classifier.py — Classify pytest failure types from error messages.

Pure-function classifier that takes a TestResult and returns a FailureDetail
describing the category, extracted locator, and relevant context.

No Streamlit imports — fully unit testable in isolation.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

# ---------------------------------------------------------------------------
# Failure categories
# ---------------------------------------------------------------------------


class FailureCategory(StrEnum):
    """Categories of test failures detected from pytest error messages."""

    LOCATOR_TIMEOUT = "locator_timeout"
    STRICT_VIOLATION = "strict_violation"
    ASSERTION_FAILURE = "assertion_failure"
    NAVIGATION_ERROR = "navigation_error"
    OTHER = "other"


# ---------------------------------------------------------------------------
# Failure detail
# ---------------------------------------------------------------------------


@dataclass
class FailureDetail:
    """Structured detail for a single test failure."""

    category: FailureCategory
    raw_locator: str | None  # locator string that failed, extracted from error
    failure_url: str | None  # URL from evidence sidecar if available
    line_number: int | None  # line in the test file where the failure occurred
    error_message: str  # original error text


# ---------------------------------------------------------------------------
# Regex patterns for detection and extraction
# ---------------------------------------------------------------------------

# Playwright timeout: "waiting for locator('page.locator("#submit-btn")')"
# Also matches: "waiting for get_by_test_id(...)", "waiting for get_by_role(...)", etc.
_LOCATOR_TIMEOUT_RE = re.compile(
    r"timeouterror",
    re.IGNORECASE,
)
_WAITING_FOR_RE = re.compile(
    r"waiting\s+for",
    re.IGNORECASE,
)

# Extract locator string from: locator('page.locator("#submit-btn")') or locator('get_by_role(...)')
_LOCATOR_EXTRACT_RE = re.compile(r"locator\(\s*['\"]([^'\"]+)['\"]\s*\)")

# Strict mode: "strict mode violation: resolved to 2 elements"
_STRICT_VIOLATION_RE = re.compile(
    r"(?:strict\s+mode\s+violation|resolved\s+\to\s+\d+\s+elements)",
    re.IGNORECASE,
)

# Assertion error (leading AssertionError)
_ASSERTION_RE = re.compile(
    r"^(?:assertionerror|assertionerror:)",
    re.IGNORECASE,
)

# Navigation errors
_NAVIGATION_ERROR_RE = re.compile(
    r"(?:err_connection_refused|net::err_)",
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def classify_failure(error_message: str) -> FailureDetail:
    """Classify a test failure based on its error message.

    Args:
        error_message: The raw error text from a failed test.

    Returns:
        FailureDetail with category, extracted locator (if any), and original message.
    """
    if not error_message.strip():
        return FailureDetail(
            category=FailureCategory.OTHER,
            raw_locator=None,
            failure_url=None,
            line_number=None,
            error_message=error_message,
        )

    # Check for locator timeout: TimeoutError + waiting for
    if _LOCATOR_TIMEOUT_RE.search(error_message) and _WAITING_FOR_RE.search(error_message):
        raw_locator = _extract_locator(error_message)
        return FailureDetail(
            category=FailureCategory.LOCATOR_TIMEOUT,
            raw_locator=raw_locator,
            failure_url=None,
            line_number=None,
            error_message=error_message,
        )

    # Strict mode violation
    if _STRICT_VIOLATION_RE.search(error_message):
        raw_locator = _extract_locator(error_message)
        return FailureDetail(
            category=FailureCategory.STRICT_VIOLATION,
            raw_locator=raw_locator,
            failure_url=None,
            line_number=None,
            error_message=error_message,
        )

    # Assertion failure
    if _ASSERTION_RE.search(error_message):
        return FailureDetail(
            category=FailureCategory.ASSERTION_FAILURE,
            raw_locator=None,
            failure_url=None,
            line_number=None,
            error_message=error_message,
        )

    # Navigation error
    if _NAVIGATION_ERROR_RE.search(error_message):
        return FailureDetail(
            category=FailureCategory.NAVIGATION_ERROR,
            raw_locator=None,
            failure_url=None,
            line_number=None,
            error_message=error_message,
        )

    # Fallback
    return FailureDetail(
        category=FailureCategory.OTHER,
        raw_locator=None,
        failure_url=None,
        line_number=None,
        error_message=error_message,
    )


def _extract_locator(error_message: str) -> str | None:
    """Extract the locator string from a Playwright error message.

    Playswright timeout errors include the locator in a pattern like:
        locator('page.locator("#submit-btn")')

    Args:
        error_message: Raw error text.

    Returns:
        The locator string (e.g. 'page.locator("#submit-btn")') or None.
    """
    match = _LOCATOR_EXTRACT_RE.search(error_message)
    if match:
        return match.group(1)
    return None
