"""Unit tests for ``src/rag_learn.py`` (AI-035 core + B-036 Phase 3 trigger)."""

from __future__ import annotations

from unittest.mock import MagicMock

from src.rag_learn import (
    _step_to_pattern,
    domain_from_url,
    learn_from_evidence,
    site_hash,
)
from src.rag_store import LearnedPattern


class TestSiteHash:
    def test_deterministic(self) -> None:
        assert site_hash("saucedemo.com") == site_hash("saucedemo.com")

    def test_case_insensitive(self) -> None:
        assert site_hash("SauceDemo.com") == site_hash("saucedemo.com")

    def test_different_domains_differ(self) -> None:
        assert site_hash("saucedemo.com") != site_hash("automationexercise.com")

    def test_one_way(self) -> None:
        digest = site_hash("saucedemo.com")
        assert "saucedemo" not in digest
        assert len(digest) == 16


class TestDomainFromUrl:
    def test_plain(self) -> None:
        assert domain_from_url("https://www.saucedemo.com/inventory.html") == "www.saucedemo.com"

    def test_strips_port(self) -> None:
        assert domain_from_url("http://localhost:8781/generated_tests/mock.html") == "localhost"

    def test_lowercases(self) -> None:
        assert domain_from_url("https://EXAMPLE.COM/") == "example.com"

    def test_empty(self) -> None:
        assert domain_from_url("") == ""
        assert domain_from_url(None) == ""  # type: ignore[arg-type]


def _step(
    step_type: str = "fill",
    label: str = "username",
    locator: str | None = "#user-name",
    status: str = "passed",
    url: str = "https://www.saucedemo.com/",
) -> dict[str, object]:
    return {
        "type": step_type,
        "label": label,
        "locator": locator,
        "url": url,
        "result": {"status": status},
    }


class TestStepToPattern:
    def test_fill_maps_to_fill(self) -> None:
        p = _step_to_pattern(_step())
        assert isinstance(p, LearnedPattern)
        assert p.action_type == "FILL"
        assert p.description == "username"
        assert p.locator == "#user-name"
        assert p.site_hash == site_hash("www.saucedemo.com")
        assert p.confidence == 0.9
        assert p.source == "evidence"

    def test_click_and_assertion_map(self) -> None:
        click_pattern = _step_to_pattern(_step(step_type="click", label="Login", locator="#login-button"))
        assert click_pattern is not None
        assert click_pattern.action_type == "CLICK"
        assert_pattern = _step_to_pattern(
            _step(step_type="assertion", label="product list", locator="[data-test=item]")
        )
        assert assert_pattern is not None
        assert assert_pattern.action_type == "ASSERT"

    def test_navigate_skipped(self) -> None:
        assert _step_to_pattern(_step(step_type="navigate", locator=None)) is None

    def test_missing_locator_skipped(self) -> None:
        assert _step_to_pattern(_step(locator="")) is None

    def test_missing_url_skipped(self) -> None:
        assert _step_to_pattern(_step(url="")) is None

    def test_unknown_type_skipped(self) -> None:
        assert _step_to_pattern(_step(step_type="hover")) is None


class TestLearnFromEvidence:
    def test_learns_passed_steps_only(self) -> None:
        store = MagicMock()
        store.upsert_pattern.return_value = ("inserted", 1)
        steps = [
            _step(label="username"),  # passed → learned
            _step(label="password", status="failed"),  # skipped
            _step(label="login", step_type="click", status="partial_pass"),  # skipped
            _step(label="product list", step_type="assertion"),  # passed → learned
            _step(step_type="navigate", label="goto home"),  # skipped (no locator)
        ]
        result = learn_from_evidence(steps, store=store)
        assert result == {"inserted": 2, "exists": 0}
        assert store.upsert_pattern.call_count == 2

    def test_dedup_repeat_counts_as_exists(self) -> None:
        store = MagicMock()
        store.upsert_pattern.side_effect = [("inserted", 1), ("exists", 2)]
        result = learn_from_evidence([_step(), _step()], store=store)
        assert result == {"inserted": 1, "exists": 1}

    def test_empty_steps(self) -> None:
        store = MagicMock()
        assert learn_from_evidence([], store=store) == {"inserted": 0, "exists": 0}
        store.upsert_pattern.assert_not_called()

    def test_result_missing_treated_as_not_passed(self) -> None:
        store = MagicMock()
        step = _step()
        step.pop("result")
        assert learn_from_evidence([step], store=store) == {"inserted": 0, "exists": 0}

    def test_site_scoping_uses_step_url_domain(self) -> None:
        store = MagicMock()
        store.upsert_pattern.return_value = ("inserted", 1)
        learn_from_evidence(
            [_step(url="https://www.saucedemo.com/inventory.html")],
            store=store,
        )
        learned: LearnedPattern = store.upsert_pattern.call_args.args[0]
        assert learned.site_hash == site_hash("www.saucedemo.com")
