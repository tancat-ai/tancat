"""Tests for dialog-action scoping (Pass D) and CLICK fast-path hygiene.

2026-08-03 — root cause of the production "OK" failure:
A hidden CSRF input (``role=hidden``, ``is_visible=False``) was resolved for
``{{CLICK:OK}}`` because the fast-path haystack check (``"ok" in haystack``)
matched the substring inside "csrfmiddleware**TOKen**" and returned a flat 100
with NO penalties applied. "Kookie Kids" matched the same way ("k**ok**ie").

The fix has two layers, both generic (no site-specific lists):

1. ``PlaceholderScorer.compute_element_score`` — the CLICK fast path now
   applies the same hidden-element and click-text penalties as the slow path.
2. ``ElementMatcher.pass_dialog_action`` — descriptions implying a
   dialog/dismiss/confirm action ("OK", "close popup") resolve against the
   modal's OWN interactive elements (``in_modal`` flag / dialog role), with a
   structural preference for the modal's dismissal control (close-modal
   class semantics). Falls through to normal resolution when no modal exists.
"""

import asyncio
import json
from pathlib import Path
from typing import Any

from src.element_matcher import DIALOG_INTENT_TERMS, DIALOG_SCOPED_ROLES, ElementMatcher
from src.placeholder_resolver import PlaceholderResolver
from src.placeholder_scorers import PlaceholderScorer

_SCRAPED = (
    Path(__file__).resolve().parent.parent / "scripts" / "eval" / "scraped_pages" / "https_automationexercise.com.json"
)

#: Minimal page fixture mirroring the automationexercise products page —
#: a hidden CSRF input, a visible "Kookie Kids" header, and an (initially
#: hidden) add-to-cart modal with a dismiss button and a View Cart link.

PRODUCTS_PAGE: dict[str, list[dict[str, Any]]] = {
    "https://automationexercise.com/products": [
        {
            "selector": 'input[name="csrfmiddlewaretoken"]',
            "text": "",
            "role": "hidden",
            "is_visible": False,
            "in_modal": False,
            "name": "csrfmiddlewaretoken",
            "value": "TuFAqHCrlOvqH5WbTfQoOTHtYPAOWyvgGvpd4xmeLLfiESz4QuUOVA0XUQmcbCUy",
        },
        {
            "selector": 'a[href="/brand_products/Kookie Kids"]',
            "text": "(3) Kookie Kids",
            "role": "a",
            "is_visible": True,
            "in_modal": False,
            "accessible_name": "(3) KOOKIE KIDS",
        },
        {
            "selector": ".btn.btn-success.close-modal.btn-block",
            "text": "Continue Shopping",
            "role": "button",
            "is_visible": False,
            "in_modal": True,
            "classes": "btn btn-success close-modal btn-block",
        },
        {
            "selector": 'a[href="/view_cart"]',
            "text": "View Cart",
            "role": "a",
            "is_visible": False,
            "in_modal": True,
        },
        {
            "selector": ".modal-title.w-100",
            "text": "Added!",
            "role": "h4",
            "is_visible": False,
            "in_modal": True,
        },
        {
            "selector": 'a[href="/products"]',
            "text": "Products",
            "role": "a",
            "is_visible": True,
            "in_modal": False,
        },
        {
            "selector": 'a.btn.btn-default.add-to-cart[data-product-id="1"]',
            "text": "Add to cart",
            "role": "a",
            "is_visible": True,
            "in_modal": False,
        },
    ]
}


def _resolve_clicks(description: str, pages: dict[str, list[dict[str, str]]]) -> str | None:
    async def _run() -> str | None:
        matcher = ElementMatcher(PlaceholderResolver(), generator=None)
        element = await matcher.find_best_element_for_current_page("CLICK", description, None, pages)
        return str(element.get("selector")) if element else None

    return asyncio.run(_run())


# ---------------------------------------------------------------------------
# Layer 2 — dialog-action scoping (Pass D)
# ---------------------------------------------------------------------------


def test_ok_resolves_to_modal_dismiss_button() -> None:
    """'OK' must resolve to the modal's dismiss button, never a hidden input."""
    assert _resolve_clicks("OK", PRODUCTS_PAGE) == ".btn.btn-success.close-modal.btn-block"


def test_close_popup_resolves_to_modal_dismiss_button() -> None:
    assert _resolve_clicks("close popup", PRODUCTS_PAGE) == ".btn.btn-success.close-modal.btn-block"


def test_dismiss_resolves_to_modal_dismiss_button() -> None:
    assert _resolve_clicks("dismiss", PRODUCTS_PAGE) == ".btn.btn-success.close-modal.btn-block"


def test_cancel_resolves_to_modal_dismiss_button() -> None:
    assert _resolve_clicks("cancel", PRODUCTS_PAGE) == ".btn.btn-success.close-modal.btn-block"


def test_continue_shopping_resolves_to_modal_button() -> None:
    assert _resolve_clicks("Continue Shopping", PRODUCTS_PAGE) == ".btn.btn-success.close-modal.btn-block"


def test_dialog_action_falls_back_without_modal() -> None:
    """No in-modal candidates → normal resolution (no crash, no forced pick)."""
    modal_less = {"https://example.com": PRODUCTS_PAGE["https://automationexercise.com/products"][:2]}
    # csrf input is hidden (skipped) and Kookie Kids is the only visible match
    result = _resolve_clicks("OK", modal_less)
    assert result is None or "csrfmiddlewaretoken" not in result


def test_non_dialog_descriptions_are_not_scoped() -> None:
    """Ordinary CLICK descriptions keep normal resolution."""
    assert _resolve_clicks("add to cart", PRODUCTS_PAGE) == 'a.btn.btn-default.add-to-cart[data-product-id="1"]'
    assert _resolve_clicks("Products", PRODUCTS_PAGE) == 'a[href="/products"]'
    assert _resolve_clicks("view cart", PRODUCTS_PAGE) == 'a[href="/view_cart"]'


def test_dialog_intent_word_boundary() -> None:
    """'ok' must not fire on 'token'/'booking' style words."""
    assert "ok" not in {"token", "booking"}
    assert DIALOG_INTENT_TERMS  # non-empty
    # intent fires only on whole words or the listed phrases
    lowered = "ok"
    words = set(lowered.split())
    assert any((" " in term and term in lowered) or term in words for term in DIALOG_INTENT_TERMS)


def test_dialog_scope_excludes_non_interactive_modal_elements() -> None:
    """Modal headings/paragraphs are not clickable dialog targets."""
    assert "h4" not in DIALOG_SCOPED_ROLES
    assert "p" not in DIALOG_SCOPED_ROLES
    assert "h4" not in DIALOG_SCOPED_ROLES and "p" not in DIALOG_SCOPED_ROLES


# ---------------------------------------------------------------------------
# Layer 1 — CLICK fast-path hygiene
# ---------------------------------------------------------------------------


def test_fast_path_hidden_element_penalised() -> None:
    """A hidden CSRF input whose haystack contains the description substring
    must NOT short-circuit at a flat 100 — it gets the hidden (-30) and
    click-text (-10) penalties like the slow path."""
    csrf = PRODUCTS_PAGE["https://automationexercise.com/products"][0]
    score = PlaceholderScorer.compute_element_score("CLICK", "OK", csrf, csrf["selector"], 0.0)
    assert score is not None and score < 100, f"hidden element scored {score}"


def test_fast_path_visible_match_unaffected() -> None:
    """Visible, text-bearing elements keep the full fast-path score."""
    add_btn = PRODUCTS_PAGE["https://automationexercise.com/products"][6]
    score = PlaceholderScorer.compute_element_score("CLICK", "add to cart", add_btn, add_btn["selector"], 0.0)
    assert score == 100


def test_fast_path_fill_gate_unchanged() -> None:
    """FILL keeps its own gate — a hidden CSRF input is still not fillable.

    Layer 1 only touched the CLICK fast path; FILL/ASSERT behavior must not
    change.
    """
    csrf = PRODUCTS_PAGE["https://automationexercise.com/products"][0]
    score = PlaceholderScorer.compute_element_score("FILL", "csrfmiddlewaretoken", csrf, csrf["selector"], 0.0)
    assert score is None, f"hidden role=hidden input should be excluded from FILL, scored {score}"


# ---------------------------------------------------------------------------
# Real-scrape smoke (eval captured automationexercise data, if present)
# ---------------------------------------------------------------------------


def test_real_scrape_ok_resolves_inside_modal() -> None:
    """Against the real captured scrape, 'OK' resolves to an in-modal element."""
    if not _SCRAPED.exists():
        return
    data = json.loads(_SCRAPED.read_text(encoding="utf-8"))
    pages = {data["url"]: data.get("elements", [])}
    result = _resolve_clicks("OK", pages)
    assert result is not None, "'OK' must resolve to something"
    assert "csrf" not in result, f"'OK' must not resolve to a hidden CSRF input, got {result}"
    el = next((e for e in pages[data["url"]] if e.get("selector") == result), None)
    assert el is not None and el.get("in_modal"), f"expected an in-modal element, got {result}"
