"""Unit tests for ``src/rag_learn.py`` (AI-035 core + B-036 Phase 3 trigger)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from src.rag_learn import (
    _step_to_pattern,
    domain_from_url,
    learn_from_evidence,
    learn_from_evidence_sidecars,
    learn_from_patch,
    pattern_from_patch,
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

    def test_mock_ports_hash_distinctly(self) -> None:
        """B-047: banking:8782, ecommerce:8783, lv_insurance:8781 must each
        scope learned patterns independently."""
        assert site_hash("localhost:8782") != site_hash("localhost:8783")
        assert site_hash("localhost:8782") != site_hash("localhost:8781")
        assert site_hash("localhost:8783") != site_hash("localhost:8781")
        assert site_hash("localhost:8781") != site_hash("localhost")

    def test_one_way(self) -> None:
        digest = site_hash("saucedemo.com")
        assert "saucedemo" not in digest
        assert len(digest) == 16


class TestDomainFromUrl:
    def test_plain(self) -> None:
        assert domain_from_url("https://www.saucedemo.com/inventory.html") == "www.saucedemo.com"

    def test_keeps_port_for_mock_sites(self) -> None:
        """B-047: the port is part of the site identity — localhost mocks on
        different ports must not collapse into one ``localhost`` bucket."""
        assert domain_from_url("http://localhost:8781/generated_tests/mock.html") == "localhost:8781"

    def test_lowercases(self) -> None:
        assert domain_from_url("https://EXAMPLE.COM/") == "example.com"

    def test_plain_explicit_port_kept(self) -> None:
        assert domain_from_url("https://www.saucedemo.com:8080/inventory.html") == "www.saucedemo.com:8080"

    def test_strips_userinfo(self) -> None:
        assert domain_from_url("https://user:pass@example.com:8782/index.html") == "example.com:8782"

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

    def test_concurrent_mocks_scope_independently(self) -> None:
        """B-047 regression: the 3 mock sites (banking:8782, ecommerce:8783,
        lv_insurance:8781) must produce distinct site hashes so learned
        patterns never earn SAME_SITE_LEARNED_BONUS cross-mock."""
        banking = _step_to_pattern(
            _step(label="login", locator="#login-button", url="http://localhost:8782/index.html")
        )
        ecommerce = _step_to_pattern(
            _step(label="login", locator="#login-button", url="http://localhost:8783/index.html")
        )
        lv_insurance = _step_to_pattern(
            _step(label="login", locator="#login-button", url="http://localhost:8781/index.html")
        )
        assert banking is not None and ecommerce is not None and lv_insurance is not None
        hashes = {banking.site_hash, ecommerce.site_hash, lv_insurance.site_hash}
        assert len(hashes) == 3


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


# ---------------------------------------------------------------------------
# Self-healing write path (AI-035) — pattern_from_patch / learn_from_patch
# ---------------------------------------------------------------------------


class TestPatternFromPatch:
    """Patch → LearnedPattern extraction (confidence 1.0, source self_healing)."""

    def test_click_replacement(self) -> None:
        pattern = pattern_from_patch(
            'page.locator("#wrong-btn").click()',
            'page.locator("#add-to-cart").click()',
            base_url="https://www.saucedemo.com/inventory.html",
            description="Add to cart",
        )
        assert isinstance(pattern, LearnedPattern)
        assert pattern.action_type == "CLICK"
        assert pattern.locator == "#add-to-cart"
        assert pattern.description == "Add to cart"
        assert pattern.site_hash == site_hash("www.saucedemo.com")
        assert pattern.confidence == 1.0
        assert pattern.source == "self_healing"

    def test_fill_replacement(self) -> None:
        pattern = pattern_from_patch(
            'page.locator("#user").fill("x")',
            'page.locator("#user-name").fill("x")',
            base_url="https://www.saucedemo.com/",
            description="username",
        )
        assert pattern is not None
        assert pattern.action_type == "FILL"
        assert pattern.locator == "#user-name"

    def test_assert_replacement(self) -> None:
        pattern = pattern_from_patch(
            'expect(page.locator("#msg")).to_be_visible()',
            'expect(page.locator("#success")).to_be_visible()',
            base_url="https://example.com/",
            description="success message",
        )
        assert pattern is not None
        assert pattern.action_type == "ASSERT"
        assert pattern.locator == "#success"

    def test_select_option_replacement(self) -> None:
        pattern = pattern_from_patch(
            'page.locator("#country").select_option("US")',
            'page.locator("select#country").select_option("US")',
            base_url="https://example.com/",
            description="country",
        )
        assert pattern is not None
        assert pattern.action_type == "SELECT"

    def test_evidence_tracker_click_replacement(self) -> None:
        """Generated tests use evidence_tracker.click(sel, label=...) — the
        corrected selector is the first quoted argument."""
        pattern = pattern_from_patch(
            "evidence_tracker.click('a[href=\"/cartxx.html\"]', label='Cart link')",
            "evidence_tracker.click('a[href=\"/cart.html\"]', label='Cart link')",
            base_url="http://localhost:8781/index.html",
            description="Cart link",
        )
        assert isinstance(pattern, LearnedPattern)
        assert pattern.action_type == "CLICK"
        assert pattern.locator == 'a[href="/cart.html"]'
        assert pattern.site_hash == site_hash("localhost:8781")

    def test_evidence_tracker_fill_and_assert(self) -> None:
        fill = pattern_from_patch(
            'evidence_tracker.fill("#emai1", "x")',
            'evidence_tracker.fill("#email", "x")',
            base_url="https://example.com/",
            description="email",
        )
        assert fill is not None and fill.action_type == "FILL" and fill.locator == "#email"
        visible = pattern_from_patch(
            'evidence_tracker.assert_visible("#msgl")',
            'evidence_tracker.assert_visible("#msg")',
            base_url="https://example.com/",
            description="success message",
        )
        assert visible is not None and visible.action_type == "ASSERT" and visible.locator == "#msg"

    def test_non_locator_strategy_returns_none(self) -> None:
        # add_wait patch — no locator to learn.
        assert (
            pattern_from_patch(
                'page.click("#x")',
                'page.wait_for_selector("#x")',
                base_url="https://example.com/",
                description="x",
            )
            is None
        )

    def test_get_by_role_returns_none(self) -> None:
        # No .locator("...") string literal to store as a plain selector.
        assert (
            pattern_from_patch(
                'page.get_by_role("button", name="Go").click()',
                'page.get_by_role("button", name="Submit").click()',
                base_url="https://example.com/",
                description="submit",
            )
            is None
        )

    def test_missing_base_url_returns_none(self) -> None:
        assert (
            pattern_from_patch(
                'page.locator("#a").click()',
                'page.locator("#b").click()',
                base_url="",
                description="x",
            )
            is None
        )

    def test_unknown_method_returns_none(self) -> None:
        assert (
            pattern_from_patch(
                'page.locator("#a").hover()',
                'page.locator("#b").hover()',
                base_url="https://example.com/",
                description="x",
            )
            is None
        )

    def test_missing_description_returns_none(self) -> None:
        assert (
            pattern_from_patch(
                'page.locator("#a").click()',
                'page.locator("#b").click()',
                base_url="https://example.com/",
            )
            is None
        )

    def test_description_from_placeholder_label(self) -> None:
        steps = [
            {
                "type": "click",
                "label": "{{CLICK:view cart link}}",
                "locator": "#wrong-btn",
                "url": "https://example.com/",
            },
            {"type": "click", "label": "Click: add to cart", "locator": "#add-to-cart", "url": "https://example.com/"},
        ]
        pattern = pattern_from_patch(
            'page.locator("#wrong-btn").click()',
            'page.locator("#add-to-cart").click()',
            base_url="https://example.com/",
            evidence_steps=steps,
        )
        assert pattern is not None
        assert pattern.description == "view cart link"
        assert pattern.locator == "#add-to-cart"

    def test_description_from_natural_label(self) -> None:
        # Evidence records the locator that ran (and failed): "#wrong".
        steps = [{"type": "click", "label": "Click: add to cart", "locator": "#wrong", "url": "https://example.com/"}]
        pattern = pattern_from_patch(
            'page.locator("#wrong").click()',
            'page.locator("#cart").click()',
            base_url="https://example.com/",
            evidence_steps=steps,
        )
        assert pattern is not None
        assert pattern.description == "add to cart"

    def test_explicit_description_wins_over_evidence(self) -> None:
        steps = [{"type": "click", "label": "Click: old label", "locator": "#cart", "url": "https://example.com/"}]
        pattern = pattern_from_patch(
            'page.locator("#wrong").click()',
            'page.locator("#cart").click()',
            base_url="https://example.com/",
            description="explicit",
            evidence_steps=steps,
        )
        assert pattern is not None
        assert pattern.description == "explicit"

    def test_no_matching_evidence_step_returns_none(self) -> None:
        steps = [{"type": "click", "label": "Click: other", "locator": "#other", "url": "https://example.com/"}]
        assert (
            pattern_from_patch(
                'page.locator("#wrong").click()',
                'page.locator("#cart").click()',
                base_url="https://example.com/",
                evidence_steps=steps,
            )
            is None
        )


class TestLearnFromPatch:
    """learn_from_patch — guarded upsert through the store."""

    def test_returns_inserted(self) -> None:
        store = MagicMock()
        store.upsert_pattern.return_value = ("inserted", 1)
        result = learn_from_patch(
            old_text='page.locator("#a").click()',
            new_text='page.locator("#b").click()',
            base_url="https://example.com/",
            description="x",
            store=store,
        )
        assert result == {"inserted": 1, "exists": 0}

    def test_returns_exists_on_dedup(self) -> None:
        store = MagicMock()
        store.upsert_pattern.return_value = ("exists", 2)
        result = learn_from_patch(
            old_text='page.locator("#a").click()',
            new_text='page.locator("#b").click()',
            base_url="https://example.com/",
            description="x",
            store=store,
        )
        assert result == {"inserted": 0, "exists": 1}

    def test_unlearnable_patch_does_not_touch_store(self) -> None:
        store = MagicMock()
        result = learn_from_patch(
            old_text='page.wait_for_selector("#a")',
            new_text='page.wait_for_selector("#b")',
            base_url="https://example.com/",
            store=store,
        )
        assert result == {"inserted": 0, "exists": 0}
        store.upsert_pattern.assert_not_called()

    def test_store_failure_swallowed(self) -> None:
        store = MagicMock()
        store.upsert_pattern.side_effect = RuntimeError("store down")
        result = learn_from_patch(
            old_text='page.locator("#a").click()',
            new_text='page.locator("#b").click()',
            base_url="https://example.com/",
            description="x",
            store=store,
        )
        assert result == {"inserted": 0, "exists": 0}


class TestLearnFromEvidenceSidecars:
    """B-047 deferred fix: parent-side sweep of evidence sidecars.

    The pytest subprocess hook cannot open the Milvus-lite store while a
    resolve-and-learn parent holds it, so the parent sweeps
    ``evidence/*.evidence.json`` and learns them itself — same gate (only
    fully-passed tests), no lock contention.
    """

    def _write_sidecar(
        self,
        evidence_dir: Path,
        name: str,
        *,
        status: str = "passed",
        steps: list[dict[str, object]] | None = None,
    ) -> Path:
        data = {
            "schema_version": "1.0",
            "test": {"name": name, "status": status},
            "steps": steps if steps is not None else [_step()],
        }
        path = evidence_dir / f"{name}.evidence.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def test_learns_steps_from_passed_sidecar(self, tmp_path: Path) -> None:
        store = MagicMock()
        store.upsert_pattern.return_value = ("inserted", 1)
        self._write_sidecar(
            tmp_path,
            "test_01_login",
            steps=[_step(label="username"), _step(label="password")],
        )
        result = learn_from_evidence_sidecars(tmp_path, store=store)
        assert result == {
            "sidecars": 1,
            "inserted": 2,
            "exists": 0,
            "errors": 0,
            "negatives_inserted": 0,
            "negatives_exists": 0,
        }
        assert store.upsert_pattern.call_count == 2

    def test_skips_failed_sidecar(self, tmp_path: Path) -> None:
        """Mirrors the conftest gate: only fully-passing runs are learned."""
        store = MagicMock()
        store.upsert_pattern.return_value = ("inserted", 1)
        self._write_sidecar(tmp_path, "test_failed", status="failed")
        self._write_sidecar(tmp_path, "test_passed", status="passed")
        result = learn_from_evidence_sidecars(tmp_path, store=store)
        assert result == {
            "sidecars": 2,
            "inserted": 1,
            "exists": 0,
            "errors": 0,
            "negatives_inserted": 0,
            "negatives_exists": 0,
        }
        assert store.upsert_pattern.call_count == 1

    def test_empty_dir_returns_zeros(self, tmp_path: Path) -> None:
        assert learn_from_evidence_sidecars(tmp_path) == {
            "sidecars": 0,
            "inserted": 0,
            "exists": 0,
            "errors": 0,
            "negatives_inserted": 0,
            "negatives_exists": 0,
        }

    def test_missing_dir_returns_zeros(self, tmp_path: Path) -> None:
        assert learn_from_evidence_sidecars(tmp_path / "nope") == {
            "sidecars": 0,
            "inserted": 0,
            "exists": 0,
            "errors": 0,
            "negatives_inserted": 0,
            "negatives_exists": 0,
        }

    def test_corrupt_sidecar_counted_not_raised(self, tmp_path: Path) -> None:
        store = MagicMock()
        store.upsert_pattern.return_value = ("inserted", 1)
        (tmp_path / "bad.evidence.json").write_text("{not json", encoding="utf-8")
        self._write_sidecar(tmp_path, "good", status="passed")
        result = learn_from_evidence_sidecars(tmp_path, store=store)
        assert result == {
            "sidecars": 2,
            "inserted": 1,
            "exists": 0,
            "errors": 1,
            "negatives_inserted": 0,
            "negatives_exists": 0,
        }

    def test_learns_negatives_from_failed_sidecar(self, tmp_path: Path) -> None:
        """AI-058 Slice 2 + AI-063: a failed sidecar feeds learned_negative.

        The sweep keeps the passed-only positive path untouched (the passed
        sidecar still only yields positives) and additionally records
        contrastive negatives: the locator timeout (confidence 0.9) and —
        AI-063 — the resolved-but-wrong assertion failure (the element
        ``#proceed`` existed, was picked, and failed its check; confidence
        0.6). An infra/navigation failure is still excluded.
        """
        store = MagicMock()
        store.upsert_pattern.return_value = ("inserted", 1)
        store.upsert_negative_pattern.return_value = ("inserted", 1)
        locator_err = (
            "TimeoutError: Timeout 5000ms exceeded.\nwaiting for locator('page.locator(\"#wrong-add\")') to be visible"
        )
        self._write_sidecar(
            tmp_path,
            "test_passed",
            status="passed",
            steps=[_step(label="username", locator="#user")],
        )
        self._write_sidecar(
            tmp_path,
            "test_failed",
            status="failed",
            steps=[
                {
                    "type": "click",
                    "label": "Add to cart",
                    "locator": "#wrong-add",
                    "url": "http://localhost:8781/x.html",
                    "result": {"status": "failed", "error": locator_err},
                },
                {
                    "type": "click",
                    "label": "Proceed",
                    "locator": "#proceed",
                    "url": "http://localhost:8781/x.html",
                    "result": {"status": "failed", "error": "AssertionError: text mismatch"},
                },
                {
                    "type": "navigate",
                    "label": "Navigate to http://localhost:8781/x.html",
                    "locator": "",
                    "url": "http://localhost:8781/x.html",
                    "result": {"status": "failed", "error": "Connection refused"},
                },
            ],
        )
        result = learn_from_evidence_sidecars(tmp_path, store=store)
        assert result["inserted"] == 1
        assert result["negatives_inserted"] == 2
        assert result["negatives_exists"] == 0
        # Two negatives: locator timeout (#wrong-add) + resolved-but-wrong (#proceed).
        # The infra navigation failure is excluded (no locator, connection error).
        assert store.upsert_negative_pattern.call_count == 2
        neg_locators = sorted(call.args[0].locator for call in store.upsert_negative_pattern.call_args_list)
        assert neg_locators == ["#proceed", "#wrong-add"]
        lasts = {
            call.args[0].locator: (call.args[0].source, call.args[0].confidence)
            for call in store.upsert_negative_pattern.call_args_list
        }
        assert lasts["#wrong-add"] == ("learned_negative", 0.9)
        assert lasts["#proceed"] == ("learned_negative", 0.6)
        # Positive path unaffected: only the passed step learned a positive.
        assert store.upsert_pattern.call_count == 1

    def test_no_negatives_when_disabled(self, tmp_path: Path) -> None:
        """The ``learn_negatives`` switch keeps the sweep positives-only."""
        store = MagicMock()
        store.upsert_pattern.return_value = ("inserted", 1)
        store.upsert_negative_pattern.return_value = ("inserted", 1)
        locator_err = (
            "TimeoutError: Timeout 5000ms exceeded.\nwaiting for locator('page.locator(\"#wrong-add\")') to be visible"
        )
        self._write_sidecar(
            tmp_path,
            "test_failed",
            status="failed",
            steps=[
                {
                    "type": "click",
                    "label": "Add to cart",
                    "locator": "#wrong-add",
                    "url": "http://localhost:8781/x.html",
                    "result": {"status": "failed", "error": locator_err},
                }
            ],
        )
        result = learn_from_evidence_sidecars(tmp_path, store=store, learn_negatives=False)
        assert result["negatives_inserted"] == 0
        assert result["negatives_exists"] == 0
        store.upsert_negative_pattern.assert_not_called()

    def test_dedup_repeat_bumps_hit_in_sweep(self, tmp_path: Path) -> None:
        store = MagicMock()
        store.upsert_pattern.side_effect = [("inserted", 1), ("exists", 3)]
        self._write_sidecar(tmp_path, "one", status="passed")
        self._write_sidecar(tmp_path, "two", status="passed")
        result = learn_from_evidence_sidecars(tmp_path, store=store)
        assert result == {
            "sidecars": 2,
            "inserted": 1,
            "exists": 1,
            "errors": 0,
            "negatives_inserted": 0,
            "negatives_exists": 0,
        }

    def test_learns_resolved_but_wrong_negative(self, tmp_path: Path) -> None:
        """AI-063: a failed ASSERTION step that carried a resolved selector is
        a *resolved-but-wrong* pick — the element existed and was picked, then
        failed its check. It becomes a ``learned_negative`` at lower confidence
        (0.6), step-scoped for the scorer."""
        store = MagicMock()
        store.upsert_pattern.return_value = ("inserted", 1)
        store.upsert_negative_pattern.return_value = ("inserted", 1)
        self._write_sidecar(
            tmp_path,
            "test_failed_checkout",
            status="failed",
            steps=[
                {
                    "type": "click",
                    "label": "Place Order",
                    "locator": "#place-order",
                    "url": "http://localhost:8781/checkout.html",
                    "result": {"status": "passed"},
                },
                {
                    "type": "assertion",
                    "label": "order success message",
                    "locator": "#order-error",
                    "url": "http://localhost:8781/checkout.html",
                    "result": {
                        "status": "failed",
                        "error": "AssertionError: expected 'Your order has been placed' but got 'Payment failed'",
                    },
                },
            ],
        )
        result = learn_from_evidence_sidecars(tmp_path, store=store)
        assert result["negatives_inserted"] == 1
        neg_pattern = store.upsert_negative_pattern.call_args.args[0]
        assert neg_pattern.locator == "#order-error"
        assert neg_pattern.source == "learned_negative"
        assert neg_pattern.action_type == "ASSERT"
        assert neg_pattern.description == "order success message"
        assert neg_pattern.confidence == 0.6  # weaker than a hard locator timeout

    def test_resolved_but_wrong_requires_resolved_selector(self, tmp_path: Path) -> None:
        """An assertion failure with NO resolved locator cannot be a negative:
        there is no element to down-weight."""
        store = MagicMock()
        store.upsert_negative_pattern.return_value = ("inserted", 1)
        self._write_sidecar(
            tmp_path,
            "test_failed_selectorless",
            status="failed",
            steps=[
                {
                    "type": "assertion",
                    "label": "page loaded",
                    "locator": "",
                    "url": "http://localhost:8781/x.html",
                    "result": {
                        "status": "failed",
                        "error": "AssertionError: expected page title",
                    },
                }
            ],
        )
        result = learn_from_evidence_sidecars(tmp_path, store=store)
        assert result["negatives_inserted"] == 0
        store.upsert_negative_pattern.assert_not_called()

    def test_infra_flake_never_becomes_negative(self, tmp_path: Path) -> None:
        """AI-063 guard: infra/unknown failures (not assertion, not locator)
        must never enter the negative store — precision is everything."""
        store = MagicMock()
        store.upsert_negative_pattern.return_value = ("inserted", 1)
        self._write_sidecar(
            tmp_path,
            "test_infra_flake",
            status="failed",
            steps=[
                {
                    "type": "navigate",
                    "label": "Navigate to http://localhost:8781/x.html",
                    "locator": "",
                    "url": "http://localhost:8781/x.html",
                    "result": {
                        "status": "failed",
                        "error": "Connection refused: navigation timed out after 30000ms",
                    },
                }
            ],
        )
        result = learn_from_evidence_sidecars(tmp_path, store=store)
        assert result["negatives_inserted"] == 0
        store.upsert_negative_pattern.assert_not_called()
