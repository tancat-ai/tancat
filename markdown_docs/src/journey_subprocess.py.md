# `src/journey_subprocess.py` — Journey Subprocess Entry Point

## Purpose
Runs the synchronous Playwright journey in a clean subprocess to avoid Windows asyncio nested-loop issues. Extracted from `journey_scraper.py`.

## Functions
- `run_journey_subprocess_entry() -> None` — deserializes steps from stdin JSON, runs `JourneyScraper._scrape_journey_sync()`, outputs scraped pages as JSON to stdout

## Related
- `src/journey_scraper.py` — `_scrape_journey_via_subprocess()` spawns this
