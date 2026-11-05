"""Scrape-backed check of the CLICK rows' pages (t-1303 steps 2-3).

The static schema gate (`golden_validator.check_page_schema`) can see that a
CLICK *has* a target page. It cannot see whether that page is the one holding
the control - the defect step 2 corrected (eval-007 c1/c3/c4/c6x2, eval-008
c1/c4/c7 pointed at the page the click LANDS on).

This reads the captures under `scripts/eval/scraped_pages/` and asks the question
the gate cannot: for a CLICK whose target page was captured, is the locator on
that page? And is its outcome page a captured page?

Deciding a target, in the order the owner set (2026-11-05):

1. **A unique capture** settles it: exactly one captured page holds the locator.
2. **The trail** settles a locator that sits on several pages. A nav link is on
   most pages of a real site, so uniqueness alone was too strict (it blocked
   eval-007 c3 `#transfer-link`, which is on account.html and dashboard.html).
   The product's own rule is used instead: a CLICK's target is the page the walk
   is on when it gets there - the page of the step immediately before it in the
   story.
3. Otherwise it is **unsettled** and this suite fails: neither rule decided it.

A locator that appears in no capture at all is not a wrong target, it is an
uncheckable row (a stale or missing capture); it is counted, not silently
dropped.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

_EVAL_DIR = Path(__file__).resolve().parent.parent / "scripts" / "eval"
sys.path.insert(0, str(_EVAL_DIR))

import pytest  # noqa: E402

DATASET = _EVAL_DIR / "dataset"
SCRAPED = _EVAL_DIR / "scraped_pages"


def _pages() -> dict[str, dict]:
    """Every captured page, keyed by its URL."""
    pages: dict[str, dict] = {}
    for path in sorted(SCRAPED.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "elements" in data and data.get("url"):
            pages[str(data["url"]).rstrip("/")] = data
    assert pages, "no scraped pages to check against"
    return pages


def _walk(dataset_dir: Path = DATASET) -> list[tuple[str, int, dict, str]]:
    """Every placeholder in story order, with the page the walk is on at it.

    The trail is the story's own order: the last page a step named (its target
    for an element row, its outcome for a navigation). That is the product's
    previous-landing idea and it is what the owner's rule says decides a CLICK
    whose locator sits on more than one page. It is carried alongside the row so
    no caller has to re-identify a dict.
    """
    walked: list[tuple[str, int, dict, str]] = []
    for path in sorted(dataset_dir.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        current = ""
        for crit in data["golden_resolutions"]:
            for ph in crit["placeholders"]:
                walked.append((str(data["id"]), int(crit["criterion_index"]), ph, current))
                current = str(ph.get("target_page") or ph.get("outcome_page") or "") or current
    return walked


def _clicks(dataset_dir: Path = DATASET) -> list[tuple[str, int, dict, str]]:
    return [row for row in _walk(dataset_dir) if row[2].get("action") == "CLICK"]


def _holds(page: dict, locator: str) -> bool:
    """Whether the captured page holds this locator.

    Only the shapes a capture can express are matched: an id selector, an exact
    CSS selector, or a ``text=`` / ``button:has-text`` phrase. A Playwright-only
    construction that a capture never records is simply not found - which is why
    a locator absent from every capture is counted as uncheckable.
    """
    locator = locator.strip()
    elements = page.get("elements", [])
    if locator.startswith("#") and " " not in locator:
        return any(e.get("id") == locator[1:] or e.get("selector") == locator for e in elements)
    if locator.startswith("text="):
        want = locator[5:].strip().strip('"').lower()
        return any(want in str(e.get("text") or "").lower() for e in elements)
    if ":has-text(" in locator:
        want = locator.split(":has-text(", 1)[1].rstrip(")").strip().strip("\"'").lower()
        return any(want in str(e.get("text") or "").lower() for e in elements)
    return any(e.get("selector") == locator for e in elements)


def _holders(locator: str, pages: dict[str, dict]) -> list[str]:
    return [url for url, page in pages.items() if _holds(page, locator)]


def _row_name(story: str, crit: int, ph: dict) -> str:
    return f"{story} c{crit} {ph.get('expected_locator')}"


def decide(dataset_dir: Path = DATASET) -> dict[str, Any]:
    """Run the target decision over a dataset directory.

    Returns the rows settled each way and the rows that fail either rule, so a
    caller (or the negative test) can see what a swapped page does.
    """
    pages = _pages()
    violations: list[str] = []
    unsettled: list[str] = []
    counts = {"unique": 0, "trail": 0, "uncheckable": 0}
    for story, crit, ph, trail_page in _clicks(dataset_dir):
        locator = str(ph.get("expected_locator") or "")
        target = str(ph.get("target_page") or "").rstrip("/")
        holders = _holders(locator, pages)
        if not holders:
            counts["uncheckable"] += 1
            continue
        if len(holders) == 1:
            want = holders[0]
            counts["unique"] += 1
        else:
            want = str(trail_page or "").rstrip("/")
            if not want or want not in holders:
                unsettled.append(_row_name(story, crit, ph))
                continue
            counts["trail"] += 1
        if target != want:
            violations.append(f"{_row_name(story, crit, ph)}: target {target} != {want}")
    decided: dict[str, Any] = dict(counts)
    decided["violations"] = violations
    decided["unsettled"] = unsettled
    return decided


class TestClickTargets:
    def test_every_click_target_is_decided_and_correct(self) -> None:
        pages = _pages()
        by_unique = by_trail = uncheckable = 0
        violations: list[str] = []
        unsettled: list[str] = []
        for story, crit, ph, trail_page in _clicks():
            locator = str(ph.get("expected_locator") or "")
            target = str(ph.get("target_page") or "").rstrip("/")
            holders = _holders(locator, pages)
            if not holders:
                uncheckable += 1
                continue
            if len(holders) == 1:
                want = holders[0]
                by_unique += 1
            else:
                # A locator on several pages: the trail decides, never a guess.
                want = str(trail_page or "").rstrip("/")
                if not want or want not in holders:
                    unsettled.append(_row_name(story, crit, ph))
                    continue
                by_trail += 1
            if target != want:
                violations.append(f"{_row_name(story, crit, ph)}: target {target} != {want}")
        assert by_unique + by_trail >= 8, (
            f"only {by_unique + by_trail} CLICK rows were decided - the check has gone blind"
        )
        assert unsettled == [], f"neither a unique capture nor the trail settles: {unsettled}"
        assert violations == [], f"a CLICK target is not the page that holds it: {violations}"
        # Counts are pinned so a shrinking check is visible. Of the 36 CLICK
        # rows: 14 are settled by a unique capture, 7 by the trail (their
        # locator sits on more than one captured page), and 15 are uncheckable
        # because no capture holds their locator (stale or missing captures).
        assert (by_unique, by_trail, uncheckable) == (14, 7, 15), (by_unique, by_trail, uncheckable)

    def test_the_nav_link_is_settled_by_the_trail_not_by_uniqueness(self) -> None:
        """eval-007 c3 `#transfer-link` is on two captured pages."""
        pages = _pages()
        holders = sorted(h.rsplit("/", 1)[-1] for h in _holders("#transfer-link", pages))
        assert holders == ["account.html", "dashboard.html"]
        story, crit, row, trail_page = next(
            r for r in _clicks() if r[0] == "eval-007" and r[1] == 3 and r[2]["expected_locator"] == "#transfer-link"
        )
        assert trail_page == "http://localhost:8781/dashboard.html"
        assert row["target_page"] == "http://localhost:8781/dashboard.html"

    def test_every_recorded_click_outcome_is_a_captured_page(self) -> None:
        pages = _pages()
        missing = [
            _row_name(story, crit, ph)
            for story, crit, ph, _trail in _clicks()
            if str(ph.get("outcome_page") or "").rstrip("/") and str(ph["outcome_page"]).rstrip("/") not in pages
        ]
        assert missing == [], f"a CLICK names an outcome page nobody captured: {missing}"


class TestTheCorrectedRows:
    """Every corrected row points at the page that holds the control."""

    @pytest.mark.parametrize(
        ("story", "crit", "description", "page"),
        [
            ("eval-007", 1, "sign in button", "index.html"),
            ("eval-007", 3, "Transfer Money link", "dashboard.html"),
            ("eval-007", 4, "Transfer Funds button", "transfer.html"),
            ("eval-007", 6, "Pay a Bill link", "dashboard.html"),
            ("eval-007", 6, "Pay Bill button", "payments.html"),
            ("eval-008", 1, "sign in button", "index.html"),
            ("eval-008", 4, "Transfer Funds button", "transfer.html"),
            ("eval-008", 7, "Pay Bill button", "payments.html"),
        ],
    )
    def test_target_is_the_page_holding_the_locator(self, story: str, crit: int, description: str, page: str) -> None:
        data = json.loads((next(DATASET.glob(f"{story}_*.json"))).read_text(encoding="utf-8"))
        row = next(
            ph
            for c in data["golden_resolutions"]
            if int(c["criterion_index"]) == crit
            for ph in c["placeholders"]
            if ph.get("description") == description
        )
        expected = f"http://localhost:8781/{page}"
        assert row["target_page"] == expected
        assert _holds(_pages()[expected], row["expected_locator"])
        # the arrival the click really has lives in outcome_page, and is captured
        assert row["outcome_page"].rstrip("/") in _pages()


class TestTheNegativeCase:
    """Swap two target pages and the scrape-backed check must name both rows.

    This is the check the *static* schema gate cannot make: a swapped page
    leaves every row schema-valid (both pages are non-empty URLs), so only the
    capture decides it. The test asserts both halves, because "the gate catches
    it" would be false for `check_page_schema`.
    """

    def test_a_swap_between_two_pages_is_caught_by_name(self, tmp_path: Path) -> None:
        import json as _json
        import shutil

        copy = tmp_path / "dataset"
        shutil.copytree(DATASET, copy)
        # Two CLICK rows with different captured targets: eval-007 c1 'sign in
        # button' (index.html) and eval-007 c4 'Transfer Funds button' (transfer.html).
        path = next(copy.glob("eval-007_*.json"))
        data = _json.loads(path.read_text(encoding="utf-8"))

        def _row(crit_index: int, description: str) -> dict:
            return next(
                ph
                for c in data["golden_resolutions"]
                if c["criterion_index"] == crit_index
                for ph in c["placeholders"]
                if ph["description"] == description
            )

        sign_in, transfer = _row(1, "sign in button"), _row(4, "Transfer Funds button")
        sign_in["target_page"], transfer["target_page"] = transfer["target_page"], sign_in["target_page"]
        path.write_text(_json.dumps(data, indent=2), encoding="utf-8")

        result = decide(copy)

        joined = "\n".join(result["violations"])
        assert "eval-007 c1 #login-button" in joined, joined
        assert "eval-007 c4 #transfer-submit" in joined, joined
        assert len(result["violations"]) == 2, result["violations"]

        # ... and the static gate cannot see it: every swapped row is still valid.
        import sys as _sys

        _sys.path.insert(0, str(_EVAL_DIR))
        from golden_validator import check_page_schema

        assert check_page_schema(data) == []
