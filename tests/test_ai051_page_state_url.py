"""AI-051: B-021 page-state URL assertions must assert the OBSERVED landing page.

Root cause: a page-state ASSERT ("page loaded", "home page title", "logged in")
was resolved by keyword-matching the description against scraped pages
(``resolve_url``). When the preceding action navigated to a page that was NEVER
scraped (e.g. saucedemo Login: home -> ``/inventory.html``), the keyword match
fell back to the base/starting URL, producing
``expect(page).to_have_url("https://www.saucedemo.com/")`` after a login click —
which always fails because saucedemo redirects to ``/inventory.html``.

Fix: when the observed trail evidences the step's landing page differs from the
keyword-inferred one, assert the trail's ``to_url`` (a browser fact). See
``docs/sessions/`` AI-051 record.
"""

from __future__ import annotations

import asyncio
from typing import Any

from src.journey_models import ObservedStep, ObservedTrail
from src.pipeline_models import PlaceholderUse, TestJourney, TestStep
from src.placeholder_orchestrator import PlaceholderOrchestrator

SEED = "https://www.saucedemo.com"
INVENTORY = "https://www.saucedemo.com/inventory.html"


def _el(selector: str, text: str, **extra: Any) -> dict[str, Any]:
    element: dict[str, Any] = {"selector": selector, "text": text, "tag": "button", "role": "button"}
    element.update(extra)
    return element


def _token(action: str, description: str) -> str:
    return "{{" + f"{action}:{description}" + "}}"


def _build(name: str, placeholders: list[tuple[str, str]]) -> tuple[str, TestJourney]:
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


def _login_data() -> dict[str, list[dict[str, Any]]]:
    """Base page + post-login inventory page scraped (both in the trail)."""
    return {
        SEED: [
            _el("#user-name", "username", tag="input", role="textbox"),
            _el("#password", "password", tag="input", role="textbox"),
            _el("#login-button", "login button"),
        ],
        INVENTORY: [
            _el("#item_1_title_link", "Sauce Labs Backpack", tag="a", href=""),
        ],
    }


def _login_trail() -> ObservedTrail:
    """Factual trail: the Login CLICK navigated home -> /inventory.html."""
    return ObservedTrail(
        steps=[
            ObservedStep(0, "fill", description="username", from_url="", to_url=SEED, scraped=True),
            ObservedStep(1, "fill", description="password", from_url=SEED, to_url=SEED, scraped=False),
            ObservedStep(
                2, "click", description="login button", from_url=SEED, to_url=INVENTORY, navigated=True, scraped=True
            ),
            # The page-state ASSERT is a "scrape" step observed ON /inventory.html.
            ObservedStep(
                3, "scrape", description="inventory page loaded", from_url=INVENTORY, to_url=INVENTORY, scraped=True
            ),
        ]
    )


def test_login_assert_uses_observed_landing_url() -> None:
    """The AI-051 repro: after Login, assert /inventory.html, not the base URL."""
    skeleton, journey = _build(
        "test_01_login",
        [
            ("FILL", "username:standard_user"),
            ("FILL", "password:secret_sauce"),
            ("CLICK", "login button"),
            ("ASSERT", "inventory page loaded"),
        ],
    )
    result = _resolve(skeleton, [journey], _login_data(), {"test_01_login": _login_trail()})

    # The assertion must target the observed post-login landing page…
    assert f'expect(page).to_have_url("{INVENTORY}")' in result
    # …and must NOT be the base/starting URL (the AI-051 bug).
    assert f'expect(page).to_have_url("{SEED}")' not in result


def test_no_trail_keeps_legacy_keyword_resolution() -> None:
    """Back-compat: without a trail, behaviour is exactly as before AI-051."""
    skeleton, journey = _build(
        "test_01_login",
        [
            ("CLICK", "login button"),
            ("ASSERT", "home page loaded"),
        ],
    )
    # "home page loaded" resolves to the base URL via the root-path guard
    # (home is a root-style term). No trail → no override → base URL stays.
    result = _resolve(skeleton, [journey], _login_data(), None)
    assert f'expect(page).to_have_url("{SEED}/")' in result


def test_assert_on_scraped_landing_stays_on_landing() -> None:
    """When the keyword-resolved page == the observed landing page, no flip."""
    data = {
        SEED: [_el("#login-button", "login button")],
        INVENTORY: [_el("#item_1", "Sauce Labs Backpack", tag="a", href="#")],
    }
    trail = ObservedTrail(
        steps=[
            ObservedStep(
                0, "click", description="login button", from_url=SEED, to_url=INVENTORY, navigated=True, scraped=True
            ),
            ObservedStep(1, "scrape", description="products page", from_url=INVENTORY, to_url=INVENTORY, scraped=True),
        ]
    )
    skeleton, journey = _build(
        "test_02_products",
        [
            ("CLICK", "login button"),
            ("ASSERT", "products page"),
        ],
    )
    result = _resolve(skeleton, [journey], data, {"test_02_products": trail})
    # "products page" (a B-021 term) keyword-resolves to /inventory.html (the
    # only page with product words), and the observed landing is ALSO inventory →
    # identical, so no flip. The base URL must not be asserted.
    assert f'expect(page).to_have_url("{SEED}/")' not in result


def test_no_override_when_keyword_and_observed_agree() -> None:
    """When keyword resolution and the trail land on the SAME page, output is stable."""
    data = {
        SEED: [_el("#cart_link", "cart", tag="a", href=INVENTORY)],
        INVENTORY: [_el("#item_1", "backpack", tag="a", href="#")],
    }
    # A page-state assert whose keyword resolves to a page that the trail also
    # confirms: no spurious flip.
    trail = ObservedTrail(
        steps=[
            ObservedStep(0, "navigate", description="home", from_url="", to_url=SEED, scraped=True),
            ObservedStep(1, "scrape", description="home page loaded", from_url=SEED, to_url=SEED, scraped=True),
        ]
    )
    skeleton, journey = _build(
        "test_03_home",
        [
            ("GOTO", "home"),
            ("ASSERT", "home page loaded"),
        ],
    )
    result = _resolve(skeleton, [journey], data, {"test_03_home": trail})
    # home page loaded resolves to the base URL; trail to_url is also base → no change.
    assert f'expect(page).to_have_url("{SEED}/")' in result
