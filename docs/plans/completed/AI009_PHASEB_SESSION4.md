# Session 4: Orchestrator Integration + End-to-End Verification

**AI-009 Phase B — Authenticated Journey Scraping**  
**Created:** 2026-05-12  
**Depends on:** Sessions 1-3 (data models, credential wiring, UI complete)  
**Original spec:** `docs/specs/FEATURE_SPEC_AI009_phase_b.md`

---

## Goal

Integrate `execute_journey()` into `TestOrchestrator.run_pipeline()`, verify end-to-end
with a real site, and update project documentation.

---

## Current State of Relevant Files

### src/orchestrator.py
- `TestOrchestrator.run_pipeline()` uses two-phase scraping:
  1. Static: `PageScraper.scrape_all()` for seed URLs
  2. Stateful: `JourneyScraper.scrape_journey()` for journey discovery
- After Session 2: Accepts `credential_profile` parameter
- **Needs:** Third path — `execute_journey()` when user provides journey steps

### src/ui_pipeline.py (after Session 3)
- `run_pipeline()` accepts `journey_steps` and `credential_profile`
- Decision tree routes to `execute_journey()` when journey steps exist
- **May need:** Adjustments if orchestrator integration reveals gaps

### streamlit_app.py (after Session 3)
- UI renders credential profiles and journey builder
- Passes journey_steps and credential_profile to pipeline
- **May need:** Minor wiring adjustments after orchestrator changes

### BACKLOG.md
- AI-009 Phase B still marked "In Progress"
- **Needs:** Update to "COMPLETE"

### docs/ARCHITECTURE.md
- Documents current pipeline architecture
- **Needs:** Section on journey scraping path

---

## Rules (from AGENTS.md)

- **Package manager:** `uv add` / `uv sync` — NEVER use `pip`
- **Test format:** pytest sync + playwright fixtures — NEVER async def
- **Type hints:** All functions must have full type annotations
- **Helper functions:** Go in `src/`, NOT in `streamlit_app.py`
- **Run app end-to-end** before declaring done
- **One feature per session**
- **Quality gates:** ruff → mypy → pytest → human reviews diff → commit
- **Protected files — DO NOT TOUCH:**
  - `src/llm_client.py`
  - `src/test_generator.py`
  - `src/llm_providers/`
  - `.github/workflows/ci.yml`

---

## Tasks in Order

### Task 1: Integrate execute_journey() into orchestrator.py

**File:** `src/orchestrator.py`

In `run_pipeline()`, add journey-based scraping as a third path:

```python
# Pseudocode for the decision point in run_pipeline():
if self._journey_steps is not None and len(self._journey_steps) > 0:
    # Journey-based scraping (Phase B)
    from src.journey_scraper import execute_journey
    journey_result = execute_journey(
        journey_steps=self._journey_steps,
        credential_profile=self._credential_profile,
        starting_url=self._starting_url,
    )
    scraped_data = journey_result.captured_pages
    
    # Record diagnostics
    self._pipeline_diagnostics["journey_failed_steps"] = journey_result.failed_steps
    if journey_result.error_message:
        self._pipeline_diagnostics["journey_error"] = journey_result.error_message
    if journey_result.redirected_urls:
        self._pipeline_diagnostics["auth_redirects"] = journey_result.redirected_urls
        
    # Merge with any static scrape data
    all_scraped_data = {**raw_scraped_data, **scraped_data}
elif self._pages_to_scrape:
    # Static multi-page scrape (Phase A)
    all_scraped_data = raw_scraped_data
else:
    # Single page
    all_scraped_data = raw_scraped_data
```

**Key points:**
- Journey data MERGES with static scrape data (don't replace)
- Failed steps are recorded but don't stop the pipeline
- Auth redirect warnings surface in diagnostics
- Backward compatible: if no journey steps, use existing paths

---

### Task 2: Update TestOrchestrator.__init__ to accept journey_steps

```python
def __init__(
    self,
    generator: TestGenerator,
    starting_url: str | None = None,
    credential_profile: CredentialProfile | None = None,
    journey_steps: list[JourneyStep] | None = None,  # NEW
) -> None:
    self._journey_steps = journey_steps
    # ... existing init
```

---

### Task 3: End-to-end test with saucedemo.com

**Manual test — run the full pipeline:**

1. Launch the UI: `streamlit run streamlit_app.py`

2. Configure:
   - Base URL: `https://www.saucedemo.com/`
   - Enable authentication
   - Add credential profile:
     - Label: "Standard user"
     - Username: `standard_user`
     - Password: `secret_sauce`
   - Build journey:
     1. `goto`: `https://www.saucedemo.com/`
     2. `fill`: selector=`#user-name`, value=`{{username}}`
     3. `fill`: selector=`#password`, value=`{{password}}`
     4. `click`: selector=`#login-button`
     5. `capture`: label="Products page"
     6. `click`: text="Add to cart" (first button)
     7. `click`: selector=`.shopping_cart_link`
     8. `capture`: label="Cart page"

3. Run the pipeline

4. **Verify:**
   - `captured_pages` contains both "Products page" and "Cart page" contexts
   - No auth redirect errors
   - Generated tests use locators from BOTH pages
   - No hardcoded credentials in logs

---

### Task 4: Run UAT script

```bash
# Use LM Studio (avoids GPU VRAM contention when Cline is running)
.venv\Scripts\python.exe scripts\uat\uat_automationexercise.py --provider lm-studio
```

**Compare with baseline:**
- Before Phase B: 4/6 tests pass on automationexercise.com
- Expected: Same or better (Phase B improves authenticated flows, not public e-commerce)
- Any improvement in cross-page resolution is a win

---

### Task 5: Run full test suite

```bash
ruff check src/
mypy src/
pytest tests/ -v
```

All must pass. If any tests break due to orchestrator changes, fix them.

---

### Task 6: Update documentation

**BACKLOG.md:**
```markdown
### AI-009 — Multi-Page Scraping ✅ COMPLETE

**Phase A (2026-03-21):** Multi-page URL scraping, UI integration, failure tracking  
**Phase B (2026-05-12):** Authenticated journey scraping, credential profiles,
auth redirect detection, SSO/MFA/CAPTCHA detection, journey builder UI
```

**docs/ARCHITECTURE.md:**
Add section:
```markdown
## Journey Scraping (Phase B)

When the user defines journey steps in the UI, the pipeline uses `execute_journey()`
instead of static URL scraping. The journey executes in a single Playwright browser
session (via subprocess), navigating through login forms, clicking elements, and
capturing page context at each step.

### Flow
1. User defines journey steps in UI (goto → fill → click → capture)
2. `execute_journey()` runs steps in subprocess
3. Auth redirect / SSO / MFA / CAPTCHA detected with explicit errors
4. Captured pages merge with static scrape data
5. Placeholder resolver uses combined context

### Data Flow
UI → ui_pipeline.py → TestOrchestrator → execute_journey() → JourneyResult → scraped_data
```

**AGENTS.md:**
- Update session log entry
- Add any new patterns or gotchas discovered

---

## Acceptance Criteria

- [x] `TestOrchestrator` accepts `journey_steps` parameter
- [x] Journey data merges with static scrape data (doesn't replace)
- [x] End-to-end test on saucedemo.com captures authenticated pages
- [x] No auth redirect errors in saucedemo.com test
- [x] UAT script runs without errors
- [x] `ruff check src/` → clean
- [x] `mypy src/` → clean
- [x] `pytest tests/ -v` → all pass
- [x] BACKLOG.md updated — AI-009 Phase B marked COMPLETE
- [x] docs/ARCHITECTURE.md updated with journey scraping section

## Verification

```bash
ruff check src/
mypy src/
pytest tests/ -v
.venv\Scripts\python.exe scripts\uat\uat_automationexercise.py --provider lm-studio
# Manual: streamlit run streamlit_app.py → run saucedemo.com journey
```

All must pass clean. Manual test must capture authenticated pages.

---

## DO NOT

- Modify protected files listed above
- Break existing non-journey scraping paths
- Commit .env or credential values
- Skip end-to-end verification