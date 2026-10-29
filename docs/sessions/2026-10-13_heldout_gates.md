# Session - held-out re-measure on current main with the accuracy A/C fixes (2026-10-13, t-0759)

**Question:** what is the true held-out gate on current `main`, which now includes the accuracy
A/C fixes (PR #91, t-0754), measured with the same settings as the 2026-10-12 baseline? The gates
are unchanged.

**Answer: gate 1 = 94/113 = 83.2% (FAIL, needs >= 90%), gate 2 = 0 hollow passes (PASS).**
This equals the 2026-10-12 baseline exactly: the A/C fixes did not move the held-out number on this
draw.

## 1. Method

- Branch/worktree: `task/heldout-remeasure-2` @ `.worktrees/maker`, off `origin/main` (`1545807`,
  the PR #91 merge carrying the A/C fixes).
- Command (the documented held-out harness; not a new one):

  ```bash
  python scripts/eval/eval_harness.py run --regenerate --mode full \
    --dataset scripts/eval/dataset \
    --test-output scratch/gate1_out_t0759 \
    --evidence-dir scratch/eval_runs/2026-10-13_heldout
  ```

- Held-out set: the 9 committed golden stories (`scripts/eval/dataset/eval-001..010`) - 6 sites,
  62 conditions, 113 placeholders.
- Settings, identical to the 2026-10-12 baseline: model `Qwen3.8-27B-UD-Q4_K_XL_v2.gguf`, provider
  `openai-local` at `http://127.0.0.1:8080/v1`, thinking off (default), temperature 0.0, RAG on with
  the bundled pack, harness mode `full --regenerate`, and the identical committed golden dataset
  (tree hash `a8acb0fadb054bb67c58966280fd6258b034a90a`, unchanged since c20c1d2 on 2026-10-03). The
  only differences are the code commit and the unseeded LLM draw.
- Wall clock: ~47 min (mean generation 189.2s/story). No stall, no partial run.
- Evidence kept: `scratch/eval_runs/2026-10-13_heldout/`, and the minimal re-score input is committed
  at `fixtures/heldout_runs/2026-10-13/`. Re-scored with no model:
  `python scripts/eval/rescore.py --run-dir fixtures/heldout_runs/2026-10-13` -> **94/113, 0**
  (identical).

## 2. Gate 1 - resolution accuracy

**94/113 = 83.2%** (need >= 90%). Unchanged from 2026-10-12.

| Story | Site | Correct | Accuracy | Tests passed |
|---|---|---|---|---|
| eval-001 | saucedemo | 17/20 | 85% | 6/6 |
| eval-002 | automationexercise | 6/8 | 75% | 5/6 |
| eval-003 | demoqa | 7/8 | 88% | 6/6 |
| eval-004 | theinternet | 4/7 | 57% | 0/5 |
| eval-005 | lv_insurance | 21/24 | 88% | 0/10 |
| eval-006 | ecommerce_mock | 14/16 | 88% | 7/8 |
| eval-007 | banking_mock | 13/13 | **100%** | 7/8 |
| eval-008 | banking_mock | 10/13 | 77% | 8/9 |
| eval-010 | ambiguous_mock | 2/4 | 50% | 1/4 |

Every per-story correct count is identical to 2026-10-12.

### Gate-1 misses by class (19 misses total)

| Class | Count |
|---|---|
| `wrong_element` | 14 |
| `target_never_captured` | 3 |
| `weakened_to_visible_element` | 1 |
| `element_instead_of_page_arrival` | 1 |

Identical to the 2026-10-12 baseline, class for class.

## 3. Gate 2 - hollow passes

**0** (need 0). ASSERT-verification split: by element (golden) 20, by element (pipeline verdict) 11,
by page arrival 5, unverified 1.

## 4. Comparison against the latest same-settings run

The baseline is the 2026-10-12 run (`1138cc5`, `fixtures/heldout_runs/2026-10-12`): 94/113, 0 hollow,
same settings and fixtures as above.

**Movement: 0 (94 -> 94, 0 -> 0). No like-for-like gate movement.** The A/C fixes changed the emitted
code for eval-002, eval-007 and eval-008, but every story's correct count is unchanged and the
per-class gate-1 breakdown is identical. `tests_passed` fell 44 -> 40: some wrong-element asserts the
fixes now turn into honest skips (or failures) instead of passing on the wrong element; gate 2 was
already 0 on the baseline.

Honest reading: on this draw the two classes the fixes target did not appear as wrong picks that
cost gate-1 accuracy - the wrong picks in this draw are `.modal-title.w-100` for content/message
criteria, `.text`/`h1.text-center` for the form/message criteria, `#dob` for a postcode, and the
`main`/page-trail and never-captured classes. The fixes remove some wrong picks (converting them to
honest skips) but do not find the golden element, so the number holds.

## 5. eval-004 flakiness

eval-004 (theinternet) scored **4/7** again, with generation 259.2s (the fastest of the recorded
runs). Its observed range across seven held-out runs is 1/7..4/7; it is not repeatable, so a delta on
that story is draw noise, not a regression.

## 6. Evidence

- Gate record: `scripts/eval/known_gate_scores.json` (updated 2026-10-13; the 2026-10-12 baseline is
  preserved under `previous`, and the 2026-09-25 82/113 record under `comparison.history`).
- Re-score input (tracked): `fixtures/heldout_runs/2026-10-13/` - `manifest.json`, `results.json`,
  `emitted/`, `junit/`, `verification_strength.json`. Re-score from the repo alone, no model:
  `python scripts/eval/rescore.py --run-dir fixtures/heldout_runs/2026-10-13`.
  `tests/test_eval_rescore.py::test_committed_heldout_evidence_rescores_to_the_record` checks it in CI.
- Not committed (not needed by `rescore.py`): the raw pytest logs and the harness log.
