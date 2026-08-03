"""One-off: replicate the orchestrator's scrape+upgrade phase for saucedemo and
dump per-URL element counts + checkout-relevant elements.

Answers: does cart.html / checkout-step-one.html actually contain the
checkout/continue/finish/form elements after _upgrade_stateful_pages?
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.journey_models import CredentialProfile  # noqa: E402
from src.placeholder_orchestrator import PlaceholderOrchestrator  # noqa: E402

CANDIDATES = [
    "https://www.saucedemo.com",
    "https://www.saucedemo.com/basket",
    "https://www.saucedemo.com/cart",
    "https://www.saucedemo.com/cart.html",
    "https://www.saucedemo.com/checkout",
    "https://www.saucedemo.com/checkout-step-one.html",
    "https://www.saucedemo.com/checkout.html",
    "https://www.saucedemo.com/checkout_step_one",
    "https://www.saucedemo.com/inventory.html",
    "https://www.saucedemo.com/products",
    "https://www.saucedemo.com/view_cart",
]

KEYWORDS = ("checkout", "continue", "finish", "first name", "last name", "postal", "your cart", "add to cart")


async def main() -> None:
    orch = PlaceholderOrchestrator(
        generator=None,  # type: ignore[arg-type]
        starting_url="https://www.saucedemo.com/",
        credential_profile=CredentialProfile(
            label="saucedemo", username="standard_user", password="secret_sauce"
        ),
        pom_mode=True,
    )
    scraped_data: dict[str, list[dict[str, str]]] = {}
    for url in CANDIDATES:
        await orch._ensure_scraped(url, scraped_data)
    scraped_data = await orch._upgrade_stateful_pages(scraped_data)

    for url, elems in scraped_data.items():
        texts = {str(e.get("accessible_name") or e.get("text") or "") for e in elems}
        hits = sorted(t for t in texts if any(k in t.lower() for k in KEYWORDS))
        print(f"\n=== {url}  ({len(elems)} elements)")
        for h in hits[:6]:
            print(f"   • {h[:90]}")


if __name__ == "__main__":
    asyncio.run(main())
