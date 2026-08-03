"""One-off: validate StatefulPageScraper + cart seeding against saucedemo's new SPA routing.

Saucedemo now serves every .html path as HTTP 404 (SPA on GitHub Pages).
This checks whether the stateful scraper (which ignores response status and
seeds the cart first) can still extract cart/checkout elements.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.journey_models import CredentialProfile  # noqa: E402
from src.stateful_scraper import StatefulPageScraper  # noqa: E402

TARGETS = [
    "https://www.saucedemo.com/cart.html",
    "https://www.saucedemo.com/checkout-step-one.html",
    "https://www.saucedemo.com/checkout-step-two.html",
    "https://www.saucedemo.com/checkout-complete.html",
]


async def main(no_creds: bool) -> None:
    creds = None
    if not no_creds:
        creds = CredentialProfile(
            label="saucedemo-demo", username="standard_user", password="secret_sauce"
        )
    scraper = StatefulPageScraper(
        "https://www.saucedemo.com/",
        credential_profile=creds,
    )
    results = await scraper.scrape_urls(TARGETS)
    for url, elements in results.items():
        texts = sorted(
            {
                str(e.get("accessible_name") or e.get("text") or e.get("tag") or "")
                for e in elements
            }
        )
        print(f"=== {url}: {len(elements)} elements ===")
        interesting = [
            t
            for t in texts
            if any(
                k in t.lower()
                for k in (
                    "checkout",
                    "continue",
                    "finish",
                    "cart",
                    "first name",
                    "last name",
                    "postal",
                    "add to cart",
                    "remove",
                )
            )
        ]
        for t in interesting[:25]:
            print(f"   • {t}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--no-creds",
        action="store_true",
        help="Simulate production behavior (no credential profile passed)",
    )
    args = parser.parse_args()
    asyncio.run(main(args.no_creds))
