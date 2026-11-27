"""j-0086: the top tier is retired; only Free and Pro are published.

Owner decision 2026-10-03: the top ("Air-Gap", later "Contact us") tier is not a
published tier at all - it read as unprofessional. Enterprise stays available as a
conversation, off the pricing page.

Covers the three things that must hold after the retirement:

- the landing page renders two pricing tiers and no Air-Gap card;
- the code publishes exactly two tiers;
- a stored licence already carrying the retired ``airgap`` key still reports its
  own claims (it must NOT silently downgrade to free).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.licensing.license import LicenseStatus, license_status
from src.licensing.tiers import RETIRED_TIERS, is_published_tier, published_tiers, tier_claims

_LANDING = Path(__file__).resolve().parent.parent / "landing" / "index.html"
_TERMS = Path(__file__).resolve().parent.parent / "landing" / "terms.html"


def _pricing_cards(html: str) -> list[str]:
    """Return the tier names shown as pricing card headings."""
    section = html.split('id="pricing"', 1)[1].split("</section>", 1)[0]
    return re.findall(r"<h3[^>]*>([^<]+)</h3>", section)


# -- the landing page ---------------------------------------------------------


def test_landing_pricing_shows_two_tiers_and_no_top_tier() -> None:
    html = _LANDING.read_text(encoding="utf-8")
    cards = _pricing_cards(html)
    assert cards == ["Free Community", "Pro Deployment"]

    pricing_section = html.split('id="pricing"', 1)[1].split("</section>", 1)[0]
    assert "Air-Gap" not in pricing_section
    assert "$1,500" not in html, "the retired tier's price must not be published anywhere"
    # Enterprise stays reachable, as a plain contact link, not a priced tier.
    assert 'href="#contact"' in pricing_section
    assert "Enterprise arrangement" in pricing_section or "enterprise arrangement" in pricing_section


def test_terms_table_drops_the_retired_tier() -> None:
    terms = _TERMS.read_text(encoding="utf-8")
    assert "Air-Gap / Defense" not in terms
    assert "Pro Deployment" in terms
    assert "Free Community" in terms


# -- the tier table ------------------------------------------------------------


def test_code_publishes_exactly_two_tiers() -> None:
    assert published_tiers() == ("free", "pro")
    assert is_published_tier("free") is True
    assert is_published_tier("pro") is True
    assert is_published_tier("airgap") is False
    assert "airgap" in RETIRED_TIERS


def test_pro_grants_the_support_the_page_promises() -> None:
    """The page and the decision record both promise support on Pro."""
    assert "support" in tier_claims("pro")
    # The retired key is still resolvable with its own claims.
    assert "private_network" in tier_claims("airgap")


# -- backward compatibility of an already-activated licence -------------------


def test_a_licence_with_a_retired_tier_key_still_reports_its_claims(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A stored licence naming the retired key must NOT silently downgrade to free.

    The tier is not sent by the store; the product records it at activation and the
    table keeps retired keys resolvable, so an already-activated deployment reports
    its own claims rather than falling to free.
    """
    import json

    path = tmp_path / "licence.json"
    path.write_text(
        json.dumps(
            {
                "key": "00000-00000-00000-00000-00000",
                "instance_id": "lki_test",
                "instance_name": "test",
                "status": "active",
                "created_at": "2026-11-01T00:00:00+00:00",
                "expires_at": "",
                "activation_limit": 1,
                "last_checked": "2026-11-01T00:00:00+00:00",
                "tier": "airgap",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("AITEST_LICENCE_FILE", str(path))

    result = license_status()
    assert result.status == LicenseStatus.VALID
    assert result.tier == "airgap"
    assert "private_network" in result.claims
