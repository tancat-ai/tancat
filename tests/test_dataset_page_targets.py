"""Scrape-backed check of the CLICK rows' pages (t-1303 steps 2-3, t-1343).

The static schema gate (`golden_validator.check_page_schema`) can see that a
CLICK *has* a target page. It cannot see whether that page is the one holding
the control - the defect step 2 corrected (eval-007 c1/c3/c4/c6x2, eval-008
c1/c4/c7 pointed at the page the click LANDS on).

This reads the **committed** captures under `fixtures/scraped_pages/` - the
banking mock this repository serves itself - and asks the question the gate
cannot: for a mock CLICK, is the locator on the page its target names, and is its
outcome page one we have a capture of?

Two boundaries, both deliberate (t-1343):

* Only the mock's captures are committed. Captures of third-party pages
  (saucedemo, automationexercise, demoqa, the-internet) are not ours to
  republish, stay in the gitignored `scripts/eval/scraped_pages/`, and are not
  evidence a test may rest on - CI cannot see them. Rows on those sites are
  counted as **outside the committed evidence**, never silently "checked".
* A capture that is missing is a **failure that names the file**. A check that
  finds nothing must say so; that is the fault this job exists to remove.

Deciding a mock target, in the order the owner set (2026-11-05):

1. **A unique capture** settles it: exactly one captured page holds the locator.
2. **The trail** settles a locator that sits on several pages (a nav link is on
   most pages of a real site, which is why uniqueness alone blocked eval-007 c3
   `#transfer-link`): a CLICK's target is the page the walk is on when it gets
   there - the page of the step immediately before it in the story.
3. Otherwise it is **unsettled** and this suite fails.
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
#: The committed captures: the mock this repository serves itself.
SCRAPED = _EVAL_DIR.parent.parent / "fixtures" / "scraped_pages"
MOCK_SITE = "http://localhost:8781"

#: The five mock pages the eight corrected rows rest on. A missing one is a
#: failure that names it.
REQUIRED_MOCK_PAGES = (
    "index.html",
    "dashboard.html",
    "transfer.html",
    "payments.html",
    "transfer_success.html",
)


def _pages(directory: Path = SCRAPED) -> dict[str, dict]:
    """Every page captured in *directory*, keyed by its URL.

    Fails, naming the file, when the directory or one of the required mock pages
    is absent - an empty mapping would read as "nothing to check" and let the
    suite pass while proving nothing.
    """
    if not directory.is_dir():
        raise AssertionError(f"no capture directory at {directory} - the mock captures are committed there")
    expected = [f"http_localhost_8781_{name}.json" for name in REQUIRED_MOCK_PAGES]
    missing_files = [name for name in expected if not (directory / name).is_file()]
    assert missing_files == [], f"capture files missing from {directory}: {missing_files}"
    pages: dict[str, dict] = {}
    for path in sorted(directory.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "elements" in data and data.get("url"):
            pages[str(data["url"]).rstrip("/")] = data
    missing_pages = [name for name in REQUIRED_MOCK_PAGES if f"{MOCK_SITE}/{name}" not in pages]
    assert missing_pages == [], f"captures present but their URLs are missing: {missing_pages}"
    return pages


def _walk(dataset_dir: Path = DATASET) -> list[tuple[str, int, dict, str, str, str]]:
    """Every placeholder in story order: (story, criterion, row, trail page, base_url).

    The trail is the story's own order: the last page a step named. That is the
    product's previous-landing idea, and it is what decides a CLICK whose locator
    sits on more than one page.
    """
    walked: list[tuple[str, int, dict, str, str, str]] = []
    for path in sorted(dataset_dir.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        current = ""
        base_url = str(data.get("base_url") or "")
        site = str(data.get("site") or "")
        for crit in data["golden_resolutions"]:
            for ph in crit["placeholders"]:
                walked.append((str(data["id"]), int(crit["criterion_index"]), ph, current, base_url, site))
                current = str(ph.get("target_page") or ph.get("outcome_page") or "") or current
    return walked


def _clicks(dataset_dir: Path = DATASET) -> list[tuple[str, int, dict, str, str, str]]:
    return [row for row in _walk(dataset_dir) if row[2].get("action") == "CLICK"]


def _holds(page: dict, locator: str) -> bool:
    """Whether the captured page holds this locator.

    Only the shapes a capture can express are matched: an id selector, an exact
    CSS selector, or a ``text=`` / ``button:has-text`` phrase.
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


def _in_scope(row: tuple[str, int, dict, str, str, str]) -> bool:
    """Whether the committed captures can speak for this row.

    They are the banking mock's pages (`site: banking_mock`, served on :8781).
    Rows on any other site - the third-party pages and the other localhost mocks
    (eval-005/006/010) whose captures are simply not committed - are outside the
    committed evidence: counted, not passed and not failed.
    """
    base_url, site = row[4] or "", row[5] or ""
    return site == "banking_mock" and base_url.startswith("http://localhost:8781")


def decide(dataset_dir: Path = DATASET, directory: Path = SCRAPED) -> dict[str, Any]:
    """Run the target decision over a dataset directory.

    Returns the rows settled each way, the rows outside the committed evidence,
    and the rows that fail either rule.
    """
    pages = _pages(directory)
    violations: list[str] = []
    unsettled: list[str] = []
    counts = {"unique": 0, "trail": 0, "outside": 0}
    for row in _clicks(dataset_dir):
        story, crit, ph, trail_page, _base_url, _site = row
        locator = str(ph.get("expected_locator") or "")
        target = str(ph.get("target_page") or "").rstrip("/")
        if not _in_scope(row):
            counts["outside"] += 1
            continue
        holders = _holders(locator, pages)
        if len(holders) == 1:
            want = holders[0]
            counts["unique"] += 1
        elif len(holders) > 1:
            want = str(trail_page or "").rstrip("/")
            if not want or want not in holders:
                unsettled.append(_row_name(story, crit, ph))
                continue
            counts["trail"] += 1
        else:
            # On the mock site, so a capture *should* hold it: this is a finding.
            unsettled.append(f"{_row_name(story, crit, ph)}: no mock capture holds it")
            continue
        if target != want:
            violations.append(f"{_row_name(story, crit, ph)}: target {target} != {want}")
    return {**counts, "violations": violations, "unsettled": unsettled}


class TestClickTargets:
    def test_every_mock_click_target_is_decided_and_correct(self) -> None:
        result = decide()
        assert result["unsettled"] == [], f"neither a unique capture nor the trail settles: {result['unsettled']}"
        assert result["violations"] == [], f"a CLICK target is not the page that holds it: {result['violations']}"
        # Of the 36 CLICK rows: the 8 on the banking mock are decided here - 7 by a
        # unique capture and 1 (#transfer-link) by the trail - and the other 28 are
        # outside the committed evidence. That is not one thing: 16 sit on
        # third-party pages (captures not ours to publish) and 12 on local mocks
        # (eval-005/006/010) whose captures were never taken. Both are counted the
        # same way, and the README says so.
        assert (result["unique"], result["trail"], result["outside"]) == (7, 1, 28), result

    def test_the_nav_link_is_settled_by_the_trail_not_by_uniqueness(self) -> None:
        """eval-007 c3 `#transfer-link` is on two captured mock pages."""
        pages = _pages()
        holders = sorted(h.rsplit("/", 1)[-1] for h in _holders("#transfer-link", pages))
        assert holders == ["account.html", "dashboard.html"]
        row = next(
            r for r in _clicks() if r[0] == "eval-007" and r[1] == 3 and r[2]["expected_locator"] == "#transfer-link"
        )
        assert row[3] == "http://localhost:8781/dashboard.html"
        assert row[2]["target_page"] == "http://localhost:8781/dashboard.html"

    def test_every_mock_click_outcome_is_a_captured_page(self) -> None:
        pages = _pages()
        missing = [
            _row_name(story, crit, ph)
            for row in _clicks()
            if _in_scope(row)
            for story, crit, ph, _trail, _base, _site in (row,)
            if str(ph.get("outcome_page") or "").rstrip("/") and str(ph["outcome_page"]).rstrip("/") not in pages
        ]
        assert missing == [], f"a mock CLICK names an outcome page nobody captured: {missing}"

    def test_a_missing_capture_directory_fails_and_names_it(self, tmp_path: Path) -> None:
        empty = tmp_path / "no-captures"
        empty.mkdir()
        with pytest.raises(AssertionError) as excinfo:
            _pages(empty)
        assert "capture files missing" in str(excinfo.value)
        assert "dashboard.html" in str(excinfo.value) or "index.html" in str(excinfo.value)

        with pytest.raises(AssertionError) as excinfo:
            _pages(tmp_path / "absent")
        assert "no capture directory" in str(excinfo.value)


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
        data = json.loads(next(DATASET.glob(f"{story}_*.json")).read_text(encoding="utf-8"))
        row = next(
            ph
            for c in data["golden_resolutions"]
            if int(c["criterion_index"]) == crit
            for ph in c["placeholders"]
            if ph.get("description") == description
        )
        expected = f"{MOCK_SITE}/{page}"
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
        from golden_validator import check_page_schema  # noqa: PLC0415

        assert check_page_schema(data) == []
