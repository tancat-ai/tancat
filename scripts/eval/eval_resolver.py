"""eval_resolver.py — Resolution-only evaluation (bypasses LLM skeleton generation).

Tests the resolver engine directly: feeds golden-key placeholder descriptions + pre-scraped
page data to the resolution pipeline and compares resolved locators to expected locators.

Modes:
    ``--mode static``    Uses frozen scraped data in ``scraped_pages/`` (fast, deterministic).
    ``--mode live``      Scrapes live sites first, then resolves (requires running servers).

Supports RAG on/off via ``RAG_ENABLED`` env var for direct comparison::

    python scripts/eval/eval_resolver.py   # RAG off
    RAG_ENABLED=1 python scripts/eval/eval_resolver.py  # RAG on

Usage:
    # Fast — requires saved_scraped_data/ populated
    python scripts/eval/eval_resolver.py --mode static

    # Live — scrapes real sites
    python scripts/eval/eval_resolver.py --mode live

    # Compare RAG on/off
    python scripts/eval/eval_resolver.py --mode static
    RAG_ENABLED=1 python scripts/eval/eval_resolver.py --mode static
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_DATASET_DIR = _PROJECT_ROOT / "scripts" / "eval" / "dataset"
_SCRAPED_DIR = _PROJECT_ROOT / "scripts" / "eval" / "scraped_pages"

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Golden key loading
# ---------------------------------------------------------------------------


def _load_golden_placeholders() -> list[dict[str, Any]]:
    """Load all golden placeholders from dataset files.

    Returns flat list with keys: action, description, expected_locator,
    tolerance_selectors, expected_page.
    """
    placeholders: list[dict[str, Any]] = []
    for fpath in sorted(_DATASET_DIR.glob("*.json")):
        data = json.loads(fpath.read_text(encoding="utf-8"))
        for crit in data.get("golden_resolutions", []):
            for ph in crit.get("placeholders", []):
                placeholders.append(
                    {
                        "action": ph["action"],
                        "description": ph["description"],
                        "expected_locator": ph["expected_locator"],
                        "tolerance_selectors": ph.get("tolerance_selectors", []),
                        "expected_page": ph.get("expected_page", ""),
                        "site": data.get("site", ""),
                        "story_id": data.get("id", ""),
                    }
                )
    return placeholders


# ---------------------------------------------------------------------------
# Scraped data loading / saving
# ---------------------------------------------------------------------------


def load_scraped_pages() -> dict[str, list[dict[str, str]]]:
    """Load pre-saved scraped page data from ``scraped_pages/`` directory.

    Each ``<url_hash>.json`` file contains ``{"url": "...", "elements": [...]}``.
    """
    pages: dict[str, list[dict[str, str]]] = {}
    if not _SCRAPED_DIR.exists():
        logger.warning("Scraped pages directory not found: %s — run 'save-scraped-data' first", _SCRAPED_DIR)
        return pages

    for fpath in _SCRAPED_DIR.glob("*.json"):
        data = json.loads(fpath.read_text(encoding="utf-8"))
        url = data.get("url", "")
        elements: list[dict[str, str]] = data.get("elements", [])
        if url and elements:
            pages[url] = elements

    logger.info("Loaded %d scraped page(s) from %s", len(pages), _SCRAPED_DIR)
    return pages


async def scrape_and_save_pages() -> dict[str, list[dict[str, str]]]:
    """Scrape all unique pages from golden keys and save to disk.

    Returns the scraped pages dict (same format as ``load_scraped_pages``).
    """
    from src.scraper import PageScraper

    placeholders = _load_golden_placeholders()
    unique_urls: set[str] = {ph["expected_page"] for ph in placeholders if ph["expected_page"]}
    logger.info("Scraping %d unique page(s)...", len(unique_urls))

    scraper = PageScraper()
    pages: dict[str, list[dict[str, str]]] = {}
    _SCRAPED_DIR.mkdir(parents=True, exist_ok=True)

    for url in sorted(unique_urls):
        logger.info("  Scraping %s ...", url)
        elements, error, _final_url = await scraper.scrape_url(url)
        if error:
            logger.warning("    Error: %s", error)
        if elements:
            pages[url] = elements
            # Save to disk
            safe_name = url.replace("://", "_").replace("/", "_").replace(":", "_")[:120]
            out_path = _SCRAPED_DIR / f"{safe_name}.json"
            out_path.write_text(
                json.dumps({"url": url, "elements": elements}, indent=2),
                encoding="utf-8",
            )
            logger.info("    Saved %d elements to %s", len(elements), out_path.name)
        else:
            logger.warning("    No elements scraped")

    return pages


# ---------------------------------------------------------------------------
# Resolution
# ---------------------------------------------------------------------------


def _resolve_placeholder(
    action: str,
    description: str,
    pages_data: dict[str, list[dict[str, str]]],
    expected_page: str,
    element_matcher: Any,
    rag_retriever: Any | None = None,
) -> str | None:
    """Resolve a single placeholder using ElementMatcher's multi-pass pipeline.

    Returns:
        Resolved locator string, or None if not found.
    """
    from src.placeholder_scorers import PlaceholderScorer

    # Filter to the expected page if specified
    if expected_page and expected_page in pages_data:
        page_specific = {expected_page: pages_data[expected_page]}
    else:
        page_specific = pages_data

    # Retrieve golden patterns from RAG if available
    golden_patterns: list[Any] | None = None
    if rag_retriever is not None:
        try:
            golden_patterns = rag_retriever.retrieve(description, action_type=action)
        except Exception:
            pass

    # Pass 0: Exact text match (ASSERT only)
    if action == "ASSERT":
        result = element_matcher.pass0_exact_text_match(action, description, page_specific)
        if result:
            return _element_to_locator(result)

    # Pass 1: Fast text match
    result = element_matcher.pass1_text_match(action, description, page_specific)
    if result:
        return _element_to_locator(result)

    # Pass 3: Scoring-based (match against all elements)
    all_elements: list[dict[str, str]] = []
    for elements in page_specific.values():
        all_elements.extend(elements)

    if not all_elements:
        return None

    # Score each element against the description
    best_score: int | float = -9999
    best_locator: str | None = None
    for element in all_elements:
        selector = _element_to_locator(element)
        score = PlaceholderScorer.compute_element_score(
            action=action,
            description=description,
            element=element,
            selector=selector,
            match_threshold=0.0,
            golden_patterns=golden_patterns,
        )
        if score is not None and score > best_score:
            best_score = score
            best_locator = selector

    return best_locator


def _element_to_locator(element: dict[str, str]) -> str:
    """Extract best locator from an element dict.

    Priority: id > data-test > name > css selector.
    """
    if element.get("id"):
        return f"#{element['id']}"
    if element.get("data-test"):
        return f'[data-test="{element["data-test"]}"]'
    if element.get("name"):
        return f'[name="{element["name"]}"]'
    return element.get("selector", element.get("tag", "*"))


# ---------------------------------------------------------------------------
# Main runner
# ---------------------------------------------------------------------------


async def run_resolver_eval(
    pages: dict[str, list[dict[str, str]]],
    rag_retriever: Any | None = None,
) -> dict[str, Any]:
    """Run resolver-only evaluation against all golden placeholders.

    Returns dict with summary stats suitable for HarnessReport.
    """
    from src.element_matcher import ElementMatcher
    from src.placeholder_resolver import PlaceholderResolver

    placeholders = _load_golden_placeholders()
    resolver = PlaceholderResolver()
    element_matcher = ElementMatcher(resolver, generator=None)

    correct = 0
    total = 0
    per_site: dict[str, dict[str, int]] = {}

    for ph in placeholders:
        total += 1
        site = ph["site"] or "unknown"
        if site not in per_site:
            per_site[site] = {"total": 0, "correct": 0}
        per_site[site]["total"] += 1

        resolved = _resolve_placeholder(
            action=ph["action"],
            description=ph["description"],
            pages_data=pages,
            expected_page=ph["expected_page"],
            element_matcher=element_matcher,
            rag_retriever=rag_retriever,
        )

        expected = ph["expected_locator"]
        tolerances = ph.get("tolerance_selectors", [])

        matched = resolved is not None and (resolved == expected or resolved in tolerances)
        if matched:
            correct += 1
            per_site[site]["correct"] += 1

        logger.debug(
            "  %s '%s' → %s (expected: %s) %s",
            ph["action"],
            ph["description"],
            resolved or "None",
            expected,
            "✓" if matched else "✗",
        )

    accuracy = (correct / total * 100) if total > 0 else 0.0

    summary: dict[str, Any] = {
        "total_placeholders": total,
        "correct": correct,
        "accuracy_pct": round(accuracy, 1),
        "per_site": {
            site: {
                "correct": stats["correct"],
                "total": stats["total"],
                "accuracy_pct": round(stats["correct"] / stats["total"] * 100, 1) if stats["total"] > 0 else 0.0,
            }
            for site, stats in sorted(per_site.items())
        },
    }

    return summary


def _format_summary(summary: dict[str, Any]) -> str:
    """Format summary dict as a readable string."""
    lines = [
        "=" * 70,
        "RESOLVER-ONLY EVALUATION",
        "=" * 70,
        "",
        f"  Placeholders evaluated:  {summary['total_placeholders']}",
        f"  Correct resolutions:     {summary['correct']}",
        f"  Resolution accuracy:     {summary['accuracy_pct']}%",
        "",
        "-" * 70,
        "PER-SITE BREAKDOWN",
        "-" * 70,
    ]

    for site, stats in summary["per_site"].items():
        lines.append(f"  {site}: {stats['correct']}/{stats['total']} ({stats['accuracy_pct']}%)")

    lines.append("")
    lines.append("=" * 70)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


async def _cmd_static() -> int:
    """Run resolver eval against pre-saved scraped data."""
    pages = load_scraped_pages()
    if not pages:
        print("ERROR: No scraped pages found.", file=sys.stderr)
        print("  Run first: python scripts/eval/eval_resolver.py --mode live", file=sys.stderr)
        return 1

    rag_enabled = os.getenv("RAG_ENABLED", "").strip() == "1"
    rag_retriever = None
    if rag_enabled:
        try:
            from src.rag_retriever import RAGRetriever
            from src.rag_store import MilvusLiteBackend, RAGStore, SentenceTransformerEmbedder
            from src.storage import get_storage

            embedder = SentenceTransformerEmbedder()
            backend = MilvusLiteBackend(str(get_storage().rag_path()), embedder.dimension)
            store = RAGStore(backend, embedder)
            rag_retriever = RAGRetriever(store)
            logger.info("RAG retriever initialised")
        except Exception:
            logger.warning("RAG enabled but failed to init — disabling", exc_info=True)

    summary = await run_resolver_eval(pages, rag_retriever)
    print(_format_summary(summary))

    if rag_enabled:
        print("\n[RAG: ENABLED]")
    else:
        print("\n[RAG: DISABLED]  (set RAG_ENABLED=1 to compare)")

    return 0


async def _cmd_live() -> int:
    """Scrape live sites using static scraper (no auth). Fast but limited.

    For stateful pages (saucedemo cart/checkout, automationexercise cart),
    use ``--mode pipeline`` instead.
    """
    print("Scraping live pages (static — no auth, no cart seeding) ...")
    pages = await scrape_and_save_pages()
    if not pages:
        print("ERROR: No pages scraped.", file=sys.stderr)
        return 1

    print(f"\nScraped {len(pages)} page(s). Saved to {_SCRAPED_DIR}/")
    print("Now run: python scripts/eval/eval_resolver.py --mode static")
    return 0


async def _cmd_pipeline() -> int:
    """Scrape pages using StatefulPageScraper — matches the real pipeline.

    Uses credentials and cart seeding so pages like saucedemo.com/cart.html
    and automationexercise.com/view_cart are scraped in their populated state
    (not empty / not 404).  Credentials are loaded from environment:

        SAUCEDEMO_USERNAME=standard_user
        SAUCEDEMO_PASSWORD=secret_sauce
    """
    from src.journey_models import CredentialProfile
    from src.stateful_scraper import StatefulPageScraper

    placeholders = _load_golden_placeholders()

    # Group pages by site to determine scraping strategy
    sites: dict[str, dict[str, Any]] = {}
    for ph in placeholders:
        site = ph["site"]
        url = ph["expected_page"]
        if site not in sites:
            sites[site] = {"urls": set(), "base_url": ""}
        sites[site]["urls"].add(url)
        # Use the first non-internal URL as the base
        if not sites[site]["base_url"] and not any(
            url.endswith(p) for p in ["/cart.html", "/checkout", "/view_cart", "/products"]
        ):
            sites[site]["base_url"] = url

    _SCRAPED_DIR.mkdir(parents=True, exist_ok=True)
    total_pages = 0

    for site, info in sorted(sites.items()):
        urls = sorted(info["urls"])
        base_url = info["base_url"] or urls[0]

        # Choose scraping strategy per site
        if site == "saucedemo":
            username = os.getenv("SAUCEDEMO_USERNAME", "standard_user")
            password = os.getenv("SAUCEDEMO_PASSWORD", "secret_sauce")
            creds = CredentialProfile(
                label="saucedemo",
                username=username,
                password=password,
            )
            scraper = StatefulPageScraper(base_url, credential_profile=creds)
            logger.info("%s: StatefulPageScraper with credentials (%d page(s))", site, len(urls))

        elif site == "automationexercise":
            # No login needed, but cart seeding helps for /view_cart state
            scraper = StatefulPageScraper(base_url)
            logger.info("%s: StatefulPageScraper (cart seeding, %d page(s))", site, len(urls))

        else:
            # Static sites — use simple PageScraper
            from src.scraper import PageScraper

            static = PageScraper()
            for url in urls:
                logger.info("  %s: scraping %s (static) ...", site, url)
                elements, error, _final_url = await static.scrape_url(url)
                if error:
                    logger.warning("    Error: %s", error)
                if elements:
                    safe_name = url.replace("://", "_").replace("/", "_").replace(":", "_")[:120]
                    out_path = _SCRAPED_DIR / f"{safe_name}.json"
                    out_path.write_text(
                        json.dumps({"url": url, "elements": elements}, indent=2),
                        encoding="utf-8",
                    )
                    logger.info("    Saved %d elements to %s", len(elements), out_path.name)
                    total_pages += 1
            continue

        # Stateful scrape: all URLs in one session
        scraped = await scraper.scrape_urls(urls)
        for url, elements in scraped.items():
            if elements:
                safe_name = url.replace("://", "_").replace("/", "_").replace(":", "_")[:120]
                out_path = _SCRAPED_DIR / f"{safe_name}.json"
                out_path.write_text(
                    json.dumps({"url": url, "elements": elements}, indent=2),
                    encoding="utf-8",
                )
                logger.info("    Saved %d elements to %s", len(elements), out_path.name)
                total_pages += 1
            else:
                logger.warning("    No elements for %s", url)

    print(f"\nScraped {total_pages} page(s) across {len(sites)} site(s). Saved to {_SCRAPED_DIR}/")
    print("Now run: python scripts/eval/eval_resolver.py --mode static")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Resolver-only evaluation — tests resolution accuracy in isolation",
    )
    parser.add_argument(
        "--mode",
        choices=["static", "live", "pipeline"],
        default="static",
        help="static: frozen scraped data | live: static scrape | pipeline: stateful scrape (matches real pipeline)",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Debug logging")

    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    if args.mode == "pipeline":
        return asyncio.run(_cmd_pipeline())
    if args.mode == "live":
        return asyncio.run(_cmd_live())
    return asyncio.run(_cmd_static())


if __name__ == "__main__":
    sys.exit(main())
