"""Tests for cli/input_parser.py — multi-format input parsing."""

from src.cli.input_parser import (
    BulletParser,
    FormatDetector,
    GherkinParser,
    InputParser,
    JiraParser,
    PlainTextParser,
    parse_bullet_format,
    parse_gherkin_format,
    parse_jira_format,
    parse_plain_text,
)

# ── FormatDetector ────────────────────────────────────────────────────────


class TestFormatDetector:
    def test_detect_jira_format(self) -> None:
        text = "Issue: PROJ-123\nSummary: Login feature\nAcceptance Criteria:\n- User can log in"
        fmt, conf = FormatDetector.detect(text)
        assert fmt == "jira"
        assert conf >= 0.8

    def test_detect_gherkin_format(self) -> None:
        text = (
            "Feature: Login\n"
            "Scenario: Valid login\n"
            "Given I am on the login page\n"
            "When I enter credentials\n"
            "Then I am logged in"
        )
        fmt, conf = FormatDetector.detect(text)
        assert fmt == "gherkin"
        assert conf >= 0.8

    def test_detect_bullet_format(self) -> None:
        text = "- First item\n- Second item\n- Third item\n- Fourth item"
        fmt, conf = FormatDetector.detect(text)
        assert fmt == "bullets"
        assert conf >= 0.7

    def test_detect_plain_text(self) -> None:
        text = "As a user I want to log in so that I can access my account."
        fmt, conf = FormatDetector.detect(text)
        assert fmt == "plain_text"
        assert conf < 0.7


# ── JiraParser ────────────────────────────────────────────────────────────


class TestJiraParser:
    def test_parse_jira_with_acceptance_criteria(self) -> None:
        text = (
            "Issue: PROJ-123\n"
            "Summary: User login\n"
            "Description: Users should be able to log in\n"
            "Acceptance Criteria:\n"
            "- User can enter valid credentials\n"
            "- User sees error on invalid password"
        )
        cases = JiraParser.parse(text)
        assert len(cases) == 2
        assert cases[0].test_type == "happy_path"
        assert cases[1].test_type == "error_handling"

    def test_parse_jira_without_acceptance_criteria(self) -> None:
        text = "Issue: PROJ-456\nSummary: Dashboard update\nDescription: Refresh the dashboard layout"
        cases = JiraParser.parse(text)
        assert len(cases) == 1
        assert cases[0].title == "Dashboard update"


# ── GherkinParser ─────────────────────────────────────────────────────────


class TestGherkinParser:
    def test_parse_gherkin_scenario(self) -> None:
        text = (
            "Feature: Shopping Cart\n"
            "Scenario: Add item to cart\n"
            "Given I am on the product page\n"
            "When I click add to cart\n"
            "Then I see the cart icon update"
        )
        cases = GherkinParser.parse(text)
        assert len(cases) == 1
        assert cases[0].title == "Add item to cart"
        assert len(cases[0].preconditions) == 1


# ── BulletParser ──────────────────────────────────────────────────────────


class TestBulletParser:
    def test_parse_bullet_list(self) -> None:
        text = "- Login with valid credentials\n- Show error for bad password\n- Logout works"
        cases = BulletParser.parse(text)
        assert len(cases) == 3


# ── PlainTextParser ───────────────────────────────────────────────────────


class TestPlainTextParser:
    def test_parse_user_story(self) -> None:
        text = "As a user I want to log in so that I can access my account."
        cases = PlainTextParser.parse(text)
        assert len(cases) >= 1

    def test_parse_plain_text_no_story_pattern(self) -> None:
        text = "The system should process orders quickly."
        cases = PlainTextParser.parse(text)
        assert len(cases) == 1
        assert cases[0].title == "Main Flow"


# ── InputParser (unified) ─────────────────────────────────────────────────


class TestInputParser:
    def test_parse_explicit_jira(self) -> None:
        parser = InputParser()
        text = "Issue: X-1\nSummary: Test\nAcceptance Criteria:\n- Must work"
        result = parser.parse(text, explicit_format="jira")
        assert result.source_format == "jira"
        assert len(result.test_cases) >= 1

    def test_parse_and_route(self) -> None:
        parser = InputParser()
        text = "Feature: X\nScenario: Y\nGiven setup\nWhen action\nThen result"
        result = parser.parse(text)
        assert result.source_format == "gherkin"


# ── Convenience functions ─────────────────────────────────────────────────


class TestConvenienceFunctions:
    def test_parse_jira_format(self) -> None:
        cases = parse_jira_format("Issue: A-1\nSummary: Hi\nAcceptance Criteria:\n- Work please")
        assert len(cases) >= 1

    def test_parse_gherkin_format(self) -> None:
        cases = parse_gherkin_format("Feature: F\nScenario: S\nGiven x\nWhen y\nThen z")
        assert len(cases) >= 1

    def test_parse_bullet_format(self) -> None:
        cases = parse_bullet_format("- One\n- Two\n- Three")
        assert len(cases) == 3

    def test_parse_plain_text(self) -> None:
        cases = parse_plain_text("As a user I want something so that I benefit.")
        assert len(cases) >= 1
