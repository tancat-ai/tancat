# Session - held-out re-measure on current main (2026-10-12, t-0750)

**Question:** what is the true held-out gate on current `main` (HEAD), after the fix classes that
landed since the last recorded number (container dominance t-0542/B-100 2026-10-08; same-page-twin
pass-1 match B-096 2026-09-25)? The gates are unchanged.

**Answer: gate 1 = 94/113 = 83.2% (FAIL, needs >= 90%), gate 2 = 0 hollow passes (PASS).**
The previous record was 82/113 = 72.6% with 3 hollow passes (2026-09-25).

## 1. Method

- Branch/worktree: `task/heldout-remeasure` @ `.worktrees/maker`, off `origin/main` (`1138cc5`).
- Command (the documented held-out harness; not a new one):

  ```bash
  python scripts/eval/eval_harness.py run --regenerate --mode full \
    --dataset scripts/eval/dataset \
    --test-output scratch/gate1_out_t0750 \
    --evidence-dir scratch/eval_runs/2026-10-12_heldout
  ```

- Held-out set: the 9 committed golden stories (`scripts/eval/dataset/eval-001..010`) - 6 sites,
  62 conditions, 113 placeholders. None was used to build the B-086/088/090/092 fixes.
- Model: `Qwen3.8-27B-UD-Q4_K_XL_v2.gguf`, provider `openai-local`, base URL `http://127.0.0.1:8080/v1`,
  thinking off (default), temperature 0.0, RAG on with the bundled pack.
- Wall clock: 23:47:56 -> 00:39:12 = **~51 min** (mean generation 210.4s/story).
- Evidence kept: `scratch/eval_runs/2026-10-12_heldout/` (`emitted/`, `junit/`, `pytest/`,
  `results.json`, `manifest.json`). Re-scored with no model:
  `python scripts/eval/rescore.py --run-dir scratch/eval_runs/2026-10-12_heldout` -> **94/113, 0**
  (identical, so the number is reproducible from the kept artifacts).
- No partial run: every story regenerated (`regeneration_failures` empty). Nothing stalled.

## 2. Gate 1 - resolution accuracy

**94/113 = 83.2%** (need >= 90%). Up from 82/113 (72.6%).

| Story | Site | Correct | Accuracy | Tests passed |
|---|---|---|---|---|
| eval-001 | saucedemo | 17/20 | 85% | 6/6 |
| eval-002 | automationexercise | 6/8 | 75% | 6/6 |
| eval-003 | demoqa | 7/8 | 88% | 6/6 |
| eval-004 | theinternet | 4/7 | 57% | 1/5 |
| eval-005 | lv_insurance | 21/24 | 88% | 0/10 |
| eval-006 | ecommerce_mock | 14/16 | 88% | 7/8 |
| eval-007 | banking_mock | 13/13 | **100%** | 8/8 |
| eval-008 | banking_mock | 10/13 | 77% | 9/9 |
| eval-010 | ambiguous_mock | 2/4 | 50% | 1/4 |

The static public sites are no longer uniformly healthy on this draw (eval-002 75%, eval-004 57%);
the mocks improved most (eval-007 100%, eval-005 88%, eval-006 88%).

### Gate-1 misses by class (13 harness `miss_class`; 19 misses total)

| Class | Count | Where (criterion -> chosen vs golden) |
|---|---|---|
| `wrong_element` | 14 | eval-001 x3; eval-002 x2; eval-003 x1; eval-004 x2; eval-005 x3; eval-006 x2; eval-010 x1 |
| `target_never_captured` | 3 | eval-008 x2 (GOTO transfer.html, payments.html -> None); eval-010 x1 (`quantity` -> None) |
| `weakened_to_visible_element` | 1 | eval-004 "JavaScript Alerts" -> `#content` vs `a[href="/javascript_alerts"]` |
| `element_instead_of_page_arrival` | 1 | eval-008 "accounts dashboard loaded" -> `#accounts-list` vs the dashboard URL |

Notable individual misses: eval-005 `postcode` -> `#dob`; eval-005 "Car Insurance product card"
and "Add Vehicle button" -> `#quoteSubmit`; eval-001 "Cart Summary" / "backpack item in cart" /
"Checkout Info form" all -> the inventory URL; eval-002 and eval-006 content criteria ->
`.modal-title.w-100`; eval-010 "order success message" -> `#order-error` (the success-vs-error
sibling class flagged in the t-0749 scout).

The per-test `pytest.skip` granularity (B-097) is still the reason eval-005 shows 0/10 tests passed
at 88% resolution: one unresolved placeholder skips every resolved step in the test.

## 3. Gate 2 - hollow passes

**0** (need 0). This is the first recorded held-out run with zero hollow passes. The
ASSERT-verification split: by element (golden) 21 - by element (pipeline verdict) 10 - by page
arrival 5 - unverified 1. The previous 3 hollow passes (eval-006 cart/checkout/order-success all
asserting `#place-order`) are gone on this draw.

## 4. Model draw and eval-004 flakiness

- Draw: `Qwen3.8-27B-UD-Q4_K_XL_v2.gguf`, thinking off, temperature 0.0, RAG on.
- eval-004 (theinternet) scored **4/7** - the top of its observed range (3/7, 1/7, 4/7, 1/7, 4/7
  across t-0534..t-0579), with generation 273.8s (the fastest of the recorded runs). Its
  per-story number is not repeatable; treat an eval-004 delta as draw noise, not a regression.
  The overall figure carries that jitter.

## 5. Comparison with the recorded number

The recorded last re-score was **82/113 (72.6%) and 3 hollow passes** (2026-09-25, Session 13:
a re-score of Session 10's generation). This run gives **94/113 (83.2%) and 0**. The difference is
not one variable: the fix classes that landed since the record (B-054 hidden-step pool, B-096
same-page twins, t-0542/t-0556/t-0560 generic-ASSERT guards, B-100 global-container check) are in
HEAD for this run, and it is a different LLM draw. Nothing was adjusted to reach 83.2%. Both the
reported 3 hollow passes and this 0 are consistent with the t-0749 scout: the container and
same-page-twin classes are fixed in HEAD; the page-arrival, polarity and capture classes remain.

## 6. Evidence

- Gate record: `scripts/eval/known_gate_scores.json` (updated 2026-10-12; the 82/113 + 3 record is
  preserved under `previous`).
- Run evidence: `scratch/eval_runs/2026-10-12_heldout/` (gitignored, ~1 MB) - re-score with
  `python scripts/eval/rescore.py --run-dir scratch/eval_runs/2026-10-12_heldout`.
- Raw log: `scratch/t0750_heldout.log`; harness rollup: `scratch/t0750_report.txt` (gitignored).
