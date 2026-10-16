"""t-0827 trace diagnostic: why did journey discovery pick #place-order for 'select item'?

Serves mock_sites/ambiguous, opens index.html, and runs JourneyScraper._discover_selector
with the description from the eval-010 journey, logging the per-candidate scores.
"""

from __future__ import annotations

import http.server
import json
import socketserver
import sys
import threading
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO))

from playwright.sync_api import sync_playwright  # noqa: E402

from src.journey_scraper import JourneyScraper  # noqa: E402
from src.placeholder_scorers import PlaceholderScorer  # noqa: E402

PORT = 8899
SITE = REPO / "mock_sites" / "ambiguous"


def main() -> None:
    handler = lambda *a, **kw: http.server.SimpleHTTPRequestHandler(*a, directory=str(SITE), **kw)  # noqa: E731
    with socketserver.TCPServer(("127.0.0.1", PORT), handler) as httpd:
        threading.Thread(target=httpd.serve_forever, daemon=True).start()

        # Instrument the scorer to log every candidate.
        orig = PlaceholderScorer.compute_element_score
        scored: list[dict] = []

        def spy(action, description, element, selector, match_threshold, *args, **kwargs):
            s = orig(action, description, element, selector, match_threshold, *args, **kwargs)
            scored.append(
                {
                    "selector": selector,
                    "role": str(element.get("role", "")),
                    "tag": str(element.get("tag", "")),
                    "text": str(element.get("text", ""))[:40],
                    "id": str(element.get("id", "")),
                    "score": s,
                }
            )
            return s

        PlaceholderScorer.compute_element_score = staticmethod(spy)  # type: ignore[assignment]

        js = JourneyScraper(starting_url=f"http://127.0.0.1:{PORT}/index.html")
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(f"http://127.0.0.1:{PORT}/index.html", wait_until="networkidle")
            page.wait_for_timeout(500)

            scored.clear()
            sel = js._discover_selector(page, "click", "select item")  # noqa: SLF001
            print("== 'select item' candidates ==")
            for row in sorted(scored, key=lambda r: -(r["score"] if r["score"] is not None else -999)):
                print(json.dumps(row))
            print("PICKED:", sel)

            scored.clear()
            sel2 = js._discover_selector(page, "click", "Place Order")  # noqa: SLF001
            print("== 'Place Order' candidates (index.html) ==")
            for row in sorted(scored, key=lambda r: -(r["score"] if r["score"] is not None else -999)):
                print(json.dumps(row))
            print("PICKED:", sel2)

            # Now the same discovery ON success.html (where the lost journey ran it).
            page.goto(f"http://127.0.0.1:{PORT}/success.html?item=blue-top&qty=1", wait_until="networkidle")
            page.wait_for_timeout(500)
            scored.clear()
            sel3 = js._discover_selector(page, "click", "Place Order")  # noqa: SLF001
            print("== 'Place Order' candidates (success.html) ==")
            for row in sorted(scored, key=lambda r: -(r["score"] if r["score"] is not None else -999)):
                print(json.dumps(row))
            print("PICKED:", sel3)
            browser.close()
        httpd.shutdown()


if __name__ == "__main__":
    main()
