"""Unit tests for the spec analyzer module."""

from unittest.mock import MagicMock

import pytest

from src.spec_analyzer import SpecAnalyzer


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


def test_spec_analyzer_empty_input() -> None:
    """Test that empty input returns an empty list immediately without LLM call."""
    mock_llm = MagicMock()
    analyzer = SpecAnalyzer(llm_client=mock_llm)

    conditions = analyzer.analyze("   ")
    assert conditions == []
    mock_llm.generate_test.assert_not_called()
