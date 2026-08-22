"""AI-052 Session 3: the resolver consumes the observed trail.

Core behaviour under test:
- **verified** — a trail step whose page is in ``scraped_data`` scopes resolution
  to that page (observation replaces ``infer_next_page_url``'s guess).
- **evidenced / unknown** — no scraped DOM for the step's page → honest
  ``pytest.skip``, NEVER a cross-page locator (including via the batch fallback).
- GOTO placeholders resolve to the observed landing URL directly.
- No regression: fully-scraped journeys still resolve everything.
- Back-compat: without trails, resolution behaves exactly as before S3.

Fixtures mirror real captured failures:
- A (saucedemo, 2026-08-20): title-link → inventory-item?id=4; the following
  add-to-cart must skip, not pick the button from the inventory page.
- B (automationexercise, 2026-08-03): checkout click while on the product
  details page skips instead of cross-page clicking `.btn.check_out`.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

from src.journey_models import ObservedStep, ObservedTrail
from src.pipeline_models import PlaceholderUse, TestJourney, TestStep
from src.placeholder_orchestrator import PlaceholderOrchestrator

SEED = "https://www.saucedemo.com"
INVENTORY = "https://www.saucedemo.com/inventory.html"
ITEM4 = "https://www.saucedemo.com/inventory-item.html?id=4"
CART = "https://www.saucedemo.com/cart.html"

PRODUCTS = "https://automationexercise.com/products"
DETAILS = "https://automationexercise.com/product_details/2"
VIEW_CART = "https://automationexercise.com/view_cart"

JACKET_BUTTON = "#add-to-cart-sauce-labs-fleece-jacket"


def _el(selector: str, text: str, **extra: Any) -> dict[str, Any]:
    element: dict[str, Any] = {"selector": selector, "text": text, "tag": "button", "role": "button"}
    element.update(extra)
    return element


def _token(action: str, description: str) -> str:
    return "{{" + f"{action}:{description}" + "}}"


def _build(name: str, placeholders: list[tuple[str, str]]) -> tuple[str, TestJourney]:
    """Build a skeleton (with a real `def test_` line) + matching TestJourney."""
    lines = [f"def {name}(page) -> None:"]
    steps: list[TestStep] = []
    for i, (action, description) in enumerate(placeholders, start=2):
        token = _token(action, description)
        raw_line = f"    act({token})"
        lines.append(raw_line)
        steps.append(
            TestStep(
                line_number=i,
                raw_line=raw_line,
                placeholders=[
                    PlaceholderUse(
                        token=token, action=action, description=description, line_number=i, raw_line=raw_line
                    )
                ],
            )
        )
    skeleton = "\n".join(lines)
    journey = TestJourney(test_name=name, start_line=1, end_line=len(lines), steps=steps)
    return skeleton, journey


def _resolve(
    skeleton: str,
    journeys: list[TestJourney],
    scraped_data: dict[str, list[dict[str, Any]]],
    observed_trails: dict[str, ObservedTrail] | None = None,
) -> str:
    orch = PlaceholderOrchestrator()
    return asyncio.run(
        orch._replace_placeholders_sequentially(
            skeleton_code=skeleton,
            journeys=journeys,
            page_requirements=[],
            seed_urls=[next(iter(scraped_data), "")],
            scraped_data=scraped_data,
            observed_trails=observed_trails,
        )
    )


# ── Fixture A — saucedemo 2026-08-20: cross-page add-to-cart ─────────────


def _fixture_a_data() -> dict[str, list[dict[str, Any]]]:
    """Inventory + item?id=4 scraped; the jacket button ONLY on inventory."""
    return {
        SEED: [
            _el("#user-name", "username", tag="input", role="textbox"),
            _el("#password", "password", tag="input", role="textbox"),
            _el("#login-button", "login button"),
        ],
        INVENTORY: [
            _el("#item_4_title_link", "Sauce Labs Backpack product title link", tag="a", href=ITEM4),
            # The trap: exists on the inventory page, NOT on item pages.
            _el(JACKET_BUTTON, "add to cart fleece jacket"),
            _el(".shopping_cart_link", "cart icon", tag="a"),
        ],
        ITEM4: [
            _el(".inventory_details_desc", "carry.allTheThings()", tag="div"),
        ],
    }


def _fixture_a_trail() -> ObservedTrail:
    """Factual trail: title-link landed on ?id=4 and was scraped."""
    return ObservedTrail(
        steps=[
            ObservedStep(0, "fill", description="username", from_url="", to_url=SEED, scraped=True),
            ObservedStep(1, "fill", description="password", from_url=SEED, to_url=SEED, scraped=False),
            ObservedStep(
                2, "click", description="login button", from_url=SEED, to_url=INVENTORY, navigated=True, scraped=True
            ),
            ObservedStep(
                3,
                "click",
                description="product title link",
                from_url=INVENTORY,
                to_url=ITEM4,
                navigated=True,
                scraped=True,
            ),
            ObservedStep(
                4,
                "click",
                description="add to cart fleece jacket",
                from_url=ITEM4,
                to_url=ITEM4,
                navigated=False,
                scraped=False,
            ),
        ]
    )


def test_fixture_a_add_to_cart_skips_instead_of_cross_page_locator() -> None:
    """Trail shows title-link → ?id=4. Add-to-cart must SKIP — never resolve to
    the inventory page's button (the AI-052 bug), not even via batch fallback."""
    skeleton, journey = _build(
        "test_fixture_a",
        [
            ("FILL", "username"),
            ("FILL", "password"),
            ("CLICK", "login button"),
            ("CLICK", "product title link"),
            ("CLICK", "add to cart fleece jacket"),
        ],
    )
    code = _resolve(skeleton, [journey], _fixture_a_data(), {"test_fixture_a": _fixture_a_trail()})
    assert JACKET_BUTTON not in code, f"cross-page locator leaked into output:\n{code}"
    assert "pytest.skip" in code


def test_fixture_a_verified_steps_still_resolve() -> None:
    """No regression on the verified path: login + title-link resolve normally."""
    skeleton, journey = _build(
        "test_fixture_a_ok",
        [("FILL", "username"), ("FILL", "password"), ("CLICK", "login button"), ("CLICK", "product title link")],
    )
    code = _resolve(skeleton, [journey], _fixture_a_data(), {"test_fixture_a_ok": _fixture_a_trail()})
    assert "#login-button" in code
    assert "#item_4_title_link" in code
    assert "pytest.skip" not in code, f"honest skip on verified path:\n{code}"


# ── Fixture B — automationexercise 2026-08-03: checkout off-page ─────────


def test_fixture_b_checkout_skips_when_not_on_cart_page() -> None:
    """.btn.check_out exists in scraped data (cart page) but the trail puts us on
    the product details page — must skip instead of cross-page clicking."""
    data: dict[str, list[dict[str, Any]]] = {
        PRODUCTS: [_el("a[href='/product_details/2']", "view product", tag="a", href=DETAILS)],
        DETAILS: [_el(".product-information", "blue top", tag="div")],
        VIEW_CART: [_el(".btn.check_out", "proceed to checkout")],
    }
    trail = ObservedTrail(
        steps=[
            ObservedStep(
                0, "click", description="view product", from_url=PRODUCTS, to_url=DETAILS, navigated=True, scraped=True
            ),
            ObservedStep(
                1,
                "click",
                description="proceed to checkout",
                from_url=DETAILS,
                to_url=DETAILS,
                navigated=False,
                scraped=False,
            ),
        ]
    )
    skeleton, journey = _build("test_fixture_b", [("CLICK", "view product"), ("CLICK", "proceed to checkout")])
    code = _resolve(skeleton, [journey], data, {"test_fixture_b": trail})
    assert ".btn.check_out" not in code, f"cross-page locator leaked:\n{code}"
    assert "pytest.skip" in code


# ── Fixture C — happy path: every step lands on a scraped page ───────────


def test_fixture_c_fully_observed_journey_has_no_regression() -> None:
    """Every step lands on a scraped page → all resolve as before (no skips)."""
    data = _fixture_a_data()
    data[CART] = [_el("#item_4_title_link", "Sauce Labs Backpack product title link", tag="a")]
    trail = ObservedTrail(
        steps=[
            ObservedStep(0, "fill", description="username", from_url="", to_url=SEED, scraped=True),
            ObservedStep(1, "fill", description="password", from_url=SEED, to_url=SEED, scraped=False),
            ObservedStep(
                2, "click", description="login button", from_url=SEED, to_url=INVENTORY, navigated=True, scraped=True
            ),
            ObservedStep(
                3, "click", description="cart icon", from_url=INVENTORY, to_url=CART, navigated=True, scraped=True
            ),
        ]
    )
    skeleton, journey = _build(
        "test_fixture_c",
        [("FILL", "username"), ("FILL", "password"), ("CLICK", "login button"), ("CLICK", "cart icon")],
    )
    code = _resolve(skeleton, [journey], data, {"test_fixture_c": trail})
    assert "#login-button" in code
    assert ".shopping_cart_link" in code
    assert "pytest.skip" not in code, f"honest skip on happy path:\n{code}"


# ── Evidenced case — real href to an unscraped page ───────────────────────


def test_evidenced_href_to_unscraped_page_skips_honestly() -> None:
    """A verified page has a REAL href to an unscraped page; the next step's
    element lives there → skip with the honest reason, never a guess."""
    data = {INVENTORY: [_el("#offers-link", "see all offers", tag="a", href="/offers.html")]}
    trail = ObservedTrail(
        steps=[
            ObservedStep(
                0,
                "click",
                description="see all offers",
                from_url=INVENTORY,
                to_url="https://www.saucedemo.com/offers.html",
                navigated=True,
                scraped=False,
            ),
            ObservedStep(
                1,
                "click",
                description="claim reward now",
                from_url="https://www.saucedemo.com/offers.html",
                to_url="https://www.saucedemo.com/offers.html",
                navigated=False,
                scraped=False,
            ),
        ]
    )
    skeleton, journey = _build("test_evidenced", [("CLICK", "see all offers"), ("CLICK", "claim reward now")])
    code = _resolve(skeleton, [journey], data, {"test_evidenced": trail})
    assert "pytest.skip" in code
    assert "not in scrape inventory" in code
    # Nothing was fabricated: the only locator emitted is from the verified page.
    assert "#offers-link" in code
    assert "offers.html" not in code.split("#offers-link", 1)[1]


def test_unknown_step_after_trail_end_stays_on_last_verified_page() -> None:
    """Trail ended early (scrape error): later steps have NO observation → scope
    stays on the last verified page; missing elements skip honestly."""
    skeleton, journey = _build("test_unknown_trail", [("CLICK", "login button"), ("CLICK", "mystery button")])
    trail = ObservedTrail(
        steps=[
            ObservedStep(
                0, "click", description="login button", from_url=SEED, to_url=INVENTORY, navigated=True, scraped=True
            ),
        ]
    )
    code = _resolve(skeleton, [journey], _fixture_a_data(), {"test_unknown_trail": trail})
    # The unknown-state skip carries the honest reason and names the step.
    assert "pytest.skip" in code
    assert "next page 'mystery button' not in scrape inventory" in code
    # No cross-page locator leaked for the unobserved step.
    assert "#add-to-cart-sauce-labs-fleece-jacket" not in code


# ── GOTO consumes observation instead of guessing ─────────────────────────


def test_goto_resolves_to_observed_landing_url() -> None:
    """GOTO with a verified observed landing resolves to that exact URL — no
    keyword/href guessing involved."""
    data = {INVENTORY: [_el(".shopping_cart_link", "cart icon", tag="a")], CART: []}
    trail = ObservedTrail(
        steps=[
            ObservedStep(
                0, "navigate", description="go to cart", from_url=INVENTORY, to_url=CART, navigated=True, scraped=True
            ),
            ObservedStep(
                1, "scrape", description="cart page visible", from_url=CART, to_url=CART, navigated=False, scraped=True
            ),
        ]
    )
    skeleton, journey = _build("test_goto_observed", [("GOTO", "go to cart"), ("ASSERT", "cart page visible")])
    code = _resolve(skeleton, [journey], data, {"test_goto_observed": trail})
    assert repr(CART) in code


def test_goto_with_empty_trail_still_resolves_via_resolver() -> None:
    """Back-compat inside a trail journey: an empty trail disables strict scope
    and the normal URL resolution path still works."""
    data: dict[str, list[dict[str, Any]]] = {INVENTORY: []}
    skeleton, journey = _build("test_goto_nomatch", [("GOTO", "inventory")])
    code = _resolve(skeleton, [journey], data, {"test_goto_nomatch": ObservedTrail(steps=[])})
    assert INVENTORY in code


# ── Back-compat: no trails at all → pre-S3 behaviour ──────────────────────


def test_no_trails_behaviour_unchanged_cross_page_still_available() -> None:
    """Without observed_trails, resolution keeps the old all-pages fallback
    (callers that scrape differently rely on it)."""
    skeleton, journey = _build(
        "test_no_trail", [("CLICK", "product title link"), ("CLICK", "add to cart fleece jacket")]
    )
    code = _resolve(skeleton, [journey], _fixture_a_data(), None)
    # Old behaviour: the jacket button is found via all-pages fallback.
    assert JACKET_BUTTON in code


# ── Scraper/resolver disagreement (found in verify run 2026-08-22) ────────


def test_emitted_href_click_invalidates_stale_verified_page() -> None:
    """The scraper clicked a non-navigating button for 'Sauce Labs Backpack' (trail
    stays on inventory), but the resolver emits the title link (real href to the
    unscraped item page). The next 'Add to cart' MUST skip — the bolt button
    exists on the stale verified page but the runtime browser won't be there."""
    data: dict[str, list[dict[str, Any]]] = {
        SEED: [_el("#login-button", "login button")],
        INVENTORY: [
            _el("#item_4_title_link", "Sauce Labs Backpack", tag="a", href=ITEM4),
            # Both add-to-cart buttons exist on inventory — the trap.
            _el(JACKET_BUTTON, "add to cart fleece jacket"),
            _el("#add-to-cart-sauce-labs-bolt-t-shirt", "add to cart bolt t-shirt"),
        ],
        # NOTE: ITEM4 deliberately NOT scraped — discovery never navigated there.
    }
    trail = ObservedTrail(
        steps=[
            ObservedStep(
                0, "click", description="login button", from_url=SEED, to_url=INVENTORY, navigated=True, scraped=True
            ),
            # The scraper clicked an add-to-cart button instead of the title link:
            ObservedStep(
                1,
                "click",
                description="Sauce Labs Backpack",
                from_url=INVENTORY,
                to_url=INVENTORY,
                navigated=False,
                scraped=False,
            ),
            ObservedStep(
                2,
                "click",
                description="add to cart",
                from_url=INVENTORY,
                to_url=INVENTORY,
                navigated=False,
                scraped=False,
            ),
        ]
    )
    skeleton, journey = _build(
        "test_disagreement",
        [("CLICK", "login button"), ("CLICK", "Sauce Labs Backpack"), ("CLICK", "add to cart")],
    )
    code = _resolve(skeleton, [journey], data, {"test_disagreement": trail})
    assert "pytest.skip" in code
    assert JACKET_BUTTON not in code, f"stale-page locator leaked:\n{code}"
    assert "bolt-t-shirt" not in code.split("pytest.skip")[0], f"stale-page locator leaked:\n{code}"


def test_observed_selector_replay_keeps_test_on_trail() -> None:
    """When the trail carries a proven selector_used, the resolver replays it —
    the generated test re-enacts the observed journey instead of re-guessing a
    different element whose navigation behaviour the trail never saw."""
    data: dict[str, list[dict[str, Any]]] = {
        SEED: [_el("#login-button", "login button")],
        INVENTORY: [
            # NOTE: no href — saucedemo's title links navigate via JS, which is
            # exactly why divergence-aware replay exists.
            _el("#item_4_title_link", "Sauce Labs Backpack", tag="a"),
            _el("#add-to-cart-sauce-labs-backpack", "add to cart sauce labs backpack"),
            _el("#add-to-cart-sauce-labs-bolt-t-shirt", "add to cart bolt t-shirt"),
        ],
    }
    trail = ObservedTrail(
        steps=[
            ObservedStep(
                0,
                "click",
                description="login button",
                from_url=SEED,
                to_url=INVENTORY,
                navigated=True,
                scraped=True,
                selector_used="#login-button",
            ),
            # The scraper clicked the backpack ADD button (not the title link):
            ObservedStep(
                1,
                "click",
                description="Sauce Labs Backpack",
                from_url=INVENTORY,
                to_url=INVENTORY,
                navigated=False,
                scraped=True,
                selector_used="#add-to-cart-sauce-labs-backpack",
            ),
        ]
    )
    skeleton, journey = _build("test_replay", [("CLICK", "login button"), ("CLICK", "Sauce Labs Backpack")])
    code = _resolve(skeleton, [journey], data, {"test_replay": trail})
    # Replay uses the scraper's proven selectors verbatim.
    assert "'#login-button'" in code
    assert "'#add-to-cart-sauce-labs-backpack'" in code
    assert "pytest.skip" not in code


def test_observed_selector_not_replayed_after_failed_step() -> None:
    """A trail step that ERRORED has no proven selector — selector_used from a
    failed attempt must NOT be replayed."""
    data: dict[str, list[dict[str, Any]]] = {
        SEED: [_el("#login-button", "login button")],
        INVENTORY: [_el("#item_4_title_link", "Sauce Labs Backpack", tag="a")],
    }
    trail = ObservedTrail(
        steps=[
            ObservedStep(
                0,
                "click",
                description="Sauce Labs Backpack",
                from_url=INVENTORY,
                to_url=INVENTORY,
                navigated=False,
                scraped=False,
                selector_used="#guessed-selector",
                error="locator_not_found_even_relaxed",
            ),
        ]
    )
    skeleton, journey = _build("test_failed_sel", [("CLICK", "Sauce Labs Backpack")])
    code = _resolve(skeleton, [journey], data, {"test_failed_sel": trail})
    assert "#guessed-selector" not in code


def test_trailing_slash_urls_still_verify() -> None:
    """Trail URLs come from page.url ('…com/') while scrape keys are normalised
    ('…com') — membership checks must not be broken by the trailing slash."""
    data: dict[str, list[dict[str, Any]]] = {
        # Keys WITHOUT trailing slash:
        SEED: [_el("#login-button", "login button")],
        INVENTORY: [_el(".shopping_cart_link", "cart icon", tag="a")],
    }
    trail = ObservedTrail(
        steps=[
            # page.url reports the seed WITH a trailing slash:
            ObservedStep(
                0,
                "click",
                description="login button",
                from_url=SEED + "/",
                to_url=INVENTORY,
                navigated=True,
                scraped=True,
                selector_used="#login-button",
            ),
            ObservedStep(
                1,
                "click",
                description="cart icon",
                from_url=INVENTORY,
                to_url=CART,
                navigated=True,
                scraped=False,
                selector_used=".shopping_cart_link",
            ),
        ]
    )
    skeleton, journey = _build("test_slash", [("CLICK", "login button"), ("CLICK", "cart icon")])
    code = _resolve(skeleton, [journey], data, {"test_slash": trail})
    # Both steps replay their proven selectors (no honest skips from URL mismatch).
    assert "'#login-button'" in code
    assert "'.shopping_cart_link'" in code
    assert "pytest.skip" not in code


# ── Divergence-aware replay + verified-href advance ───────────────────


def test_divergent_verified_href_keeps_resolvers_pick() -> None:
    """'Cart' scenario (verify run 2026-08-22): the scraper clicked an add-to-cart
    button for 'Cart', but the resolver's pick (.shopping_cart_link) carries a
    real href to a SCRAPED page — keep ours; the anchor advances to cart.html."""
    data: dict[str, list[dict[str, Any]]] = {
        SEED: [_el("#login-button", "login button")],
        INVENTORY: [
            _el(".shopping_cart_link", "cart icon", tag="a", href=CART),
            _el("#add-to-cart-sauce-labs-bolt-t-shirt", "add to cart bolt t-shirt"),
        ],
        CART: [_el(".btn.check_out", "proceed to checkout")],
    }
    trail = ObservedTrail(
        steps=[
            ObservedStep(
                0,
                "click",
                description="login button",
                from_url=SEED,
                to_url=INVENTORY,
                navigated=True,
                scraped=True,
                selector_used="#login-button",
            ),
            # The scraper clicked a wrong add-to-cart button for 'Cart':
            ObservedStep(
                1,
                "click",
                description="cart icon",
                from_url=INVENTORY,
                to_url=INVENTORY,
                navigated=False,
                scraped=True,
                selector_used="#add-to-cart-sauce-labs-bolt-t-shirt",
            ),
        ]
    )
    skeleton, journey = _build("test_cart_href", [("CLICK", "login button"), ("CLICK", "cart icon")])
    code = _resolve(skeleton, [journey], data, {"test_cart_href": trail})
    assert ".shopping_cart_link" in code
    assert "pytest.skip" not in code


# ── Proven-static click + navigation intent → emit navigation ─────────


def test_proven_static_click_with_nav_intent_becomes_navigation() -> None:
    """'Cart' scenario: BOTH the scraper and the resolver picked a non-navigating
    add-to-cart button for 'Cart', and the trail proves the click never navigated.
    With a verified cart page in the inventory, emit a navigation instead."""
    data: dict[str, list[dict[str, Any]]] = {
        SEED: [_el("#login-button", "login button")],
        INVENTORY: [
            _el(".shopping_cart_link", "", tag="a", href=CART),  # icon: no text
            _el("#add-to-cart-sauce-labs-bolt-t-shirt", "add to cart bolt t-shirt"),
        ],
        CART: [_el(".btn.check_out", "proceed to checkout")],
    }
    trail = ObservedTrail(
        steps=[
            ObservedStep(
                0,
                "click",
                description="login button",
                from_url=SEED,
                to_url=INVENTORY,
                navigated=True,
                scraped=True,
                selector_used="#login-button",
            ),
            # Scraper clicked bolt-add for 'Cart' — provably stayed put:
            ObservedStep(
                1,
                "click",
                description="Cart",
                from_url=INVENTORY,
                to_url=INVENTORY,
                navigated=False,
                scraped=False,
                selector_used="#add-to-cart-sauce-labs-bolt-t-shirt",
            ),
        ]
    )
    skeleton, journey = _build("test_proven_static", [("CLICK", "login button"), ("CLICK", "Cart")])
    code = _resolve(skeleton, [journey], data, {"test_proven_static": trail})
    # The dead click is replaced by a verified navigation.
    assert repr(CART) in code or "navigate" in code
    assert "pytest.skip" not in code


def test_divergence_latches_trail_no_longer_trusted() -> None:
    """After OUR path departs from the observed one (proven-static 'Cart' became
    a verified navigation to cart.html), later trail steps must NOT drag scope
    back to the scraper's stale page nor replay its garbage selector."""
    data: dict[str, list[dict[str, Any]]] = {
        SEED: [_el("#login-button", "login button")],
        INVENTORY: [
            _el(".shopping_cart_link", "", tag="a", href=CART),
            _el("#add-to-cart-sauce-labs-bolt-t-shirt", "add to cart bolt t-shirt"),
            _el("#react-burger-menu-btn", "open menu"),
        ],
        CART: [_el("#checkout", "checkout"), _el(".btn.check_out", "proceed to checkout")],
    }
    trail = ObservedTrail(
        steps=[
            ObservedStep(
                0,
                "click",
                description="login button",
                from_url=SEED,
                to_url=INVENTORY,
                navigated=True,
                scraped=True,
                selector_used="#login-button",
            ),
            # Scraper's 'Cart' click stayed on inventory (wrong button):
            ObservedStep(
                1,
                "click",
                description="Cart",
                from_url=INVENTORY,
                to_url=INVENTORY,
                navigated=False,
                scraped=False,
                selector_used="#add-to-cart-sauce-labs-bolt-t-shirt",
            ),
            # Scraper's 'Checkout' click also on inventory (burger menu garbage):
            ObservedStep(
                2,
                "click",
                description="Checkout",
                from_url=INVENTORY,
                to_url=INVENTORY,
                navigated=False,
                scraped=False,
                selector_used="#react-burger-menu-btn",
            ),
        ]
    )
    skeleton, journey = _build("test_latch", [("CLICK", "login button"), ("CLICK", "Cart"), ("CLICK", "Checkout")])
    code = _resolve(skeleton, [journey], data, {"test_latch": trail})
    # 'Cart' becomes a verified navigation; 'Checkout' then resolves from the
    # cart page scope (#checkout), NOT the burger menu from the stale path.
    assert repr(CART) in code
    assert "#react-burger-menu-btn" not in code


# ── Index alignment (plan open question #1) ───────────────────────────────


def test_trail_map_matches_by_description_across_action_kinds() -> None:
    """ "ASSERT→scrape" and "GOTO→navigate" mapping holds; unmatched GOTOs (no
    scraping step produced) do not desync later matches (monotonic cursor)."""
    journey = _build(
        "test_align",
        [("GOTO", "products"), ("CLICK", "login button"), ("ASSERT", "inventory visible")],
    )[1]
    trail_steps = [
        ObservedStep(
            0, "click", description="login button", from_url=SEED, to_url=INVENTORY, navigated=True, scraped=True
        ),
        ObservedStep(1, "scrape", description="inventory visible", from_url=INVENTORY, to_url=INVENTORY, scraped=True),
        ObservedStep(2, "scrape", description="final page state", from_url=INVENTORY, to_url=INVENTORY, scraped=True),
    ]
    mapping = PlaceholderOrchestrator._map_trail_to_placeholders(journey, trail_steps)
    # GOTO "products" produced no navigate step → unmatched.
    assert len(mapping) == 2
    assert mapping[_token("CLICK", "login button")].to_url == INVENTORY
    assert mapping[_token("ASSERT", "inventory visible")].action == "scrape"


def test_strict_scope_never_returns_all_pages_fallback() -> None:
    """strict_scope=True: empty verified scope → honest skip, not all-pages search."""
    orch = PlaceholderOrchestrator()

    async def drive() -> tuple[str, str | None]:
        resolved, next_url, _at = await orch._resolve_placeholder_for_page(
            action="CLICK",
            description="nonexistent widget",
            current_url=CART,  # in scraped_data but has no matching element
            scraped_data={CART: [], INVENTORY: [_el(JACKET_BUTTON, "add to cart")]},
            strict_scope=True,
        )
        return resolved, next_url

    resolved, next_url = asyncio.run(drive())
    assert "pytest.skip" in resolved
    assert next_url is None


def test_skip_message_quotes_descriptions_safely() -> None:
    """Descriptions containing quotes must not break the emitted pytest.skip()."""
    weird = "click 'absent' widget"
    data = {INVENTORY: [_el("#special-item", "special item")]}
    trail = ObservedTrail(
        steps=[
            ObservedStep(0, "click", description=weird, from_url=INVENTORY, to_url=ITEM4, navigated=True, scraped=False)
        ]
    )
    skeleton, journey = _build("test_quote_safe", [("CLICK", weird)])
    code = _resolve(skeleton, [journey], data, {"test_quote_safe": trail})
    match = re.search(r"pytest\.skip\(", code)
    assert match, f"expected a skip in output:\n{code}"
