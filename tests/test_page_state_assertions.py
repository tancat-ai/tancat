"""Tests for page-state ASSERT routing and golden-key URL-slash matching.

Covers the "verify page loads" fix (2026-08-03):

1. ``_is_page_state_assertion`` — "<page> page title" must route as a page-state
   (URL) assertion, matching how the golden dataset encodes eval-002
   ("products page title", "cart page title" → to_have_url). "title" was an
   element keyword that misrouted LLM-invented "{{ASSERT:home page title}}"
   to element resolution (it matched a 200-char paragraph instead of the URL).
2. ``golden_validator._locators_match`` — production ``normalize_url`` emits the
   trailing-slash form of root URLs; goldens hold the bare form. The validator
   must treat them as the same assertion target.
"""

import sys
from pathlib import Path

from src.placeholder_orchestrator import PlaceholderOrchestrator

# golden_validator uses sibling imports (``from eval_metrics import ...``),
# so scripts/eval must be on sys.path — same setup as eval_harness itself.
_SCRIPTS_EVAL = Path(__file__).resolve().parent.parent / "scripts" / "eval"
if str(_SCRIPTS_EVAL) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_EVAL))

from golden_validator import _locators_match  # noqa: E402


def test_is_page_state_assertion_routes_page_title_to_url() -> None:
    """'<page> page title' is the title OF that page → URL assertion.

    Golden encoding: eval-002 criterion 1 ("products page title") and
    criterion 4 ("cart page title") are url_assertion goldens. The
    LLM-invented "home page title" (from 'verify it loads') must route the
    same way instead of falling to element resolution.
    """
    orchestrator = PlaceholderOrchestrator()
    for desc in (
        "home page loaded",
        "home page title",
        "products page title",
        "cart page title",
        "cart page loaded",
        "checkout page",
    ):
        assert orchestrator._is_page_state_assertion(desc), f"{desc!r} should be page-state"


def test_is_page_state_assertion_keeps_element_titles_as_elements() -> None:
    """Element-level 'title' descriptions stay element assertions.

    - "practice form page title" has NO page-state term → element (golden
      eval-003 expects the h5 form heading).
    - "product title" / "page title" alone → element.
    - Element keywords still veto page-state ("cart page badge updated").
    """
    orchestrator = PlaceholderOrchestrator()
    for desc in (
        "practice form page title",
        "product title",
        "page title",
        "cart page badge updated",
        "popup closed",
    ):
        assert not orchestrator._is_page_state_assertion(desc), f"{desc!r} should be element-level"


def test_is_page_state_assertion_other_actions_ignored() -> None:
    """Only ASSERT semantics are evaluated here; CLICK descriptions route elsewhere."""
    orchestrator = PlaceholderOrchestrator()
    # CLICK/other actions never call _is_page_state_assertion, but the guard
    # stays in the action == "ASSERT" branches — verify no crash on odd input.
    assert not orchestrator._is_page_state_assertion("")


# ---------------------------------------------------------------------------
# golden_validator trailing-slash comparison
# ---------------------------------------------------------------------------


def test_locators_match_to_have_url_ignores_trailing_slash() -> None:
    """Production emits to_have_url(\"https://host/\"), goldens hold the bare form."""
    assert _locators_match(
        'expect(page).to_have_url("https://automationexercise.com/")',
        'expect(page).to_have_url("https://automationexercise.com")',
        ["expect(page).to_have_url"],
    )


def test_locators_match_to_have_url_same_path_matches() -> None:
    """Same path, no slash involved — unchanged behavior."""
    assert _locators_match(
        'expect(page).to_have_url("https://automationexercise.com/view_cart")',
        'expect(page).to_have_url("https://automationexercise.com/view_cart")',
        ["expect(page).to_have_url", "#cart_item"],
    )


def test_locators_match_to_have_url_wrong_path_does_not_match() -> None:
    """Slash-insensitivity must not collapse different paths."""
    assert not _locators_match(
        'expect(page).to_have_url("https://automationexercise.com/products/")',
        'expect(page).to_have_url("https://automationexercise.com/view_cart")',
        [],
    )


def test_locators_match_element_locator_still_not_url_equivalent() -> None:
    """Element locators are not to_have_url expressions — no accidental match."""
    assert not _locators_match(
        '[data-test="title"]',
        'expect(page).to_have_url("https://automationexercise.com")',
        [],
    )


def test_locators_match_element_tolerance_still_works() -> None:
    """Element tolerances (eval-002 'products page title' → h2) are unaffected."""
    assert _locators_match(
        "h2",
        'expect(page).to_have_url("https://automationexercise.com/products")',
        ["expect(page).to_have_url", "h2"],
    )
