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

## 5. Comparison - like-for-like on settings, not against the 82/113 record

The right comparison is the latest run with the **same settings**, not the 2026-09-25 record.

Settings of the runs compared (this run and the same-settings baseline):

- provider `openai-local`; model file `Qwen3.8-27B-UD-Q4_K_XL_v2.gguf`; thinking off;
  temperature 0.0; `RAG_ENABLED=1`; harness mode `full --regenerate`.
- The committed golden dataset is identical (tree hash `a8acb0fadb054bb67c58966280fd6258b034a90a`,
  unchanged since the last dataset commit c20c1d2 on 2026-10-03).
- The only differences are the code commit (the fixes under measure) and the unseeded LLM draw.

Same-settings runs before this one (from `eval_runs`, same model / config / RAG / fixtures):

| Run | Commit | Gate 1 |
|---|---|---|
| 2026-10-08 14:56 | d0444fd | 89/113 |
| 2026-10-08 19:32 | 8e4366b | 92/113 |
| 2026-10-09 00:30 (latest) | c68fe5f | 89/113 |
| **2026-10-12 23:39 (this run)** | **1138cc5** | **94/113** |

Movement: **+5 against the latest same-settings run (89 -> 94)**; **+2 against the best of the
same-settings band (92 -> 94)**. Of the +5, **+3 is eval-004** (the known flaky story: 1/7 on that
draw, 4/7 on this one) and **+2 is eval-007** (c6 pay-bill / c7 payment-success - the
submit-control change). No other story moved, so the code-attributable movement is **+2** and the
rest is draw noise.

The 82/113 (2026-09-25) record is **not** a like-for-like baseline: a different generation
(Session 10, before B-054/B-096/t-0542), re-scored in Session 13, with its evidence deleted. Do not
read 82 -> 94 as a same-settings gate movement. Gate 2's move from 3 hollow passes to 0 is real for
this run, but the two runs are not the same draw. Both the 3 then and the 0 now are consistent with
the t-0749 scout: the container and same-page-twin classes are fixed in HEAD; page-arrival,
polarity and capture remain.

## 6. Evidence

- Gate record: `scripts/eval/known_gate_scores.json` (updated 2026-10-12; the 82/113 + 3 record is
  preserved under `previous`).
- Re-score input (tracked): `fixtures/heldout_runs/2026-10-12/` - `manifest.json`, `results.json`,
  `emitted/` (the 9 per-story tests), `junit/` (the per-test outcomes) and
  `verification_strength.json`. Re-score from the repo alone, no model:
  `python scripts/eval/rescore.py --run-dir fixtures/heldout_runs/2026-10-12` -> 94/113, 0.
  `tests/test_eval_rescore.py::test_committed_heldout_evidence_rescores_to_the_record` runs this
  in CI, so the record cannot rot again.
- Not committed (not needed by `rescore.py`): the raw pytest logs (`pytest/`), the harness log and
  the full rollup. The worktree copy under `scratch/eval_runs/2026-10-12_heldout/` is transient.
