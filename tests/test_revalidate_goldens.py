"""Phase 6i — golden-key re-validation script, hermetic logic tests.

The script's browser/mock parts need network or chromium; CI-safe tests cover
the pure logic: OR (tolerance) semantics, stateful-page classification,
mock-origin rewriting, and report rendering.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

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
            _ds("eval-006"), {"target_page": "http://localhost:8781/cart.html", "description": "cart page title"}
        )
        is True
    )
    assert (
        R._is_stateful_golden(
            _ds("eval-007"), {"target_page": "http://localhost:8781/dashboard.html", "description": "sign in button"}
        )
        is True
    )
    # Stateless page on the same dataset → not stateful.
    assert (
        R._is_stateful_golden(
            _ds("eval-006"), {"target_page": "http://localhost:8781/index.html", "description": "home page loaded"}
        )
        is False
    )


def test_stateful_description_rule() -> None:
    # demoqa renders the confirmation only after submit.
    assert (
        R._is_stateful_golden(
            _ds("eval-003"), {"target_page": "https://demoqa.com/x", "description": "Submission success message"}
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
            {"criterion_index": 0, "placeholders": [{"target_page": "http://localhost:8781/success.html"}]}
        ],
    }
    out = R._rewrite_mock_expected_pages(ds, old_origin="http://localhost:8781", new_origin="http://localhost:8791")
    assert out["golden_resolutions"][0]["placeholders"][0]["target_page"] == "http://localhost:8791/success.html"


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
            "missing": [{"description": "la", "target_page": "u", "missing_selectors": ["#x"]}],
        },
    ]
    text = R.render_report(records)
    assert "eval-001" in text and "eval-005" in text and "eval-002" in text
    assert "stateful-skipped" in text


# -- t-1303 step 3: the three checks, and the end of the STATEFUL_PATHS skip --

BANK = "http://localhost:8781"


class _GotoPage:
    """Page stub with a URL, visited history and per-URL selectors."""

    def __init__(self, selectors: dict[str, set[str]], redirects: dict[str, str] | None = None) -> None:
        self.selectors = {k.rstrip("/"): v for k, v in selectors.items()}
        self.redirects = {k.rstrip("/"): v for k, v in (redirects or {}).items()}
        self.url = ""
        self.visited: list[str] = []

    def set_default_timeout(self, _ms: int) -> None:
        return None

    def goto(self, url: str, timeout: int | None = None, wait_until: str | None = None) -> None:
        self.url = self.redirects.get(url.rstrip("/"), url)
        self.visited.append(self.url)

    def locator(self, sel: str) -> object:
        found = self.selectors.get(self.url.rstrip("/"), set())

        class _Loc:
            def count(self) -> int:
                return 1 if sel in found else 0

        return _Loc()


def _row(action: str, description: str, locator: str, target: str, outcome: str = "", **extra: object) -> dict:
    return {
        "action": action,
        "description": description,
        "expected_locator": locator,
        "tolerance_selectors": [],
        "target_page": target,
        "outcome_page": outcome,
        **extra,
    }


def _dataset(*rows: dict, kind: str = "element", dataset_id: str = "eval-007") -> dict:
    return {
        "id": dataset_id,
        "site": "banking_mock",
        "base_url": f"{BANK}/index.html",
        "golden_resolutions": [{"criterion_index": 0, "criterion_kind": kind, "placeholders": list(rows)}],
    }


def test_a_schema_violation_is_reported_and_not_checked() -> None:
    """The static gate runs first: a row with the retired field is not judged."""
    page = _GotoPage({f"{BANK}/index.html": {"#login-button"}})
    ds = _dataset(
        {
            "action": "CLICK",
            "description": "sign in",
            "expected_locator": "#login-button",
            "expected_page": f"{BANK}/index.html",
        }
    )
    record = R._check_live_dataset(ds, page=page, timeout_s=1)
    assert record["status"] == "fail"
    assert any("retired field" in str(m.get("schema") or "") for m in record["missing"])
    assert page.visited == [], "a schema-invalid row must not be driven through the browser"


def test_target_check_reports_a_locator_missing_from_its_page() -> None:
    page = _GotoPage({f"{BANK}/index.html": set()})
    ds = _dataset(_row("CLICK", "sign in", "#login-button", f"{BANK}/index.html"))
    record = R._check_live_dataset(ds, page=page, timeout_s=1)
    assert record["status"] == "fail"
    assert record["missing"][0]["target_page"] == f"{BANK}/index.html"
    assert "#login-button" in record["missing"][0]["missing_selectors"]


def test_outcome_page_check_reports_where_the_browser_landed() -> None:
    page = _GotoPage({f"{BANK}/cart.html": set()}, redirects={f"{BANK}/cart.html": f"{BANK}/index.html"})
    ds = _dataset(
        _row(
            "ASSERT",
            "cart loaded",
            f'expect(page).to_have_url("{BANK}/cart.html")',
            "",
            f"{BANK}/cart.html",
            expected_type="url_assertion",
        ),
        kind="page",
    )
    record = R._check_live_dataset(ds, page=page, timeout_s=1)
    assert record["status"] == "fail"
    assert record["missing"][0]["outcome_page"] == f"{BANK}/cart.html"
    assert record["missing"][0]["actual_url"] == f"{BANK}/index.html"


def test_outcome_element_check_checks_the_locator_on_the_outcome_page() -> None:
    page = _GotoPage({f"{BANK}/index.html": {"#login-button"}, f"{BANK}/cart.html": set()})
    ds = _dataset(_row("ASSERT", "login button present", "#login-button", f"{BANK}/index.html", f"{BANK}/cart.html"))
    record = R._check_live_dataset(ds, page=page, timeout_s=1)
    assert record["status"] == "fail"
    assert record["missing"][0]["outcome_page"] == f"{BANK}/cart.html"
    assert page.visited == [f"{BANK}/index.html", f"{BANK}/cart.html"]


def test_a_stateful_row_is_checked_against_its_capture_not_skipped() -> None:
    """The STATEFUL_PATHS skip is gone: the banking row is checked, offline."""
    captures = R.load_captures()
    assert f"{BANK}/dashboard.html" in captures
    page = _GotoPage({})
    ds = _dataset(
        _row("CLICK", "Transfer Money link", "#transfer-link", f"{BANK}/dashboard.html", f"{BANK}/transfer.html")
    )
    record = R._check_live_dataset(ds, page=page, timeout_s=1, captures=captures)
    assert record["stateful_skipped"] == 0, "a captured stateful row must not be skipped"
    assert record["stateful_checked_from_capture"][0]["status"] == "ok"
    assert record["goldens_matched"] == 1
    assert page.visited == [], "the capture settles it - no browser needed"


def test_a_stateful_row_with_no_capture_is_reported_as_unproven() -> None:
    page = _GotoPage({})
    ds = _dataset(_row("CLICK", "Transfer Money link", "#transfer-link", f"{BANK}/dashboard.html"))
    record = R._check_live_dataset(ds, page=page, timeout_s=1, captures={})
    assert record["goldens_checked"] == 0
    assert record["stateful_skipped"] == 1
    assert "needs a session" in record["stateful_needs_session"][0]["reason"]


def test_a_capture_that_lacks_the_locator_is_a_missing_finding() -> None:
    captures = {f"{BANK}/dashboard.html": {"url": f"{BANK}/dashboard.html", "elements": []}}
    ds = _dataset(_row("CLICK", "Transfer Money link", "#transfer-link", f"{BANK}/dashboard.html"))
    record = R._check_live_dataset(ds, page=_GotoPage({}), timeout_s=1, captures=captures)
    assert record["status"] == "fail"
    assert record["missing"][0]["basis"] == "capture"
    assert "#transfer-link" in record["missing"][0]["missing_selectors"]


def test_a_missing_capture_directory_fails_and_names_it(tmp_path: Path) -> None:
    """t-1343: the captures are committed; their absence is a failure, not a skip."""
    with pytest.raises(FileNotFoundError) as excinfo:
        R.load_captures(tmp_path / "no-such-captures")
    assert "no capture directory" in str(excinfo.value)
    assert "fixtures/scraped_pages" in str(excinfo.value)


def test_the_committed_captures_are_the_banking_mock_pages() -> None:
    """The five pages the eight corrected rows rest on are in the repository."""
    captures = R.load_captures()
    for name in ("index", "dashboard", "transfer", "payments", "transfer_success"):
        assert f"http://localhost:8781/{name}.html" in captures, name
    assert str(R.CAPTURES_DIR).replace("\\", "/").endswith("fixtures/scraped_pages")


# -- j-0293: the printed summary must not fuse a capture pass into a live one --


def test_the_summary_prints_live_and_capture_counts_separately() -> None:
    """One live-style row and one capture row: the reader sees two numbers."""
    records = [
        {
            "dataset_id": "eval-008",
            "site": "banking_mock",
            "status": "ok",
            "goldens_matched": 5,
            "goldens_checked": 5,
            "stateful_checked_from_capture": [
                {"description": "a", "status": "ok"},
                {"description": "b", "status": "ok"},
            ],
            "missing": [],
        },
        {
            "dataset_id": "eval-001",
            "site": "saucedemo",
            "status": "ok",
            "goldens_matched": 3,
            "goldens_checked": 4,
            "stateful_checked_from_capture": [],
            "missing": [],
        },
    ]

    text = R.render_report(records)

    capture_line = next(line for line in text.splitlines() if "eval-008" in line)
    assert "3/3 live" in capture_line, capture_line
    assert "2/2 by capture" in capture_line, capture_line
    assert "3/3 goldens" not in capture_line, "the row still prints one fused total"
    live_line = next(line for line in text.splitlines() if "eval-001" in line)
    assert "3/4 live" in live_line and "capture" not in live_line
    assert "frozen capture" in text  # the note that says what "by capture" means


def test_a_capture_only_row_prints_no_live_count_that_includes_them() -> None:
    """Every match came from the frozen capture: the live count must read 0."""
    records = [
        {
            "dataset_id": "eval-008",
            "site": "banking_mock",
            "status": "ok",
            "goldens_matched": 3,
            "goldens_checked": 3,
            "stateful_checked_from_capture": [
                {"description": "a", "status": "ok"},
                {"description": "b", "status": "ok"},
                {"description": "c", "status": "ok"},
            ],
            "missing": [],
        }
    ]

    text = R.render_report(records)
    line = next(line for line in text.splitlines() if "eval-008" in line)

    assert "0/0 live" in line, line
    assert "3/3 by capture" in line, line
    assert "3/3 live" not in line, "a capture pass was printed as a live pass"
    assert "capture-only" in line, "the status still reads as a live ok"


# -- j-0293 follow-up: the stored record must say what its numbers rest on ----


def test_a_capture_settled_record_stores_its_basis_not_a_live_pass() -> None:
    """Stored status "ok" alone read as a live pass; the record now says capture."""
    record = R._check_live_dataset(
        _dataset(
            _row("CLICK", "Transfer Money link", "#transfer-link", f"{BANK}/dashboard.html", f"{BANK}/transfer.html")
        ),
        page=_GotoPage({}),
        timeout_s=1,
        captures=R.load_captures(),
    )

    assert record["basis"] == "capture", f"the record does not say what settled it: {record.get('basis')!r}"
    assert record["kind"] == "capture", f"kind still names the path that ran, not the evidence: {record['kind']!r}"
    assert record["status"] == "ok"  # the stored status stays a stable machine value


def test_a_mixed_record_says_live_and_capture() -> None:
    """One stateful row from a capture, one ordinary row from the served page."""
    captures = R.load_captures()
    ds = _dataset(
        _row("CLICK", "Transfer Money link", "#transfer-link", f"{BANK}/dashboard.html", f"{BANK}/transfer.html"),
        _row("CLICK", "Login button", "#login-button", f"{BANK}/index.html"),
    )
    page = _GotoPage({f"{BANK}/index.html": {"#login-button"}})

    record = R._check_live_dataset(ds, page=page, timeout_s=1, captures=captures)

    assert record["goldens_checked"] == 2
    assert record["basis"] == "live+capture", record["basis"]
    assert record["kind"] == "live+capture", record["kind"]


def test_a_live_only_record_still_says_live() -> None:
    record = R._check_live_dataset(
        _dataset(_row("CLICK", "Login button", "#login-button", f"{BANK}/index.html")),
        page=_GotoPage({f"{BANK}/index.html": {"#login-button"}}),
        timeout_s=1,
        captures=R.load_captures(),
    )
    assert record["basis"] == "live", record["basis"]
    assert record["kind"] == "live", record["kind"]
