"""One-off: replay the saucedemo checkout test's placeholder sequence against the
REAL scraped data, printing current_url + matched element at each step.

Simulates what _replace_placeholders_sequentially does, to find where the page
context diverges from cart.html / checkout-step-one.html.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.journey_models import CredentialProfile  # noqa: E402
from src.placeholder_orchestrator import PlaceholderOrchestrator  # noqa: E402
from src.url_inference import infer_next_page_url  # noqa: E402

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

# test_06 flow from the generated skeleton
STEPS = [
    ("navigate", "https://www.saucedemo.com/"),
    ("FILL", "username:standard_user"),
    ("FILL", "password:secret_sauce"),
    ("CLICK", "login button"),
    ("CLICK", "Add to cart"),
    ("CLICK", "cart icon"),
    ("CLICK", "checkout button"),
    ("FILL", "first name:John"),
    ("FILL", "last name:Doe"),
    ("FILL", "zip code:12345"),
    ("CLICK", "continue button"),
    ("ASSERT", "success message"),
]


async def main() -> None:
    orch = PlaceholderOrchestrator(
        generator=None,  # type: ignore[arg-type]
        starting_url="https://www.saucedemo.com/",
        credential_profile=CredentialProfile(
            label="saucedemo", username="standard_user", password="secret_sauce"
        ),
        pom_mode=True,
    )
    sd: dict[str, list[dict[str, str]]] = {}
    for url in CANDIDATES:
        await orch._ensure_scraped(url, sd)
    sd = await orch._upgrade_stateful_pages(sd)

    current_url: str | None = "https://www.saucedemo.com/"
    for action, raw in STEPS:
        if action == "navigate":
            current_url = raw
            print(f"\n[NAV] -> {current_url}")
            continue
        desc, _, _fill = raw.partition(":")
        print(f"\n[{action}] {desc!r}  (current={current_url})")
        scoped = orch._build_scoped_pages(current_url, sd)
        pages_to_search = scoped if scoped else sd
        print(f"   scoped pages: {sorted(pages_to_search.keys())}")
        matched = await orch._element_matcher.find_best_element_for_current_page(
            action, desc, current_url, pages_to_search
        )
        if matched is None:
            # mirror the navigation-intent fallback in _replace_placeholders_sequentially
            if action in {"CLICK", "GOTO"} and orch._is_navigation_description(desc):
                nav_resolved, nav_next, _at = await orch._resolve_placeholder_for_page(
                    action="GOTO", description=desc, current_url=current_url, scraped_data=sd
                )
                if "pytest.skip" not in nav_resolved:
                    print(f"   NAV-FALLBACK -> {nav_resolved}")
                    current_url = nav_next
                    continue
            print("   NO MATCH")
            continue
        print(f"   matched: selector={matched.get('selector')!r} text={matched.get('text')!r} "
              f"id={matched.get('id')!r} href={matched.get('href')!r} page?={matched.get('url')!r}")
        next_url = infer_next_page_url(action, desc, matched, sd, current_url)
        if next_url:
            print(f"   next_url -> {next_url}")
            current_url = next_url


if __name__ == "__main__":
    asyncio.run(main())
