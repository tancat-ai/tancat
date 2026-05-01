"""Scratch: dump scrape manifest for debugging - shows all pages and elements."""

import json

MANIFEST = "generated_tests/test_20260427_121941_as_a_customer_i_want_to_add_items_to_cart/scrape_manifest.json"

with open(MANIFEST, encoding="utf-8") as fh:
    data = json.load(fh)

pages = data.get("pages_scraped", [])
print(f"Total pages scraped: {len(pages)}")
for page in pages:
    url = page.get("url", "?")
    elems = page.get("elements", [])
    err = page.get("error")
    print()
    print(f"=== {url} ({len(elems)} elements) error={err!r} ===")
    for el in elems:
        role = el.get("role", "?")
        sel = el.get("selector", "?")
        txt = str(el.get("text", ""))[:40]
        print(f"  {role:14} | {sel:80} | {txt!r}")
