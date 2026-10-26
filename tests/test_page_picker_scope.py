"""The page picker is scoped to the current page's links, then the trail.

Owner's design, 2026-10-26. A step's page address comes from:

1. a link on the page the browser is on before the step;
2. the trail's recorded landing for the step;
3. nothing, which is an honest skip.

The full scraped page list is never a fallback. The path-word rule is only a
tie-break among links whose visible text already matches.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from src.pipeline_models import PlaceholderUse, TestJourney, TestStep
from src.placeholder_orchestrator import PlaceholderOrchestrator
from src.placeholder_resolver import PlaceholderResolver

SITE = "https://shop.example.com"
HOME = f"{SITE}/index.html"
DASH = f"{SITE}/dashboard.html"
TRANSFER = f"{SITE}/transfer.html"
PAYMENTS = f"{SITE}/payments.html"
SUCCESS = f"{SITE}/transfer_success.html?amount=100"
HIDDEN = f"{SITE}/hidden.html"


def _link(href: str, text: str) -> dict[str, str]:
    return {"selector": f"a[href='{href}']", "text": text, "tag": "a", "role": "link", "href": href}


def _pages() -> dict[str, list[dict[str, str]]]:
    return {
        HOME: [_link("/dashboard.html", "Sign in")],
        DASH: [
            _link("/transfer.html", "Transfer"),
            _link("/payments.html", "Bill Payments"),
            _link("/index.html", "Home"),
            {"selector": "#accounts", "text": "Accounts overview", "tag": "div"},
        ],
        TRANSFER: [
            _link("/transfer.html", "Transfer"),
            {"selector": "#amount", "text": "amount", "tag": "input", "role": "textbox"},
        ],
        PAYMENTS: [{"selector": "#payment-amount", "text": "payment amount", "tag": "input", "role": "textbox"}],
        SUCCESS: [{"selector": "#transfer-success-title", "text": "Transfer successful", "tag": "h2"}],
        HIDDEN: [{"selector": "#hidden", "text": "hidden page", "tag": "div"}],
    }


def test_a_link_on_the_current_page_resolves_the_step() -> None:
    resolver = PlaceholderResolver()

    assert resolver.resolve_url_from_links("go to the transfer page", DASH, _pages()) == TRANSFER
    assert resolver.resolve_url_from_links("navigate to bill payments", DASH, _pages()) == PAYMENTS


def test_a_step_that_is_not_a_link_resolves_through_the_trail() -> None:
    resolver = PlaceholderResolver()

    assert resolver.resolve_url_from_links("transfer success message", TRANSFER, _pages(), trail_url=SUCCESS) == SUCCESS


def test_neither_a_link_nor_the_trail_is_unresolved() -> None:
    resolver = PlaceholderResolver()

    # The hidden page exists in the full scraped list and its text matches, but
    # it is not a link on the dashboard. It must not be picked.
    assert resolver.resolve_url_from_links("hidden page", DASH, _pages()) is None


def test_the_index_page_still_resolves_through_its_link() -> None:
    resolver = PlaceholderResolver()

    assert resolver.resolve_url_from_links("home page loaded", DASH, _pages()) == HOME


def test_a_success_page_is_not_confused_with_its_parent() -> None:
    resolver = PlaceholderResolver()

    # TRANSFER has a "Transfer" link; the success page does not. The result
    # word in the description keeps the parent link from winning.
    assert resolver.resolve_url_from_links("transfer success message", TRANSFER, _pages(), trail_url=SUCCESS) == SUCCESS


def test_an_orchestrator_goto_never_consults_the_full_scraped_list(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A page with no link and no trail is an honest skip, not a full-list pick."""
    orchestrator = PlaceholderOrchestrator(starting_url=DASH)
    pages = _pages()

    def _forbidden(*args: object, **kwargs: object) -> str | None:
        raise AssertionError("the full-list resolve_url was consulted")

    monkeypatch.setattr(orchestrator.resolver, "resolve_url", _forbidden)

    resolved, next_url, _assertion = asyncio.run(
        orchestrator._resolve_placeholder_for_page(  # noqa: SLF001
            action="GOTO",
            description="hidden page",
            current_url=DASH,
            scraped_data={DASH: pages[DASH], HIDDEN: pages[HIDDEN]},
        )
    )

    assert next_url is None
    assert resolved.startswith("pytest.skip("), resolved


def test_an_orchestrator_goto_resolves_through_the_current_page_link() -> None:
    orchestrator = PlaceholderOrchestrator(starting_url=DASH)
    pages = _pages()

    resolved, next_url, _assertion = asyncio.run(
        orchestrator._resolve_placeholder_for_page(  # noqa: SLF001
            action="GOTO",
            description="go to the transfer page",
            current_url=DASH,
            scraped_data={DASH: pages[DASH], TRANSFER: pages[TRANSFER]},
        )
    )

    assert next_url == TRANSFER, resolved


def test_an_orchestrator_goto_falls_back_to_the_trail_landing() -> None:
    orchestrator = PlaceholderOrchestrator(starting_url=HOME)
    pages = _pages()

    # HOME has only a sign-in link, so the transfer step is not a link there.
    resolved, next_url, _assertion = asyncio.run(
        orchestrator._resolve_placeholder_for_page(  # noqa: SLF001
            action="GOTO",
            description="go to the transfer page",
            current_url=HOME,
            scraped_data={HOME: pages[HOME], TRANSFER: pages[TRANSFER]},
            trail_url=TRANSFER,
        )
    )

    assert next_url == TRANSFER, resolved


def test_path_words_break_a_tie_between_matching_links() -> None:
    resolver = PlaceholderResolver()
    pages = {
        DASH: [
            _link("/transfer.html", "Details"),
            _link("/payments.html", "Details"),
        ]
    }

    assert resolver.resolve_url_from_links("transfer details", DASH, pages) == TRANSFER


def test_an_icon_link_can_resolve_by_its_target_path() -> None:
    resolver = PlaceholderResolver()
    pages = {DASH: [_link("/transfer.html", "")]}

    assert resolver.resolve_url_from_links("transfer page", DASH, pages) == TRANSFER


def test_the_index_page_also_resolves_through_the_trail_when_no_link_names_it() -> None:
    resolver = PlaceholderResolver()

    assert resolver.resolve_url_from_links("home page loaded", TRANSFER, _pages(), trail_url=HOME) == HOME


def _page_state_assert_journey(description: str) -> tuple[str, TestJourney]:
    token = "{{ASSERT:" + description + "}}"
    raw = f"    act('{token}')"
    skeleton = "def test_assert(page):\n" + raw + "\n"
    journey = TestJourney(
        test_name="test_assert",
        start_line=1,
        end_line=2,
        steps=[
            TestStep(
                line_number=2,
                raw_line=raw,
                placeholders=[
                    PlaceholderUse(
                        token=token,
                        action="ASSERT",
                        description=description,
                        line_number=2,
                        raw_line=raw,
                    )
                ],
            )
        ],
    )
    return skeleton, journey


def test_page_state_assert_with_no_link_or_trail_skips_instead_of_cross_page_element() -> None:
    """The reviewer's exact probe: #dash-title exists only on dashboard.html."""
    orchestrator = PlaceholderOrchestrator()
    skeleton, journey = _page_state_assert_journey("dashboard loaded")
    data = {
        HOME: [],
        DASH: [{"selector": "#dash-title", "text": "Dashboard", "tag": "h1"}],
    }

    code = asyncio.run(
        orchestrator._replace_placeholders_sequentially(  # noqa: SLF001
            skeleton_code=skeleton,
            journeys=[journey],
            page_requirements=[],
            seed_urls=[HOME],
            scraped_data=data,
        )
    )

    assert "pytest.skip" in code, code
    assert "#dash-title" not in code, code
    assert "no link on" in code, code
    assert "no trail landing" in code, code


def test_page_state_assert_element_on_the_current_page_still_acts() -> None:
    """The fallback is scoped, not deleted: a same-page element must act."""
    orchestrator = PlaceholderOrchestrator()
    skeleton, journey = _page_state_assert_journey("dashboard loaded")
    data = {DASH: [{"selector": "#dash-title", "text": "Dashboard", "tag": "h1"}]}

    code = asyncio.run(
        orchestrator._replace_placeholders_sequentially(  # noqa: SLF001
            skeleton_code=skeleton,
            journeys=[journey],
            page_requirements=[],
            seed_urls=[DASH],
            scraped_data=data,
        )
    )

    assert "#dash-title" in code, code
    assert "pytest.skip" not in code, code


def test_page_state_assert_fallback_is_scoped_to_the_current_page(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The element fallback may run, but only with strict current-page scope."""

    calls: list[dict[str, Any]] = []
    orchestrator_resolve = PlaceholderOrchestrator._resolve_placeholder_for_page

    async def _scoped_only(
        self: PlaceholderOrchestrator, *args: Any, **kwargs: Any
    ) -> tuple[str, str | None, str | None]:
        calls.append(kwargs)
        assert kwargs.get("strict_scope") is True, kwargs
        assert kwargs.get("page_state_element_fallback") is True, kwargs
        return await orchestrator_resolve(self, *args, **kwargs)

    def _forbidden_url(*args: object, **kwargs: object) -> str | None:
        raise AssertionError("the old full-list resolve_url was consulted")

    orchestrator = PlaceholderOrchestrator()
    skeleton, journey = _page_state_assert_journey("dashboard loaded")
    data = {
        HOME: [],
        DASH: [{"selector": "#dash-title", "text": "Dashboard", "tag": "h1"}],
    }
    monkeypatch.setattr(PlaceholderOrchestrator, "_resolve_placeholder_for_page", _scoped_only)
    monkeypatch.setattr(orchestrator.resolver, "resolve_url", _forbidden_url)

    code = asyncio.run(
        orchestrator._replace_placeholders_sequentially(  # noqa: SLF001
            skeleton_code=skeleton,
            journeys=[journey],
            page_requirements=[],
            seed_urls=[HOME],
            scraped_data=data,
        )
    )

    assert calls, "the scoped element fallback was not tried"
    assert "pytest.skip" in code, code
    assert "#dash-title" not in code, code


def test_goto_with_no_link_or_trail_does_not_take_the_keyword_map_page() -> None:
    orchestrator = PlaceholderOrchestrator(starting_url=HOME)
    orchestrator.url_resolver.build_mapping(
        keywords=["transfer"],
        scraped_urls=[HOME, TRANSFER],
        seed_url=HOME,
        concepts=["transfer"],
    )
    data: dict[str, list[dict[str, str]]] = {HOME: [], TRANSFER: []}

    resolved, next_url, _assertion = asyncio.run(
        orchestrator._resolve_placeholder_for_page(  # noqa: SLF001
            action="GOTO",
            description="go to the transfer page",
            current_url=HOME,
            scraped_data=data,
        )
    )

    assert next_url is None, resolved
    assert resolved.startswith("pytest.skip("), resolved
    assert TRANSFER not in resolved


def test_a_link_wins_over_the_keyword_map() -> None:
    orchestrator = PlaceholderOrchestrator(starting_url=HOME)
    orchestrator.url_resolver.build_mapping(
        keywords=["transfer"],
        scraped_urls=[HOME, HIDDEN],
        seed_url=HOME,
        concepts=["transfer"],
    )
    data = {DASH: _pages()[DASH], TRANSFER: [], HIDDEN: []}

    resolved, next_url, _assertion = asyncio.run(
        orchestrator._resolve_placeholder_for_page(  # noqa: SLF001
            action="GOTO",
            description="go to the transfer page",
            current_url=DASH,
            scraped_data=data,
        )
    )

    assert next_url == TRANSFER, resolved
    assert HIDDEN not in resolved


def test_goto_with_no_current_page_still_uses_the_keyword_map() -> None:
    orchestrator = PlaceholderOrchestrator(starting_url=HOME)
    orchestrator.url_resolver.build_mapping(
        keywords=["transfer"],
        scraped_urls=[HOME, TRANSFER],
        seed_url=HOME,
        concepts=["transfer"],
    )

    resolved, next_url, _assertion = asyncio.run(
        orchestrator._resolve_placeholder_for_page(  # noqa: SLF001
            action="GOTO",
            description="go to the transfer page",
            current_url=None,
            scraped_data={HOME: [], TRANSFER: []},
        )
    )

    assert next_url == TRANSFER, resolved


def test_goto_still_uses_a_url_the_human_supplied() -> None:
    orchestrator = PlaceholderOrchestrator(starting_url=HOME)
    orchestrator._provided_target_urls = [HOME]

    resolved, next_url, _assertion = asyncio.run(
        orchestrator._resolve_placeholder_for_page(  # noqa: SLF001
            action="GOTO",
            description="home",
            current_url=HOME,
            scraped_data={HOME: []},
        )
    )

    assert next_url == HOME, resolved
