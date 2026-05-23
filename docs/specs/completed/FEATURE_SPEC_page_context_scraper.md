# FEATURE SPEC: Page Context Scraper
## AI Playwright Test Generator — Phase 2 Enhancement

**Status:** Proposed  
**Priority:** High  
**Fits into:** Phase 2 (User Story Intelligence)  
**New file:** `src/page_context_scraper.py`  
**Estimated effort:** 2–3 days  

---

## Problem Statement

The generator currently has no knowledge of the application it is testing.
It invents locators, guesses URLs, and produces tests that fail immediately
because the selectors don't match the real DOM.

Manual testers then have to open DevTools, hunt for the right attributes,
and hand-edit the generated file — exactly the kind of technical task the
tool is supposed to remove.

---

## Proposed Solution: Two-Phase Generation

Split generation into two distinct phases so each does what it's good at:

```
BEFORE (current)
────────────────
User story  ──►  LLM  ──►  Test (guessed locators, wrong URL)

AFTER (proposed)
────────────────
User story  ──►  LLM (intent)   ──►  "what to test"
Site URL    ──►  Scraper (DOM)  ──►  "real selectors"
                       │
                       ▼
                LLM (combines both)  ──►  Test (real locators, correct URL)
```

The scraper's job is purely technical — visit the page, read the DOM, return
a structured summary of what is actually there.  The LLM's job is purely
intentional — given the user story AND the real page structure, write a test
that does what the tester meant.

---

## What the Scraper Extracts

The scraper visits the URL with a headless Playwright browser and pulls:

| Category | What it collects | Why |
|----------|-----------------|-----|
| **Inputs** | `aria-label`, `id`, `name`, `placeholder`, `type` | Real locator candidates |
| **Buttons** | `aria-label`, `role`, visible text, `data-testid` | Click targets |
| **Links** | `href`, visible text, `aria-label` | Navigation |
| **Forms** | Which inputs belong together, submit button | Test flow structure |
| **Page title** | `<title>` and `<h1>` | Confirms correct page |
| **data-testid** | All elements with this attribute | Highest-quality locators |
| **Visible text** | Key headings and labels | Confirms page state |

It does **not** attempt to understand the page, follow links, or discover
happy paths automatically.  That boundary is intentional — see Design
Decisions below.

---

## Output Format

The scraper returns a `PageContext` dataclass that gets serialised into the
LLM prompt as a structured block:

```python
@dataclass
class PageElement:
    tag: str                          # input, button, a, etc.
    role: Optional[str]               # ARIA role
    label: Optional[str]              # aria-label or associated <label>
    test_id: Optional[str]            # data-testid value
    element_id: Optional[str]         # id attribute
    name: Optional[str]               # name attribute
    placeholder: Optional[str]        # placeholder text
    visible_text: Optional[str]       # innerText (buttons/links)
    input_type: Optional[str]         # text, password, email, etc.
    is_required: bool = False


@dataclass
class PageContext:
    url: str                          # actual URL visited
    page_title: str                   # <title> content
    h1_text: Optional[str]            # first <h1>
    elements: list[PageElement]       # all interactive elements
    forms: list[list[PageElement]]    # grouped by parent <form>
    scraped_at: str                   # ISO timestamp
    scrape_duration_ms: int           # how long it took
```

---

## LLM Prompt Injection

The `PageContext` gets formatted and prepended to the existing LLM prompt:

```
=== PAGE CONTEXT (scraped from http://localhost:8080/mock_insurance_site.html) ===
Page title : Insurance Policy Management
H1         : Insurance Policy Management

INTERACTIVE ELEMENTS:
  [button]  aria-label="Add Driver"        visible="Add Driver"
  [button]  aria-label="Save Vehicle"      visible="Save Vehicle"  disabled=true
  [input]   aria-label="Driver Name"       id="driverNameInput"    type=text
  [input]   aria-label="License Number"    id="licenseInput"       type=text
  [ul]      aria-label="Assigned Drivers"  id="driverList"

FORMS: 1 form detected
  Form 1: driverNameInput, licenseInput → addDriverToListBtn

USE THESE LOCATORS. Do not invent selectors that are not listed above.
=============================================================

USER STORY:
As a policy holder I want to add multiple drivers to my vehicle so that
they are covered under my insurance policy.

ACCEPTANCE CRITERIA:
- I can enter a driver name and licence number
- Clicking Add Driver adds them to the list
- I can add multiple drivers before saving
- Save Vehicle is disabled until at least one driver is added
```

The key instruction — **"Do not invent selectors not listed above"** — is
what prevents the LLM from hallucinating `[data-testid=email]` on a page
that has no such element.

---

## Locator Priority

When building the prompt context, elements are ranked so the LLM picks the
most robust locator first:

```
1. data-testid    →  page.get_by_test_id("add-driver")
2. aria-label     →  page.get_by_role("button", name="Add Driver")
3. id attribute   →  page.locator("#driverNameInput")
4. name attribute →  page.locator("[name='driverName']")
5. visible text   →  page.get_by_text("Add Driver")   ← least preferred
```

The scraper annotates each element with its recommended Playwright locator
string so the LLM can use it directly.

---

## Design Decisions

### Why NOT auto-discover happy paths?

If the scraper followed links and clicked through the site autonomously it
would find paths that technically work but may represent poor UX.  A
"Submit" button that exists is not the same as a submit flow that a real
user can complete without confusion.

The tester's user story is the source of truth for **what should work**.
The scraper only answers **where are the controls to do it**.

### Why scrape at generation time, not ahead of time?

Scraping at the moment the user clicks Generate means the context is always
fresh.  A pre-built site map would go stale whenever a developer changes
the DOM.

### What about pages behind authentication?

Phase 2 scope: public pages only.  The Streamlit UI will show a clear
message if the scraper gets a 401/403 or is redirected to a login page, and
fall back to generation without context (current behaviour).

Authentication support (cookie injection, credential passing) is a Phase 4
concern.

### What if the URL is unreachable?

Scraper failure is non-fatal.  If the URL is down, times out, or returns an
error, generation continues without page context and the user sees a warning:

```
⚠ Could not reach http://localhost:8080 — generating without page context.
  Locators in the output may need manual adjustment.
```

---

## File: `src/page_context_scraper.py`

```python
"""
page_context_scraper.py — Extract interactive elements from a live page.

Uses a headless Playwright browser to visit the target URL and return
a structured PageContext for injection into the LLM prompt.

Protected file once stable — do not modify without explicit request.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
from playwright.sync_api import sync_playwright, Page, TimeoutError as PWTimeout


@dataclass
class PageElement:
    tag: str
    role: Optional[str] = None
    label: Optional[str] = None
    test_id: Optional[str] = None
    element_id: Optional[str] = None
    name: Optional[str] = None
    placeholder: Optional[str] = None
    visible_text: Optional[str] = None
    input_type: Optional[str] = None
    is_required: bool = False
    recommended_locator: Optional[str] = None  # pre-built Playwright locator string


@dataclass
class PageContext:
    url: str
    page_title: str
    h1_text: Optional[str]
    elements: list[PageElement] = field(default_factory=list)
    forms: list[list[PageElement]] = field(default_factory=list)
    scraped_at: str = ""
    scrape_duration_ms: int = 0

    def to_prompt_block(self) -> str:
        """Format as a context block for LLM prompt injection."""
        ...

    def element_count(self) -> int:
        return len(self.elements)


def scrape_page_context(
    url: str,
    timeout_ms: int = 10_000,
) -> tuple[Optional[PageContext], Optional[str]]:
    """
    Visit url and extract interactive elements.

    Returns:
        (PageContext, None)        on success
        (None, error_message)      on failure — caller falls back gracefully
    """
    ...
```

---

## Integration Points

### `src/test_generator.py` (protected — minimal change)

Add one optional parameter to the existing generate function:

```python
def generate(
    self,
    criteria: list[str],
    base_url: str,
    page_context: Optional[PageContext] = None,   # ← new, optional
) -> str:
```

If `page_context` is provided, prepend the context block to the prompt.
If not, behaviour is identical to today.

### `streamlit_app.py`

The URL field already exists.  Wire it to the scraper:

```python
# After the user enters a URL and before calling run_generation:
if base_url:
    with st.spinner("Scanning page for elements…"):
        context, error = scrape_page_context(base_url)
    if error:
        st.warning(f"⚠ {error} — generating without page context")
        context = None
```

Progress shown to user:
```
[10:42:01] Scanning http://localhost:8080/mock_insurance_site.html…
[10:42:02] Found 5 interactive elements (2 inputs, 2 buttons, 1 list)
[10:42:02] Page context ready — injecting into prompt
```

---

## Success Criteria

- [ ] Scraper visits a URL and returns a populated `PageContext`
- [ ] `PageContext.to_prompt_block()` produces clean, readable output
- [ ] LLM uses real locators from context instead of inventing them
- [ ] Scraper failure is non-fatal — generation still works without it
- [ ] Generated test for mock insurance site passes without manual locator edits
- [ ] Unit tests for scraper in `tests/test_page_context_scraper.py`
- [ ] Scrape adds < 3 seconds to total generation time

---

## Out of Scope (Future Phases)

- Following links to discover multi-page flows
- Authenticated page access
- Detecting accessibility issues
- Comparing current DOM against a previous snapshot (regression)
- Automatic re-scraping when tests fail due to locator errors

---

*Created: 2026-03-05*  
*Status: Awaiting Phase 1 completion before implementation*
