"""Quick debug: scrape saucedemo login page and print elements."""
import asyncio
import sys
sys.path.insert(0, ".")

from src.scraper import PageScraper

async def main():
    scraper = PageScraper(timeout_ms=30000)
    elements, error, final_url = await scraper.scrape_url("https://www.saucedemo.com")
    print(f"Final URL: {final_url}")
    print(f"Error: {error}")
    print(f"Elements count: {len(elements)}")
    for e in elements:
        print(f"  selector={e.get('selector')}, id={e.get('id')}, name={e.get('name')}, text={e.get('text')}, role={e.get('role')}")

asyncio.run(main())
