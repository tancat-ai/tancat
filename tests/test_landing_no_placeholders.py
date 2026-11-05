"""j-0289: a placeholder must never be published.

``pages-deploy.yml`` builds ``landing/`` as the site root on every push to main,
so a placeholder in that tree is a placeholder a customer reads. This test is the
commit-time half of that guard; the deploy workflow runs the same rule, so a merge
that carries a marker publishes nothing.

It keys on the marker convention, not on today's wording (see
``scripts/maintenance/check_landing_placeholders.py``): a new placeholder of any
wording still fails.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts" / "maintenance"))

from check_landing_placeholders import LANDING, find_placeholders  # type: ignore[import-not-found]  # noqa: E402


def test_the_landing_tree_carries_no_owner_placeholder() -> None:
    findings = find_placeholders(LANDING)
    assert findings == [], (
        "the landing tree still carries owner placeholder(s), and pages-deploy publishes "
        "landing/ on every push to main:\n  " + "\n  ".join(findings)
    )


def test_the_marker_rule_catches_a_placeholder_it_has_never_seen(tmp_path: Path) -> None:
    """The rule is on the marker, so the NEXT placeholder fails too."""
    page = tmp_path / "landing" / "pricing.html"
    page.parent.mkdir(parents=True)
    page.write_text('<p>Trading name: <span class="placeholder-owner">x</span></p>', encoding="utf-8")

    findings = find_placeholders(tmp_path / "landing")

    assert any("placeholder-owner" in finding for finding in findings)


def test_the_phrase_and_an_uppercase_bracket_also_fail(tmp_path: Path) -> None:
    root = tmp_path / "landing"
    root.mkdir()
    (root / "a.html").write_text("<p>Address: to be supplied by the owner</p>", encoding="utf-8")
    (root / "b.html").write_text("<p>VAT: [VAT NUMBER TO BE CONFIRMED]</p>", encoding="utf-8")

    findings = find_placeholders(root)

    assert any("to be supplied by the owner" in finding for finding in findings)
    assert any("[VAT NUMBER TO BE CONFIRMED]" in finding for finding in findings)


def test_a_clean_page_passes(tmp_path: Path) -> None:
    root = tmp_path / "landing"
    root.mkdir()
    (root / "index.html").write_text('<p><span class="placeholder-owner">YOUR COMPANY LTD</span></p>', encoding="utf-8")
    (root / "clean.html").write_text("<p>TanCat is the trading name of Your Company Ltd.</p>", encoding="utf-8")
    (root / "clean.html").write_text("<p>TanCat is the trading name of Acme Ltd.</p>", encoding="utf-8")

    findings = find_placeholders(root)

    # Only the first page still carries the marker; the filled one is clean.
    assert len(findings) == 1
    assert "index.html" in findings[0]
