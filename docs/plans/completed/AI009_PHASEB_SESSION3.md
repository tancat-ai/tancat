# Session 3: UI — Credential Profiles + Journey Builder

**AI-009 Phase B — Authenticated Journey Scraping**  
**Created:** 2026-05-12  
**Depends on:** Session 2 (credential profile wiring complete)  
**Original spec:** `docs/specs/FEATURE_SPEC_AI009_phase_b.md`

---

## Goal

Add credential profiles section and journey builder section to the Streamlit UI,
wired through `src/ui_renderers.py` and `src/ui_pipeline.py`.

---

## Current State of Relevant Files

### streamlit_app.py (~362 lines after May 2026 refactor)
- Wires together UI rendering and pipeline execution
- Calls `run_pipeline()` from `src/ui_pipeline.py`
- Rendering delegated to `src/ui_renderers.py`
- Session state manages: user story, criteria, base URL, additional URLs, provider settings

### src/ui_renderers.py
- Contains all Streamlit rendering logic extracted from streamlit_app.py
- **Needs:** `render_credential_profiles()` and `render_journey_builder()` functions

### src/ui_pipeline.py
- Contains pipeline execution logic (`run_pipeline()`)
- Currently calls `TestOrchestrator.run_pipeline()` with: generator, pages_to_scrape, starting_url
- **Needs:** Accept `credential_profile` and `journey_steps` parameters

### src/journey_scraper.py (after Session 1)
- Has `JourneyStep`, `JourneyResult`, `CredentialProfile` dataclasses
- Has `execute_journey()` function

### src/orchestrator.py (after Session 2)
- `TestOrchestrator` accepts `credential_profile` parameter
- Passes through to scrapers

---

## Rules (from AGENTS.md)

- **Package manager:** `uv add` / `uv sync` — NEVER use `pip`
- **Test format:** pytest sync + playwright fixtures — NEVER async def
- **Type hints:** All functions must have full type annotations
- **Helper functions:** Go in `src/`, NOT in `streamlit_app.py`
- **Credential values:** NEVER appear in log output or error messages
- **Session state only:** Credentials stored in `st.session_state` — never persisted
- **Quality gates:** ruff → mypy → pytest before declaring done
- **Protected files — DO NOT TOUCH:**
  - `src/llm_client.py`
  - `src/test_generator.py`
  - `src/llm_providers/`
  - `.github/workflows/ci.yml`

---

## Tasks in Order

### Task 1: Add credential profiles section to src/ui_renderers.py

Create `render_credential_profiles()` function:

```python
def render_credential_profiles() -> CredentialProfile | None:
    """Render the authentication section of the UI.
    
    Returns the active credential profile, or None if authentication is disabled.
    """
```

**UI Elements:**
1. Expander: `"🔐 Authentication (optional)"`
2. Toggle: `"Pages require login"` — when off, entire section collapsed
3. When toggle is ON:
   - List existing profiles (label, username, password fields inline)
   - "Add profile" button — adds new empty profile row
   - "Remove" button per profile
   - Active profile selector: `st.selectbox` with profile labels
   - Profiles stored in `st.session_state.credential_profiles: list[dict]`
4. Return active `CredentialProfile` or `None`

**Session state keys:**
```python
st.session_state.credential_profiles: list[dict]  # [{"label": "...", "username": "...", "password": "..."}]
st.session_state.active_credential_index: int      # index of selected profile
st.session_state.auth_enabled: bool                # toggle state
```

**Security:** Never print credential values. Mask passwords in display (show "••••••").

---

### Task 2: Add journey builder section to src/ui_renderers.py

Create `render_journey_builder()` function:

```python
def render_journey_builder(additional_urls: list[str]) -> list[JourneyStep] | None:
    """Render the journey builder section of the UI.
    
    Args:
        additional_urls: Current URL list for "Build from URL list" auto-populate.
        
    Returns:
        List of JourneyStep objects, or None if journey builder is not used.
    """
```

**UI Elements:**
1. Expander: `"🗺️ Journey steps (optional — for dynamic or authenticated pages)"`
2. Instruction text: `"Define the steps the scraper will follow. Add a Capture step wherever you want page context collected."`
3. Step list — each step rendered as a row:
   - Step type selector (`st.selectbox`): `goto` / `click` / `fill` / `capture` / `wait`
   - Dynamic fields depending on type:
     - `goto` → URL text input
     - `click` → selector input OR visible text input (radio to choose)
     - `fill` → selector input + value input (value can be `{{username}}` or `{{password}}`)
     - `capture` → label input (e.g., "Dashboard page")
     - `wait` → selector input
   - "Remove step" button per row
4. "Add step" button — appends new empty step row
5. "Build from URL list" button — converts `additional_urls` into goto+capture steps
6. Steps stored in `st.session_state.journey_steps: list[dict]`
7. Return list of `JourneyStep` objects or `None`

**Session state keys:**
```python
st.session_state.journey_steps: list[dict]  # [{"action": "goto", "url": "...", ...}]
st.session_state.journey_enabled: bool      # whether journey builder is in use
```

**"Build from URL list" logic:**
```python
def _urls_to_journey_steps(urls: list[str]) -> list[JourneyStep]:
    """Convert a list of URLs into goto + capture journey steps."""
    steps: list[JourneyStep] = []
    for url in urls:
        steps.append(JourneyStep(action="goto", url=url, description=f"Navigate to {url}"))
        steps.append(JourneyStep(action="capture", label=url, description=f"Capture {url}"))
    return steps
```

---

### Task 3: Wire into streamlit_app.py

In `streamlit_app.py`, after the URL input section and before the generate button:

```python
# After URL inputs, before pipeline execution
from src.ui_renderers import render_credential_profiles, render_journey_builder
from src.journey_scraper import JourneyStep, CredentialProfile

# Credential profiles
active_profile = render_credential_profiles()

# Journey builder  
journey_steps = render_journey_builder(additional_urls) if additional_urls else None

# Pass to pipeline
asyncio.run(run_pipeline(
    # ... existing params ...
    credential_profile=active_profile,
    journey_steps=journey_steps,
))
```

---

### Task 4: Update src/ui_pipeline.py

Modify `run_pipeline()` to accept and use the new parameters:

```python
async def run_pipeline(
    # ... existing params ...
    credential_profile: CredentialProfile | None = None,  # NEW
    journey_steps: list[JourneyStep] | None = None,       # NEW
) -> PipelineResult:
```

**Decision tree for scraping:**
```python
if journey_steps is not None and len(journey_steps) > 0:
    # Use journey-based scraping
    from src.journey_scraper import execute_journey
    journey_result = execute_journey(
        journey_steps=journey_steps,
        credential_profile=credential_profile,
        starting_url=starting_url,
    )
    scraped_data = journey_result.captured_pages
    # Surface errors in pipeline diagnostics
    if journey_result.failed_steps:
        diagnostics["scraper_warnings"] = journey_result.failed_steps
    if journey_result.error_message:
        diagnostics["scraper_errors"] = [journey_result.error_message]
elif additional_urls:
    # Static multi-page scrape (existing Phase A)
    scraped_data = await scraper.scrape_all(pages_to_scrape)
else:
    # Single page scrape
    scraped_data = await scraper.scrape_single(base_url)
```

**Pass credential_profile to TestOrchestrator:**
```python
orchestrator = TestOrchestrator(
    generator=generator,
    starting_url=starting_url,
    credential_profile=credential_profile,  # NEW
)
```

---

### Task 5: Error surfacing

All scraper errors must surface in the UI sidebar:

```python
# In streamlit_app.py after pipeline completes
if diagnostics.get("scraper_warnings"):
    for warning in diagnostics["scraper_warnings"]:
        st.warning(f"⚠️ Scraper: {warning}")

if diagnostics.get("scraper_errors"):
    for error in diagnostics["scraper_errors"]:
        st.error(f"❌ Scraper: {error}")
```

Show success count:
```python
if journey_steps:
    st.success(f"✅ Captured context from {len(journey_result.captured_pages)} pages")
```

---

## Acceptance Criteria

- [x] Credential profiles section renders correctly in UI
- [x] Journey builder section renders correctly in UI
- [x] "Build from URL list" converts URLs to goto+capture steps
- [x] Active credential profile is passed to pipeline
- [x] Journey steps are passed to pipeline
- [x] Scraper errors surface as st.warning / st.error in sidebar
- [x] Session state persists across reruns
- [x] Passwords are masked in display (never shown in plain text)
- [x] `ruff check src/ui_renderers.py src/ui_pipeline.py streamlit_app.py` → clean
- [x] `mypy src/ui_renderers.py src/ui_pipeline.py` → clean
- [x] `pytest tests/ -v` → 580 passed (2 pre-existing failures in `test_stateful_scrape_switch.py` unrelated to this session)

## Verification Results (2026-05-12)

```bash
ruff check src/ui_renderers.py src/ui_pipeline.py streamlit_app.py   # All checks passed!
mypy src/ui_renderers.py src/ui_pipeline.py                          # Success: no issues found in 2 source files
pytest tests/ -v                                                      # 580 passed, 2 failed (pre-existing)
```

**Manual verification:** UI renders credential profiles expander and journey builder expander correctly. Credential profiles support add/remove/active selection with password masking. Journey builder supports dynamic step types with "Build from URL list" conversion.

---

## DO NOT

- Touch `orchestrator.py` (already done in Session 2)
- Touch `src/stateful_scraper.py` (already done in Session 2)
- Touch protected files listed above
- Store credentials in any file — session state only
- Print credential values to logs or console
