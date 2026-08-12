# Playwright Navigation — Reference

Curated from Playwright documentation. Navigation is the most fundamental
Playwright capability — every test begins with a `page.goto`, and the
reliability of a suite depends on navigating to the *right* page. This
reference exists so the resolver's GOTO/URL resolution has the framework's
own navigation vocabulary (AI-042-F1: the corpus previously covered
locators/assertions/actionability but had only one navigation section).

---

## page.goto — the core navigation API

```python
page.goto("https://example.com/products")
page.goto("https://example.com/login")
page.goto("https://example.com/cart")
```

- Navigates the page to the given URL; the page object now represents that
  page.
- Waits for the page to reach the **load** state by default (can be
  configured: `domcontentloaded`, `commit`, `networkidle`).
- Returns the main resource response; `None` for cross-process navigations.
- `wait_until="commit"` is useful for SPAs where the document never reaches
  a classic "load" (client-side routing).

## Navigation is NOT subject to actionability checks

Playwright documentation is explicit: **navigation actions are not subject
to actionability checks**. A `goto` to a URL "just happens" — Playwright does
not verify the target element is visible/stable/enabled first (there is no
element). The consequence for test generation: a wrong navigation is *silent*
until the next assertion fails. Resolution accuracy of the destination URL is
therefore the *first* quality gate of any generated test — a GOTO to the
wrong page cascades into every downstream step (wrong page scraped → locators
missing → skips/failures).

## Navigation states

After navigation, Playwright exposes the load state:

```python
page.wait_for_load_state()  # 'load'
page.wait_for_load_state("networkidle")
page.wait_for_load_state("domcontentloaded")
```

Generated tests should wait for the settled state after a GOTO before
interacting — product grids lazy-load images, so acting immediately can hit
half-rendered DOM.

## Back / forward / reload

```python
page.go_back()  # history back
page.go_forward()  # history forward
page.reload()  # reload current page
```

Used in journeys that verify state persistence (e.g. cart survives a reload).

## URL assertions — verifying WHERE we are

```python
expect(page).to_have_url("https://example.com/cart")
expect(page).to_have_url("**/checkout**")  # glob patterns supported
```

- `to_have_url` is the precise page-identity check — a heading can appear on
  multiple pages, the URL cannot.
- Generated tests use `expect(page).to_have_url(...)` for page-state
  assertions ("cart page loaded") instead of element visibility — the only
  reliable page-identity signal (B-021).

## Same-page vs cross-page actions

- A click whose target has an `href` to a different path **navigates**; the
  next step's context is the new page.
- A click that opens a modal (add-to-cart confirmation) stays on the page.
- Distinguishing these determines whether the next placeholder resolves on
  the current page or after a navigation — the journey model tracks this.

## SPA / soft navigation

- Single-page apps re-render without a document navigation; `page.url` may
  change via the history API while `goto` never fires again.
- Route keywords (cart, checkout, products) normalize the same page type
  across sites that name routes differently (view_cart vs cart.html vs
  basket) — the flow-memory vocabulary.
