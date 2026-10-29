"""t-0855 (D1a, D1b): the two resolver sources that fabricated a destination.

Both cuts remove a way a GOTO could name a URL that nobody gave us and that
the browser never reached.

(a) **Learned cross-site transitions.** Flow memory (AI-042) learns "on site X,
'login' leads to /dashboard" from earlier runs. In the GOTO branch it could
then type a URL for a page this run never visited. Removed from that branch.

(b) **Common path candidates.** With nothing scraped, ``UrlResolver`` used to
invent ``/cart``, ``/checkout`` and friends from a shared route vocabulary and
offer them as destinations. Removed.

Both cuts keep the honest-skip rule the owner set (2026-10-21): a navigation is
only valid when its destination is known - the human's URL, the story's route
concepts mapped onto real pages, or a page the pipeline really scraped.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from src.flow_memory import FlowMemoryStore, FlowTransition, flow_resolved_url
from src.placeholder_orchestrator import PlaceholderOrchestrator
from src.url_resolver import UrlResolver

SITE = "https://shop.example.com"
LOGIN = f"{SITE}/login"
# The learned destination's path says nothing about "dashboard", so the scraped
# page cannot answer the description on its own - flow memory was the only
# source that could, which is exactly what the cut must have removed.
LEARNED = f"{SITE}/h2x.html"


def _elements() -> list[dict[str, str]]:
    return [{"selector": "body", "tag": "div"}]


def _learned_store(tmp_path: Path) -> FlowMemoryStore:
    """A store that learned: a link labelled "dashboard" leads to /h2x.html.

    The destination's path says nothing about "dashboard", and the label does
    not appear in the path - so the only thing that could ever resolve this
    GOTO is the learned store.
    """
    store = FlowMemoryStore(tmp_path / "flow_memory.json")
    store.upsert_flow(FlowTransition("login", "CLICK", "dashboard", "h2x"), "site-a.com")
    return store


# ── (a) the learned-store source is gone from the GOTO branch ────────────


def test_flow_memory_would_resolve_this_goto(tmp_path: Path) -> None:
    """Control: the store really does answer this GOTO, so the test below
    fails for the right reason - the cut, not an empty store."""
    store = _learned_store(tmp_path)
    assert (
        flow_resolved_url(
            store,
            description="dashboard",
            from_url=LOGIN,
            scraped_urls=[LOGIN, LEARNED],
        )
        == LEARNED
    )


def test_goto_branch_ignores_the_learned_store(tmp_path: Path) -> None:
    """A GOTO that only flow memory could answer is now an honest skip."""
    store = _learned_store(tmp_path)
    orchestrator = PlaceholderOrchestrator(starting_url=LOGIN, flow_store=store)

    resolved, next_url, _assertion = asyncio.run(
        orchestrator._resolve_placeholder_for_page(  # noqa: SLF001
            action="GOTO",
            description="dashboard",
            current_url=LOGIN,
            scraped_data={LOGIN: _elements(), LEARNED: _elements()},
        )
    )

    assert next_url is None, f"the GOTO still moved the cursor to {next_url}"
    assert resolved.startswith("pytest.skip("), f"a URL was still typed: {resolved}"
    assert f"no link on '{LOGIN}' and no trail landing for 'dashboard'" in resolved


# ── (b) the common-path-candidate fabrication is gone ────────────────────


def test_no_candidates_are_fabricated_when_nothing_was_scraped() -> None:
    """Concepts alone never invent a destination.

    2026-08-03 this test pinned the opposite (SPA sites "needed" the guess).
    t-0855 removes the guess: a page nobody scraped is not a known page.
    """
    resolver = UrlResolver()
    resolver.build_mapping(
        keywords=["products", "cart"],
        scraped_urls=[],
        seed_url="https://www.example.com/",
        concepts=["products", "cart"],
    )

    assert resolver.resolve("products") is None
    assert resolver.resolve("cart") is None
    # The human's own URL is still a known destination.
    assert resolver.resolve("home") == "https://www.example.com/"
    assert resolver.resolve("homepage") == "https://www.example.com/"


def test_scraped_urls_still_map_as_before() -> None:
    """The cut removes the fabrication only - real scraped pages still map."""
    resolver = UrlResolver()
    resolver.build_mapping(
        keywords=["cart"],
        scraped_urls=["https://www.example.com/", "https://www.example.com/cart.html"],
        seed_url="https://www.example.com/",
        concepts=["cart", "products"],
    )
    assert resolver.resolve("cart") == "https://www.example.com/cart.html"


def test_goto_branch_skips_when_the_url_resolver_has_nothing() -> None:
    """End to end through the branch: no mapped keyword, no scraped match,
    no learned store -> honest skip, never a typed URL."""
    orchestrator = PlaceholderOrchestrator(starting_url=LOGIN, flow_store=None)
    orchestrator.url_resolver.build_mapping(
        keywords=["dashboard"],
        scraped_urls=[],
        seed_url=LOGIN,
        concepts=["dashboard"],
    )

    resolved, next_url, _assertion = asyncio.run(
        orchestrator._resolve_placeholder_for_page(  # noqa: SLF001
            action="GOTO",
            description="dashboard",
            current_url=LOGIN,
            scraped_data={LOGIN: _elements()},
        )
    )
    assert next_url is None
    assert resolved.startswith("pytest.skip(")


# ── t-0877: every guessed-URL path is gone (owner's rule, 2026-10-23) ────


def test_a_first_step_goto_records_an_honest_skip_not_a_guessed_page() -> None:
    """The story-level behaviour: a guessed page becomes an honest skip.

    Owner's rule (2026-10-23): "if its not something a real user would have then
    its not accurate testing behaviour". A story whose first step is a GOTO at a
    page nobody named, with only the home page scraped, used to end up pointed at
    "whichever page is first" (the non-strict ``resolve_url`` fallback reached
    from ``_select_initial_page_url``), and the test then asserted against the
    wrong page. It now records a skip.
    """
    from src.pipeline_models import PageRequirement, PlaceholderUse, TestJourney, TestStep

    skeleton = "def test_goto():\n    act('{{GOTO:accounts overview}}')\n"
    journey = TestJourney(
        test_name="test_goto",
        start_line=1,
        end_line=2,
        steps=[
            TestStep(
                line_number=2,
                raw_line="    act('{{GOTO:accounts overview}}')",
                placeholders=[
                    PlaceholderUse(
                        token="{{GOTO:accounts overview}}",
                        action="GOTO",
                        description="accounts overview",
                        line_number=2,
                        raw_line="    act('{{GOTO:accounts overview}}')",
                    )
                ],
            )
        ],
    )
    orchestrator = PlaceholderOrchestrator(starting_url=LOGIN, flow_store=None)

    code = asyncio.run(
        orchestrator._replace_placeholders_sequentially(  # noqa: SLF001
            skeleton_code=skeleton,
            journeys=[journey],
            page_requirements=[PageRequirement(keyword="accounts")],
            seed_urls=[LOGIN],
            scraped_data={LOGIN: _elements()},
            scraped_errors={},
        )
    )

    assert "pytest.skip" in code, f"a guessed destination was emitted instead of a skip:\n{code}"
    assert "h2x.html" not in code and "/accounts" not in code, code


def test_resolve_url_has_no_non_strict_fallback_left() -> None:
    """``resolve_url`` cannot be asked to guess any more - the flag is gone."""
    import inspect

    from src.placeholder_resolver import PlaceholderResolver

    params = inspect.signature(PlaceholderResolver.resolve_url).parameters
    assert "strict" not in params, "the non-strict fallback flag still exists"

    resolver = PlaceholderResolver()
    # A description that matches nothing, against real scraped pages, is None.
    assert resolver.resolve_url("accounts overview", {LOGIN: _elements()}) is None
