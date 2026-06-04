# FEATURE SPEC — AI-010: Evidence-Aware Page Object Model Mode

**Status:** Design — not yet implemented
**Created:** 2026-06-04
**Supersedes:** N/A
**Depends on:** `src/page_object_builder.py` (stable), `src/evidence_tracker.py` (stable), `src/placeholder_orchestrator.py`, `src/orchestrator.py`, `src/pipeline_writer.py`
**Related:** AI-026 (persist generated tests — uses same page object exports)
**Priority:** Medium — portfolio differentiator + Engineering Manager persona

---

## Problem Statement

The current pipeline generates tests using two patterns:
1. **Direct `evidence_tracker` calls** — each test step calls `evidence_tracker.click()`, `evidence_tracker.fill()` directly
2. **Page Object classes** — `src/page_object_builder.py` generates POM classes, but they use raw `page.locator()` (not evidence-aware)

There is no mechanism to generate tests that use evidence-aware POM classes — i.e., POM methods that delegate to `EvidenceTracker` for diagnostic capture while providing reusable, maintainable structure.

### Current Gap

| Mode | Evidence Tracking | Reusability | Maintainability |
|------|------------------|-------------|-----------------|
| Direct `evidence_tracker` | ✅ Yes | ❌ Duplicated across tests | ❌ Update all tests on locator change |
| Current POM (`page.locator()`) | ❌ No | ✅ Methods per page | ✅ Update one class |
| **Proposed: Evidence-aware POM** | ✅ Yes (wrapped) | ✅ Methods per page | ✅ Update one class |

### Why Evidence-Aware POM?

1. **Evidence tracking is non-negotiable** — the sidecar JSON, failure diagnostics, and screenshot capture are core features. Any POM mode must preserve this.
2. **POM without evidence is a regression** — generating `page.locator()` POM classes would lose all diagnostic data.
3. **POM provides maintainability** — one class per page, one change fixes all tests using that page.
4. **The toggle is about structure, not evidence** — the user chooses whether tests use flat `evidence_tracker` calls or structured POM methods. Evidence tracking happens in both modes.

---

## Proposed Solution: Evidence-Aware POM (Always On)

### Design Principle

**Evidence tracking is always enabled.** The POM toggle controls *structure* (flat calls vs. POM methods), not *evidence collection*.

### Architecture

```
Generated test (POM mode):
┌─────────────────────────────────────────┐
│ def test_02_add_item(page):             │
│     login = LoginPage(page, et)    ◄── POM method (evidence-aware)
│     login.login('user', 'pass')         │
│     products = ProductsPage(page, et)   │
│     products.add_item_to_cart()         │
│                                         │
│     et.assert_visible(...)        ◄── Direct evidence call (assertions)
└─────────────────────────────────────────┘
         │                    │
         ▼                    ▼
┌──────────────────┐  ┌──────────────────┐
│ EvidenceTracker  │  │ Generated POM    │
│ (sidecar JSON,   │  │ class methods    │
│  screenshots,    │  │ delegate to      │
│  diagnostics)    │  │ EvidenceTracker  │
└──────────────────┘  └──────────────────┘
```

### Evidence-Aware POM Class

The existing `PageObjectBuilder` generates classes like:
```python
class LoginPage:
    def __init__(self, page: Page) -> None:
        self.page = page

    def click_login_button(self) -> None:
        self.page.locator("#login-button").click()
```

**Proposed evidence-aware version:**
```python
class LoginPage:
    """Page Object for https://www.saucedemo.com"""
    
    URL = "https://www.saucedemo.com"
    
    def __init__(self, page: Page, tracker: EvidenceTracker) -> None:
        self.page = page
        self.tracker = tracker  # EvidenceTracker injected
    
    def navigate(self) -> None:
        self.tracker.navigate(self.URL)
    
    def click_login_button(self) -> None:
        self.tracker.click("#login-button", label="login button")
    
    def fill_username(self, value: str) -> None:
        self.tracker.fill("#user-name", value, label="username input")
```

### Key Insight: Export vs. Internal

The evidence-aware POM is used **internally during test execution** to capture diagnostics. When the test package is exported (for consumption by other teams/tools), the evidence wrapper is stripped:

```python
# INTERNAL (used at test generation time — evidence-aware):
class LoginPage:
    def __init__(self, page: Page, tracker: EvidenceTracker) -> None:
        self.page = page
        self.tracker = tracker

    def click_login_button(self) -> None:
        self.tracker.click("#login-button", label="login button")

# EXPORTED (clean POM for external consumption):
class LoginPage:
    def __init__(self, page: Page) -> None:
        self.page = page

    def click_login_button(self) -> None:
        self.page.locator("#login-button").click()
```

This is achieved by running the generated code through `code_postprocessor._rewrite_evidence_tracker()` which strips the evidence wrapper for export.

---

## Implementation Plan

### Phase 1: Evidence-Aware PageObjectBuilder

**File:** `src/page_object_builder.py`

Extend `PageObjectBuilder` to generate evidence-aware POM classes:

1. Add `use_evidence_tracker: bool = False` parameter to `build_page_object()` and `_build_module_source()`
2. When enabled, generate `__init__` with `EvidenceTracker` parameter
3. Generate methods that delegate to `self.tracker.click()` / `self.tracker.fill()` / `self.tracker.navigate()` instead of `self.page.locator()`
4. Keep existing `page.locator()` generation as fallback (backward compatible)

**Changes to `_build_method_source()`:**
```python
@staticmethod
def _build_method_source(
    method_name: str,
    selector: str,
    role: str,
    *,
    prefer_first: bool = False,
    use_evidence_tracker: bool = False,
) -> str:
    if use_evidence_tracker:
        label = method_name.replace("click_", "").replace("fill_", "").replace("_", " ")
        if method_name.startswith("fill_"):
            return (
                f"    def {method_name}(self, value: str) -> None:\n"
                f"        self.tracker.fill({selector!r}, value, label={label!r})\n"
            )
        if method_name.startswith("navigate_"):
            return (
                f"    def {method_name}(self) -> None:\n"
                f"        self.tracker.navigate({selector!r}, label={label!r})\n"
            )
        return (
            f"    def {method_name}(self) -> None:\n"
            f"        self.tracker.click({selector!r}, label={label!r})\n"
        )
    # Existing page.locator() path (backward compatible)
    ...
```

**Changes to `_build_module_source()`:**
```python
def _build_module_source(
    self,
    *,
    class_name: str,
    url: str,
    methods: list[tuple[str, str]],
    element_count: int,
    use_evidence_tracker: bool = False,
) -> str:
    if use_evidence_tracker:
        init_code = (
            "    def __init__(self, page: Page, tracker: EvidenceTracker) -> None:\n"
            "        self.page = page\n"
            "        self.tracker = tracker\n"
        )
        imports = (
            '"""Auto-generated page object module."""\n\n'
            "from playwright.sync_api import Page\n"
            "from src.evidence_tracker import EvidenceTracker\n\n\n"
        )
    else:
        init_code = (
            "    def __init__(self, page: Page) -> None:\n"
            "        self.page = page\n"
        )
        imports = (
            '"""Auto-generated page object module."""\n\n'
            "from playwright.sync_api import Page\n\n\n"
        )
    ...
```

### Phase 2: POM Mode in PlaceholderOrchestrator

**File:** `src/placeholder_orchestrator.py`

The orchestrator currently resolves placeholders to `evidence_tracker` calls. Add POM mode:

1. Add `pom_mode: bool = False` to `PlaceholderOrchestrator.__init__()`
2. In `_generate_test_code()`, when POM mode is enabled:
   - Generate POM class imports: `from pages.login_page import LoginPage`
   - Generate POM instantiations: `login = LoginPage(page, evidence_tracker)`
   - Group resolved steps by page, then generate POM method calls
3. Assertions remain as direct `evidence_tracker` calls (not POM methods)

**Skeleton prompt update** — add POM-style placeholders:
```
=== ALLOWED STEP FORMATS ===
{{CLICK:element description}}
{{FILL:element description:value to type}}
{{ASSERT:element description}}
{{GOTO:page keyword}}
{{POM:ClassName:method_name}}        ← NEW: POM method call
```

**Resolution flow:**
```
Skeleton: {{POM:LoginPage:login}}
  → PlaceholderOrchestrator detects {{POM:...}}
  → Generates: login = LoginPage(page, evidence_tracker)
               login.login('standard_user', 'secret_sauce')
```

### Phase 3: Pipeline Configuration

**Files:** `src/orchestrator.py`, `src/pipeline_models.py`

1. Add `pom_mode: bool` to pipeline configuration
2. Pass through to `PlaceholderOrchestrator` and `PageObjectBuilder`
3. When POM mode is enabled, generate both:
   - POM classes (evidence-aware) in `generated_tests/pages/`
   - Test files that import and use POM classes

### Phase 4: UI Toggle

**Files:** `streamlit_app.py`, `cli/main.py`, `cli/config.py`

**Streamlit UI:**
- Add radio button: "Test Structure" → `Simple tests` / `Page Object Model`
- Display in configuration section alongside URL and user story inputs
- Store in `st.session_state.pom_mode`

**CLI:**
- Add `--pom` flag to CLI argument parser
- Store in session state

### Phase 5: Export Stripping

**File:** `src/code_postprocessor.py`

When exporting generated tests for external consumption, strip evidence wrapper from POM classes:

```python
def _strip_evidence_from_pom(code: str) -> str:
    """Convert evidence-aware POM to clean POM for export.
    
    Before: self.tracker.click("#button", label="button")
    After:  self.page.locator("#button").click()
    
    Before: def __init__(self, page: Page, tracker: EvidenceTracker) -> None:
    After:  def __init__(self, page: Page) -> None:
    """
    # 1. Remove EvidenceTracker import
    # 2. Replace __init__ signature
    # 3. Replace self.tracker.* calls with self.page.locator().*
    ...
```

This is triggered when the user exports the test package (AI-026 integration).

---

## Benefits Analysis

### For the User

| Benefit | Simple Mode | POM Mode |
|---------|-------------|----------|
| Evidence tracking | ✅ | ✅ |
| Failure diagnostics | ✅ | ✅ |
| Screenshot capture | ✅ | ✅ |
| Sidecar JSON | ✅ | ✅ |
| Code structure | Flat | Structured (POM classes) |
| Locator reuse | No (duplicated) | Yes (one class per page) |
| Maintainability | Low (update all tests) | High (update one class) |

### For the Project

1. **Portfolio differentiator** — "Evidence-aware POM generation" is a unique selling point
2. **Engineering Manager appeal** — POM mode produces code that looks like industry-standard Playwright tests
3. **No evidence regression** — Unlike current POM (which loses evidence), this mode preserves all diagnostics
4. **Backward compatible** — Existing simple mode unchanged, POM mode is opt-in
5. **AI-026 integration** — Export stripping makes POM packages consumable by external teams

---

## Interaction with EvidenceTracker

### How Evidence-Aware POM Uses EvidenceTracker

1. **All interactions go through EvidenceTracker** — `click()`, `fill()`, `navigate()`, `assert_visible()` all delegate to `self.tracker.*`
2. **Sidecar JSON is still generated** — EvidenceTracker writes `<test_name>.evidence.json` per test, not per POM class
3. **Failure diagnostics preserved** — When a POM method call fails, EvidenceTracker captures the failure note, diagnosis, and screenshot
4. **No changes to EvidenceTracker needed** — The EvidenceTracker API is used as-is; POM is just a wrapper

### Evidence Flow (POM Mode)

```
Test execution:
  test_02_add_item(page)
    → login = LoginPage(page, evidence_tracker)
    → login.login('user', 'pass')
       → evidence_tracker.fill("#user-name", "user", label="username input")  [STEP 1 recorded]
       → evidence_tracker.fill("#password", "pass", label="password input")  [STEP 2 recorded]
       → evidence_tracker.click("#login-button", label="login button")  [STEP 3 recorded]
    → products = ProductsPage(page, evidence_tracker)
    → products.add_item_to_cart()
       → evidence_tracker.click("#add-to-cart", label="add to cart")  [STEP 4 recorded]
    → evidence_tracker.assert_visible(".cart-badge", label="cart badge")  [STEP 5 recorded]

EvidenceTracker writes:
  evidence/test_02_add_item.evidence.json
  (contains 5 steps with locators, timestamps, screenshots, failure notes)
```

### Evidence Flow (Export Mode)

When the user exports the test package for external consumption:
1. POM classes are rewritten by `code_postprocessor._strip_evidence_from_pom()`
2. EvidenceTracker dependency is removed
3. Clean POM classes use `page.locator()` directly
4. No evidence sidecar generated (external tests don't use EvidenceTracker)

---

## Interaction with AI-026 (Persist Generated Tests)

### Shared Infrastructure

Both AI-010 and AI-026 use the same generated test package structure:

```
generated_tests/<package_name>/
├── test_*.py                    # Generated test files (use POM classes in POM mode)
├── conftest.py                  # Shared fixtures (includes evidence_tracker fixture)
├── pages/                       # Generated page object modules
│   ├── __init__.py
│   └── po_*.py                  # Evidence-aware POM classes
├── scrape_manifest.json         # Scraped page data
├── package_manifest.json        # Package metadata (AI-026)
├── run_results_*.json           # Run outcomes (AI-026)
└── evidence/                    # Screenshot evidence, failure diagnostics
```

### AI-026 Integration Points

1. **Package manifest** — `package_manifest.json` includes `pom_mode: true/false` to indicate generation mode
2. **Re-run saved suite** — When re-running a POM-mode package, the evidence-aware POM classes are used as-is
3. **Export for external use** — AI-026's export functionality strips evidence wrapper (Phase 5)
4. **Evidence paths** — Both modes generate evidence sidecars in the same location

### No Conflicts

- AI-010 controls *structure* (POM vs. flat)
- AI-026 controls *persistence* (save/load/re-run)
- They operate on different aspects of the same artifacts
- Both benefit from shared evidence infrastructure

---

## Success Criteria

- [ ] `PageObjectBuilder` generates evidence-aware POM classes when `use_evidence_tracker=True`
- [ ] POM classes accept `EvidenceTracker` as a dependency in `__init__`
- [ ] POM methods delegate to `self.tracker.click()` / `self.tracker.fill()` / `self.tracker.navigate()`
- [ ] UI toggle in Streamlit: "Simple tests" / "Page Object Model"
- [ ] CLI `--pom` flag enables POM mode
- [ ] Generated tests in POM mode import and use POM classes
- [ ] Assertions remain as direct `evidence_tracker` calls (not POM methods)
- [ ] Evidence sidecar JSON is generated in both modes
- [ ] Failure diagnostics captured in both modes
- [ ] Export mode strips evidence wrapper from POM classes
- [ ] `ruff`, `mypy`, and `pytest` pass after all changes
- [ ] Existing simple mode tests continue to work (backward compatible)

---

## Testing Strategy

| Test | Type | Description |
|------|------|-------------|
| `test_build_evidence_aware_pom` | Unit | POM class generates with EvidenceTracker dependency |
| `test_pom_method_delegates_to_tracker` | Unit | POM method calls `self.tracker.click()` not `self.page.locator()` |
| `test_pom_fill_method_with_value` | Unit | Fill methods pass value parameter through |
| `test_pom_label_generation` | Unit | Labels are derived from method names |
| `test_backward_compatible_no_tracker` | Unit | Without `use_evidence_tracker`, generates raw `page.locator()` |
| `test_pom_mode_generates_imports` | Unit | Test files import POM classes correctly |
| `test_pom_mode_instantiates_with_tracker` | Unit | Test code creates POM with `(page, evidence_tracker)` |
| `test_assertions_remain_direct` | Unit | ASSERT placeholders generate direct `evidence_tracker` calls |
| `test_export_strips_evidence` | Unit | `_strip_evidence_from_pom()` converts tracker calls to locator calls |
| `test_export_removes_import` | Unit | Export removes `EvidenceTracker` import |
| `test_evidence_sidecar_in_pom_mode` | Integration | Evidence JSON generated when running POM-mode test |
| `test_failure_diagnostics_in_pom_mode` | Integration | Failed POM method captures failure note |

---

## Session Execution Plan

This feature should be completed in **2 focused sessions**:

### Session 1: Evidence-Aware PageObjectBuilder
1. Extend `page_object_builder.py` with `use_evidence_tracker` mode
2. Generate evidence-aware `__init__` and method signatures
3. Write unit tests for POM generation
4. Run ruff, mypy, pytest

### Session 2: Pipeline Integration + UI Toggle
1. Add `pom_mode` to `PlaceholderOrchestrator`
2. Wire through `orchestrator.py` pipeline
3. Add UI toggle to Streamlit and CLI
4. Add export stripping to `code_postprocessor.py`
5. Write integration tests
6. Run ruff, mypy, pytest
7. Manual UAT with saucedemo

---

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| EvidenceTracker API changes | POM breaks | EvidenceTracker is stable — any changes documented in AGENTS.md |
| LLM doesn't use POM placeholders | Falls back to inline evidence_tracker | Simple mode remains as fallback |
| Export stripping misses edge cases | External tests break | Comprehensive unit tests for `_strip_evidence_from_pom()` |
| Complex to implement | Long development time | Phased rollout — Phase 1 (POM builder) first, then pipeline integration |
| Breaking change to existing tests | Users can't run old tests | Backward compatible — POM is opt-in via toggle |

---

*Last updated: 2026-06-04*
*Author: AI Session (Cline)*