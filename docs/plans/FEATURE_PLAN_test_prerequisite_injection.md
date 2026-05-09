# Feature Plan: Test Prerequisite Injection (Stage A)

> **Status:** Implemented  
> **Created:** 2026-05-09  
> **Completed:** 2026-05-09  
> **Updated:** 2026-05-09
> **Supersedes:** N/A (new feature)  
> **Related:** BACKLOG.md — to be added after implementation  
> **Followed by:** FEATURE_PLAN_pom_with_evidence_tracker.md (Stage B)  
> **Root Cause Analysis:** UAT saucedemo 2026-05-09 — tests 2-6 skip because they navigate to login page but never execute login steps

---

## Problem Statement

When a user provides acceptance criteria that have implicit dependencies (e.g., "add item to cart" requires being logged in), the skeleton generator creates independent test functions that do NOT include prerequisite steps. This is because:

1. **Human mental model:** Users write only the _relevant_ steps for each criterion, not the full automation chain
2. **LLM behavior:** The skeleton prompt instructs "one test per criterion" but doesn't instruct to include prerequisite steps from earlier criteria
3. **Automation reality:** Each pytest test runs in a fresh browser context with no shared state

**Concrete example from UAT (2026-05-09):**

```python
# Generated — test_02 starts at login page but never logs in:
def test_02_add_item(page):
    evidence_tracker.navigate('https://www.saucedemo.com')  # ← Login page
    dismiss_consent_overlays(page)
    pytest.skip("Unresolved placeholder: {{CLICK:Sauce Labs Backpack add to cart button}}")
    # ^ This button doesn't exist on the login page because user isn't logged in
```

**Impact:** 5 of 6 generated tests skip or fail because they try to interact with elements on pages they haven't navigated to yet.

---

## Proposed Solution (Stage A)

Add a **prerequisite injection** step in the pipeline that:

1. **Detects** which tests need prerequisite steps (dependency chain analysis)
2. **Extracts** prerequisite steps from earlier tests
3. **Injects** those steps at the start of dependent tests

This is implemented as a **post-processing step** after placeholder resolution, so it works with the existing `evidence_tracker` pattern without any changes to evidence tracking.

### How Dependency Detection Works

```
Parse the journey chain:
  TC-01: "Log in with username..." → first GOTO points to starting URL → marks as "auth entry point"
  TC-02: "Add item to cart" → first GOTO points to starting URL (login page) → needs auth → inject TC-01 steps
  TC-03: "Navigate to cart" → first GOTO points to starting URL → needs auth + items → inject TC-01 + TC-02 steps
  ...
```

**Detection logic:**
1. For each test journey, examine the first `GOTO` placeholder
2. Resolve it to a page URL (using UrlResolver or seed URL)
3. If the resolved URL is the **starting URL** (login page) but the criterion describes a **post-authentication action** (contains keywords like "cart", "checkout", "item", "add"), then the test needs prerequisite injection
4. Extract the resolved steps from the prerequisite test(s) and prepend them

### Before and After

**Before (broken):**
```python
def test_02_add_item(page):
    evidence_tracker.navigate('https://www.saucedemo.com')
    dismiss_consent_overlays(page)
    evidence_tracker.click('#backpack-add-to-cart', label='Sauce Labs Backpack add to cart button')
```

**After (fixed):**
```python
def test_02_add_item(page):
    # --- Prerequisite: login (injected from TC-01) ---
    evidence_tracker.navigate('https://www.saucedemo.com')
    dismiss_consent_overlays(page)
    evidence_tracker.fill('#user-name', 'standard_user', label='username input')
    evidence_tracker.fill('#password', 'secret_sauce', label='password input')
    evidence_tracker.click('#login-button', label='login button')
    # --- Original test steps ---
    evidence_tracker.click('#backpack-add-to-cart', label='Sauce Labs Backpack add to cart button')
    evidence_tracker.assert_visible('.cart-badge', label='cart badge updated')
```

---

## Architecture Changes

### New Files

| File | Purpose |
|------|---------|
| `src/prerequisite_injector.py` | Detects dependency chains and injects prerequisite steps |
| `tests/test_prerequisite_injector.py` | Unit tests for prerequisite detection and injection |

### Modified Files

| File | Change |
|------|--------|
| `src/orchestrator.py` | Call `PrerequisiteInjector` after placeholder resolution, before post-processing |
| `src/prompt_utils.py` | Add "prerequisite steps" instruction to skeleton prompt template |

### Unchanged Files (Protected)

| File | Reason |
|------|--------|
| `src/test_generator.py` | PROTECTED — stable |
| `src/evidence_tracker.py` | No changes — injected steps use existing `evidence_tracker` pattern |
| `src/placeholder_resolver.py` | No changes — injection happens after resolution |
| `src/placeholder_orchestrator.py` | No changes |
| `src/page_object_builder.py` | Not touched in Stage A (used in Stage B) |

---

## Implementation Plan

### Phase 1 — PrerequisiteInjector Module

**`src/prerequisite_injector.py`** — New module with:

```python
@dataclass
class PrerequisiteStep:
    """A resolved step extracted from a prerequisite test."""
    raw_line: str          # e.g., "    evidence_tracker.fill('#user-name', 'standard_user', ...)"
    source_test: str       # e.g., "test_01_login"
    source_condition: str  # e.g., "TC-01"

@dataclass
class InjectionPlan:
    """Describes what needs to be injected into a test."""
    target_test: str
    prerequisites: list[PrerequisiteStep]
    reason: str            # e.g., "TC-02 requires authentication (TC-01)"

class PrerequisiteInjector:
    """Detect dependency chains and inject prerequisite steps.
    
    Operates on resolved code (after placeholder resolution) using TestJourney data
    to understand which tests need prerequisite steps.
    """
    
    def analyze_dependencies(
        self,
        journeys: list[TestJourney],
        starting_url: str,
        scraped_pages: dict[str, list[dict]],
    ) -> dict[str, InjectionPlan]:
        """Return injection plans for tests that need prerequisite steps.
        
        Algorithm:
        1. Build a map of test_name → first GOTO target page
        2. For each test, check if first GOTO resolves to starting_url
        3. If yes, check if criterion text contains post-auth keywords
        4. If both true, mark as needing prerequisite injection
        5. Extract resolved steps from the auth test (usually test_01)
        """
        ...
    
    def inject_into_code(
        self,
        code: str,
        injection_plans: dict[str, InjectionPlan],
    ) -> str:
        """Prepend prerequisite steps into the target test functions.
        
        Preserves indentation, adds comment markers, maintains evidence_tracker pattern.
        """
        ...
```

**Key design decisions:**
- Operates on **resolved code** (after placeholder resolution), not skeleton code
- Uses `TestJourney` data to identify test boundaries and step content
- Injects **resolved `evidence_tracker` calls** (not placeholders) — no second resolution pass needed
- Adds `# --- Prerequisite: <condition_ref> ---` comment markers for human readability

### Phase 2 — Prompt Enhancement

**`src/prompt_utils.py`** — Add prerequisite instruction to skeleton prompt:

```
=== PREREQUISITE STEPS ===
Each test must be self-contained. If a test depends on earlier criteria 
being completed first (e.g., you must log in before adding items to cart),
include those prerequisite steps at the start of the test function.
```

This is a **soft fix** — it helps the LLM generate better skeletons but doesn't replace the post-processing injection (which handles edge cases the LLM still gets wrong).

### Phase 3 — Orchestrator Integration

**`src/orchestrator.py`** — Add injection step after Phase 4 (placeholder resolution):

```python
# After placeholder resolution, before post-processing:
self._debug("phase=prerequisite_injection start")
injector = PrerequisiteInjector()
injection_plans = injector.analyze_dependencies(
    journeys=journeys,
    starting_url=self._starting_url,
    scraped_pages=scraped_data,
)
if injection_plans:
    final_code = injector.inject_into_code(final_code, injection_plans)
    self._debug(f"phase=prerequisite_injection injected={len(injection_plans)} tests")
self._debug("phase=prerequisite_injection done")
```

### Phase 4 — Tests

**`tests/test_prerequisite_injector.py`** — Unit tests covering:
- Detects auth dependency when first GOTO resolves to starting URL
- Does NOT inject for tests that already include login steps
- Handles multi-level chains (TC-03 depends on TC-01 → TC-02)
- Preserves indentation and comment markers
- Edge case: no starting URL provided
- Edge case: single test (no prerequisites possible)

---

## Success Criteria

- [x] `src/prerequisite_injector.py` created with full type annotations (96% test coverage)
- [x] `tests/test_prerequisite_injector.py` — 17 tests, all pass
- [x] Orchestrator integration — injection runs after placeholder resolution
- [x] Prompt enhancement — skeleton prompt includes prerequisite instruction
- [ ] UAT re-run: saucedemo tests 2-6 include login steps and no longer skip (requires LLM/GPU)
- [x] `ruff check src/prerequisite_injector.py` passes
- [x] `mypy src/prerequisite_injector.py` passes
- [x] Tests for modified files pass (`pytest tests/test_prerequisite_injector.py tests/test_prompt_utils.py tests/test_skeleton_prompt_template.py -v`) — 54/54 pass
- [x] No regressions in evidence tracking (sidecar JSON still captured)

---

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| LLM already includes login steps → double injection | Tests have duplicate login code | Detection logic checks existing steps before injecting |
| Wrong prerequisite detected | Tests inject wrong steps | Conservative keyword matching + explicit test before merge |
| Large prerequisite chains | Tests become very long | Cap injection at 2 levels deep (TC-01 → TC-02, not TC-01 → TC-02 → TC-03) |
| Breaks existing working tests | Regression | Gate behind feature flag (`INJECT_PREREQUISITES=true` env var) |

---

## What This Does NOT Do (Stage B Scope)

Stage A is a **pragmatic fix** that solves the immediate problem. The following are deferred to Stage B:

- [ ] Page Object Model generation with composite methods (`LoginPage.login()`)
- [ ] EvidenceTracker-aware POM (injection of `EvidenceTracker` into POM methods)
- [ ] Test plan review UI (reorder criteria before generation)
- [ ] Dynamic prerequisite detection via LLM reasoning (not keyword-based)

---

## Session Execution Plan

This feature is designed to be completed in **one focused session** following the AGENTS.md rules:

1. Create `src/prerequisite_injector.py` with `PrerequisiteInjector` class
2. Create `tests/test_prerequisite_injector.py` with unit tests
3. Update `src/prompt_utils.py` with prerequisite instruction
4. Integrate into `src/orchestrator.py`
5. Run `ruff`, `mypy`, `pytest`
6. Re-run UAT saucedemo script to verify tests 2-6 no longer skip
7. Human reviews `git diff --staged` → commit

---

*Last updated: 2026-05-09*  
*Author: AI Session (Cline)*