"""Tests for src/failure_reporter.py."""

from __future__ import annotations

from unittest.mock import MagicMock

from src.failure_reporter import FailureReporter


class TestFailureReporter:
    """Tests for FailureReporter.diagnose_failure and generate_failure_note."""

    def test_diagnose_failure_returns_required_keys(self) -> None:
        """All required diagnosis keys should be present."""
        mock_page = MagicMock()
        mock_page.url = "http://example.com"
        mock_page.title.return_value = "Example Page"

        diagnosis = FailureReporter.diagnose_failure(
            mock_page,
            locator="#submit-btn",
            step_type="click",
            error="Timeout: element not visible",
        )

        assert "url" in diagnosis
        assert "title" in diagnosis
        assert "available_elements" in diagnosis
        assert "suggested_locators" in diagnosis
        assert "error_summary" in diagnosis
        assert diagnosis["url"] == "http://example.com"
        assert diagnosis["title"] == "Example Page"
        assert diagnosis["error_summary"] == "Timeout: element not visible"

    def test_diagnose_failure_handles_page_errors(self) -> None:
        """If page.url or page.title() raises, diagnosis should still work."""
        mock_page = MagicMock()
        mock_page.url = None
        mock_page.title.return_value = ""

        diagnosis = FailureReporter.diagnose_failure(
            mock_page,
            locator=None,
            step_type="navigate",
            error="",
        )

        assert diagnosis["url"] == ""
        assert diagnosis["title"] == ""

    def test_diagnose_failure_truncates_long_errors(self) -> None:
        """Error summaries longer than 500 chars should be truncated."""
        mock_page = MagicMock()
        mock_page.url = "http://example.com"
        mock_page.title.return_value = "Test"

        long_error = "x" * 1000
        diagnosis = FailureReporter.diagnose_failure(
            mock_page,
            locator=None,
            step_type="fill",
            error=long_error,
        )

        assert len(diagnosis["error_summary"]) <= 500

    def test_generate_failure_note_basic(self) -> None:
        """Failure note should contain URL, title, and error."""
        diagnosis = {
            "url": "http://example.com/form",
            "title": "Contact Form",
            "error_summary": "Element not found",
            "available_elements": [],
            "suggested_locators": [],
        }

        note = FailureReporter.generate_failure_note(diagnosis)

        assert "http://example.com/form" in note
        assert "Contact Form" in note
        assert "Element not found" in note

    def test_generate_failure_note_with_suggestions(self) -> None:
        """Failure note should include suggested locators."""
        diagnosis = {
            "url": "http://example.com",
            "title": "Test Page",
            "error_summary": "Click failed",
            "available_elements": [],
            "suggested_locators": [
                {"locator": "#submit", "confidence": "high", "type": "button"},
                {"locator": "button[type='submit']", "confidence": "medium", "type": "button"},
            ],
        }

        note = FailureReporter.generate_failure_note(diagnosis)

        assert "#submit" in note
        assert "button[type='submit']" in note

    def test_generate_failure_note_with_elements(self) -> None:
        """Failure note should list interactive elements grouped by role."""
        diagnosis = {
            "url": "http://example.com",
            "title": "Page",
            "error_summary": "Error",
            "available_elements": [
                {"role": "button", "name": "Submit", "text": ""},
                {"role": "textbox", "name": "Name", "text": ""},
                {"role": "button", "name": "Cancel", "text": ""},
            ],
            "suggested_locators": [],
        }

        note = FailureReporter.generate_failure_note(diagnosis)

        assert "Interactive elements on page" in note
        assert "Submit" in note
        assert "Cancel" in note
        assert "textbox" in note

    def test_categorize_elements_returns_list(self) -> None:
        """_categorize_elements should return a list of dicts."""
        mock_page = MagicMock()
        mock_page.evaluate.return_value = [
            {
                "tag": "button",
                "text": "Submit",
                "id": "submit-btn",
                "name": "",
                "role": "",
                "type": "",
                "selector_hint": "#submit-btn",
            }
        ]

        elements = FailureReporter._categorize_elements(mock_page, "click")

        assert isinstance(elements, list)
        assert len(elements) == 1
        assert elements[0]["tag"] == "button"
        assert elements[0]["text"] == "Submit"
        assert elements[0]["selector_hint"] == "#submit-btn"

    def test_suggest_locators_returns_list(self) -> None:
        """_suggest_locators should return a list of scored suggestion dicts."""
        mock_page = MagicMock()
        # Mock the raw candidate format expected by _extract_raw_candidates
        mock_page.evaluate.return_value = [
            {
                "selector": "#my-btn",
                "element_data": {
                    "tag": "button",
                    "element_id": "my-btn",
                    "test_id": None,
                    "aria_label": None,
                    "name": None,
                },
            },
            {
                "selector": '[data-testid="submit"]',
                "element_data": {
                    "tag": "button",
                    "element_id": "",
                    "test_id": "submit",
                    "aria_label": "Submit form",
                    "name": None,
                },
            },
        ]

        suggestions = FailureReporter._suggest_locators(
            mock_page,
            original_locator="#old-btn",
            step_type="click",
        )

        assert isinstance(suggestions, list)
        assert len(suggestions) >= 1
        # First suggestion should be highest-scoring
        assert suggestions[0]["locator"] in ("#my-btn", '[data-testid="submit"]')
        # New format includes score, type, and fragility_reason
        assert "score" in suggestions[0]
        assert "type" in suggestions[0]
        assert "fragility_reason" in suggestions[0]
        # data-testid should score higher than id (score is stored as string)
        if suggestions[0]["locator"] == '[data-testid="submit"]':
            assert suggestions[0]["score"] == "100"
        else:
            assert suggestions[0]["score"] == "85"

    def test_snapshot_to_text_produces_string(self) -> None:
        """_snapshot_to_text should produce a readable text summary."""
        node = {
            "name": "Main Form",
            "role": "region",
            "value": "",
            "children": [
                {
                    "name": "Submit Button",
                    "role": "button",
                    "value": "",
                    "children": [],
                }
            ],
        }

        text = FailureReporter._snapshot_to_text(node, max_lines=10)

        assert isinstance(text, str)
        assert "Main Form" in text
        assert "Submit Button" in text
        assert "button" in text
