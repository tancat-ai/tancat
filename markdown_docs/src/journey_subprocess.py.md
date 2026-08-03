# `src/journey_subprocess.py` — Journey Subprocess Entry Point

## Purpose
Runs the synchronous Playwright journey in a clean subprocess to avoid Windows asyncio nested-loop issues. Extracted from `journey_scraper.py`.

## Functions
- `run_journey_subprocess_entry() -> int` — deserializes steps **and credential profile** from stdin JSON, reconstructs `JourneyStep`/`CredentialProfile`, runs `JourneyScraper._scrape_journey_sync()`, outputs scraped pages as JSON to stdout

## Key Logic
- **Credential round-trip (2026-08-03):** the payload always serialized `credential_profile` but the subprocess never read it back — auth-gated journeys silently ran without a session (saucedemo hit the login wall). The entry point now reconstructs `CredentialProfile` from `payload["credential_profile"]` and passes it to `JourneyScraper`.

## Related
- `src/journey_scraper.py` — `_scrape_journey_via_subprocess()` spawns this
