# Session 2: Credential Profile Integration

**AI-009 Phase B — Authenticated Journey Scraping**  
**Created:** 2026-05-12  
**Completed:** 2026-05-12  
**Depends on:** Session 1 (data models + execute_journey complete)  
**Original spec:** `docs/specs/FEATURE_SPEC_AI009_phase_b.md`

---

## Status: ✅ COMPLETE

All acceptance criteria met. Quality gates passed clean.

---

## Goal

Remove hardcoded saucedemo credentials from `stateful_scraper.py`, wire
`CredentialProfile` through the pipeline, and add credential-aware login.

---

## Changes Made

### 1. `src/stateful_scraper.py` — Accept CredentialProfile

- `__init__` now accepts `credential_profile: CredentialProfile | None = None`
- `_attempt_login()` uses `self._credential_profile.username` / `.password` when provided
- Falls back to form detection only when no credential profile is provided
- **Removed:** hardcoded `"standard_user"` and `"secret_sauce"` strings
- Subprocess payload serializes credential_profile via `asdict()`

### 2. `src/orchestrator.py` — Wire CredentialProfile through TestOrchestrator

- `__init__` accepts `credential_profile: CredentialProfile | None = None`
- Stores as `self._credential_profile`
- Passes to `PlaceholderOrchestrator` at construction time
- Passes to `_scrape_journeys_statefully()` → `JourneyScraper` → `scrape_journey()`
- Import: `from src.journey_scraper import CredentialProfile, JourneyScraper, JourneyStep`

### 3. `src/journey_scraper.py` — CredentialProfile in JourneyScraper

- `JourneyScraper.__init__` accepts `credential_profile: CredentialProfile | None = None`
- Stores as `self._credential_profile`
- `scrape_journey()` accepts `credential_profile` as keyword argument
- Falls back to instance-level `self._credential_profile` if not provided at call-site
- `_scrape_journey_via_subprocess()` serializes credential_profile into subprocess payload

### 4. `src/placeholder_orchestrator.py` — Accept CredentialProfile

- `__init__` accepts `credential_profile: CredentialProfile | None = None`
- Passes to `StatefulPageScraper` instances in `_replace_placeholders_sequentially()`
- Stores as `self._credential_profile`

### 5. Tests — New test cases added

**`tests/test_stateful_scraper.py`:**
- `test_init_with_credential_profile` ✅
- `test_init_without_credential_profile` ✅
- `test_scrape_urls_passes_credential_profile_to_subprocess` ✅
- `test_scrape_urls_omits_credential_profile_when_none` ✅

**`tests/test_orchestrator.py`:**
- `test_orchestrator_passes_credential_to_scraper` ✅
- `test_orchestrator_without_credential_profile` ✅

---

## Acceptance Criteria

- [x] No hardcoded credentials remain in `stateful_scraper.py`
- [x] `StatefulPageScraper` accepts `credential_profile: CredentialProfile | None`
- [x] `TestOrchestrator` accepts and passes through `credential_profile`
- [x] `JourneyScraper` accepts and passes through `credential_profile`
- [x] `PlaceholderOrchestrator` accepts and passes through `credential_profile`
- [x] Backward compatible: works without credential profile (graceful degradation)
- [x] `ruff check src/stateful_scraper.py src/orchestrator.py src/journey_scraper.py src/placeholder_orchestrator.py` → clean
- [x] `mypy src/stateful_scraper.py src/orchestrator.py src/journey_scraper.py src/placeholder_orchestrator.py` → clean
- [x] `pytest tests/test_stateful_scraper.py tests/test_orchestrator.py tests/test_journey_scraper.py -v` → 67 passed

---

## Quality Gate Results

```
ruff check:     All checks passed!
mypy:           Success: no issues found in 4 source files
pytest:         67 passed in 46.88s
credential check: No hardcoded credentials found
```

---

## Credential Flow Diagram

```
User Input (Streamlit UI - Session 3)
    ↓
CredentialProfile(label, username, password)
    ↓
TestOrchestrator(credential_profile=...)
    ↓
┌─────────────────────────────────────────┐
│ PlaceholderOrchestrator                 │
│  └─ StatefulPageScraper(...)            │
│      └─ _attempt_login() uses creds     │
└─────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────┐
│ JourneyScraper(credential_profile=...)  │
│  └─ scrape_journey() → subprocess       │
│      └─ _substitute_templates()         │
└─────────────────────────────────────────┘
```

---

## DO NOT

- Touch `streamlit_app.py` (Session 3)
- Touch `src/ui_renderers.py` (Session 3)
- Touch `src/ui_pipeline.py` (Session 3)
- Modify `JourneyStep` in journey_scraper.py
- Touch protected files (`src/llm_client.py`, `src/test_generator.py`, `src/llm_providers/`, `.github/workflows/ci.yml`)
- Break existing scraper behavior when no credentials provided

---

*Session completed: 2026-05-12*