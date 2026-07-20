"""Subprocess entry point for journey scraping.

Extracted from ``journey_scraper.py``. Runs the synchronous Playwright journey
in a clean subprocess to avoid Windows asyncio nested-loop issues.
"""

from __future__ import annotations

import json
import sys

from src.journey_models import JourneyStep
from src.journey_scraper import JourneyScraper


def run_journey_subprocess_entry() -> int:
    """Entry point for the subprocess-backed journey scrape.

    Reads a JSON payload from stdin, reconstructs JourneyStep objects,
    executes the journey synchronously, and prints JSON output to stdout.

    Returns 0 on success, 1 on failure.
    """
    payload = json.loads(sys.stdin.read() or "{}")
    if not isinstance(payload, dict):
        print("{}")
        return 1

    starting_url = str(payload.get("starting_url", "")).strip()
    timeout_ms = int(payload.get("timeout_ms", 30_000))
    max_retries = int(payload.get("max_retries", 2))
    base_backoff_ms = int(payload.get("base_backoff_ms", 1000))
    headless = payload.get("headless", True)
    steps_data = payload.get("steps", [])

    # Reconstruct JourneyStep objects from JSON
    steps: list[JourneyStep] = []
    for s in steps_data:
        if not isinstance(s, dict):
            continue
        steps.append(
            JourneyStep(
                action=str(s.get("action", "")),
                url=str(s["url"]) if s.get("url") else None,
                selector=str(s["selector"]) if s.get("selector") else None,
                text=str(s["text"]) if s.get("text") else None,
                description=str(s.get("description", "")),
                timeout_ms=int(s.get("timeout_ms", 30_000)),
            )
        )

    scraper = JourneyScraper(
        starting_url=starting_url,
        timeout_ms=timeout_ms,
        max_retries=max_retries,
        base_backoff_ms=base_backoff_ms,
        headless=bool(headless),
    )
    output = scraper._scrape_journey_sync(steps)
    print(json.dumps(output))
    return 0


if __name__ == "__main__":
    if "--journey-scrape" in sys.argv:
        raise SystemExit(run_journey_subprocess_entry())
