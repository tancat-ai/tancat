# Session - the ASSERT-pool filter measured against the held-out gate (2026-10-13, t-0814 / j-0171)

**Question:** does the ASSERT candidate-pool filter on `task/gate1-wrong-element`
(`filter_assert_candidates`, t-0790) move the held-out gate, measured with the same settings as
the latest recorded run (2026-10-13)?

**Answer: no. Gate 1 = 93/113 = 82.3% (FAIL, needs >= 90%), gate 2 = 0 hollow passes (PASS).**
Against the latest same-settings run (94/113, 83.2%) this is **-1 placeholder, inside the
same-settings draw band**. The filter did not fix any of the 14 named `wrong_element` picks.

## 1. Method

- Branch/worktree: `task/gate1-wrong-element` @ `.worktrees/maker`, commit `8a1e014` (the branch
  merge; contains the filter at `bc14f82`).
- Command (the documented held-out harness; identical shape to the 2026-10-13 baseline, with a
  new output dir):

  ```bash
  LLM_PROVIDER=openai-local OPENAI_BASE_URL=http://127.0.0.1:8080/v1 \
    AITEST_LLM_TEMPERATURE=0 RAG_ENABLED=1 \
    python scripts/eval/eval_harness.py run --regenerate --mode full \
      --dataset scripts/eval/dataset \
      --test-output scratch/gate1_out_t0814 \
      --evidence-dir scratch/eval_runs/2026-10-13_gate1_filter
  ```

- Held-out set: the 9 committed golden stories - 6 sites, 62 conditions, 113 placeholders (the
  identical committed dataset, tree hash `a8acb0f`).
- Settings: model `Qwen3.8-27B-UD-Q4_K_XL_v2.gguf`, provider `openai-local` at
  `http://127.0.0.1:8080/v1`, thinking off, temperature 0.0, RAG on with the bundled pack,
  harness mode `full --regenerate`, `pipeline: linear` (per the manifest). The only differences
  from the baseline are the code commit (the filter) and the unseeded LLM draw.
- Wall clock: 18:07:26 -> 18:54:30 = **~47 min** (mean generation 191.5s/story). No stall, no
  partial run. eval-004's slow site produced the usual `Page.goto` 30s timeout traces; the run
  recovered (stateful re-scrape) and finished.
- Evidence kept: `fixtures/heldout_runs/2026-10-13_gate1_filter/`. Re-scored with no model:
  `python scripts/eval/rescore.py --run-dir fixtures/heldout_runs/2026-10-13_gate1_filter`
  -> **93/113, 0** (identical).

## 2. Gate 1 - resolution accuracy

**93/113 = 82.3%** (need >= 90%). Down 1 from 94/113.

| Story | Site | Baseline 2026-10-13 | This run | Delta |
|---|---|---|---|---|
| eval-001 | saucedemo | 17/20 | 17/20 | 0 |
| eval-002 | automationexercise | 6/8 | 6/8 | 0 |
| eval-003 | demoqa | 7/8 | 7/8 | 0 |
| eval-004 | theinternet | 4/7 | 5/7 | +1 |
| eval-005 | lv_insurance | 21/24 | 20/24 | -1 |
| eval-006 | ecommerce_mock | 14/16 | 14/16 | 0 |
| eval-007 | banking_mock | 13/13 | 13/13 | 0 |
| eval-008 | banking_mock | 10/13 | 9/13 | -1 |
| eval-010 | ambiguous_mock | 2/4 | 2/4 | 0 |

### Gate-1 misses by class (20 misses total)

| Class | Baseline | This run |
|---|---|---|
| `wrong_element` | 14 | 15 |
| `target_never_captured` | 3 | 3 |
| `weakened_to_visible_element` | 1 | 1 |
| `element_instead_of_page_arrival` | 1 | 1 |

The named wrong picks are unchanged and all persist: eval-002 c3/c5 and eval-006 c4/c7
`.modal-title.w-100`; eval-003 c5 `h1.text-center`; eval-005 c0 `#dob` and c1/c6 `#quoteSubmit`;
eval-010 c3 `#order-error`; eval-001 c2/c3/c4 the inventory URL. The new `wrong_element` on
eval-008 c8 (`payment success message` -> `#accounts-list`) and the new
`weakened_to_visible_element` on eval-005 c9 (`quote reference number` -> `#page-account`) are
the two places the draw moved against us; eval-004 c1 lost its `#content` weakened pick (the
flaky story moved +1).

## 3. Gate 2 - hollow passes

**0** (need 0). ASSERT-verification split: by element (golden) 20, by element (pipeline verdict)
9, by page arrival 5, unverified 3.

## 4. Reading

- **No movement.** 94 -> 93 is -1 placeholder (0.9 pp), inside the same-settings band
  (89-94/113) and dominated by the known-flaky eval-004 (4/7 -> 5/7). The filter is not the lever
  for the `wrong_element` class.
- The filter acts on the B-020 ASSERT semantic candidate pool (`_resolve_assert_semantically` and
  the batch shortlist). The named wrong picks are reached by other paths: the page-context /
  page-arrival path (the eval-001 URL asserts), the FILL/CLICK tokenizer (eval-005 `#dob` for
  postcode, `#quoteSubmit` for the card and Add-Vehicle clicks), or the target never enters the
  pool at all (the eval-008 GOTOs and eval-010 `quantity`). The message-control and identity
  drops only fire when the criterion's target and the wrong lookalike are both in the ASSERT
  semantic pool - which is not where these misses are decided.
- No regression is claimed from the -1 either: the same band, one flaky story, and no change to
  any of the 14 target misses.

## 5. Evidence

- Gate record: `scripts/eval/known_gate_scores.json` (current 93/113; the superseded 2026-10-13
  94/113 run under `previous`; the pre-A/C 2026-10-12 run under `comparison.history`).
- Re-score input (tracked): `fixtures/heldout_runs/2026-10-13_gate1_filter/` - `manifest.json`,
  `results.json`, `summary.txt`, `emitted/`, `junit/`, `verification_strength.json`. Re-score
  from the repo alone, no model:
  `python scripts/eval/rescore.py --run-dir fixtures/heldout_runs/2026-10-13_gate1_filter`.
  `tests/test_eval_rescore.py` pins the recorded number against this evidence.
- Not committed: the raw pytest logs (`pytest/`) and the harness log - `rescore.py` does not need
  them. The worktree copy under `scratch/eval_runs/2026-10-13_gate1_filter/` is transient.
