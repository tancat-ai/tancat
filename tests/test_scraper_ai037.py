"""Regression tests for AI-037 scraper fixes.

Covers:
* radio/checkbox inputs wrapped in <label> get the label text as accessible_name
* clickable divs with an explicit id are captured even without direct text
* <strong> elements are captured as display elements (e.g. #quoteRef)
"""

from __future__ import annotations

from src.scraper import PageScraper


def _ids(elements: list[dict]) -> set[str]:
    return {e.get("id", "") for e in elements if e.get("id")}


def test_radio_wrapped_in_label_gets_accessible_name() -> None:
    """AI-037: radios wrapped in <label> must capture the label text."""
    scraper = PageScraper()
    html = """
    <html><body>
      <label><input type="radio" name="usageType" value="SDP"> Social, Domestic & Pleasure</label>
      <label><input type="radio" name="usageType" value="business"> Business Use</label>
    </body></html>
    """
    elements = scraper._extract_elements_from_html(html)
    radios = {e.get("value"): e for e in elements if e.get("name") == "usageType"}
    assert radios["SDP"]["accessible_name"] == "Social, Domestic & Pleasure"
    assert radios["business"]["accessible_name"] == "Business Use"


def test_radio_without_label_keeps_empty_accessible_name() -> None:
    """Radios not wrapped in a label must not get a fabricated name."""
    scraper = PageScraper()
    html = """
    <html><body>
      <input type="radio" name="group1" value="a">
      <input type="radio" name="group1" value="b">
    </body></html>
    """
    elements = scraper._extract_elements_from_html(html)
    radios = [e for e in elements if e.get("name") == "group1"]
    assert all(e.get("accessible_name", "") == "" for e in radios)


def test_clickable_div_with_id_captured_without_direct_text() -> None:
    """AI-037: card-option divs (#productCar) carry semantics in child headings."""
    scraper = PageScraper()
    html = """
    <html><body>
      <div class="card-option" id="productCar" data-product="car">
        <h4>Car Insurance</h4>
        <p>Comprehensive cover for your vehicle</p>
      </div>
      <div class="generic-container">
        <button>Inside</button>
      </div>
    </body></html>
    """
    elements = scraper._extract_elements_from_html(html)
    ids = _ids(elements)
    assert "productCar" in ids
    # Plain container divs without ids stay filtered (no direct text)
    divs = [e for e in elements if e.get("role") == "div"]
    assert all(e.get("id") != "" for e in divs)  # only id-bearing divs survive
    assert len(divs) == 1


def test_strong_element_captured() -> None:
    """AI-037: <strong> is a leaf display element (e.g. #quoteRef)."""
    scraper = PageScraper()
    html = """
    <html><body>
      <p>Your quote reference is: <strong id="quoteRef">LVQ-000000</strong></p>
    </body></html>
    """
    elements = scraper._extract_elements_from_html(html)
    ids = _ids(elements)
    assert "quoteRef" in ids
    ref = next(e for e in elements if e.get("id") == "quoteRef")
    assert ref["text"] == "LVQ-000000"
