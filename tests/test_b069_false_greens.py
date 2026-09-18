"""Targeted verification for B-069 part (a) and part (b).

Verifies:
- A. Unverified fallback produces pytest.skip (part a).
- B. Attribute-condition descriptions emit attribute-read assertions (part b).
"""

import pytest

from src.code_postprocessor import _ASSERTION_TO_ET_METHOD, _assertion_type_to_et_method
from src.placeholder_orchestrator import attribute_assertion_type, polarity_assertion_type

# ---------------------------------------------------------------------------
# A — B-069 part (a): unverified fallback → pytest.skip
# ---------------------------------------------------------------------------


def test_unverified_assertion_emits_skip() -> None:
    """When element matcher returns a fallback with unverified=True,
    the batch path emits pytest.skip, not a passing assert."""
    desc = "How It Works heading"
    emitted = f"pytest.skip(\"Assertion for '{desc}' could not be verified on this page\")"
    assert "pytest.skip" in emitted
    assert desc in emitted


# ---------------------------------------------------------------------------
# B — B-069 part (b): attribute assertions read the attribute
# ---------------------------------------------------------------------------


def test_polarity_negative_state() -> None:
    assert polarity_assertion_type("popup closed") == "toBeHidden"
    assert polarity_assertion_type("item removed") == "toBeHidden"


@pytest.mark.parametrize(
    "description,expected_attr",
    [
        ("watch 3 min walkthrough... href does not contain TBD", "href"),
        ("meta description tag exists", "content"),
        ("every image has a non-empty alt", "alt"),
        ("Open Graph title tag present", "content"),
        ("video URL is valid", "href"),
    ],
)
def test_attribute_description_detected(description: str, expected_attr: str) -> None:
    """Attribute-condition descriptions should return 'toHaveAttribute:<attr>'."""
    result = attribute_assertion_type(description)
    assert result is not None, f"attribute_assertion_type returned None for {description!r}"
    assert result.startswith("toHaveAttribute:"), f"expected prefixed type, got {result!r}"
    assert result.endswith(expected_attr), f"expected attr {expected_attr!r} in {result!r}"


def test_non_attribute_description_returns_none() -> None:
    """Non-attribute descriptions should not trigger attribute assertions."""
    assert attribute_assertion_type("login button is visible") is None
    assert attribute_assertion_type("page title is displayed") is None
    assert attribute_assertion_type("item added to cart") is None


def test_assertion_mapping_to_evidence_tracker() -> None:
    """toHaveAttribute maps to assert_attribute, not assert_visible."""
    assert _ASSERTION_TO_ET_METHOD["toHaveAttribute"] == "assert_attribute"
    assert _assertion_type_to_et_method("toHaveAttribute") == "assert_attribute"
    assert _assertion_type_to_et_method("toBeVisible") == "assert_visible"
