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
