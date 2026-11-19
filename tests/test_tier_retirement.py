"""j-0086: the top tier is retired; only Free and Pro are published.

Owner decision 2026-10-03: the top ("Air-Gap", later "Contact us") tier is not a
published tier at all - it read as unprofessional. Enterprise stays available as a
conversation, off the pricing page.

Covers the three things that must hold after the retirement:

- the landing page renders two pricing tiers and no Air-Gap card;
- the code publishes exactly two tiers;
- a licence already signed with the retired ``airgap`` key still verifies with
  its own claims (it must NOT silently downgrade to free).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from src.licensing import signed_file
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


# -- backward compatibility of an already-issued licence ----------------------


def test_licence_with_retired_airgap_key_still_verifies(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A signed licence naming the retired key must NOT silently downgrade to free.

    An unknown tier is refused outright (``signed_file``) rather than demoted, and the
    retired key stays resolvable, so a licence that named it still reports its own
    claims.
    """
    import base64
    from datetime import date

    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    private = Ed25519PrivateKey.generate()
    raw = private.private_bytes(
        serialization.Encoding.Raw,
        serialization.PrivateFormat.Raw,
        serialization.NoEncryption(),
    )
    public = base64.b64encode(
        private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    ).decode()
    monkeypatch.setattr(signed_file, "VENDORED_PUBLIC_KEY_B64", public)

    path = tmp_path / "licence.signed.json"
    purchased = date(2026, 11, 1)
    path.write_text(
        signed_file.signed_file_text(
            {
                "id": "TC-TEST-AIRGAP",
                "product": "tancat",
                "buyer_ref": "test",
                "period": purchased.isoformat(),
                "purchased_at": purchased.isoformat(),
                "window_end": "2099-01-01",
                "tier": "airgap",
            },
            raw,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("AITEST_LICENCE_FILE", str(path))

    result = license_status()
    assert result.status == LicenseStatus.VALID
    assert result.tier == "airgap"
    assert "private_network" in result.claims
