"""B-090 / B-092 — page-fact and content criteria must check the real thing.

The Session 7 landing-page re-run (2026-09-24) reported 31 passed, but several
of those "passes" checked nothing:

- **B-090** (geometric/page facts): criteria 3 ("at least four capability
  cards"), 6 (natural width > 0), 7 (no broken images) and 35 (no horizontal
  scroll at 375px) all emitted ``assert_visible(<one element>)``.
- **B-092** (content / wrong element): criterion 1 checked a ``<p>`` instead of
  the ``<h1>``; 4 never read the install command; 8 checked the tab button not
  the image; 11 checked a heading not a price; 18/19 checked one link, not
  "every".

This module pins the classifier + emitter for those families and the
element-kind scoping that stops the wrong-element resolutions.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from src.code_postprocessor import (
    page_fact_from_description,
    replace_token_in_line,
)
from src.content_scoping import (
    is_heading_criterion,
    is_image_criterion,
    is_image_element,
    kind_matches,
    scope_pages_to_headings,
    scope_pages_to_images,
)
from src.element_matcher import ElementMatcher
from src.evidence_tracker import EvidenceTracker
from src.placeholder_orchestrator import _is_page_level_assert
from src.placeholder_resolver import PlaceholderResolver

# ---------------------------------------------------------------------------
# Classifier — Session 7 descriptions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("description", "method"),
    [
        ("no broken images", "assert_no_broken_images"),
        ("no image on the page is broken", "assert_no_broken_images"),
        ("every image element has a non-zero natural width", "assert_no_broken_images"),
        ("all images loaded", "assert_no_broken_images"),
        ("hero product screenshot loaded", "assert_natural_width"),
        ("Noir Art artwork image loaded", "assert_natural_width"),
        ("no horizontal scroll at 375px", "assert_no_horizontal_scroll"),
        ("the page does not scroll horizontally at 375 pixels", "assert_no_horizontal_scroll"),
        ("at least four capability cards", "assert_count_at_least"),
        ("at least 4 cards", "assert_count_at_least"),
        ("anchor links resolve", "assert_anchor_targets_exist"),
        (
            "Every same-page anchor link on the page points at an element that exists",
            "assert_anchor_targets_exist",
        ),
        (
            "Every header navigation link scrolls to a section that exists on the page",
            "assert_anchor_targets_exist",
        ),
        ("git clone https://github.com/tancat-ai/tancat", "assert_text_contains"),
        ("$0 / forever", "assert_text_contains"),
        ("Pro Deployment price", "assert_section_has_price"),
        ("Air-Gap price", "assert_section_has_price"),
    ],
)
def test_session7_descriptions_are_classified(description: str, method: str) -> None:
    check = page_fact_from_description(description, resolved_selector="img.hero")
    assert check is not None, f"not classified: {description!r}"
    assert check.method == method


def test_count_assertion_carries_the_minimum() -> None:
    check = page_fact_from_description("at least four capability cards")
    assert check is not None
    assert check.minimum == 4
    assert check.selector


def test_scroll_assertion_carries_the_viewport_width() -> None:
    check = page_fact_from_description("no horizontal scroll at 375px")
    assert check is not None
    assert check.width == 375
    # Default width when the criterion omits it.
    default = page_fact_from_description("no horizontal scroll")
    assert default is not None and default.width == 375


def test_price_section_is_extracted() -> None:
    check = page_fact_from_description("Pro Deployment price")
    assert check is not None
    assert check.section == "Pro Deployment"
    check2 = page_fact_from_description("the Air-Gap / Defense tier is shown with a price")
    assert check2 is not None
    assert "Air-Gap / Defense" in check2.section


def test_natural_width_needs_a_resolved_selector() -> None:
    assert page_fact_from_description("hero product screenshot natural width", "img.hero") is not None
    assert page_fact_from_description("hero product screenshot natural width", "") is None
    assert page_fact_from_description("hero product screenshot natural width", 'pytest.skip("x")') is None
    # "loaded" on an image criterion is the same fact as a natural-width check.
    check = page_fact_from_description("hero product screenshot loaded", "#view-product-ui img")
    assert check is not None and check.method == "assert_natural_width"


def test_section_heading_is_not_mistaken_for_the_install_command() -> None:
    assert page_fact_from_description("Clone + uv sync + run section") is None
    assert page_fact_from_description("Clone + uv sync + run") is None
    assert page_fact_from_description("git clone https://github.com/tancat-ai/tancat") is not None


def test_price_section_strips_leading_inside() -> None:
    check = page_fact_from_description("price inside Air-Gap / Defense tier")
    assert check is not None
    assert check.section == "Air-Gap / Defense"


@pytest.mark.parametrize(
    "description",
    ["hero headline visible", "Air-Gap / Defense tier", "Copy Command button", "Per deployment, not per seat"],
)
def test_ordinary_descriptions_are_not_page_facts(description: str) -> None:
    assert page_fact_from_description(description) is None


def test_page_level_asserts_never_trigger_the_journey_skip() -> None:
    assert _is_page_level_assert("ASSERT", "no broken images")
    assert _is_page_level_assert("ASSERT", "no horizontal scroll at 375px")
    assert _is_page_level_assert("ASSERT", "at least four capability cards")
    assert _is_page_level_assert("ASSERT", "anchor links resolve")
    assert _is_page_level_assert("ASSERT", "git clone https://github.com/tancat-ai/tancat")
    assert _is_page_level_assert("ASSERT", "Pro Deployment price")
    # Natural width still needs resolution — an unresolved result must skip.
    assert not _is_page_level_assert("ASSERT", "hero product screenshot natural width")
    assert not _is_page_level_assert("ASSERT", "hero headline visible")


# ---------------------------------------------------------------------------
# Emitter
# ---------------------------------------------------------------------------


def _emit(description: str, resolved: str = "'p.hero'", assertion_type: str = "toBeVisible") -> str:
    token = f"{{{{ASSERT:{description}}}}}"
    return replace_token_in_line(
        f"    {token}", "ASSERT", token, resolved, set(), description, assertion_type=assertion_type
    ).strip()


def test_broken_images_emit_page_scan() -> None:
    assert _emit("no broken images") == "evidence_tracker.assert_no_broken_images(label='no broken images')"


def test_natural_width_emit_uses_resolved_image() -> None:
    out = _emit("hero product screenshot natural width", resolved="'#view-product-ui img'")
    assert out == (
        "evidence_tracker.assert_natural_width('#view-product-ui img', label='hero product screenshot natural width')"
    )


def test_count_emit_uses_lower_bound() -> None:
    out = _emit("at least four capability cards")
    assert out.startswith("evidence_tracker.assert_count_at_least(")
    assert ", 4, label=" in out
    assert "assert_visible" not in out


def test_scroll_emit_passes_viewport_width() -> None:
    out = _emit("no horizontal scroll at 375px")
    assert out == "evidence_tracker.assert_no_horizontal_scroll(width=375, label='no horizontal scroll at 375px')"


def test_anchor_scan_emit_has_no_resolved_element() -> None:
    out = _emit("anchor links resolve")
    assert out == "evidence_tracker.assert_anchor_targets_exist(label='anchor links resolve')"
    assert "assert_visible" not in out


def test_install_command_emit_reads_page_copy() -> None:
    out = _emit("git clone https://github.com/tancat-ai/tancat")
    assert out == (
        "evidence_tracker.assert_text_contains('body', "
        "'git clone https://github.com/tancat-ai/tancat', "
        "label='git clone https://github.com/tancat-ai/tancat')"
    )


def test_price_emit_is_section_scoped() -> None:
    out = _emit("Pro Deployment price")
    assert out == "evidence_tracker.assert_section_has_price('Pro Deployment', label='Pro Deployment price')"


def test_emitted_page_fact_lines_compile() -> None:
    for description in [
        "no broken images",
        "no horizontal scroll at 375px",
        "at least four capability cards",
        "anchor links resolve",
        "git clone https://github.com/tancat-ai/tancat",
        "Pro Deployment price",
        "hero product screenshot natural width",
    ]:
        out = _emit(description, resolved="'#view-product-ui img'")
        compile("def _emitted() -> None:\n    " + out + "\n", "<emitted>", "exec")


# ---------------------------------------------------------------------------
# EvidenceTracker — page-fact methods
# ---------------------------------------------------------------------------


def _page_tracker(tmp_path: Any) -> tuple[EvidenceTracker, MagicMock]:
    page = MagicMock()
    page.url = "https://example.com"
    return EvidenceTracker(page, "test_b090", evidence_root=Path(tmp_path)), page


def test_no_broken_images_passes_when_all_loaded(tmp_path: Any) -> None:
    tracker, page = _page_tracker(tmp_path)
    page.evaluate.side_effect = [None, [], 3]
    tracker.assert_no_broken_images(label="no broken images")
    assert tracker.steps[-1]["result"]["status"] == "passed"


def test_no_broken_images_fails_and_names_the_offender(tmp_path: Any) -> None:
    tracker, page = _page_tracker(tmp_path)
    page.evaluate.side_effect = [None, ["broken.png"]]
    with pytest.raises(AssertionError, match="broken.png"):
        tracker.assert_no_broken_images(label="no broken images")


def test_natural_width_passes_for_loaded_image(tmp_path: Any) -> None:
    tracker, page = _page_tracker(tmp_path)
    loc = MagicMock()
    loc.evaluate.return_value = 1280
    page.locator.return_value.first = loc
    tracker.assert_natural_width("#view-product-ui img", label="hero screenshot")
    assert tracker.steps[-1]["result"]["status"] == "passed"


def test_natural_width_fails_for_broken_image(tmp_path: Any) -> None:
    tracker, page = _page_tracker(tmp_path)
    loc = MagicMock()
    loc.evaluate.return_value = 0
    page.locator.return_value.first = loc
    with pytest.raises(AssertionError, match="not loaded"):
        tracker.assert_natural_width("#view-product-ui img", label="hero screenshot")


def test_no_horizontal_scroll_passes_and_restores_viewport(tmp_path: Any) -> None:
    tracker, page = _page_tracker(tmp_path)
    page.viewport_size = {"width": 1280, "height": 800}
    page.evaluate.return_value = {"scrollWidth": 375, "clientWidth": 375}
    tracker.assert_no_horizontal_scroll(width=375, label="no horizontal scroll")
    assert tracker.steps[-1]["result"]["status"] == "passed"
    page.set_viewport_size.assert_any_call({"width": 375, "height": 800})
    page.set_viewport_size.assert_any_call({"width": 1280, "height": 800})


def test_no_horizontal_scroll_fails_when_page_overflows(tmp_path: Any) -> None:
    tracker, page = _page_tracker(tmp_path)
    page.viewport_size = {"width": 1280, "height": 800}
    page.evaluate.return_value = {"scrollWidth": 600, "clientWidth": 375}
    with pytest.raises(AssertionError, match="scrolls horizontally"):
        tracker.assert_no_horizontal_scroll(width=375, label="no horizontal scroll")


def test_count_at_least_passes_at_the_boundary(tmp_path: Any) -> None:
    tracker, page = _page_tracker(tmp_path)
    page.locator.return_value.count.return_value = 4
    tracker.assert_count_at_least('[class*="card"]', 4, label="four cards")
    assert tracker.steps[-1]["result"]["status"] == "passed"


def test_count_at_least_fails_below_the_boundary(tmp_path: Any) -> None:
    tracker, page = _page_tracker(tmp_path)
    page.locator.return_value.count.return_value = 3
    with pytest.raises(AssertionError, match="at least 4"):
        tracker.assert_count_at_least('[class*="card"]', 4, label="four cards")


def test_anchor_targets_exist_passes_when_none_missing(tmp_path: Any) -> None:
    tracker, page = _page_tracker(tmp_path)
    page.evaluate.side_effect = [[], 6]
    tracker.assert_anchor_targets_exist(label="every anchor")
    assert tracker.steps[-1]["result"]["status"] == "passed"


def test_anchor_targets_exist_fails_and_names_the_fragment(tmp_path: Any) -> None:
    tracker, page = _page_tracker(tmp_path)
    page.evaluate.side_effect = [["#nowhere"], 6]
    with pytest.raises(AssertionError, match="#nowhere"):
        tracker.assert_anchor_targets_exist(label="every anchor")


def _price_tracker(tmp_path: Any, container_count: int, text: str) -> EvidenceTracker:
    page = MagicMock()
    page.url = "https://example.com"
    heading = MagicMock()
    container = MagicMock()
    container.count.return_value = container_count
    container.first.text_content.return_value = text
    chain = MagicMock()
    chain.filter.return_value = chain
    chain.last = container
    page.locator.side_effect = lambda sel: heading if ":has-text(" in sel else chain
    return EvidenceTracker(page, "test_b092_price", evidence_root=Path(tmp_path))


def test_section_has_price_passes_when_amount_present(tmp_path: Any) -> None:
    tracker = _price_tracker(tmp_path, 1, "Pro Deployment $399 / month / deployment")
    tracker.assert_section_has_price("Pro Deployment", label="Pro price")
    assert tracker.steps[-1]["result"]["status"] == "passed"


def test_section_has_price_fails_without_an_amount(tmp_path: Any) -> None:
    tracker = _price_tracker(tmp_path, 1, "Pro Deployment unlimited runs")
    with pytest.raises(AssertionError, match="shows no price"):
        tracker.assert_section_has_price("Pro Deployment", label="Pro price")


# ---------------------------------------------------------------------------
# content_scoping — image / heading kind gates
# ---------------------------------------------------------------------------


def test_image_criterion_detects_image_shapes() -> None:
    assert is_image_criterion("Noir Art image")
    assert is_image_criterion("hero product screenshot natural width")
    assert is_image_criterion("the product picture loads")
    assert not is_image_criterion("all images have alt")
    assert not is_image_criterion("GitHub link resolves")


def test_heading_criterion_detects_headline_shapes() -> None:
    assert is_heading_criterion("hero headline visible")
    assert is_heading_criterion("the pricing heading reads X")
    assert not is_heading_criterion("How It Works section")
    assert not is_heading_criterion("every heading has text")


def test_kind_matches_rejects_the_wrong_element() -> None:
    paragraph = {"tag": "p", "role": "paragraph"}
    h1 = {"tag": "h1", "role": "heading"}
    img = {"tag": "img", "role": "img"}
    button = {"tag": "button", "role": "button"}
    assert kind_matches("hero headline visible", h1)
    assert not kind_matches("hero headline visible", paragraph)
    assert kind_matches("Noir Art image", img)
    assert not kind_matches("Noir Art image", button)
    # A description naming neither kind is unconstrained.
    assert kind_matches("Copy Command button", button)


def test_scope_to_images_drops_non_images() -> None:
    img = {"tag": "img", "role": "img", "selector": "#view-mascot-art img"}
    button = {"tag": "button", "role": "button", "selector": "#btn-tab-mascot"}
    pages = {"https://x": [button, img]}
    assert scope_pages_to_images("ASSERT", "Noir Art image", pages) == {"https://x": [img]}
    # Non-image criteria are untouched.
    assert scope_pages_to_images("ASSERT", "Copy Command button", pages) == pages


def test_scope_to_headings_prefers_h1_for_headline() -> None:
    h1 = {"tag": "h1", "role": "heading"}
    h2 = {"tag": "h2", "role": "heading"}
    p = {"tag": "p", "role": "paragraph"}
    pages = {"https://x": [p, h2, h1]}
    assert scope_pages_to_headings("ASSERT", "hero headline visible", pages) == {"https://x": [h1]}
    assert scope_pages_to_headings("ASSERT", "pricing heading", pages) == {"https://x": [h2, h1]}


# ---------------------------------------------------------------------------
# ElementMatcher integration — Session 7 wrong-element cases
# ---------------------------------------------------------------------------


def _resolve(description: str, pages: dict[str, list[dict[str, Any]]]) -> Any:
    matcher = ElementMatcher(PlaceholderResolver())
    return asyncio.run(
        matcher.find_best_element_for_current_page(
            action="ASSERT", description=description, current_url="https://x.test/", pages_data=pages
        )
    )


def test_headline_resolves_to_h1_not_the_paragraph() -> None:
    paragraph = {"selector": "p.leading-relaxed", "text": "Paste a user story", "tag": "p", "role": "paragraph"}
    h1 = {"selector": "h1", "text": "The AI test generator", "tag": "h1", "role": "heading"}
    matched = _resolve("hero headline visible", {"https://x.test/": [paragraph, h1]})
    assert matched is not None
    assert matched.get("tag") == "h1"


def test_noir_art_resolves_to_the_image_not_the_button() -> None:
    button = {"selector": "#btn-tab-mascot", "text": "Noir Art", "tag": "button", "role": "button"}
    img = {
        "selector": "#view-mascot-art img",
        "text": "",
        "tag": "img",
        "role": "img",
        "alt": "Neon-noir illustration: orange tabby cat",
    }
    matched = _resolve("Noir Art image", {"https://x.test/": [button, img]})
    assert matched is not None
    assert matched.get("tag") == "img"


def test_image_criterion_with_no_image_skips_instead_of_the_button() -> None:
    button = {"selector": "#btn-tab-mascot", "text": "Noir Art", "tag": "button", "role": "button"}
    matched = _resolve("Noir Art image", {"https://x.test/": [button]})
    assert matched is None


# ---------------------------------------------------------------------------
# Scraper — images must be in the candidate pool at all (B-090/B-092)
# ---------------------------------------------------------------------------


def test_kind_bonus_ranks_the_named_image_first() -> None:
    """c6 must rank the visible product screenshot above the logos; c8 must
    rank the hidden Noir Art image first (its alt names the artwork)."""
    from src.placeholder_scorers import PlaceholderScorer

    hero = {"tag": "img", "role": "img", "alt": "Real product UI screenshot", "is_visible": True}
    mascot = {"tag": "img", "role": "img", "alt": "Neon-noir illustration", "is_visible": False}
    logo = {"tag": "img", "role": "img", "alt": "TanCat logo", "is_visible": True}

    hero_desc = "hero product screenshot loaded"
    assert PlaceholderScorer._kind_bonus("ASSERT", hero_desc, hero) > PlaceholderScorer._kind_bonus(
        "ASSERT", hero_desc, logo
    )
    assert PlaceholderScorer._kind_bonus("ASSERT", hero_desc, hero) > PlaceholderScorer._kind_bonus(
        "ASSERT", hero_desc, mascot
    )

    art_desc = "Noir Art artwork image loaded"
    assert PlaceholderScorer._kind_bonus("ASSERT", art_desc, mascot) > PlaceholderScorer._kind_bonus(
        "ASSERT", art_desc, hero
    )


def test_image_visibility_penalty_is_waived_for_image_criteria() -> None:
    from src.placeholder_scorers import PlaceholderScorer

    hidden_img = {"tag": "img", "role": "img", "alt": "x", "is_visible": False}
    assert PlaceholderScorer._assert_visibility_penalty("ASSERT", hidden_img, "Noir Art image loaded") == 0
    # A non-image hidden element still pays the penalty.
    hidden_div = {"tag": "div", "role": "div", "is_visible": False}
    assert PlaceholderScorer._assert_visibility_penalty("ASSERT", hidden_div, "some text") == -40


def test_journey_subprocess_runs_the_same_checkout(monkeypatch: Any) -> None:
    """A script under src/ puts src/ on sys.path[0]; without an explicit
    PYTHONPATH the child would import `src` from the main repo's editable
    install and miss this branch's scraper changes."""
    import subprocess

    from src.journey_scraper import JourneyScraper

    captured: dict[str, Any] = {}

    def fake_run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        captured.update(kwargs)
        return subprocess.CompletedProcess(cmd, 0, stdout="{}", stderr="")

    monkeypatch.setattr(subprocess, "run", fake_run)
    JourneyScraper(starting_url="http://x/")._scrape_journey_via_subprocess([])

    checkout_root = str(Path(__file__).resolve().parent.parent)
    assert checkout_root in captured["env"]["PYTHONPATH"]


def test_scraper_extracts_images_with_alt() -> None:
    """Before B-090 the scraper collected zero <img> elements, so an image
    criterion could never resolve to an image — it picked a nearby div/button."""
    from src.scraper import PageScraper

    html = """
    <html><body>
      <img alt="Real product screenshot" class="hero-shot" src="hero.png"/>
      <img alt="" src="decorative.png"/>
    </body></html>
    """
    elements = PageScraper()._extract_elements_from_html(html)
    imgs = [e for e in elements if e.get("tag") == "img"]
    assert len(imgs) == 2
    assert imgs[0]["alt"] == "Real product screenshot"
    assert is_image_element(imgs[0])
