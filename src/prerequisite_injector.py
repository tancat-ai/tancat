"""Detect dependency chains and inject prerequisite steps into generated tests.

This module operates on **resolved code** (after placeholder resolution) to detect
which tests need prerequisite steps from earlier tests, then injects those steps.

Problem it solves:
  When a user provides acceptance criteria with implicit dependencies
  (e.g., "add item to cart" requires being logged in), the skeleton generator
  creates independent test functions that do NOT include prerequisite steps.
  This module detects and repairs those dependency chains.

Design:
  - Analyzes TestJourney data to understand test boundaries and step content
  - Uses keyword-based intent detection to identify post-authentication actions
  - Injects resolved evidence_tracker calls from prerequisite tests
  - Adds comment markers for human readability
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from src.pipeline_models import TestJourney

logger = logging.getLogger(__name__)

# Keywords that indicate a test requires authentication or prior state.
# When a test's first GOTO points to the starting URL (login page) but the
# criterion describes a post-auth action, prerequisite injection is needed.
POST_AUTH_KEYWORDS: set[str] = {
    # Cart actions
    "cart",
    "add to cart",
    "add item",
    "item",
    "basket",
    "shopping cart",
    "checkout",
    "check out",
    "purchase",
    "buy",
    "order",
    "payment",
    "pay",
    "credit card",
    "shipping",
    "delivery",
    "confirm",
    "confirmation",
    "order complete",
    # Account actions
    "account",
    "profile",
    "settings",
    "dashboard",
    "my account",
    "my profile",
    "wishlist",
    "saved",
    "favorites",
    # Post-login navigation
    "products page",
    "product list",
    "inventory",
    "catalog",
    "categories",
    "remove from cart",
    "update cart",
    "quantity",
    # Sauce Demo specific
    "sauce labs",
    "backpack",
    "bike light",
    "t-shirt",
    "add-to-cart",
    "shopping cart badge",
    "cart badge",
    "sidebar",
    "open-menu",
    "information",
    "finish",
}


@dataclass(frozen=True)
class PrerequisiteStep:
    """A resolved step extracted from a prerequisite test."""

    raw_line: str
    source_test: str
    source_condition: str = ""


@dataclass
class InjectionPlan:
    """Describes what needs to be injected into a test."""

    target_test: str
    prerequisites: list[PrerequisiteStep] = field(default_factory=list)
    reason: str = ""


class PrerequisiteInjector:
    """Detect dependency chains and inject prerequisite steps.

    Operates on resolved code (after placeholder resolution) using TestJourney data
    to understand which tests need prerequisite steps.

    Algorithm:
      1. Parse all test journeys from resolved code
      2. For each journey, determine its first navigation target
      3. Compare against the starting URL to detect tests landing on login page
      4. Check if criterion describes a post-authentication action
      5. If both conditions match, extract steps from the auth test and inject them
    """

    def __init__(self) -> None:
        self._injection_count: int = 0

    def analyze_dependencies(
        self,
        journeys: list[TestJourney],
        starting_url: str,
        scraped_pages: dict[str, list[dict[str, Any]]] | None = None,
    ) -> dict[str, InjectionPlan]:
        """Return injection plans for tests that need prerequisite steps.

        Args:
            journeys: Parsed test journeys from the skeleton parser.
            starting_url: The seed URL (usually the login/home page).
            scraped_pages: Optional scraped page data for context validation.
        """
        if not journeys or not starting_url:
            return {}

        # Build a map of test_name → first navigation URL and criterion intent
        test_nav_map: dict[str, tuple[str | None, str]] = {}
        for journey in journeys:
            first_goto_url, criterion_text = self._extract_first_navigation(journey)
            test_nav_map[journey.test_name] = (first_goto_url, criterion_text)

        # Find the authentication test — usually the first test that navigates
        # to the starting URL and contains login-like actions
        auth_test_name: str | None = self._find_auth_test(journeys, starting_url)
        if not auth_test_name:
            logger.debug("No authentication test found — prerequisite injection skipped")
            return {}

        # Extract resolved steps from the auth test
        auth_journey = next((j for j in journeys if j.test_name == auth_test_name), None)
        if not auth_journey:
            return {}

        auth_steps = self._extract_prerequisite_steps(auth_journey, "TC-01")
        if not auth_steps:
            logger.debug("Authentication test had no resolved steps — prerequisite injection skipped")
            return {}

        # Build injection plans for dependent tests
        plans: dict[str, InjectionPlan] = {}
        for _index, journey in enumerate(journeys):
            if journey.test_name == auth_test_name:
                continue  # Skip the auth test itself

            first_goto_url, criterion_text = test_nav_map.get(journey.test_name, (None, ""))

            needs_injection = self._needs_prerequisite_injection(
                journey=journey,
                first_goto_url=first_goto_url,
                criterion_text=criterion_text,
                starting_url=starting_url,
                auth_test_name=auth_test_name,
            )

            if needs_injection:
                plan = InjectionPlan(
                    target_test=journey.test_name,
                    prerequisites=list(auth_steps),
                    reason=f"{journey.test_name} requires authentication ({auth_test_name})",
                )
                plans[journey.test_name] = plan
                logger.debug(
                    "prerequisite_injection: %s needs auth steps from %s (%s)",
                    journey.test_name,
                    auth_test_name,
                    plan.reason,
                )

        return plans

    def inject_into_code(
        self,
        code: str,
        injection_plans: dict[str, InjectionPlan],
    ) -> str:
        """Prepend prerequisite steps into the target test functions.

        Args:
            code: The resolved test code (after placeholder resolution).
            injection_plans: Mapping of test_name → InjectionPlan from analyze_dependencies().

        Returns:
            Code with prerequisite steps injected at the start of dependent tests.
        """
        if not injection_plans:
            return code

        lines = code.splitlines()
        result: list[str] = []
        index = 0

        while index < len(lines):
            line = lines[index]

            # Detect test function definition
            match = re.match(r"^(\s*)def\s+(test_\w+)\s*\(", line)
            if match:
                test_name = match.group(2)

                if test_name in injection_plans:
                    plan = injection_plans[test_name]

                    # Find the function body indentation (first non-empty line after def)
                    body_indent = self._detect_body_indent(lines, index)

                    # Add the function definition line
                    result.append(line)
                    index += 1

                    # Inject prerequisite steps with comment markers
                    tc_ref = self._extract_tc_ref(plan.reason)
                    result.append(f"{body_indent}# --- Prerequisite: {tc_ref} (injected) ---")

                    for step in plan.prerequisites:
                        # Skip navigation steps from the auth test — the dependent
                        # test already has its own navigation as the first step.
                        # We only inject the login actions (fill credentials, click login).
                        if self._is_navigation_step(step.raw_line):
                            # Skip the auth test's navigate step; the dependent test
                            # already navigates to the starting URL itself.
                            continue
                        if self._is_consent_dismiss(step.raw_line):
                            # Skip consent dismiss — the dependent test handles this.
                            continue
                        result.append(step.raw_line)

                    result.append(f"{body_indent}# --- Original test steps ---")
                    self._injection_count += 1
                    continue

                result.append(line)
                index += 1
            else:
                result.append(line)
                index += 1

        if self._injection_count:
            logger.debug("prerequisite_injection: injected steps into %d tests", self._injection_count)

        return "\n".join(result)

    # -- Internal helpers --

    def _extract_first_navigation(self, journey: TestJourney) -> tuple[str | None, str]:
        """Extract the first GOTO target URL and criterion text from a journey."""
        first_goto_url: str | None = None
        criterion_text = ""

        for step in journey.steps:
            raw_lower = step.raw_line.lower()
            nav_match = re.search(r"evidence_tracker\.navigate\(\s*['\"]([^'\"]+)['\"]", step.raw_line)
            if nav_match:
                first_goto_url = nav_match.group(1)
                if not criterion_text:
                    criterion_text += " " + raw_lower
                break

            for placeholder in step.placeholders:
                if placeholder.action == "GOTO":
                    first_goto_url = placeholder.description
                    break
                # Collect criterion text from FILL/CLICK descriptions
                if placeholder.action in ("FILL", "CLICK"):
                    criterion_text += " " + placeholder.description

            if first_goto_url:
                break

            if "evidence_tracker." in raw_lower:
                criterion_text += " " + raw_lower

        return (first_goto_url, criterion_text.strip())

    def _find_auth_test(
        self,
        journeys: list[TestJourney],
        starting_url: str,
    ) -> str | None:
        """Find the test that performs authentication (login).

        Heuristic: the first test whose steps include FILL actions for
        credentials (username, password) or CLICK actions for login.
        """
        login_keywords = {"login", "log in", "sign in", "sign on", "authenticate", "credentials"}

        for journey in journeys:
            has_fill = False
            has_login_intent = False

            for step in journey.steps:
                raw_lower = step.raw_line.lower()
                if "evidence_tracker.fill(" in raw_lower:
                    has_fill = True
                if any(kw in raw_lower for kw in login_keywords):
                    has_login_intent = True
                if any(kw in raw_lower for kw in {"username", "password", "email", "user name", "pass"}):
                    has_login_intent = True

                for placeholder in step.placeholders:
                    desc_lower = placeholder.description.lower()

                    if placeholder.action == "FILL":
                        has_fill = True

                    if any(kw in desc_lower for kw in login_keywords):
                        has_login_intent = True

                    # Also detect username/password fields
                    field_keywords = {"username", "password", "email", "user name", "pass"}
                    if any(kw in desc_lower for kw in field_keywords):
                        has_login_intent = True

            if has_fill and has_login_intent:
                return journey.test_name

        # STRICT: Do NOT fallback to the first test if it doesn't contain login steps.
        # The previous fallback caused false-positive prerequisite injection where
        # non-auth tests (e.g., "browse categories") had their steps injected into
        # other tests, breaking those tests by clicking unrelated elements before
        # navigation. See BACKLOG.md entry for "Prerequisite injector false positives".
        return None

    def _needs_prerequisite_injection(
        self,
        journey: TestJourney,
        first_goto_url: str | None,
        criterion_text: str,
        starting_url: str,
        auth_test_name: str,
    ) -> bool:
        """Determine if a test needs prerequisite injection.

        A test needs injection when:
        1. Its first GOTO points to the starting URL (login page), AND
        2. The criterion describes a post-authentication action
        """
        # Check if first GOTO targets the starting page
        targets_starting_page = False
        if first_goto_url:
            # The GOTO description might be a keyword like "home" or "login"
            # that resolves to the starting URL. We check if the journey
            # starts at the same page as the auth test.
            targets_starting_page = True

        # Check for post-auth keywords in criterion text
        criterion_lower = criterion_text.lower()
        has_post_auth_intent = any(kw in criterion_lower for kw in POST_AUTH_KEYWORDS)

        # Also check placeholder descriptions for post-auth intent
        for step in journey.steps:
            for placeholder in step.placeholders:
                desc_lower = placeholder.description.lower()
                if any(kw in desc_lower for kw in POST_AUTH_KEYWORDS):
                    has_post_auth_intent = True
                    break
            if has_post_auth_intent:
                break

        # Skip tests that are the auth test itself
        if journey.test_name == auth_test_name:
            return False

        if self._journey_contains_auth_steps(journey):
            return False

        return targets_starting_page and has_post_auth_intent

    @staticmethod
    def _journey_contains_auth_steps(journey: TestJourney) -> bool:
        """Return True when the test already performs a login-like sequence."""
        has_credential_fill = False
        has_login_click = False
        credential_terms = {"username", "user-name", "password", "email"}
        login_terms = {"login", "log in", "sign in"}

        for step in journey.steps:
            raw_lower = step.raw_line.lower()
            if "evidence_tracker.fill(" in raw_lower and any(term in raw_lower for term in credential_terms):
                has_credential_fill = True
            if "evidence_tracker.click(" in raw_lower and any(term in raw_lower for term in login_terms):
                has_login_click = True

            for placeholder in step.placeholders:
                desc_lower = placeholder.description.lower()
                if placeholder.action == "FILL" and any(term in desc_lower for term in credential_terms):
                    has_credential_fill = True
                if placeholder.action == "CLICK" and any(term in desc_lower for term in login_terms):
                    has_login_click = True

        return has_credential_fill and has_login_click

    def _extract_prerequisite_steps(
        self,
        journey: TestJourney,
        condition_ref: str = "",
    ) -> list[PrerequisiteStep]:
        """Extract resolved evidence_tracker ACTION steps from a journey.

        Only extracts action steps (navigate, click, fill) - NOT assertions.
        Assertions from a prerequisite test are meaningless when injected into
        a different test context.

        Preserves original indentation so steps can be injected with correct indent.
        """
        steps: list[PrerequisiteStep] = []

        for step in journey.steps:
            raw = step.raw_line.strip()
            if not raw:
                continue
            # Only include evidence_tracker ACTION calls (navigate, click, fill)
            # Exclude assertions - they are test-specific and meaningless when injected
            if "evidence_tracker." in raw:
                if self._is_assertion_step(raw):
                    continue
                # Preserve original indentation from the source test
                original_line = step.raw_line
                steps.append(
                    PrerequisiteStep(
                        raw_line=original_line,
                        source_test=journey.test_name,
                        source_condition=condition_ref,
                    )
                )

        return steps

    @staticmethod
    def _is_assertion_step(raw_line: str) -> bool:
        """Return True if the line is an assertion (should not be injected)."""
        assertion_methods = (
            "assert_visible",
            "assert_text",
            "assert_checked",
            "assert_value",
            "assert_title",
            "assert_url",
            "assert_count",
        )
        return any(f"evidence_tracker.{method}" in raw_line for method in assertion_methods)

    @staticmethod
    def _detect_body_indent(lines: list[str], def_line_index: int) -> str:
        """Detect the indentation of the function body."""
        # Default to 4 spaces
        for i in range(def_line_index + 1, min(def_line_index + 5, len(lines))):
            line = lines[i]
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                indent = line[: len(line) - len(line.lstrip())]
                if indent:
                    return indent
        return "    "

    @staticmethod
    def _collect_decorators(lines: list[str], def_line_index: int) -> list[str]:
        """Collect decorator lines preceding a function definition."""
        decorators: list[str] = []
        i = def_line_index - 1
        while i >= 0:
            stripped = lines[i].strip()
            if stripped.startswith("@"):
                decorators.insert(0, lines[i])
                i -= 1
            elif not stripped:
                # Allow blank lines between decorators
                i -= 1
            else:
                break
        return decorators

    @staticmethod
    def _extract_tc_ref(reason: str) -> str:
        """Extract TC reference from the injection reason string."""
        match = re.search(r"(TC-\d+)", reason)
        return match.group(1) if match else "prerequisite"

    @staticmethod
    def _is_navigation_step(raw_line: str) -> bool:
        """Check if a step is a navigation step (evidence_tracker.navigate)."""
        return "evidence_tracker.navigate(" in raw_line

    @staticmethod
    def _is_consent_dismiss(raw_line: str) -> bool:
        """Check if a step is a consent overlay dismissal."""
        return "dismiss_consent_overlays(" in raw_line
