"""Unit tests for the spec analyzer module."""

from unittest.mock import MagicMock

import pytest

from src.spec_analyzer import SpecAnalyzer, TestCondition, infer_condition_intent


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


# ---------------------------------------------------------------------------
# B-027 regression: multi-concern unstructured requirements must NOT collapse
# ---------------------------------------------------------------------------

MULTI_CONCERN_TEXT = (
    "As a shopper on automationexercise.com, I want to browse products by category, add items to my cart, "
    "review the cart contents, and proceed to checkout so that I can complete a purchase. "
    "I want to check how many items I can add to cart and maximum quantity of an item."
)


def test_prompt_contains_multi_concern_splitting_rules() -> None:
    assert "SPLITTING RULES" in SpecAnalyzer.SYSTEM_PROMPT
    assert "ONE condition PER CONCERN" in SpecAnalyzer.SYSTEM_PROMPT
    assert "Do NOT collapse" in SpecAnalyzer.SYSTEM_PROMPT


def test_has_multi_concern_signal() -> None:
    assert SpecAnalyzer._has_multi_concern_signal("how many items can I add")
    assert SpecAnalyzer._has_multi_concern_signal("maximum quantity of an item")
    assert SpecAnalyzer._has_multi_concern_signal("max items limit")
    assert not SpecAnalyzer._has_multi_concern_signal("login with valid credentials")


def test_conservative_sentence_split_multiple_sentences() -> None:
    sentences = SpecAnalyzer._conservative_sentence_split(MULTI_CONCERN_TEXT)
    assert sentences is not None
    assert len(sentences) == 2
    assert "complete a purchase" in sentences[0]
    assert "maximum quantity" in sentences[1]


def test_conservative_sentence_split_atomic_returns_none() -> None:
    assert SpecAnalyzer._conservative_sentence_split("login with valid credentials") is None
    assert SpecAnalyzer._conservative_sentence_split("") is None


def test_conservative_sentence_split_never_splits_mid_sentence_commas() -> None:
    """A single narrative sentence with commas stays whole (the B-027 revert lesson)."""
    journey = (
        "As a user I want to browse products by category, add items to my cart, "
        "review the cart contents, and proceed to checkout to complete a purchase."
    )
    assert SpecAnalyzer._conservative_sentence_split(journey) is None


def test_conservative_sentence_split_skips_structured_text() -> None:
    assert SpecAnalyzer._conservative_sentence_split("1. filters\n2. login") is None


def test_collapsed_multi_concern_detection() -> None:

    collapsed = [TestCondition(id="TC01.01", type="happy_path", text=MULTI_CONCERN_TEXT, expected="ok", source="AC 1")]
    assert SpecAnalyzer._collapsed_multi_concern(collapsed, MULTI_CONCERN_TEXT) is True
    # Multiple conditions → not collapsed
    multi = collapsed + [TestCondition(id="TC01.02", type="boundary", text="max items", expected="ok", source="AC 2")]
    assert SpecAnalyzer._collapsed_multi_concern(multi, MULTI_CONCERN_TEXT) is False
    # Single condition but atomic text → not collapsed
    assert SpecAnalyzer._collapsed_multi_concern(collapsed, "login with valid credentials") is False


def test_analyze_fallback_when_llm_collapses() -> None:
    """LLM returns one happy_path for a multi-concern story → conservative fallback kicks in."""
    mock_llm = MagicMock()
    mock_llm.generate_test.return_value = (
        '[{"id": "TC01.01", "type": "happy_path", "text": "whole story", '
        '"expected": "ok", "source": "Acceptance Criteria 1", "src": "ai", "intent": "element_behavior"}]'
    )
    analyzer = SpecAnalyzer(llm_client=mock_llm)
    conditions = analyzer.analyze(f"User Story:\n{MULTI_CONCERN_TEXT}\n\nAcceptance Criteria:\n{MULTI_CONCERN_TEXT}")

    assert len(conditions) >= 2
    assert conditions[0].type == "happy_path"
    assert conditions[-1].type == "boundary"  # limit question
    assert all(condition.id.startswith("TC01.") for condition in conditions)


def test_analyze_keeps_llm_output_when_not_collapsed() -> None:
    mock_llm = MagicMock()
    mock_llm.generate_test.return_value = (
        "[\n"
        '  {"id": "TC01.01", "type": "happy_path", "text": "journey", "expected": "ok", "source": "AC 1", "src": "ai", "intent": "element_behavior"},\n'
        '  {"id": "TC01.02", "type": "boundary", "text": "max items", "expected": "ok", "source": "AC 2", "src": "ai", "intent": "element_behavior"}\n'
        "]"
    )
    analyzer = SpecAnalyzer(llm_client=mock_llm)
    conditions = analyzer.analyze(MULTI_CONCERN_TEXT)
    assert len(conditions) == 2
    assert conditions[0].id == "TC01.01"
    assert conditions[1].id == "TC01.02"


def test_analyze_atomic_text_unchanged() -> None:
    """Atomic stories must still produce exactly one condition (no over-splitting)."""
    mock_llm = MagicMock()
    mock_llm.generate_test.return_value = '[{"id": "TC01.01", "type": "happy_path", "text": "login", "expected": "ok", "source": "AC 1", "src": "ai", "intent": "element_behavior"}]'
    analyzer = SpecAnalyzer(llm_client=mock_llm)
    conditions = analyzer.analyze("login with valid credentials")
    assert len(conditions) == 1


# ---------------------------------------------------------------------------
# JSON robustness — LLM quoting story text verbatim breaks parsing; retry once
# ---------------------------------------------------------------------------


def test_prompt_forbids_verbatim_quotes_in_source() -> None:
    assert "NEVER quote the spec text verbatim" in SpecAnalyzer.SYSTEM_PROMPT
    assert "Do NOT use double-quote characters inside any string value" in SpecAnalyzer.SYSTEM_PROMPT


def test_analyze_retries_once_when_llm_embeds_quotes() -> None:
    """First response has an unescaped quote in source; correction retry succeeds."""
    mock_llm = MagicMock()
    mock_llm.generate_test.side_effect = [
        # Broken: unescaped double quote inside "source" value
        (
            '[{"id": "TC01.01", "type": "happy_path", "text": "journey", "expected": "ok", '
            '"source": "User Story: "browse products"", "src": "ai", "intent": "element_behavior"},'
            '{"id": "TC01.02", "type": "boundary", "text": "max items", "expected": "ok", '
            '"source": "AC 2", "src": "ai", "intent": "element_behavior"}]'
        ),
        # Corrected response
        (
            "[\n"
            '  {"id": "TC01.01", "type": "happy_path", "text": "journey", "expected": "ok", "source": "User Story", "src": "ai", "intent": "element_behavior"},\n'
            '  {"id": "TC01.02", "type": "boundary", "text": "max items", "expected": "ok", "source": "AC 2", "src": "ai", "intent": "element_behavior"}\n'
            "]"
        ),
    ]
    analyzer = SpecAnalyzer(llm_client=mock_llm)
    conditions = analyzer.analyze(MULTI_CONCERN_TEXT)

    assert mock_llm.generate_test.call_count == 2
    assert len(conditions) == 2
    assert "CORRECTION" in mock_llm.generate_test.call_args_list[1].kwargs["prompt"]
    assert conditions[1].id == "TC01.02"


def test_analyze_raises_after_retry_still_fails() -> None:
    """Both the initial call and the correction retry return unusable JSON."""
    mock_llm = MagicMock()
    mock_llm.generate_test.side_effect = ["not json at all", "also not json"]
    analyzer = SpecAnalyzer(llm_client=mock_llm)
    with pytest.raises(RuntimeError, match="Failed to parse LLM response"):
        analyzer.analyze(MULTI_CONCERN_TEXT)
    assert mock_llm.generate_test.call_count == 2
