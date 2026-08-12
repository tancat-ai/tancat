"""Unit tests for ``src/flow_memory.py`` (AI-042 — cross-site flow memory).

The learner (route normalization, transition extraction) and the store
(dedup, site diversity, persistence) are pure and tested offline; the
consumption hook (``flow_resolved_url``) is tested with learned stores.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.flow_memory import (
    FlowMemoryStore,
    FlowTransition,
    clean_description,
    flow_resolved_url,
    flow_transitions,
    normalize_route,
)

LOGIN = "https://site-a.com/login"
DASHBOARD = "https://site-a.com/dashboard.html"
TRANSFER = "https://site-a.com/transfer"


def _step(
    step_type: str,
    *,
    label: str,
    url: str,
    value: str | None = None,
    status: str = "passed",
    locator: str | None = "x",
) -> dict[str, Any]:
    return {
        "type": step_type,
        "label": label,
        "locator": locator,
        "value": value,
        "url": url,
        "result": {"status": status, "run_count": 1},
    }


def _navigate(url: str) -> dict[str, Any]:
    return _step("navigate", label=f"Navigate to {url}", url=url, value=url)


def _login_to_dashboard_flow() -> list[dict[str, Any]]:
    """login → sign in → dashboard → transfer (a realistic e-commerce shape)."""
    return [
        _navigate(LOGIN),
        _step("fill", label="Fill: username", url=LOGIN),
        _step("fill", label="Fill: password", url=LOGIN),
        _step("click", label="Click: sign in", url=DASHBOARD),
        _step("click", label="Click: transfer money", url=TRANSFER),
    ]


# ---------------------------------------------------------------------------
# normalize_route
# ---------------------------------------------------------------------------


class TestNormalizeRoute:
    def test_strips_extensions(self) -> None:
        assert normalize_route("https://www.saucedemo.com/cart.html") == "cart"
        assert normalize_route("https://site.com/cart.php") == "cart"

    def test_drops_numeric_segments(self) -> None:
        assert normalize_route("https://site.com/category_products/1") == "category_products"

    def test_keeps_hyphenated_multi_word_routes(self) -> None:
        assert normalize_route("https://site.com/checkout-step-one.html") == "checkout-step-one"
        # step pages are distinct flow states — never collapsed
        assert normalize_route("https://site.com/checkout-step-two.html") == "checkout-step-two"

    def test_canonicalizes_page_type_aliases(self) -> None:
        # saucedemo's /inventory.html is the product listing — the learned
        # analog of url_resolver's alias groups (AI-042 finding)
        assert normalize_route("https://www.saucedemo.com/inventory.html") == "products"
        assert normalize_route("https://www.saucedemo.com/cart.html") == "cart"
        assert normalize_route("https://automationexercise.com/view_cart") == "cart"
        assert normalize_route("https://site.com/basket") == "cart"
        assert normalize_route("https://site.com/signin") == "login"
        assert normalize_route("https://site.com/auth") == "login"

    def test_root_and_index_become_home(self) -> None:
        assert normalize_route("https://site.com/") == "home"
        assert normalize_route("https://site.com") == "home"
        assert normalize_route("https://site.com/index.html") == "home"
        assert normalize_route("http://localhost:8783/index.html") == "home"

    def test_query_and_fragment_ignored(self) -> None:
        assert normalize_route("https://site.com/product_details.html?id=1") == "product_details"

    def test_empty_and_garbage(self) -> None:
        assert normalize_route("") == "home"
        assert normalize_route("not a url") == "not a url"

    def test_case_insensitive(self) -> None:
        assert normalize_route("https://SITE.com/Cart.HTML") == "cart"


# ---------------------------------------------------------------------------
# clean_description
# ---------------------------------------------------------------------------


class TestCleanDescription:
    def test_action_prefix_form(self) -> None:
        assert clean_description("Click: view cart link") == "view cart link"

    def test_placeholder_form(self) -> None:
        assert clean_description("{{CLICK:view cart link}}") == "view cart link"

    def test_plain_label_unchanged(self) -> None:
        assert clean_description("order summary") == "order summary"

    def test_empty(self) -> None:
        assert clean_description("") == ""
        assert clean_description("   ") == ""


# ---------------------------------------------------------------------------
# flow_transitions
# ---------------------------------------------------------------------------


class TestFlowTransitions:
    def test_extracts_flow_with_sites(self) -> None:
        transitions = flow_transitions(_login_to_dashboard_flow())
        # same-page FILL steps (login → login) are dropped by design — only
        # navigation-advancing steps emit transitions
        assert [(t.from_route, t.action, t.description, t.to_route) for t, _ in transitions] == [
            ("login", "CLICK", "sign in", "dashboard"),
            ("dashboard", "CLICK", "transfer money", "transfer"),
        ]
        # site identity comes from each step's own URL
        assert {site for _, site in transitions} == {"site-a.com"}

    def test_only_passed_steps_emit(self) -> None:
        steps = [
            _navigate(LOGIN),
            _step("click", label="Click: sign in", url=DASHBOARD, status="failed"),
            _step("click", label="Click: transfer money", url=TRANSFER, status="passed"),
        ]
        transitions = flow_transitions(steps)
        # failed step emits nothing; the passed step after it still sees the
        # failed step's page as context (dashboard — the recorded URL is factual)
        assert [(t.from_route, t.description, t.to_route) for t, _ in transitions] == [
            ("dashboard", "transfer money", "transfer")
        ]

    def test_same_page_actions_dropped(self) -> None:
        steps = [
            _navigate(LOGIN),
            _step("click", label="Click: show password", url=LOGIN),  # stays on login
            _step("click", label="Click: sign in", url=DASHBOARD),
        ]
        transitions = flow_transitions(steps)
        assert [(t.from_route, t.description, t.to_route) for t, _ in transitions] == [
            ("login", "sign in", "dashboard")
        ]

    def test_navigate_sets_context(self) -> None:
        steps = [
            _navigate("https://site-a.com/"),
            _step("click", label="Click: browse products", url="https://site-a.com/products.html"),
        ]
        transitions = flow_transitions(steps)
        assert [(t.from_route, t.description, t.to_route) for t, _ in transitions] == [
            ("home", "browse products", "products")
        ]

    def test_steps_without_url_are_skipped_safely(self) -> None:
        steps = [
            _navigate(LOGIN),
            {"type": "click", "label": "Click: sign in", "result": {"status": "passed"}},  # no url
            _step("click", label="Click: transfer money", url=TRANSFER),
        ]
        transitions = flow_transitions(steps)
        # no-url step: to_route = home == from? from=login → to=home → dropped
        # context does not advance (no url) → next step from = login
        assert [(t.from_route, t.description, t.to_route) for t, _ in transitions] == [
            ("login", "transfer money", "transfer")
        ]


# ---------------------------------------------------------------------------
# FlowMemoryStore
# ---------------------------------------------------------------------------


class TestFlowMemoryStore:
    def test_upsert_dedups_and_bumps_hit_count(self, tmp_path: Path) -> None:
        store = FlowMemoryStore(tmp_path / "flow_memory.json")
        transition = FlowTransition("login", "CLICK", "sign in", "dashboard")
        assert store.upsert_flow(transition, "site-a.com") == "inserted"
        assert store.upsert_flow(transition, "site-a.com") == "exists"
        patterns = store.query("login")
        assert len(patterns) == 1
        assert patterns[0].hit_count == 2
        assert patterns[0].site_count == 1

    def test_site_diversity_tracks_distinct_sites(self, tmp_path: Path) -> None:
        store = FlowMemoryStore(tmp_path / "flow_memory.json")
        transition = FlowTransition("login", "CLICK", "sign in", "dashboard")
        store.upsert_flow(transition, "site-a.com")
        store.upsert_flow(transition, "site-b.com")
        patterns = store.query("login")
        assert patterns[0].site_count == 2
        assert store.stats()["cross_site"] == 1

    def test_learn_from_evidence_round_trip(self, tmp_path: Path) -> None:
        path = tmp_path / "evidence" / "flow_memory.json"
        store = FlowMemoryStore(path)
        result = store.learn_from_evidence(_login_to_dashboard_flow())
        assert result == {"inserted": 2, "exists": 0}
        # reload from disk
        reloaded = FlowMemoryStore(path)
        assert reloaded.stats()["patterns"] == 2
        assert reloaded.stats()["sites"] == 1

    def test_relearning_bumps_hits_and_dedups(self, tmp_path: Path) -> None:
        store = FlowMemoryStore(tmp_path / "flow_memory.json")
        store.learn_from_evidence(_login_to_dashboard_flow())
        result = store.learn_from_evidence(_login_to_dashboard_flow())
        assert result == {"inserted": 0, "exists": 2}
        pattern = store.query("login", description="sign in")[0]
        assert pattern.hit_count == 2

    def test_corrupt_file_starts_empty(self, tmp_path: Path) -> None:
        path = tmp_path / "flow_memory.json"
        path.write_text("{ not json !!", encoding="utf-8")
        store = FlowMemoryStore(path)  # must not raise
        assert store.stats()["patterns"] == 0
        assert store.query("login") == []

    def test_clear(self, tmp_path: Path) -> None:
        store = FlowMemoryStore(tmp_path / "flow_memory.json")
        store.learn_from_evidence(_login_to_dashboard_flow())
        assert store.stats()["patterns"] == 2
        store.clear()
        assert store.stats()["patterns"] == 0
        assert not store.path.exists()

    def test_query_filters_and_ranks(self, tmp_path: Path) -> None:
        store = FlowMemoryStore(tmp_path / "flow_memory.json")
        store.upsert_flow(FlowTransition("login", "CLICK", "sign in", "dashboard"), "site-a.com")
        store.upsert_flow(FlowTransition("login", "CLICK", "sign in", "dashboard"), "site-b.com")
        store.upsert_flow(FlowTransition("login", "CLICK", "sign in", "portal"), "site-a.com")
        # exact description filter
        assert [p.to_route for p in store.query("login", description="sign in")] == ["dashboard", "portal"]
        # cross-site pattern ranks first
        assert store.query("login")[0].to_route == "dashboard"
        # action filter
        assert store.query("login", action="FILL") == []
        # unrelated from_route
        assert store.query("cart") == []

    def test_route_hints_and_min_sites_guardrail(self, tmp_path: Path) -> None:
        store = FlowMemoryStore(tmp_path / "flow_memory.json")
        store.upsert_flow(FlowTransition("login", "CLICK", "sign in", "dashboard"), "site-a.com")
        store.upsert_flow(FlowTransition("login", "CLICK", "sign in", "dashboard"), "site-b.com")
        store.upsert_flow(FlowTransition("login", "CLICK", "forgot password", "reset"), "site-a.com")

        hints = store.route_hints("login")
        assert hints[0] == ("dashboard", 2, 2)  # ranked by site_count
        # min_sites=2 keeps only the cross-site flow
        assert store.route_hints("login", min_sites=2) == [("dashboard", 2, 2)]
        # description filter narrows
        assert store.route_hints("login", description="forgot password") == [("reset", 1, 1)]

    def test_learn_from_sidecars_gates_on_passing_test(self, tmp_path: Path) -> None:
        evidence_dir = tmp_path / "evidence"
        evidence_dir.mkdir()
        (evidence_dir / "pass.evidence.json").write_text(
            json.dumps({"test": {"status": "passed"}, "steps": _login_to_dashboard_flow()}), encoding="utf-8"
        )
        (evidence_dir / "fail.evidence.json").write_text(
            json.dumps({"test": {"status": "failed"}, "steps": _login_to_dashboard_flow()}), encoding="utf-8"
        )
        (evidence_dir / "junk.evidence.json").write_text("{ nope", encoding="utf-8")

        store = FlowMemoryStore(tmp_path / "flow_memory.json")
        totals = store.learn_from_sidecars(evidence_dir)
        assert totals["sidecars"] == 3
        assert totals["inserted"] == 2  # only the passing sidecar learned
        assert totals["exists"] == 0
        assert totals["errors"] == 1  # corrupt sidecar counted, not raised


# ---------------------------------------------------------------------------
# flow_resolved_url (consumption hook)
# ---------------------------------------------------------------------------


class TestFlowResolvedUrl:
    def _learned_store(self, tmp_path: Path) -> FlowMemoryStore:
        store = FlowMemoryStore(tmp_path / "flow_memory.json")
        # site-a and site-b both verify login → dashboard
        store.upsert_flow(FlowTransition("login", "CLICK", "sign in", "dashboard"), "site-a.com")
        store.upsert_flow(FlowTransition("login", "CLICK", "sign in", "dashboard"), "site-b.com")
        store.upsert_flow(FlowTransition("dashboard", "CLICK", "transfer money", "transfer"), "site-a.com")
        return store

    def test_resolves_unseen_site_via_cross_site_flow(self, tmp_path: Path) -> None:
        """The value moment: an unseen site (no evidence of its own) resolves a
        GOTO using flows verified on other sites."""
        store = self._learned_store(tmp_path)
        url = flow_resolved_url(
            store,
            description="dashboard",
            from_url="https://brand-new-site.com/login",
            scraped_urls=[
                "https://brand-new-site.com/login",
                "https://brand-new-site.com/dashboard.html",
                "https://brand-new-site.com/transfer.html",
            ],
        )
        assert url == "https://brand-new-site.com/dashboard.html"

    def test_matches_destination_vocabulary_not_only_action_label(self, tmp_path: Path) -> None:
        """A GOTO description like 'dashboard page' matches the learned
        to_route vocabulary, not just the exact action label 'sign in'."""
        store = self._learned_store(tmp_path)
        url = flow_resolved_url(
            store,
            description="dashboard page is loaded",
            from_url="https://unseen.com/login",
            scraped_urls=["https://unseen.com/dashboard.html", "https://unseen.com/transfer.html"],
        )
        assert url == "https://unseen.com/dashboard.html"

    def test_none_when_no_flow_supports_destination(self, tmp_path: Path) -> None:
        store = self._learned_store(tmp_path)
        url = flow_resolved_url(
            store,
            description="payment",
            from_url="https://unseen.com/login",
            scraped_urls=["https://unseen.com/payment.html"],
        )
        assert url is None

    def test_none_when_destination_not_scraped(self, tmp_path: Path) -> None:
        store = self._learned_store(tmp_path)
        url = flow_resolved_url(
            store,
            description="dashboard",
            from_url="https://unseen.com/login",
            scraped_urls=["https://unseen.com/login", "https://unseen.com/transfer.html"],
        )
        assert url is None

    def test_none_with_min_sites_guardrail(self, tmp_path: Path) -> None:
        store = self._learned_store(tmp_path)
        # dashboard is cross-site (2 sites) but transfer is single-site
        url = flow_resolved_url(
            store,
            description="transfer",
            from_url="https://unseen.com/dashboard.html",
            scraped_urls=["https://unseen.com/dashboard.html", "https://unseen.com/transfer.html"],
            min_sites=2,
        )
        assert url is None

    def test_site_specific_flow_still_resolves_at_min_sites_1(self, tmp_path: Path) -> None:
        store = self._learned_store(tmp_path)
        url = flow_resolved_url(
            store,
            description="transfer",
            from_url="https://unseen.com/dashboard.html",
            scraped_urls=["https://unseen.com/dashboard.html", "https://unseen.com/transfer.html"],
        )
        assert url == "https://unseen.com/transfer.html"


# ---------------------------------------------------------------------------
# Orchestrator consumption hook (step 2.5 in the GOTO/URL resolution chain)
# ---------------------------------------------------------------------------


class _NullUrlResolver:
    """Stub: no site-specific keyword→URL knowledge (forces flow fallback)."""

    def resolve(self, description: str) -> str | None:  # noqa: ARG002
        return None

    def get_seed_url(self) -> str | None:
        return None


class _NullResolver:
    """Stub: no DOM/text resolution (forces flow fallback)."""

    def resolve_url(self, *args: Any, **kwargs: Any) -> str | None:  # noqa: ARG002
        return None


def test_goto_resolves_via_flow_memory_when_site_resolution_fails(tmp_path: Path) -> None:
    """The orchestrator's GOTO chain: after UrlResolver and resolve_url both
    fail, a cross-site flow (login → dashboard verified on 2 sites) rescues
    'dashboard' on an unseen site."""
    import asyncio

    from src.flow_memory import FlowMemoryStore, FlowTransition
    from src.pipeline_models import PageRequirement, PlaceholderUse, TestJourney, TestStep
    from src.placeholder_orchestrator import PlaceholderOrchestrator

    store = FlowMemoryStore(tmp_path / "flow_memory.json")
    store.upsert_flow(FlowTransition("login", "CLICK", "sign in", "dashboard"), "site-a.com")
    store.upsert_flow(FlowTransition("login", "CLICK", "sign in", "dashboard"), "site-b.com")

    skeleton = "page.goto('{{GOTO:dashboard}}')\n"
    scraped_data = {
        "https://unseen.com/login": [{"selector": "input#user", "tag": "input"}],
        "https://unseen.com/dashboard.html": [{"selector": "h1", "tag": "h1", "text": "Accounts"}],
    }
    journey = TestJourney(
        test_name="test_flow_goto",
        start_line=1,
        end_line=2,
        steps=[
            TestStep(
                line_number=1,
                raw_line="page.goto('{{GOTO:dashboard}}')",
                placeholders=[
                    PlaceholderUse(
                        action="GOTO",
                        description="dashboard",
                        token="{{GOTO:dashboard}}",
                        line_number=1,
                        raw_line="page.goto('{{GOTO:dashboard}}')",
                    )
                ],
            )
        ],
    )

    orch = PlaceholderOrchestrator(starting_url="https://unseen.com/login", flow_store=store)
    orch.url_resolver = _NullUrlResolver()  # type: ignore[assignment]
    orch.resolver = _NullResolver()  # type: ignore[assignment]

    async def run() -> str:
        return await orch._replace_placeholders_sequentially(  # noqa: SLF001
            skeleton_code=skeleton,
            journeys=[journey],
            page_requirements=[PageRequirement(keyword="login")],
            seed_urls=["https://unseen.com/login"],
            scraped_data=scraped_data,
            scraped_errors={},
        )

    result = asyncio.run(run())
    assert "https://unseen.com/dashboard.html" in result
    assert "pytest.skip" not in result


def test_goto_skips_when_flow_memory_disabled_or_empty(tmp_path: Path) -> None:
    """With no flow store, the GOTO chain falls through to the skip path —
    the default behavior (zero overhead when flows are absent)."""
    import asyncio

    from src.pipeline_models import PageRequirement, PlaceholderUse, TestJourney, TestStep
    from src.placeholder_orchestrator import PlaceholderOrchestrator

    skeleton = "page.goto('{{GOTO:dashboard}}')\n"
    scraped_data = {
        "https://unseen.com/login": [{"selector": "input#user", "tag": "input"}],
        "https://unseen.com/dashboard.html": [{"selector": "h1", "tag": "h1", "text": "Accounts"}],
    }
    journey = TestJourney(
        test_name="test_flow_goto_off",
        start_line=1,
        end_line=2,
        steps=[
            TestStep(
                line_number=1,
                raw_line="page.goto('{{GOTO:dashboard}}')",
                placeholders=[
                    PlaceholderUse(
                        action="GOTO",
                        description="dashboard",
                        token="{{GOTO:dashboard}}",
                        line_number=1,
                        raw_line="page.goto('{{GOTO:dashboard}}')",
                    )
                ],
            )
        ],
    )

    orch = PlaceholderOrchestrator(starting_url="https://unseen.com/login")  # flow_store=None
    orch.url_resolver = _NullUrlResolver()  # type: ignore[assignment]
    orch.resolver = _NullResolver()  # type: ignore[assignment]

    async def run() -> str:
        return await orch._replace_placeholders_sequentially(  # noqa: SLF001
            skeleton_code=skeleton,
            journeys=[journey],
            page_requirements=[PageRequirement(keyword="login")],
            seed_urls=["https://unseen.com/login"],
            scraped_data=scraped_data,
            scraped_errors={},
        )

    result = asyncio.run(run())
    # no flow store → no flow resolution; the unresolved GOTO stays literal
    # (pre-existing behavior — zero interference from the flow feature)
    assert "https://unseen.com/dashboard.html" not in result
    assert "{{GOTO:dashboard}}" in result
