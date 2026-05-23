# Feature Plan: Page Object Model with EvidenceTracker (Stage B)

> **Status:** Planned  
> **Created:** 2026-05-09  
> **Updated:** 2026-05-09  
> **Supersedes:** N/A (new feature)  
> **Prerequisite:** FEATURE_PLAN_test_prerequisite_injection.md (Stage A must be complete)  
> **Related:** BACKLOG.md — to be added after implementation  

---

## Problem Statement

Stage A (prerequisite injection) solves the immediate problem of missing login steps by duplicating `evidence_tracker` calls across tests. This works but creates **code duplication**: every test that needs authentication repeats the same login steps inline.

**Current pattern (after Stage A):**
```python
def test_02_add_item(page):
    # --- Prerequisite: login (injected from TC-01) ---
    evidence_tracker.fill('#user-name', 'standard_user', label='username input')
    evidence_tracker.fill('#password', 'secret_sauce', label='password input')
    evidence_tracker.click('#login-button', label='login button')
    # --- Original test steps ---
    evidence_tracker.click('#backpack-add-to-cart', label='add to cart')

def test_03_navigate_cart(page):
    # --- Prerequisite: login (injected from TC-01) ---
    evidence_tracker.fill('#user-name', 'standard_user', label='username input')
    evidence_tracker.fill('#password', 'secret_sauce', label='password input')
    evidence_tracker.click('#login-button', label='login button')
    # --- Original test steps ---
    evidence_tracker.click('#cart-icon', label='shopping cart icon')
```

**Problems with duplication:**
1. **Maintenance burden:** If login credentials or locators change, every test must be regenerated
2. **Readability:** Test functions are cluttered with boilerplate setup code
3. **No semantic grouping:** Login steps are scattered across tests instead of being a cohesive unit

**Industry standard solution:** Page Object Model (POM) — encapsulate page interactions in reusable classes with composite methods.

---

## Proposed Solution (Stage B)

Generate **Page Object classes** that wrap `EvidenceTracker` and provide composite methods for common operations (login, add to cart, navigate checkout). Tests call POM methods instead of inline `evidence_tracker` calls.

### Key Design: EvidenceTracker-Aware POM

The critical insight from Stage A analysis is that **evidence tracking must be preserved**. The POM must accept `EvidenceTracker` as a dependency and delegate all interactions through it:

```python
# generated_tests/pages/login_page.py
class LoginPage:
    """Page Object for https://www.saucedemo.com"""
    
    URL = "https://www.saucedemo.com"
    
    def __init__(self, page: Page, tracker: EvidenceTracker) -> None:
        self.page = page
        self.tracker = tracker  # EvidenceTracker injected
    
    def navigate(self) -> None:
        self.tracker.navigate(self.URL)
    
    def fill_username(self, value: str) -> None:
        self.tracker.fill("#user-name", value, label="username input")
    
    def fill_password(self, value: str) -> None:
        self.tracker.fill("#password", value, label="password input")
    
    def click_login_button(self) -> None:
        self.tracker.click("#login-button", label="login button")
    
    def login(self, username: str, password: str) -> None:
        """Composite action — combines prerequisite steps."""
        self.navigate()
        self.fill_username(username)
        self.fill_password(password)
        self.click_login_button()
```

```python
# generated_tests/test_saucedemo.py
from pages.login_page import LoginPage
from pages.products_page import ProductsPage

def test_01_login(page):
    login = LoginPage(page, evidence_tracker)
    login.login('standard_user', 'secret_sauce')
    evidence_tracker.assert_visible(".inventory_item", label="products page")

def test_02_add_item(page):
    # Reuse login — ONE line instead of 4 inline steps
    login = LoginPage(page, evidence_tracker)
    login.login('standard_user', 'secret_sauce')
    products = ProductsPage(page, evidence_tracker)
    products.click_add_to_cart_backpack()
    evidence_tracker.assert_visible(".cart-badge", label="cart badge updated")
```

### Benefits

| Aspect | Before (Stage A) | After (Stage B) |
|--------|------------------|-----------------|
| Login code location | Duplicated in every test | Defined once in `LoginPage` |
| Evidence tracking | ✅ Preserved | ✅ Preserved (via tracker delegation) |
| Test readability | Cluttered with boilerplate | Clean — focus on test-specific steps |
| Maintenance | Regenerate all tests on locator change | Update one POM class |
| Composite actions | Manual injection | `login.login(...)` — semantic |

---

## Architecture Changes

### New Files

| File | Purpose |
|------|---------|
| `src/pom_generator.py` | Generates POM classes from scraped page data + resolved locators |
| `tests/test_pom_generator.py` | Unit tests for POM generation |

### Modified Files

| File | Change |
|------|--------|
| `src/page_object_builder.py` | Extend to accept `EvidenceTracker` pattern, generate composite methods |
| `src/placeholder_resolver.py` | New resolution mode: resolve to POM method calls instead of inline `evidence_tracker` |
| `src/orchestrator.py` | New phase: generate POM classes after scraping, before test generation |
| `src/prompt_utils.py` | Update skeleton prompt to allow `{{POM:ClassName:method}}` placeholder syntax |
| `src/skeleton_parser.py` | Parse POM-style placeholders |
| `src/code_postprocessor.py` | Import POM classes into generated tests |
| `streamlit_app.py` | Add "Test Plan Review" step with reorderable criteria |

### Unchanged Files (Protected)

| File | Reason |
|------|--------|
| `src/test_generator.py` | PROTECTED — stable |
| `src/evidence_tracker.py` | No changes — POM delegates to it |
| `src/scraper.py` | No changes |
| `src/journey_scraper.py` | No changes |

---

## Implementation Plan

### Phase 1 — EvidenceTracker-Aware POM Generation

**Extend `src/page_object_builder.py`:**

The existing `PageObjectBuilder` generates POM classes but they use raw `page.locator()` calls. Extend it to:

1. Accept `use_evidence_tracker: bool` flag
2. Generate methods that delegate to `self.tracker.click()` / `self.tracker.fill()` instead of `self.page.locator().click()`
3. Generate composite methods for common patterns (login, add_to_cart, checkout)

```python
def _build_method_source(
    self,
    method_name: str,
    selector: str,
    role: str,
    *,
    prefer_first: bool = False,
    use_evidence_tracker: bool = False,
) -> str:
    if use_evidence_tracker:
        if method_name.startswith("fill_"):
            return f"    def {method_name}(self, value: str) -> None:\n" \
                   f"        self.tracker.fill({selector!r}, value, label={method_name!r})\n"
        return f"    def {method_name}(self) -> None:\n" \
               f"        self.tracker.click({selector!r}, label={method_name!r})\n"
    # Existing raw page.locator() path (backward compatible)
    ...
```

**New composite method detection:**

The generator detects common patterns and creates composite methods:
- If page has username + password + login button → generate `login(username, password)` method
- If page has product cards with "add to cart" buttons → generate `add_item_to_cart(item_name)` method
- If page has checkout form fields → generate `checkout(first_name, last_name, postal_code)` method

### Phase 2 — POM Placeholder Syntax

**Extend skeleton prompt to support POM-style placeholders:**

```
=== ALLOWED STEP FORMATS ===
{{CLICK:element description}}
{{FILL:element description:value to type}}
{{ASSERT:element description}}
{{GOTO:page keyword}}
{{POM:ClassName:method_name}}        ← NEW: POM method call
```

**Example skeleton with POM:**
```python
def test_02_add_item(page):
    {{POM:LoginPage:login}}
    {{POM:ProductsPage:add_item_to_cart}}
    {{ASSERT:cart badge updated}}
```

**Resolves to:**
```python
def test_02_add_item(page):
    login = LoginPage(page, evidence_tracker)
    login.login('standard_user', 'secret_sauce')
    products = ProductsPage(page, evidence_tracker)
    products.add_item_to_cart('Sauce Labs Backpack')
    evidence_tracker.assert_visible('.cart-badge', label='cart badge updated')
```

### Phase 3 — Placeholder Resolver POM Mode

**Extend `src/placeholder_resolver.py`:**

Add a new resolution path for `{{POM:...}}` placeholders:

```python
def resolve_pom_placeholder(self, placeholder: PlaceholderUse) -> str:
    """Resolve a POM-style placeholder to a POM method call.
    
    {{POM:LoginPage:login}} → LoginPage(page, evidence_tracker).login(...)
    """
    class_name, method_name = placeholder.description.split(':')
    # Generate instantiation + method call
    return f"    {method_name} = {class_name}(page, evidence_tracker)\n    {method_name}.{method_name}(...)"
```

### Phase 4 — Test Plan Review UI

**Extend `streamlit_app.py`:**

Add a "Review Test Plan" step between analysis and generation:

1. Display inferred test plan as a table:
   | Order | Test Name | Criteria | Estimated Prerequisites |
   |-------|-----------|----------|------------------------|
   | 1 | test_01_login | TC-01: Log in... | None |
   | 2 | test_02_add_item | TC-02: Add item... | test_01_login |
   | 3 | test_03_navigate_cart | TC-03: Navigate... | test_01_login, test_02_add_item |

2. Allow user to reorder tests using drag-and-drop or up/down buttons
3. Allow user to edit prerequisites (add/remove)
4. Pass reordered plan to generator

**This uses `src/test_plan.py`** which already exists but is not yet integrated with the UI.

### Phase 5 — Code Post-Processor POM Imports

**Extend `src/code_postprocessor.py`:**

Add POM class imports to generated test files:

```python
def _add_pom_imports(code: str, pom_classes: list[str]) -> str:
    """Add POM import statements to generated test code."""
    imports = "\n".join(f"from pages.{cls.lower()}_page import {cls}" for cls in pom_classes)
    return f"{imports}\n\n{code}"
```

---

## Success Criteria

- [ ] `src/pom_generator.py` created (or `page_object_builder.py` extended)
- [ ] POM classes use `EvidenceTracker` for all interactions
- [ ] Composite methods generated for common patterns (login, add_to_cart, checkout)
- [ ] `{{POM:...}}` placeholder syntax supported in skeleton prompt
- [ ] Placeholder resolver handles POM placeholders
- [ ] Generated tests import and use POM classes
- [ ] Evidence tracking preserved (sidecar JSON captured for all POM method calls)
- [ ] UAT re-run: saucedemo tests use POM and pass
- [ ] `ruff`, `mypy` pass on all modified files
- [ ] Existing tests still pass
- [ ] Test plan review UI allows reordering criteria

---

## Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| LLM doesn't use POM placeholders | Falls back to inline evidence_tracker | Stage A injection still works as fallback |
| Composite method detection too aggressive | Generates wrong composite methods | Conservative pattern matching + human review in UI |
| Breaking change to existing generated tests | Users can't run old tests | Backward compatible — POM is opt-in |
| EvidenceTracker API changes | POM breaks | EvidenceTracker is stable — any changes documented |
| Complex to implement | Long development time | Phased rollout — Phase 1 first, then POM syntax |

---

## Relationship to Stage A

Stage B **depends on** Stage A being complete:

1. Stage A proves the prerequisite injection concept works
2. Stage A's detection logic (`PrerequisiteInjector.analyze_dependencies()`) is reused by Stage B's composite method detection
3. Stage B replaces Stage A's inline injection with POM method calls
4. Stage A remains as a **fallback** for cases where POM generation doesn't produce useful composite methods

**Migration path:**
```
Stage 0 (current): No prerequisite handling → tests skip
Stage A: Inline prerequisite injection → tests pass but duplicate code
Stage B: POM with composite methods → tests pass with clean, maintainable code
```

---

## Session Execution Plan

This feature should be completed in **2-3 focused sessions** (one feature per session rule):

### Session B1: POM Generation
1. Extend `page_object_builder.py` with `use_evidence_tracker` mode
2. Create composite method detection logic
3. Write unit tests
4. Run ruff, mypy, pytest

### Session B2: POM Placeholder Syntax
1. Add `{{POM:...}}` to skeleton prompt
2. Extend placeholder resolver for POM mode
3. Extend code post-processor for POM imports
4. Write unit tests
5. Run ruff, mypy, pytest

### Session B3: Test Plan Review UI
1. Extend `streamlit_app.py` with review step
2. Integrate `test_plan.py` for reorderable criteria
3. Manual UAT testing
4. Run ruff, mypy, pytest

---

## Out of Scope (Future Considerations)

- [ ] LLM-driven composite method naming (currently keyword-based)
- [ ] Automatic POM class splitting (one file per page vs. single file)
- [ ] POM versioning (track POM changes across regenerations)
- [ ] Cross-page composite actions (e.g., `checkout_flow.login_and_add_item()`)

---

*Last updated: 2026-05-09*  
*Author: AI Session (Cline)*