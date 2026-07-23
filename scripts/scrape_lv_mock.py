"""Scrape the LV Insurance mock site with Playwright and save for eval."""

import asyncio
import http.server
import json
import os
import socketserver
import sys
import threading
import time

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")

PORT = 8781


# Start HTTP server in background
class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        pass


server = socketserver.TCPServer(("", PORT), Handler)
t = threading.Thread(target=server.serve_forever, daemon=True)
t.start()
time.sleep(0.5)

BASE_URL = f"http://localhost:{PORT}/generated_tests/mock_insurance_site.html"


async def scrape():
    from src.scraper import PageScraper

    scraper = PageScraper()
    elements, error, final_url = await scraper.scrape_url(BASE_URL)

    if error:
        print(f"ERROR: {error}")
        return

    print(f"Scraped {len(elements)} elements from {final_url}")

    # Save in eval format
    out_dir = "scripts/eval/scraped_pages"
    os.makedirs(out_dir, exist_ok=True)
    safe_name = BASE_URL.replace("://", "_").replace("/", "_").replace(":", "_")[:120]
    out_path = f"{out_dir}/{safe_name}.json"

    with open(out_path, "w") as f:
        json.dump({"url": BASE_URL, "elements": elements}, f, indent=2)

    print(f"Saved to {out_path}")

    # Show sample elements with text
    text_els = [e for e in elements if e.get("text", "").strip()]
    print(f"\nElements with text: {len(text_els)}/{len(elements)}")
    for e in text_els[:10]:
        print(f'  {e.get("selector", "?"):50} role={e.get("role", "?"):12} text="{e.get("text", "")[:60]}"')


asyncio.run(scrape())
server.shutdown()
