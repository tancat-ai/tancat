# Session - the page cursor follows a known navigation (2026-10-21, t-0847)

**Question:** does the journey page cursor move to a page whose identity is KNOWN, and does
the eval-008 c2 "loaded" assertion become a page arrival?

**Answer (dev measurement, one story + the five mock stories, live `full --regenerate`):**
eval-001 (saucedemo) **8/20 -> 16/20**, its tests **2/6 -> 5/6**, gate 2 **0 hollow**. The
held-out re-measure itself is still owed the owner's go (see section 6).

## 1. What was wrong (traced on the live pipeline, not inferred)

The 2026-10-16 held-out run drew eval-001's third criterion as a navigation step
(`{{GOTO:cart}}`). The journey discovery could not turn that step into a navigation: the
GOTO's URL is not in the human's input, and the only source the journey had was the
story's own target URLs, so the step was **dropped**. The browser therefore never left
`inventory.html`, the observed trail said so, and every later step of the journey
("Checkout", "First Name", "Continue", "Finish") was resolved against the inventory page:
`#react-burger-menu-btn` (the burger menu) for the clicks, `.product_sort_container` (a
sort dropdown) for the fields. The resolver still emitted `navigate(".../cart.html")` for
the GOTO - a URL it had guessed from the keyword - and the cursor stayed on the stale
page. That is the whole defect: **a navigation whose destination nobody knew, performed
as a guess, leaving the cursor behind.**

Two facts made it worse on saucedemo specifically:

- The cart link is a JavaScript link: `<a class="shopping_cart_link" data-test="shopping-cart-link"
  role="button" aria-label="Cart, empty">` - **no `href`**. There is no URL in the markup
  to type, and no way to know the destination without a browser.
- The pipeline's initial scrape of `cart.html` returned the site's SPA shell (a soft-404),
  so even "the cursor moves to cart.html" would have scoped the later steps to the wrong
  elements. Only a browser that actually clicks the cart link produces the real cart page.

## 2. The rule (the owner's, 2026-10-21)

> A GOTO is only valid if its URL is KNOWN - either a provided target_url (from the story
> or the reference documents the human gave) or the real href of a hyperlink on the
> current page. The cursor advances to a known GOTO target. If a journey needs to reach a
> page by typing a URL the human already knows, that URL must be in the INPUT - the
> generator must not fabricate it, and the resolver must not resolve that step against the
> current page's elements. For saucedemo specifically: the 'Cart icon' step should stay a
> CLICK on the cart link (the human-practice journey), and the cursor must follow both the
> click and any legitimate known-URL navigate.

## 3. The change (branch `task/page-cursor`)

1. **The journey performs the navigation the human way** (`src/orchestrator.py`,
   `src/journey_scraper.py`, `src/journey_models.py`). A GOTO whose URL is not in the
   human's input becomes a journey step that clicks the **hyperlink that names the
   destination** (`JourneyStep.prefer_link`). The browser then observes where the click
   really lands, and the trail carries the real transition - the cart page, the checkout
   page, the order-complete page. `src/navigation_target.py` decides which element that
   link is: only an anchor counts ("Add to cart" is a button, not the cart page), and it
   must cover every identity word of the description.
2. **The cursor follows the observation** (`src/placeholder_orchestrator.py`). A GOTO
   placeholder now also matches a trail **click** (the journey performed the navigation as
   a link click), the resolver emits that **proven click** (the customer clicks the cart
   icon; the test does the same, instead of typing a URL nobody gave us), and the cursor
   advances to the observed landing page. The next step is scoped to the page the browser
   is on.
3. **A GOTO with no known destination is an honest unresolved** (`src/placeholder_orchestrator.py`,
   `src/placeholder_resolver.py`). The GOTO branch now resolves only from known sources -
   the URL the human gave us (the entry page they named), the story-derived keyword map,
   a page the pipeline really scraped whose identity matches, or a learned cross-site
   transition. The two guesses are gone: the path heuristic and the "fall back to the seed
   URL" rule, plus `resolve_url`'s last-resort "return whichever page is first".
4. **`<noun> loaded` is a page state** (`src/placeholder_orchestrator.py`). "accounts
   dashboard loaded" resolved as an element; it now resolves as a URL assertion. The
   existing element-keyword guard still wins, so "cart summary loaded" and "product list
   loaded" stay element assertions.

Not touched, on purpose: the element scoring and candidate generation, the skeleton
prompt, the model, the temperature. The draw stays like-for-like.

## 4. What the change did (dev measurement, live `full --regenerate`)

Six stories - eval-001 (the live saucedemo one) plus the five that carry the local mocks
- same model, same temperature 0.0, RAG on, bundled store, `full --regenerate`:

| story | placeholders before | after | tests before | after |
|---|---|---|---|---|
| eval-001 (saucedemo) | 8/20 | **16/20** | 2/6 | **5/6** |
| eval-005 (lv_insurance) | 20/24 | 20/24 | 0/10 | 0/10 |
| eval-006 (ecommerce_mock) | 14/16 | 14/16 | 5/8 | 7/8 |
| eval-007 (banking_mock) | 13/13 | 13/13 | 8/8 | 8/8 |
| eval-008 (banking_mock) | 12/13 | **13/13** | 7/9 | **9/9** |
| eval-010 (ambiguous_mock) | 4/4 | 4/4 | 4/4 | 4/4 |
| **the six together** | **71/90 = 78.9%** | **80/90 = 88.9%** | 26/49 | **33/49** |

Hollow passes (gate 2): **0** before, **0** after. The three stories the change does not
touch (eval-002, eval-003, eval-004) are not in this set; if they hold their recorded
scores the full 113-placeholder gate lands at 98/113 = 86.7%.

The journey now walks the whole flow in the browser - "cart" picks the cart link
(`.shopping_cart_link[data-test="shopping-cart-link"]`), "Checkout" picks `#checkout` on
the cart page, the name fields pick `#first-name` / `#last-name` / `#postal-code` on
`checkout-step-one.html`, "Continue" picks `#continue`, "Finish" picks `#finish` - and the
trail reads `home -> inventory.html -> cart.html -> checkout-step-one.html ->
checkout-step-two.html -> checkout-complete.html`. Every later step is scoped to the page
the browser is on.

Eight of eval-001's twelve misses are recovered: the "Cart icon" click, the "Checkout"
click, the three checkout fields, "Continue", "Finish", and the "Thank You page" arrival.
The four that remain are **not** cursor misses:

- c2 "Cart Summary" (`#cart_contents_container`) and c4 "Checkout Info form"
  (`#checkout_info_container`): the draw's skeleton described these criteria as page
  states ("cart page loaded", "checkout page loaded"), so they resolve to a URL arrival.
  The golden keys want an element. No cursor change can produce an element assertion
  from a page-state description.
- c0 "product list" and c3 "backpack item in cart": the draw's skeleton described c3 as
  "at least one item row", which the specificity guard (t-0354) refuses to assert against
  one specific element ("open-ended step resolved to one specific element"). The guard
  turns it into an honest skip, so the element never reaches the emitted code. c0's
  golden is matched through c3's assert in the same file, so the two move together.

## 5. Tests

- `tests/test_navigation_target.py` (9) - the link rules: an anchor, not a button; full
  coverage of the description's words; grammar words are not identity; a hidden link is
  not a target; the href is the only proof of a destination; "home" is the entry page.
- `tests/test_t0847_page_cursor.py` (4) - the GOTO maps to the trail click that performed
  it; the navigation is emitted as the proven click; the cursor advances so the next
  step resolves on the cart page; "<noun> loaded" is a page state and an element keyword
  still wins.
- `tests/test_resolver_observed_scope.py` - the B-060 test's assert description changed
  from "accounts dashboard loaded" to "account balances visible", because that shape is a
  page state now and the test is about the divergence latch, not about the routing. The
  page-state routing has its own test (above).

## 6. What is NOT done - the re-measure needs the owner's go

The full held-out re-measure (9 stories, 6 sites, ~50 min) has **not** been run: it is the
owner's call, and the brief for it is ready. The owner's standing rule for a resolver
change: `full --regenerate` (never the static captures), RAG on **and** RAG off, empty
store **and** bundled-pack store, same commit, temperature 0.0, more than one
configuration as the repetition.

```bash
# four legs, same commit, one at a time (never two heavy runs at once)
RAG_ENABLED=1 python scripts/eval/eval_harness.py run --regenerate --mode full \
  --dataset scripts/eval/dataset \
  --test-output scratch/gate1_out_t0847_rag_on_bundled \
  --evidence-dir scratch/eval_runs/2026-10-21_t0847_rag_on_bundled
RAG_ENABLED=0 ... (rag off, bundled store)
RAG_ENABLED=1 ... (rag on, empty store: point the storage root at a fresh dir)
RAG_ENABLED=0 ... (rag off, empty store)
python scripts/eval/rescore.py --run-dir <each leg>
```

The pass condition: eval-001 keeps its recovered points, the eval-008 c2 point is
recovered, no currently-passing story (eval-002 .. eval-010 at their 10-16 scores) drops
by more than the draw noise the record already shows, and gate 2 stays 0.

## 7. What this does NOT change

- No scoring, candidate generation, prompt, model or temperature change - the draw stays
  comparable with the 2026-10-16 run.
- The static gate is computed from frozen captures and cannot move: 91/96 = 94.8%.
- The two eval-001 ASSERT misses that need an element assertion from a page-state
  description are a **skeleton wording** problem, not a cursor problem.
