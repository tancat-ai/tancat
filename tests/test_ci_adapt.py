"""Verified adaptation engine tests (Phase 7b, spec §9.6).

Offline: parsing, source-step location, patching, and the full
keep-or-revert decision loop run against a synthetic package with the
scrape + pytest subprocess stubbed (no browser, no Docker). The real-browser
loop is exercised hermetically by the Docker self-test and the workflow.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

import action.adapt as adapt
from action.adapt import (
    adapt_package,
    find_replacement_locator,
    find_source_steps,
    parse_failure,
    patch_locator,
)

# ---------------------------------------------------------------------------
# Failure-message parsing
# ---------------------------------------------------------------------------


def test_parse_failure_extracts_locator_and_action() -> None:
    parsed = parse_failure("Timeout 3000ms exceeded. waiting for locator('a[href=\"/nope\"]')")
    assert parsed == {"locator": 'a[href="/nope"]', "action": "CLICK"}
    parsed_fill = parse_failure("locator.fill: waiting for locator('#email')")
    assert parsed_fill == {"locator": "#email", "action": "FILL"}
    parsed_assert = parse_failure("expect(locator('h2')).to_be_visible: waiting for locator('h2')")
    assert parsed_assert == {"locator": "h2", "action": "ASSERT"}


def test_parse_failure_non_locator_is_none() -> None:
    assert parse_failure("AssertionError: expected text to be visible") is None
    assert parse_failure("") is None


def test_parse_failure_tracker_error_format() -> None:
    """evidence_tracker's own fast-fail message (src/evidence_tracker.py)."""
    msg = (
        "src.evidence_tracker._LocatorNotFoundError: Locator 'a[href=\"/bogus.html\"]' not found on "
        "current page (http://127.0.0.1:8781/index.html). The element exists on a different page."
    )
    parsed = parse_failure(msg)
    assert parsed == {"locator": 'a[href="/bogus.html"]', "action": "CLICK"}


def test_parse_failure_tracker_fill_format() -> None:
    msg = "Locator '#email' not found on current page (http://x)."
    parsed = parse_failure(msg)
    assert parsed is not None
    assert parsed["locator"] == "#email"


# ---------------------------------------------------------------------------
# Source-step discovery
# ---------------------------------------------------------------------------


def _package(tmp_path: Path) -> Path:
    pkg = tmp_path / "test_pkg"
    (pkg / "pages").mkdir(parents=True)
    (pkg / "pages" / "home_page.py").write_text(
        "from playwright.sync_api import Page\n"
        "class HomePage:\n"
        "    def click_products(self):\n"
        "        self.tracker.click('a[href=\"/nope\"]', label='products')\n"
        "    def fill_email(self):\n"
        "        self.tracker.fill('#email', 'x', label='Email')\n"
        "    def check_visible(self):\n"
        "        self.tracker.assert_visible('h2', label='Product category listing page')\n",
        encoding="utf-8",
    )
    (pkg / "test_main.py").write_text(
        "def test_01(page):\n    page.locator('a[href=\"/nope\"]').click()\n",
        encoding="utf-8",
    )
    (pkg / "package_manifest.json").write_text(
        json.dumps({"starting_url": "http://127.0.0.1:9999/index.html"}), encoding="utf-8"
    )
    return pkg


def test_find_source_steps_locate_tracker_lines(tmp_path: Path) -> None:
    pkg = _package(tmp_path)
    steps = find_source_steps(pkg, 'a[href="/nope"]')
    assert len(steps) == 2
    tracker_step = next(s for s in steps if "tracker.click" in s.line)
    assert tracker_step.action == "CLICK"
    assert tracker_step.label == "products"
    page_step = next(s for s in steps if "page.locator" in s.line)
    assert page_step.action == "CLICK"


def test_patch_locator_only_changes_quoted_string(tmp_path: Path) -> None:
    pkg = _package(tmp_path)
    path = pkg / "pages" / "home_page.py"
    before = path.read_text(encoding="utf-8")
    n = patch_locator(str(path), 'a[href="/nope"]', 'a[href="/products.html"]')
    assert n == 1
    after = path.read_text(encoding="utf-8")
    assert 'a[href="/products.html"]' in after
    assert 'a[href="/nope"]' not in after
    assert before != after


def test_patch_locator_noop_when_absent(tmp_path: Path) -> None:
    pkg = _package(tmp_path)
    path = pkg / "pages" / "home_page.py"
    assert patch_locator(str(path), "ghost", "new") == 0
    assert patch_locator(str(path), 'a[href="/nope"]', 'a[href="/nope"]') == 0


def test_patch_locator_works_when_new_locator_already_present(tmp_path: Path) -> None:
    """The new locator may already exist elsewhere in the file (other steps use
    it) — that must not abort the patch of the failing occurrence."""
    pkg = _package(tmp_path)
    path = pkg / "pages" / "home_page.py"
    # Seed the file with a line that ALREADY uses the target locator.
    text = path.read_text(encoding="utf-8")
    path.write_text(
        text
        + "    def click_products_already(self):\n        self.tracker.click('a[href=\"/products.html\"]', label='products')\n",
        encoding="utf-8",
    )
    n = patch_locator(str(path), 'a[href="/nope"]', 'a[href="/products.html"]')
    assert n == 1
    after = path.read_text(encoding="utf-8")
    assert 'a[href="/nope"]' not in after
    assert after.count('a[href="/products.html"]') == 2


# ---------------------------------------------------------------------------
# Replacement resolution (scrape stubbed)
# ---------------------------------------------------------------------------


def _fake_elements() -> list[dict[str, object]]:
    return [
        {"selector": 'a[href="/products.html"]', "role": "link", "text": "Products", "tag": "a", "is_visible": True},
        {"selector": 'a[href="/cart.html"]', "role": "link", "text": "Cart", "tag": "a", "is_visible": True},
        {"selector": "#email", "role": "textbox", "text": "", "tag": "input", "is_visible": True},
        {"selector": "h2", "role": "heading", "text": "Product category listing page", "tag": "h2", "is_visible": True},
    ]


def test_find_replacement_locator_uses_scored_top(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(adapt, "scrape_elements", lambda url: _fake_elements())
    new = find_replacement_locator("http://x", "CLICK", "products", 'a[href="/nope"]')
    assert new == 'a[href="/products.html"]'


def test_find_replacement_locator_skips_identical(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(adapt, "scrape_elements", lambda url: _fake_elements())
    # Asking for the locator that IS the top candidate yields the next one, or None.
    new = find_replacement_locator("http://x", "CLICK", "products", 'a[href="/products.html"]')
    assert new is None or new != 'a[href="/products.html"]'


def test_find_replacement_locator_empty_description(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(adapt, "scrape_elements", lambda url: _fake_elements())
    assert find_replacement_locator("http://x", "CLICK", "", "a") is None


# ---------------------------------------------------------------------------
# Full decision loop: patch -> gate -> keep-or-revert
# ---------------------------------------------------------------------------


def _junit_with_failure(tmp_path: Path, test: str = "test_01") -> Path:
    path = tmp_path / "junit.xml"
    suite = ET.Element("testsuite", {"tests": "1"})
    case = ET.SubElement(suite, "testcase", {"name": test, "classname": "pkg"})
    ET.SubElement(case, "failure", {"message": "waiting for locator('a[href=\"/nope\"]')"}).text = "log"
    ET.ElementTree(suite).write(path, encoding="utf-8", xml_declaration=False)
    return path


def test_adapt_package_keeps_patch_when_rerun_passes(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pkg = _package(tmp_path)
    junit = _junit_with_failure(tmp_path)
    monkeypatch.setattr(adapt, "scrape_elements", lambda url: _fake_elements())

    # Re-run gate: first attempt passes -> patch kept.
    monkeypatch.setattr(adapt, "run_single_test", lambda pkg, test, root: (0, "1 passed"))

    report = adapt_package(pkg, junit)
    assert report.summary["adapted"] == 1
    assert report.summary["reverted"] == 0
    assert report.kept[0]["new_locator"] == 'a[href="/products.html"]'
    # Source is patched on disk.
    text = (pkg / "pages" / "home_page.py").read_text(encoding="utf-8")
    assert 'a[href="/products.html"]' in text


def test_adapt_package_reverts_when_rerun_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pkg = _package(tmp_path)
    junit = _junit_with_failure(tmp_path)
    monkeypatch.setattr(adapt, "scrape_elements", lambda url: _fake_elements())
    # Re-run gate: the patched test still fails -> revert, never silent mutation.
    monkeypatch.setattr(adapt, "run_single_test", lambda pkg, test, root: (1, "assertion failed"))

    report = adapt_package(pkg, junit)
    assert report.summary["adapted"] == 0
    assert report.summary["reverted"] == 1
    assert "reverted" in report.reverted[0]["status"]
    # Source restored to the original locator.
    text = (pkg / "pages" / "home_page.py").read_text(encoding="utf-8")
    assert 'a[href="/nope"]' in text
    assert 'a[href="/products.html"]' not in text


def test_adapt_package_only_test_filter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pkg = _package(tmp_path)
    junit = tmp_path / "junit.xml"
    suite = ET.Element("testsuite", {"tests": "2"})
    for name in ("test_01", "test_02"):
        case = ET.SubElement(suite, "testcase", {"name": name, "classname": "pkg"})
        ET.SubElement(case, "failure", {"message": "waiting for locator('a[href=\"/nope\"]')"}).text = "log"
    ET.ElementTree(suite).write(junit, encoding="utf-8", xml_declaration=False)
    monkeypatch.setattr(adapt, "scrape_elements", lambda url: _fake_elements())
    monkeypatch.setattr(adapt, "run_single_test", lambda pkg, test, root: (0, "1 passed"))

    report = adapt_package(pkg, junit, only_test="test_02")
    assert report.summary["candidates"] == 1
    assert report.kept[0]["test"] == "test_02"


def test_adapt_skips_non_repair_failures(tmp_path: Path) -> None:
    """Assertion failures are filtered BEFORE the engine — they always surface."""
    pkg = _package(tmp_path)
    junit = tmp_path / "junit.xml"
    suite = ET.Element("testsuite", {"tests": "1"})
    case = ET.SubElement(suite, "testcase", {"name": "test_01", "classname": "pkg"})
    ET.SubElement(case, "failure", {"message": "AssertionError: expected 5 to equal 6"}).text = "log"
    ET.ElementTree(suite).write(junit, encoding="utf-8", xml_declaration=False)

    report = adapt_package(pkg, junit)
    # Spec §9.6: assertion failures are never auto-adapted — zero candidates reach the engine.
    assert report.summary["candidates"] == 0
    assert report.summary["adapted"] == 0
    assert report.kept == []


def test_adapt_report_writes_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    pkg = _package(tmp_path)
    junit = _junit_with_failure(tmp_path)
    monkeypatch.setattr(adapt, "scrape_elements", lambda url: _fake_elements())
    monkeypatch.setattr(adapt, "run_single_test", lambda pkg, test, root: (0, "1 passed"))

    report = adapt_package(pkg, junit)
    data = report.to_dict()
    assert data["summary"]["adapted"] == 1
    assert data["url"] == "http://127.0.0.1:9999/index.html"  # from the manifest
    assert data["package"].endswith("test_pkg")
