"""d-0153: the free export cap has one number, in code and in every page that quotes it.

landing/terms.html said "unlimited evidence exports" while the landing card said
10 and ``src/licensing/tiers.py`` enforced 10 - and the terms are the document a
buyer can quote back. These tests read the cap from the tier table and hold both
pages to it, so the three cannot drift again.
"""

from __future__ import annotations

import re
from pathlib import Path

from src.licensing.tiers import tiers

REPO_ROOT = Path(__file__).resolve().parent.parent
TERMS = REPO_ROOT / "landing" / "terms.html"
INDEX = REPO_ROOT / "landing" / "index.html"


def _free_cap(name: str) -> int:
    """The free tier's limit for *name*, read from the code that enforces it."""
    spec = tiers()["free"]
    limits = dict(spec.limits)
    value = limits[f"{name}_per_month"]
    assert isinstance(value, int) and value > 0, f"free tier {name} limit is not a positive number: {value!r}"
    return value


def test_the_free_export_cap_is_a_real_number_in_the_code() -> None:
    assert _free_cap("evidence_exports") == 10


def test_the_landing_card_quotes_the_cap_from_the_code() -> None:
    cap = _free_cap("evidence_exports")
    html = INDEX.read_text(encoding="utf-8")
    assert f"{cap} evidence exports per 30 days" in html


def test_the_terms_quote_the_cap_from_the_code() -> None:
    cap = _free_cap("evidence_exports")
    html = TERMS.read_text(encoding="utf-8")
    assert f"{cap} evidence exports per 30 days" in html
    assert "unlimited evidence exports" not in html.lower()


def test_the_terms_free_row_quotes_both_caps_from_the_code() -> None:
    """A hand-typed number is exactly how the drift started."""
    exports_cap = _free_cap("evidence_exports")
    runs_cap = _free_cap("runs")
    html = TERMS.read_text(encoding="utf-8")
    free_row = next((line for line in html.splitlines() if "Free Community" in line), "")
    assert free_row, "the terms free-tier row is gone"

    assert f"{runs_cap} test runs per 30 days" in free_row
    export_mentions = re.findall(r"(\d+|unlimited)\s+evidence exports", free_row, re.IGNORECASE)
    assert export_mentions == [str(exports_cap)], (
        f"the free row reads {export_mentions} for evidence exports; the code enforces {exports_cap}"
    )
