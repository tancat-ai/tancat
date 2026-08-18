"""Integration tests for SSRF-guard wiring in the scraper path (Phase 6 6a).

The guard refusal happens *before* any browser/network I/O, so the refusal
test is fast and offline (default suite). Loopback/mock-site regression is
covered by the existing E2E generate-against-mock tests, which exercise the
same wiring with the loopback default ON.
"""

from __future__ import annotations

import pytest

from src.scraper import PageScraper

METADATA_URL = "http://169.254.169.254/latest/meta-data/"


@pytest.mark.asyncio
async def test_scrape_refuses_cloud_metadata_url() -> None:
    """A cloud-metadata URL is refused with the guard error, not scraped."""
    elements, error, final_url = await PageScraper().scrape_url(METADATA_URL)
    assert elements == []
    assert error is not None
    assert "SSRF guard refused" in error
    assert "169.254.169.254" in error
    assert final_url == METADATA_URL


@pytest.mark.asyncio
async def test_scrape_refuses_private_network_url() -> None:
    """Private networks are refused by default (no browser spawned)."""
    elements, error, _final_url = await PageScraper().scrape_url("http://10.0.0.5/")
    assert elements == []
    assert error is not None and "SSRF guard refused" in error


@pytest.mark.asyncio
async def test_scrape_all_refuses_blocked_targets() -> None:
    """scrape_all (used by journey discovery) refuses the same way."""
    results = await PageScraper().scrape_all([METADATA_URL])
    elements, error, _final_url = results[METADATA_URL]
    assert elements == []
    assert error is not None and "SSRF guard refused" in error
