"""Phase 6i — golden-key re-validation script, hermetic logic tests.

The script's browser/mock parts need network or chromium; CI-safe tests cover
the pure logic: OR (tolerance) semantics, stateful-page classification,
mock-origin rewriting, and report rendering.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "eval" / "revalidate_goldens.py"
_spec = importlib.util.spec_from_file_location("revalidate_goldens", _SCRIPT)
assert _spec and _spec.loader
R = importlib.util.module_from_spec(_spec)
sys.modules.setdefault("revalidate_goldens", R)
_spec.loader.exec_module(R)


# -- OR tolerance semantics ---------------------------------------------------


def _fake_page(found: set[str]) -> object:
    """Page stub: returns count>=1 for selectors in *found*, else 0."""

    class Page:
        def locator(self, sel: str) -> Page:
            self._sel = sel
            return self

        def count(self) -> int:
            return 1 if getattr(self, "_sel", "") in found else 0

    return Page()


def test_any_tolerance_matches_passes_golden() -> None:
    """Golden tolerance semantics are OR: one live selector is enough."""
    page = _fake_page({"[data-test='inventory-item']"})
    ok, missing = R._check_selectors_on_page(page, ["[data-test=old-stale]", "[data-test='inventory-item']"])
    assert ok is True
    assert missing == []


def test_none_match_reports_all_missing() -> None:
    page = _fake_page(set())
    ok, missing = R._check_selectors_on_page(page, ["#a", ".b"])
    assert ok is False
    assert missing == ["#a", ".b"]


def test_expect_snippet_skipped() -> None:
    """URL-assert style code snippets are never locator-checked."""
    page = _fake_page(set())
    ok, missing = R._check_selectors_on_page(page, ["expect(page).to_have_url"])
    assert ok is False
    assert missing == []  # snippet ignored, no decay reported


# -- stateful classification ---------------------------------------------------


def _ds(dataset_id: str) -> dict:
    return {"id": dataset_id, "site": "x", "base_url": "http://localhost:8781", "golden_resolutions": []}


def test_stateful_path_classification() -> None:
    assert (
        R._is_stateful_golden(
            _ds("eval-006"), {"expected_page": "http://localhost:8781/cart.html", "description": "cart page title"}
        )
        is True
    )
    assert (
        R._is_stateful_golden(
            _ds("eval-007"), {"expected_page": "http://localhost:8781/dashboard.html", "description": "sign in button"}
        )
        is True
    )
    # Stateless page on the same dataset → not stateful.
    assert (
        R._is_stateful_golden(
            _ds("eval-006"), {"expected_page": "http://localhost:8781/index.html", "description": "home page loaded"}
        )
        is False
    )


def test_stateful_description_rule() -> None:
    # demoqa renders the confirmation only after submit.
    assert (
        R._is_stateful_golden(
            _ds("eval-003"), {"expected_page": "https://demoqa.com/x", "description": "Submission success message"}
        )
        is True
    )


# -- mock-origin rewriting ----------------------------------------------------


def test_rewrite_mock_expected_pages_with_path_base_url() -> None:
    """A mock dataset whose base_url carries a path must still rewrite."""
    ds = {
        "id": "eval-010",
        "base_url": "http://localhost:8781/index.html",
        "golden_resolutions": [
            {"criterion_index": 0, "placeholders": [{"expected_page": "http://localhost:8781/success.html"}]}
        ],
    }
    out = R._rewrite_mock_expected_pages(ds, old_origin="http://localhost:8781", new_origin="http://localhost:8791")
    assert out["golden_resolutions"][0]["placeholders"][0]["expected_page"] == "http://localhost:8791/success.html"


def test_origin_of_strips_path() -> None:
    assert R._origin_of("http://localhost:8781/index.html") == "http://localhost:8781"
    assert R._origin_of("https://www.saucedemo.com?x=1") == "https://www.saucedemo.com"


def test_report_shape() -> None:
    records = [
        {
            "dataset_id": "eval-001",
            "site": "saucedemo",
            "status": "ok",
            "goldens_matched": 6,
            "goldens_checked": 6,
            "stateful_skipped": 14,
            "missing": [],
        },
        {
            "dataset_id": "eval-005",
            "site": "lv_insurance",
            "status": "static-only",
            "goldens_matched": None,
            "goldens_checked": 24,
            "missing": [],
        },
        {
            "dataset_id": "eval-002",
            "site": "x",
            "status": "fail",
            "goldens_matched": 5,
            "goldens_checked": 6,
            "stateful_skipped": 0,
            "missing": [{"description": "la", "expected_page": "u", "missing_selectors": ["#x"]}],
        },
    ]
    text = R.render_report(records)
    assert "eval-001" in text and "eval-005" in text and "eval-002" in text
    assert "stateful-skipped" in text
