"""Tests for UrlResolver-backed page requirement scoping."""

from typing import Any

from src.pipeline_models import PageRequirement
from src.placeholder_orchestrator import PlaceholderOrchestrator
from src.url_resolver import UrlResolver


def test_page_requirements_to_pages_filters_by_keyword() -> None:
    orchestrator = PlaceholderOrchestrator()
    orchestrator.url_resolver.build_mapping(
        keywords=["cart", "home"],
        scraped_urls=["https://example.com/", "https://example.com/view_cart"],
        seed_url="https://example.com/",
    )
    scraped = {
        "https://example.com/": [{"selector": "#home", "text": "Home", "role": "link"}],
        "https://example.com/view_cart": [{"selector": "#cart", "text": "Cart", "role": "link"}],
    }
    requirements = [PageRequirement(keyword="cart", description="shopping cart page")]

    scoped = orchestrator._page_requirements_to_pages(requirements, scraped)

    assert scoped is not None
    assert list(scoped.keys()) == ["https://example.com/view_cart"]


def test_page_requirements_to_pages_returns_none_when_unmapped() -> None:
    orchestrator = PlaceholderOrchestrator()
    orchestrator.url_resolver = UrlResolver()
    scraped: dict[str, list[Any]] = {"https://example.com/": []}
    requirements = [PageRequirement(keyword="unknown_page")]

    assert orchestrator._page_requirements_to_pages(requirements, scraped) is None
