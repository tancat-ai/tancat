# FEATURE SPEC: Multi-Page Scraping
## AI Playwright Test Generator — AI-009

**Status:** Phase A Complete (Session 10 — 2026-03-21)  
**Priority:** Phase B deferred — core multi-page scraping is functional  
**Fits into:** Phase 2 (User Story Intelligence) — extends AI-001  
**Modified files:** `src/page_context_scraper.py`  
**Protected files:** `src/llm_client.py`, `src/test_generator.py`, `main.py`  
**Estimated effort:** 2–3 sessions  

---

## Problem Statement

The current scraper visits **one URL** — the base URL the user provides. For
multi-step user flows (login → inventory → cart → checkout) this means:

- The scraper sees only the login page elements
- Every page after login has zero real context
- The LLM guesses selectors for all subsequent pages
- Tests fail immediately with `Locator expected to be visible`

This is not an edge case. Almost every real user story spans more than one
page. A tool that generates guesses for most of its tests has little value.

```
CURRENT (broken for multi-step flows)
──────────────────────────────────────
Base URL ──► Scraper visits 1 page ──► 4 elements from login page only
                                            │
                                            ▼
                              LLM invents selectors for pages 2, 3, 4
                                            │
                                            ▼
                              Tests fail: "Locator expected to be visible"

TARGET
──────
Base URL + User Story ──► Scraper infers flow ──► Visits each page in order
                                                        │
                                                        ▼
                                          Real elements from ALL pages
                                                        │
                                                        ▼
                                          LLM writes tests with real locators
                                                        │
                                                        ▼
                                          Tests pass first time
```

---

## Proposed Solution: Flow-Aware Scraping

### Phase A — URL list from user story (quick win, low risk)

Allow the user to provide additional URLs alongside the base URL. The scraper
visits each one and returns a combined `MultiPageContext`.

This requires zero LLM involvement for URL discovery — the user knows their
own application's URLs.

UI change: replace the single "Base URL" field with a small URL list:

```
Base URL (login / start page)
  https://www.saucedemo.com

Additional pages to scrape (one per line, optional)
  https://www.saucedemo.com/inventory.html
  https://www.saucedemo.com/cart.html
  https://www.saucedemo.com/checkout-step-one.html
```

### Phase B — Playwright-driven flow scraping (full solution)

The scraper follows the user flow by executing the steps it can infer from
the user story, visiting each resulting page and collecting elements.

This requires the scraper to attempt basic navigation actions (click, fill)
to reach pages that are only accessible after completing earlier steps
(e.g. the inventory page is only reachable after login).

---

## Implementation — Phase A (Recommended First)

Phase A is safe, fast, and solves the immediate problem without complex
state management. Implement this first.

### Data model changes

```python
@dataclass
class MultiPageContext:
    """Context scraped from multiple pages in a user flow."""
    pages: list[PageContext]          # one PageContext per URL visited
    base_url: str                     # the starting URL
    total_elements: int               # sum across all pages
    scrape_duration_ms: int

    def to_prompt_block(self) -> str:
        """
        Format all pages as a combined context block for LLM injection.

        Each page gets its own section header so the LLM knows which
        elements belong to which page in the flow.
        """
        ...

    def element_count(self) -> int:
        return self.total_elements
```

### New function signature

```python
def scrape_multiple_pages(
    urls: list[str],
    timeout_ms: int = 10_000,
) -> tuple[MultiPageContext | None, str | None]:
    """
    Visit each URL and collect elements from all pages.

    Visits pages in order. Failures on individual pages are non-fatal —
    that page is skipped and a warning is added to the error message.
    Returns None only if ALL pages fail.

    Returns:
        (MultiPageContext, None)          all pages succeeded
        (MultiPageContext, warning_str)   some pages failed — partial context
        (None, error_str)                 all pages failed
    """
```

### Prompt block format (multi-page)

```
=== PAGE CONTEXT: 3 pages scraped ===

--- PAGE 1: https://www.saucedemo.com (Login) ---
Page title : Swag Labs
H1         : (none)

INTERACTIVE ELEMENTS:
  [input]   id="user-name"        placeholder="Username"    type=text
  [input]   id="password"         placeholder="Password"    type=password
  [button]  id="login-button"     visible="Login"

--- PAGE 2: https://www.saucedemo.com/inventory.html (Inventory) ---
Page title : Swag Labs
H1         : Products

INTERACTIVE ELEMENTS:
  [button]  data-testid="add-to-cart-sauce-labs-backpack"   visible="Add to cart"
  [button]  data-testid="add-to-cart-sauce-labs-bike-light" visible="Add to cart"
  [a]       class="shopping_cart_link"                       visible="🛒"

--- PAGE 3: https://www.saucedemo.com/cart.html (Cart) ---
Page title : Swag Labs
H1         : Your Cart

INTERACTIVE ELEMENTS:
  [button]  id="checkout"         visible="Checkout"
  [button]  id="continue-shopping" visible="Continue Shopping"

USE THESE LOCATORS. Do not invent selectors not listed above.
Each test step must use locators from the page that step navigates to.
=============================================================
```

### `streamlit_app.py` UI changes

Replace the single URL input with a two-field layout:

```python
base_url = st.text_input("Base URL", placeholder="https://www.saucedemo.com")

with st.expander("➕ Add more pages to scrape (optional)", expanded=False):
    additional_urls_raw = st.text_area(
        "Additional page URLs (one per line)",
        placeholder="https://www.saucedemo.com/inventory.html\nhttps://www.saucedemo.com/cart.html",
        height=100,
    )
```

Parse additional URLs:
```python
additional_urls = [
    u.strip() for u in additional_urls_raw.splitlines()
    if u.strip().startswith("http")
]
all_urls = [base_url] + additional_urls if base_url else []
```

Sidebar scraper status updates to show per-page results:
```
✅ Scraped 3 pages — 18 elements total
   • saucedemo.com → 3 elements
   • saucedemo.com/inventory.html → 12 elements
   • saucedemo.com/cart.html → 3 elements
```

---

## Implementation — Phase B (Future)

Phase B requires the scraper to navigate the application by performing
actions, not just visiting static URLs. This is significantly more complex.

### Approach

1. Visit the base URL and collect elements (same as Phase A page 1)
2. Parse the user story for action keywords: "log in", "click", "add", "submit"
3. For each action, attempt to execute it using the elements collected from
   the current page
4. After each action, check if the URL changed — if so, scrape the new page
5. Continue until the story steps are exhausted or navigation stops

### Risks

- Login requires credentials — needs a way to pass test credentials safely
- Some navigation requires state that is hard to infer automatically
- Error recovery is complex (what to do when an action fails mid-flow)

### Credentials handling

```python
# .env additions for Phase B
TEST_USERNAME=standard_user
TEST_PASSWORD=secret_sauce
```

These would be injected into the scraper when it encounters login forms.

**This is deferred — Phase A solves 80% of the problem safely.**

---

## Backward Compatibility

- `scrape_page_context(url)` is kept unchanged — protected file, minimal change
- `scrape_multiple_pages([url])` with a single URL is equivalent to the current behaviour
- `streamlit_app.py` falls back to single-page scraping if no additional URLs provided
- All existing tests continue to pass

---

## Unit Tests — `tests/test_page_context_scraper.py` additions

```python
def test_scrape_multiple_pages_returns_multi_page_context() -> None: ...
def test_scrape_multiple_pages_single_url_equivalent_to_single_scrape() -> None: ...
def test_scrape_multiple_pages_partial_failure_returns_warning() -> None: ...
def test_scrape_multiple_pages_all_fail_returns_none() -> None: ...
def test_multi_page_context_to_prompt_block_includes_all_pages() -> None: ...
def test_multi_page_context_element_count_is_sum() -> None: ...
def test_prompt_block_labels_pages_with_url() -> None: ...
```

---

## Success Criteria

- [ ] User can provide multiple URLs in the UI
- [ ] Scraper visits all provided URLs and returns a combined context
- [ ] Prompt block clearly labels which elements belong to which page
- [ ] Single-URL behaviour is unchanged (no regression)
- [ ] Sidebar shows per-page scrape results
- [ ] Generated tests for saucedemo.com happy path pass without manual edits
- [ ] All new unit tests pass
- [ ] `ruff check . && mypy src/ streamlit_app.py` clean

---

## Out of Scope (Phase B — future)

- Automatic page discovery without user-provided URLs
- Authenticated scraping via credential injection (deferred)
- Following links autonomously to map the full site
- Comparing DOM snapshots across runs

---

*Created: 2026-03-16*  
*Status: Awaiting BREAK-1 / BREAK-2 fixes before implementation*  
*Depends on: AI-001 (complete)*
