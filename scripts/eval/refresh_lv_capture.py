"""Re-scrape the LV Insurance mock site in post-journey state for the resolver eval.

The static initial-load scrape leaves #excessInfo empty (JS fills it via
updateExtrasPage() after vehicle submission). This capture drives the real
quote flow (account → product → policy → drivers → vehicles → extras) so the
frozen eval data reflects what the real pipeline's journey scrape produces.

Usage:
    uv run python scripts/eval/refresh_lv_capture.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from playwright.sync_api import sync_playwright  # noqa: E402

from scripts.mock_server import MockServer  # noqa: E402
from src.journey_scraper import JourneyScraper  # noqa: E402
from src.scraper import PageScraper  # noqa: E402

URL = "http://localhost:8781/generated_tests/mock_insurance_site.html"
OUT = (
    Path(__file__).resolve().parent
    / "scraped_pages"
    / "http_localhost_8781_generated_tests_mock_insurance_site.html.json"
)


def drive_quote_flow(page: object) -> None:
    """Walk the mock quote flow so populated pages are in post-interaction state."""
    page.goto(URL, wait_until="networkidle")
    page.wait_for_timeout(400)
    JourneyScraper._reveal_hidden_sections(page)  # type: ignore[attr-defined]

    def step(label: str, fn: object) -> None:
        try:
            fn()
        except Exception as exc:  # noqa: BLE001
            print(f"  [warn] {label}: {exc}")

    # Page 1: Account (title is required by the form validation)
    step(
        "account fields",
        lambda: (
            page.fill("#email", "john@example.com"),
            page.fill("#password", "Password123!"),
            page.select_option("#title", "Mr"),
            page.fill("#firstName", "John"),
            page.fill("#lastName", "Smith"),
            page.fill("#dob", "1990-01-01"),
            page.fill("#postcode", "SW1A 1AA"),
            page.fill("#addressLine1", "10 Downing St"),
        ),
    )
    step("account next", lambda: page.click("#accountNext"))
    page.wait_for_timeout(300)

    # Page 2: Product
    step("select car", lambda: page.click("#productCar"))
    page.wait_for_timeout(100)
    step("product next", lambda: page.click("#productNext"))
    page.wait_for_timeout(300)

    # Page 3: Policy details
    step(
        "policy fields",
        lambda: (
            page.fill("#startDate", "2026-08-01"),
            page.select_option("#scheme", "standard"),
        ),
    )
    step("policy next", lambda: page.click("#policyNext"))
    page.wait_for_timeout(300)

    # Page 4: Drivers — account holder fields
    step(
        "driver fields",
        lambda: (
            page.fill("#mainLicenseNumber", "MORGA753116SM9IJ"),
            page.fill("#mainLicenseYears", "10"),
            page.select_option("#mainOccupation", label="Engineer"),
        ),
    )
    step("drivers next", lambda: page.click("#driversNext"))
    page.wait_for_timeout(400)

    # Page 5: Vehicles — registration lookup + add
    step(
        "reg lookup",
        lambda: (
            page.fill("#vehicleReg", "AB12CDE"),
            page.click("#lookupRegBtn"),
            page.wait_for_timeout(900),
        ),
    )
    step(
        "usage + ncd + overnight",
        lambda: (
            page.check('input[name="usageType"][value="SDP"]'),
            page.fill("#ncdYears", "5"),
            page.select_option("#overnightLocation", label="Private Garage"),
        ),
    )
    # Driver/owner selects are populated by refreshDriverOptions() after driversNext
    step(
        "driver selects",
        lambda: (
            page.select_option("#mainDriverSelect", label="Mr John Smith"),
            page.select_option("#ncdHolder", label="Mr John Smith"),
            page.select_option("#vehicleOwner", label="Mr John Smith"),
            page.select_option("#registeredKeeper", label="Mr John Smith"),
        ),
    )
    step("add vehicle", lambda: page.click("#addVehicleBtn"))
    page.wait_for_timeout(200)
    step("vehicles next", lambda: page.click("#vehiclesNext"))  # → calculatePremium → updateExtrasPage
    page.wait_for_timeout(400)

    # Verify post-journey state
    vehicle_count = page.evaluate("() => window.__state ? window.__state.vehicles.length : 0")
    excess_text = page.evaluate("() => document.getElementById('excessInfo')?.innerText || ''")
    print(f"  vehicles in state: {vehicle_count} | excessInfo: {excess_text[:40]!r}")


def main() -> int:
    server = MockServer.start(port=8781, directory=str(Path(__file__).resolve().parent.parent.parent))
    scraper = PageScraper()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        drive_quote_flow(page)

        # Keep all sections revealed so elements on every page are captured.
        JourneyScraper._reveal_hidden_sections(page)  # type: ignore[attr-defined]
        page.wait_for_timeout(200)
        html = page.content()
        bs4 = scraper._extract_elements_from_html(html, base_url=URL)
        elements = scraper._extract_elements_from_aria(page, bs4)
        elements = scraper._capture_element_visibility(page, elements)
        browser.close()

    # Sanity checks
    ids = {e.get("id") for e in elements}
    missing = [k for k in ("productCar", "paymentFull", "quoteRef", "excessInfo") if k not in ids]
    excess = next((e for e in elements if e.get("id") == "excessInfo"), None)
    print(f"elements: {len(elements)} | missing: {missing or 'none'}")
    print(f"excessInfo text: {str(excess.get('text'))[:50]!r}" if excess else "excessInfo absent")
    if missing:
        print("WARNING: golden elements missing from capture", file=sys.stderr)
        return 1

    OUT.write_text(json.dumps({"url": URL, "elements": elements}, indent=2), encoding="utf-8")
    print(f"saved {OUT}")
    server.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
