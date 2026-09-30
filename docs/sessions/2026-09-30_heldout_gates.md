# Session - the held-out re-measure (2026-09-30)

**Question:** on sites the tool has not seen, does it target the right element (gate 1 >= 90%), and
does a passing test prove anything (gate 2 = 0)? The gates are unchanged.

**Answer: gate 1 = 86/113 = 76.1% (FAIL), gate 2 = 2 hollow passes (FAIL).** The live number varies
by model draw; this run used Qwen3.8-27B-UD-Q4_K_XL_v2.

## 1. Method

- Branch/worktree: `task/gate-rescore` @ `.worktrees/maker` (carries the measurement work at
  `2279b4e`; `src/` is byte-identical to `origin/main` 4b9b6ad).
- Command:
  `python scripts/eval/eval_harness.py run --regenerate --mode full --dataset scripts/eval/dataset
  --test-output scratch/gate1_out --evidence-dir scratch/eval_runs/2026-09-30_heldout --no-persist`
- Held-out set: the 9 committed golden stories (6 sites, 62 conditions, 113 placeholders). None was
  used to build the B-086/088/090/092 fixes.
- Model: `Qwen3.8-27B-UD-Q4_K_XL_v2.gguf`, LM Studio `:8080`, provider `openai-local`, thinking off
  (default), RAG on with the bundled pack (113 golden patterns + 35 doc chunks, seeded on first use).
- Wall clock: 22:09:19 -> 22:53:39 = **~44 min** (mean generation 206.0s/story).
- Evidence kept: `scratch/eval_runs/2026-09-30_heldout/` (emitted/, junit/, pytest/, results.json,
  manifest.json, summary.txt, verification_strength.json, harness.log). Re-scored with no model:
  `python scripts/eval/rescore.py --run-dir scratch/eval_runs/2026-09-30_heldout` -> same numbers.

## 2. Gate 1 - resolution accuracy

**86/113 = 76.1%** (need >= 90%).

| Story | Site | Correct | Accuracy | Tests passed |
|---|---|---|---|---|
| eval-001 | saucedemo | 15/20 | 75% | 6/6 |
| eval-002 | automationexercise | 8/8 | **100%** | 3/6 |
| eval-003 | demoqa | 7/8 | 88% | 5/6 |
| eval-004 | theinternet | 6/7 | 86% | 5/5 |
| eval-005 | lv_insurance | 19/24 | 79% | 0/10 |
| eval-006 | ecommerce_mock | 12/16 | 75% | 8/8 |
| eval-007 | banking_mock | 7/13 | **54%** | 3/8 |
| eval-008 | banking_mock | 10/13 | 77% | 9/9 |
| eval-010 | ambiguous_mock | 2/4 | **50%** | 1/4 |

Static public sites are healthy (eval-002 100%, eval-003 88%, eval-004 86%). The deficit is still the
stateful / auth-gated / multi-step stories.

## 3. Gate 2 - hollow passes

**2** (need 0). Both are `eval-006` (ecommerce_mock), both page-title criteria where the golden wants
a URL assertion and the generated test asserted `.brand`:

| crit | test | golden wants | asserted |
|---|---|---|---|
| 3 | `test_04_go_to_cart` | `to_have_url(".../cart.html")` | `.brand` |
| 5 | `test_06_proceed_to_checkout` | `to_have_url(".../checkout.html")` | `.brand` |

The ASSERT verification split: golden 16 - element (pipeline verdict) 7 - page arrival 6 - unverified 8.
Of the 8 unverified, 2 passed their own test (the hollow passes above); the other 6 sat on skipped or
failed tests (an honest outcome).

## 4. The 27 gate-1 misses, by class

| Class | Count | Where |
|---|---|---|
| Assertion weakened to a visible element/container | **9** | eval-003 c5 (`.text`); eval-004 c0 (`#content`); eval-006 c3/c4/c5/c7 (`.brand` x4); eval-007 c2/c5/c7 (`main:has-text(...)` x3) |
| Wrong element on the criterion's own page | **9** | eval-001 c0 (cart link), c4 (backpack), c5 (backpack); eval-005 c0 last name, c0 postcode (both `#dob`), c1 (`#quoteSubmit`), c6 (`#quoteSubmit`), c9 (`h2:has-text("Create Your Account")`); eval-010 c3 (`#order-error` for a success claim) |
| Page context / trail assigned to the wrong step | 3 | eval-007 c4 FILL (`#user-name`), c4 CLICK (`#login-button`), c6 CLICK (`#login-button`) - all resolved against the index/login page |
| Target never captured (resolver returned nothing) | 3 | eval-008 c3 GOTO `transfer.html`, c6 GOTO `payments.html`; eval-010 c1 FILL `#quantity` |
| Anything else | 3 | eval-001 c2/c3 - the generated check is the specific backpack, the golden expects a container (B-101 golden quality); eval-008 c2 - asserted `#accounts-list`, the golden (a page criterion) wants the URL |

**Most of the 27: a tie at 9 each.** "Assertion weakened to a visible element" and "wrong element on
the criterion's own page" are 18 of 27 (67%) between them. The "wrong element" block is dominated by
two stories: eval-005 (5, the multi-step form) and eval-001 (3, one locator reused across criteria).
The "weakened" block is one weak locator reused per story: `.brand` in eval-006, `main:has-text(...)`
in eval-007, plus `.text` and `#content`.

## 5. What changed since the last measurement

Since Session 10/13: **B-054** (hidden-element pool) and **B-096** (pass-1 / same-page twins) are
fixed and are in this run; **B-097** (per-test skip counts), **B-100** (the product reports its own
verification strength) and **B-101** (golden-quality audit) have landed. B-101 is not applied to the
goldens (it is a watch item), so eval-001 c2/c3 still count as misses.

## 6. Comparison with the recorded numbers

The recorded last re-score was **82/113 (72.6%) and 3 hollow passes**. This run gives **86/113 (76.1%)
and 2**. Nothing was adjusted. The difference is the **model draw**: the recorded 82/113 was Session
13's re-score of Session 10's generation, while Session 12's separate generation also measured 86/113
(76.1%) - the same figure this run gives. Gate 2 improved by one (eval-006 crit 7 is no longer a
hollow pass on this draw). The gates themselves are unchanged: >= 90% and zero.

## 7. Evidence

`scratch/eval_runs/2026-09-30_heldout/` (gitignored scratch, ~969 KB): `emitted/` (9 test files),
`junit/` (9 outcome XMLs), `pytest/` (9 raw logs), `results.json` (the per-placeholder result),
`manifest.json`, `summary.txt`, `verification_strength.json`, `harness.log`. Re-score:
`python scripts/eval/rescore.py --run-dir scratch/eval_runs/2026-09-30_heldout`.
