# B-093 defect triage - the eval-006 false greens are 4 symptoms, 3 root causes

**Date:** 2026-09-26
**Status:** paused mid-session (by decision, to work on multi-agent setup instead). No code changed. Nothing committed. B-093 stays open and failing.
**Question:** Session 13 re-scored gate 2 at 3 false greens, all in `eval-006` (ecommerce_mock), all the resolver answering the cart-page, checkout-page and order-success criteria with `#place-order`. What is the actual defect?
**Answer:** Four symptom-level defects from **three** root causes, plus one measurement defect found on the way, plus one dead-code bug. The original "one resolver bug" framing was wrong.

**Independently verified** by the `verifier` agent on 2026-09-26 (scout, no edits). All eight claims reproduce. It found four errors in the first version of this record; they are corrected below. Its report: `scratch/b093_verifier_report.md`.

---

## 1. How to run the repros

Use the **venv** Python. `src/placeholder_resolver.py` uses PEP 758 syntax
(`except ValueError, TypeError:`), which is valid only in Python 3.14.
`pyproject.toml` declares `requires-python = ">=3.14"` and ruff targets `py314`.
The system Python on this box is 3.13 and fails with a SyntaxError.

```bash
./.venv/Scripts/python.exe scratch/b093_eval006_repro.py   # frozen-pool replay
./.venv/Scripts/python.exe scratch/b093_rank_repro.py      # real mock, per-page ranking
```

Artifacts: `scratch/b093_repro_run1.log`, `scratch/b093_rank_run1.log`,
`scratch/b093_pool_ecommerce.json`.

## 2. Measured defect - the frozen pool is contaminated

`_resolve_placeholder` in `scripts/eval/eval_resolver.py`:

```python
if expected_page and expected_page in pages_data:
    page_specific = {expected_page: pages_data[expected_page]}
else:
    page_specific = pages_data  # every page of every site
```

A missing page does not mean "cannot resolve". It means "resolve against everything", silently.

Measured: `scripts/eval/scraped_pages/` holds **20 pages / 1170 elements from every site**
(saucedemo, automationexercise, demoqa, the-internet, banking mock, ambiguous mock).

eval-006 needs four pages:

| Page | In the frozen pool? |
|---|---|
| `http://localhost:8781/cart.html` | MISSING |
| `http://localhost:8781/checkout.html` | MISSING |
| `http://localhost:8781/checkout_success.html` | MISSING |
| `http://localhost:8781/index.html` | PRESENT, but it is the **banking** mock's index (10 elements) |

So eval-006 resolves against 1170 competing candidates. Replay result: 15 mismatches, with
resolved locators such as `#login-button`, `.brand`, `#susbscribe_email`,
`#react-select-4-input` and `#order-success-message` (that last one is from the *ambiguous* mock).

**Port collision, corrected:** not two mocks. **Three** families use port 8781 (ecommerce,
banking, ambiguous) and the pool mixes two of them. The pool is keyed by URL, so a second
mock on the same port silently answers for the first.

**Consequence:** `eval_resolver.py --mode static` produces a meaningless number for eval-006.

### Scope note (checked, and the doc was wrong on this too)

The CI gate is **not** affected. `eval_harness.py run --mode static` goes to
`EvalRunner.run(mode="static")` at **`eval_harness.py:122`** (the earlier version of this
record said line 171; 171 is the baseline call). That path validates *captured code* against
golden keys, which is a different thing from a resolver replay.

### Dead code found while checking the above

`_cmd_run` in `eval_harness.py` delegates to `eval_resolver` **after** a `return 0`
(`eval_harness.py:91-97`). The delegate is unreachable code. So `--mode resolver` never
reaches the resolver-only evaluator: it falls through to the generic `EvalRunner` path at
line 99, the same path `--mode static` uses. Whether `EvalRunner.run(mode="resolver")` then
differs from `static` internally was not checked. What is certain: the delegate never runs.

## 3. Repro 2 - rank against the real pages

Served `mock_sites/ecommerce` on :8781 and scraped it (no LLM):

```
index.html 33   products.html 38   product_details.html 19
cart.html 11    checkout.html 18   checkout_success.html 10
```

Then ranked every eval-006 placeholder against **its own page only**. 7 mismatches.

### Root cause 1 - unguarded fall-through to whole-pool element ranking

Four symptoms, one mechanism. When the expected page is absent, or when a URL-typed
criterion finds no flow answer, the code falls through to plain element ranking over
whatever pool it has. Nothing guards the fall-through.

| Criterion | Symptom | Golden wants |
|---|---|---|
| 0 "home page loaded" | resolved to `a[href="/index.html"]` | `to_have_url(.../index.html)` |
| 3 "cart page title" | `.title` ("Shopping Cart", score 36) | `to_have_url(.../cart.html)` |
| 5 "checkout page title" | `.title` ("Checkout", score 37) | `to_have_url(.../checkout.html)` |
| 7 "order success message" | live run got `#place-order` | `#success-title` |

Criterion 7 is the clearest evidence: scoped to `checkout_success.html` it resolves
**correctly** to `#success-title`. So the live false green is not a scoring error. The live
pool was not scoped to the criterion's page.

**Correction to the first version:** it described criteria 3/5 as "classifier and emitter work,
not ranking work". That overstates it. `rank_candidates` is called directly by the repro and is
never passed `expected_type`, so the `url_assertion` branch returns `None` and the unguarded
fall-through takes over. The gap is the missing guard, not a classifier that cannot classify.

### Root cause 2 - equal scores broken the wrong way

| Description | Chosen | Score | Golden | Score |
|---|---|---|---|---|
| FILL `name` | `#card-name` ("Cardholder Name") | 100 | `#name` | 100 |
| FILL `email address` | `#address` | 28 | `#email` | 28 |

Both are exact ties. The tie-break picks the wrong element.

### Root cause 3 - ASSERT resolved to an interactive control

Criterion 2 ("add to cart confirmation") resolved to the add-to-cart button (score 95) instead
of the modal `.text-center` (`index.html:66`, inside `#cartModal`). An assert is answered by the
thing it should exclude. This is the `pass1_text_match` firing before the assert penalty, the
same shape **B-096** was meant to fix.

## 4. Not proven

`#place-order` for criterion 3 could **not** be reproduced through `rank_candidates`, even with
`checkout.html` in the pool. So that live pick comes from another stage (orchestrator pass
ordering / journey context), which remains unexamined. The verifier confirmed the negative and
marked the live stage CANNOT CHECK. Parked by decision: if root cause 1 is fixed, it may be moot.

Gate 1 (82/113) and gate 2 (3 false greens) were **not** re-measured: both need heavy runs.

## 5. My own artifact, not a defect

Criterion 4 ("product name and price") had only 2 candidates because the scrape had an **empty
cart**. Confirmed: `cart.html` contains only `#empty_cart`, and `cart.js:136` injects
`.cart_total_price` only when items exist. Seeding is needed for a faithful replay.

## 6. The decision taken

**Adopt "refuse to resolve" at the fall-through.** Do not resolve when:

- the criterion's `expected_page` is absent from the pool, **or**
- `expected_type` is `url_assertion` and flow memory returns nothing.

**Why:** it matches the product's existing principle that an honest skip beats a wrong guess
(AI-052). The cost is more skips, which is the correct trade for a gate that measures false
greens.

This collapses root cause 1's four symptoms into one guard.

## 7. Resume plan

1. Add the fall-through guard (section 6). Re-run the two repros: criteria 0/3/5/7 should stop
   producing element locators.
2. Fix the wrong-way tie-break in `rank_candidates` (B-096 added a deterministic tie-break; it
   clearly does not cover these two pairs).
3. Check why the assert penalty loses to `pass1_text_match` on criterion 2.
4. Fix the dead `return 0` in `eval_harness.py._cmd_run`.
5. Only then chase the live `#place-order` stage.

## 8. Candidate backlog items (not yet filed)

- **Scraped-pool contamination:** `eval_resolver.py --mode static` mixes mocks that share a port
  and falls back to the whole multi-site pool. Measurement-integrity class, same family as
  B-095/B-099.
- **Two static modes under one name:** `eval_resolver.py --mode static` (resolver replay) and
  `eval_harness.py --mode static` (captured-code validation) mean different things.
- **Unreachable delegate:** `eval_harness.py._cmd_run` returns before delegating, so the
  resolver-only evaluator is unreachable through `eval_harness`. The dead lines are 93-97.

## 9. State of the gates

Unchanged by this session. Nothing ran, nothing committed.

- Gate 1 resolution: **82/113 = 72.6%** (target >= 90%) - FAIL
- Gate 2 false greens: **3** (target 0) - FAIL
- Repo `main` clean at `423e79b`.

---

*Session record, B-093. Written 2026-09-26, corrected the same day after independent
verification.*
