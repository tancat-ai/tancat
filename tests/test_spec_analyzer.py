"""Unit tests for the spec analyzer module."""

from unittest.mock import MagicMock

import pytest

from src.spec_analyzer import SpecAnalyzer, infer_condition_intent


def test_spec_analyzer_success() -> None:
    """Test that SpecAnalyzer correctly parses a valid JSON response."""
    mock_llm = MagicMock()
    mock_llm.generate_test.return_value = """[
        {
            "id": "BC01.01",
            "type": "happy_path",
            "text": "Valid size bag",
            "expected": "Accepted",
            "source": "Bags under 55cm",
            "flagged": false,
            "src": "ai"
        }
    ]"""

    analyzer = SpecAnalyzer(llm_client=mock_llm)
    conditions = analyzer.analyze("Some spec text")

    assert len(conditions) == 1
    assert conditions[0].id == "BC01.01"
    assert conditions[0].type == "happy_path"
    assert conditions[0].text == "Valid size bag"
    assert conditions[0].expected == "Accepted"
    assert conditions[0].source == "Bags under 55cm"
    assert conditions[0].flagged is False
    assert conditions[0].src == "ai"


def test_spec_analyzer_handles_markdown_fences() -> None:
    """Test that markdown JSON blocks are stripped correctly."""
    mock_llm = MagicMock()
    mock_llm.generate_test.return_value = """```json
[
    {
        "id": "BC01.02",
        "type": "ambiguity",
        "text": "What about handles?",
        "expected": "Undefined",
        "source": "Spec implicitly assumes boxes",
        "flagged": true,
        "src": "ai"
    }
]
```"""

    analyzer = SpecAnalyzer(llm_client=mock_llm)
    conditions = analyzer.analyze("Some spec text")

    assert len(conditions) == 1
    assert conditions[0].id == "BC01.02"
    assert conditions[0].flagged is True


def test_spec_analyzer_invalid_json() -> None:
    """Test that invalid JSON raises RuntimeError."""
    mock_llm = MagicMock()
    mock_llm.generate_test.return_value = "This is not JSON"

    analyzer = SpecAnalyzer(llm_client=mock_llm)

    with pytest.raises(RuntimeError, match="Failed to parse LLM response"):
        analyzer.analyze("Some spec text")


def test_spec_analyzer_repairs_unquoted_keys_and_trailing_commas() -> None:
    mock_llm = MagicMock()
    mock_llm.generate_test.return_value = """[
      { id: "TC01.01", type: "happy_path", text: "ok", expected: "ok", source: "spec", flagged: false, src: "ai", },
    ]"""
    analyzer = SpecAnalyzer(llm_client=mock_llm)
    conditions = analyzer.analyze("Some spec text")
    assert len(conditions) == 1
    assert conditions[0].id == "TC01.01"


def test_spec_analyzer_repairs_raw_newlines_inside_string_values() -> None:
    mock_llm = MagicMock()
    # This is invalid JSON because it contains a raw newline inside a quoted string.
    mock_llm.generate_test.return_value = """[
      {
        "id": "TC01.01",
        "type": "happy_path",
        "text": "Line1
Line2",
        "expected": "ok",
        "source": "spec",
        "flagged": false,
        "src": "ai"
      }
    ]"""
    analyzer = SpecAnalyzer(llm_client=mock_llm)
    conditions = analyzer.analyze("Some spec text")
    assert len(conditions) == 1
    assert "Line1" in conditions[0].text


def test_spec_analyzer_salvages_objects_when_array_is_malformed() -> None:
    mock_llm = MagicMock()
    # Missing comma between objects -> malformed array, but objects are individually valid.
    mock_llm.generate_test.return_value = """[
      { "id": "TC01.01", "type": "happy_path", "text": "A", "expected": "ok", "source": "s", "flagged": false, "src": "ai" }
      { "id": "TC01.02", "type": "happy_path", "text": "B", "expected": "ok", "source": "s", "flagged": false, "src": "ai" }
    ]"""
    analyzer = SpecAnalyzer(llm_client=mock_llm)
    conditions = analyzer.analyze("Some spec text")
    assert [c.id for c in conditions] == ["TC01.01", "TC01.02"]


def test_spec_analyzer_empty_input() -> None:
    """Test that empty input returns an empty list immediately without LLM call."""
    mock_llm = MagicMock()
    analyzer = SpecAnalyzer(llm_client=mock_llm)

    conditions = analyzer.analyze("   ")
    assert conditions == []
    mock_llm.generate_test.assert_not_called()


def test_spec_analyzer_prefers_explicit_numbered_acceptance_criteria() -> None:
    mock_llm = MagicMock()
    analyzer = SpecAnalyzer(llm_client=mock_llm)

    spec_text = """## User Story
As a customer I want X

## Acceptance Criteria
1. do thing A
2. do thing B
3. verify thing C
"""
    conditions = analyzer.analyze(spec_text)
    assert [c.id for c in conditions] == ["TC01.01", "TC01.02", "TC01.03"]
    assert [c.text for c in conditions] == ["do thing A", "do thing B", "verify thing C"]
    assert [c.intent for c in conditions] == ["journey_step", "journey_step", "journey_step"]
    mock_llm.generate_test.assert_not_called()


def test_infer_condition_intent_maps_common_testing_shapes() -> None:
    assert infer_condition_intent("Add to Cart button is visible") == "element_presence"
    assert infer_condition_intent("Cart icon opens the cart") == "element_behavior"
    assert infer_condition_intent("Check items are added correctly") == "state_assertion"
    assert infer_condition_intent("Go to checkout") == "journey_step"
    assert infer_condition_intent("Check out successfully") == "journey_outcome"


# ── B-027: Unstructured comma-separated criteria ─────────────────────────


def test_split_unstructured_criteria_comma_and_separated() -> None:
    """Comma + 'and'-separated concerns are split into multiple criteria."""
    text = "changes around max items, max quantity of items and filters"
    result = SpecAnalyzer._split_unstructured_criteria(text)
    assert result is not None
    assert len(result) == 3
    assert result[0] == "changes around max items"
    assert result[1] == "max quantity of items"
    assert "filters" in result[2]


def test_split_unstructured_criteria_single_item_returns_none() -> None:
    """Single concern without commas or 'and' returns None."""
    result = SpecAnalyzer._split_unstructured_criteria("test the login page")
    assert result is None


def test_split_unstructured_criteria_numbered_list_returns_none() -> None:
    """Already-numbered list returns None (should use existing logic)."""
    result = SpecAnalyzer._split_unstructured_criteria("1. do thing\n2. do other")
    assert result is None


def test_split_unstructured_criteria_multi_line_returns_none() -> None:
    """Multi-line text returns None (already has structure)."""
    result = SpecAnalyzer._split_unstructured_criteria("login functionality\ncheckout flow")
    assert result is None


def test_analyze_splits_comma_separated_unstructured_input() -> None:
    """Full analyze() flow splits comma-separated concerns into separate conditions."""
    mock_llm = MagicMock()
    analyzer = SpecAnalyzer(llm_client=mock_llm)

    spec_text = """User Story:
As a user I want to test site changes

Acceptance Criteria:
changes made to the site around maximum amount of items purchaseable, maximum quantity of items and filters."""

    conditions = analyzer.analyze(spec_text)
    assert len(conditions) == 3
    assert [c.id for c in conditions] == ["TC01.01", "TC01.02", "TC01.03"]
    assert "amount" in conditions[0].text.lower()
    assert "quantity" in conditions[1].text.lower()
    assert "filter" in conditions[2].text.lower()
    assert all(c.type == "exploratory" for c in conditions)
    assert "edit this cell" in conditions[0].expected.lower()
    # Should bypass LLM entirely
    mock_llm.generate_test.assert_not_called()


def test_analyze_splits_parse_requirements_text_output() -> None:
    """Handle the case where parse_requirements_text wraps input as '1. X, Y and Z'.

    This simulates what actually happens with the user's input:
    FeatureParser parses unstructured text → produces "1. X, Y and Z" →
    _extract_numbered_criteria finds 1 item → expansion logic splits it.
    """
    mock_llm = MagicMock()
    analyzer = SpecAnalyzer(llm_client=mock_llm)

    # This is what parse_requirements_text actually produces
    spec_text = """User Story:
changes made to the site around maximum amount of items purchaseable, maximum quantity of items and filters.

Acceptance Criteria:
1. changes made to the site around maximum amount of items purchaseable, maximum quantity of items and filters."""

    conditions = analyzer.analyze(spec_text)
    assert len(conditions) == 3, f"Expected 3 conditions, got {len(conditions)}"
    assert [c.id for c in conditions] == ["TC01.01", "TC01.02", "TC01.03"]
    # Single numbered item that was comma-expanded -> treated as unstructured
    assert all(c.type == "exploratory" for c in conditions)
    assert all(c.flagged for c in conditions)
    assert all(c.src == "ai" for c in conditions)
    assert "amount" in conditions[0].text.lower()
    assert "quantity" in conditions[1].text.lower()
    assert "filter" in conditions[2].text.lower()
    mock_llm.generate_test.assert_not_called()
