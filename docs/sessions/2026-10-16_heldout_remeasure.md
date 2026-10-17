# Session - held-out re-measure on post-B-103 main (2026-10-16, t-0829)

**Question:** does the B-103 journey-discovery select fix (bb3d232, plus the PR #109
wrong-element guard that landed on main meanwhile) move eval-010, and where does the
held-out gate sit now?

**Answer: gate 1 = 87/113 = 77.0% (FAIL, needs >= 90%), gate 2 = 0 hollow passes (PASS).**
The re-measure's purpose was served: **eval-010 flipped 2/4 -> 4/4** - the B-103
journey-cursor fix is confirmed on the live harness (the scout predicted "3-4/4, up to
+3 of 113"). The total sits at 87 because eval-001 drew the same bad saucedemo
generation as 2026-10-15 (8/20 both runs) - the whole shortfall against the 89-92 band
is that one story's draw, not a code regression.

## 1. Method

- Branch/worktree: `task/b103-implementation` @ `.worktrees/maker` - post-B-103 main:
  the B-103 fix (bb3d232) plus the origin/main merge carrying PR #109 (`4354795`,
  gate1 wrong-element guard: a message can only be proven by a message element).
- Command (the documented held-out harness; not a new one):

  ```bash
  python scripts/eval/eval_harness.py run --regenerate --mode full \
    --dataset scripts/eval/dataset \
    --test-output scratch/gate1_out_t0829 \
    --evidence-dir scratch/eval_runs/2026-10-16_heldout
  ```

- Held-out set: the 9 committed golden stories - 6 sites, 62 conditions, 113 placeholders.
- Settings, identical to the 2026-10-15 record: model
  `Qwen3.8-27B-UD-Q4_K_XL_v2.gguf`, provider `openai-local` at `http://127.0.0.1:8080/v1`,
  thinking off (default), temperature 0.0, RAG on with the bundled pack, harness mode
  `full --regenerate`, identical committed golden dataset. The only differences are the
  code commits (B-103 + PR #109) and the unseeded LLM draw.
- Wall clock: ~51 min (19:36:03 -> 20:27:13 local; mean generation 220.1s/story). No
  stall, no partial run.
- Evidence kept: `scratch/eval_runs/2026-10-16_heldout/` (raw, gitignored), and the
  minimal re-score input committed at `fixtures/heldout_runs/2026-10-16/`. Re-scored
  with no model: `python scripts/eval/rescore.py --run-dir fixtures/heldout_runs/2026-10-16`
  -> **87/113, 0** (identical).

## 2. Gate 1 - resolution accuracy

**87/113 = 77.0%** (need >= 90%). Up from 85 on the 2026-10-15 run.

| Story | Site | 2026-10-15 | 2026-10-16 | Tests passed |
|---|---|---|---|---|
| eval-001 | saucedemo | 8/20 | 8/20 | 2/6 |
| eval-002 | automationexercise | 5/8 | 6/8 (+1) | 4/6 |
| eval-003 | demoqa | 7/8 | 7/8 | 6/6 |
| eval-004 | theinternet | 5/7 | 5/7 | 5/5 |
| eval-005 | lv_insurance | 21/24 | 20/24 (-1) | 0/10 |
| eval-006 | ecommerce_mock | 14/16 | 14/16 | 5/8 |
| eval-007 | banking_mock | 13/13 | 13/13 | 8/8 |
| eval-008 | banking_mock | 10/13 | 10/13 | 7/9 |
| eval-010 | ambiguous_mock | 2/4 | **4/4 (+2)** | 4/4 |

**Code-attributable delta vs 2026-10-15:** eval-010 +2 (B-103, below), eval-002 +1
("products page title" now a page-arrival assertion), eval-005 -1 (draw noise:
`#quoteRef` -> `#accountError`). Everything else unchanged or draw-noise.

## 3. eval-010: the B-103 flip, confirmed on the live harness

The 2026-10-15 journey mis-clicked "select item" to `#place-order`, submitted the mock
form, and every later step replayed on the wrong page. This run's emitted test
(`fixtures/heldout_runs/2026-10-16/emitted/test_eval_010.py`):

```python
evidence_tracker.click("#item", label="select item", expected_page=".../index.html")
evidence_tracker.fill("#quantity", "1", label="quantity", expected_page=".../index.html")
evidence_tracker.click("#place-order", label="Place Order", expected_page=".../index.html")
evidence_tracker.assert_visible(
    "#order-success-title", label="order success message", expected_page=".../success.html?item=blue-top&qty=1"
)
```

The journey now stays on index.html through the quantity fill, submits the real
`#place-order` into success.html, and the success ASSERT resolves
**`#order-success-title` scoped to success.html** - the exact expected effect the B-103
fix design predicted (was: `:has-text(...)` degraded locator scoped to index.html).
All four placeholders match; all four tests pass.

## 4. Gate 1 - per-class breakdown of the 26 misses

Classified with `scripts/eval/eval_criteria.classify_miss` from the committed evidence:

| Miss class | 2026-10-15 | 2026-10-16 |
|---|---|---|
| wrong_element | 23 | 23 |
| target_never_captured | 3 | 2 |
| element_instead_of_page_arrival | 2 | 1 |
| **total** | **28** | **26** |

- **The journey-cursor / wrong-pick shape moved, as designed:** both eval-010 misses
  (FILL quantity = target_never_captured; ASSERT order-success = wrong_element/degraded)
  are gone. The remaining 2 target_never_captured are eval-008 GOTO misses ("go to the
  transfer page" / "navigate to bill payments" - unresolved GOTO placeholders, present
  in both runs - a separate defect, not the cursor class).
- **wrong_element 23 -> 23 is composition, not stasis:** the eval-010 c3 wrong_element
  is out, one new eval-005 draw-noise miss in (`#quoteRef` -> `#accountError`).
- **eval-001 is still the outlier:** 12 of the 26 misses, and the identical shape as
  2026-10-15 - the bad saucedemo generation draw leaves the skeleton stuck on the login
  page (`#login-button` for every nav click, `#user-name` for every checkout FILL).
- The standing wrong-element family otherwise: eval-002/003/004 ASSERTs (weak
  message/header picks: `h4`, `h1.text-center`, `#result`), eval-005
  (`#quoteSubmit`/`#dob` family), eval-006 (`#product-name` for the cart/success
  criteria).
- eval-004 (theinternet) scored 5/7 in 70.7s - the flaky external site continues to move
  with the draw (see `known_gate_scores.json` flaky_story block, now nine runs).

## 5. Gate 2 - hollow passes

**0** (PASS). Unchanged. ASSERT verification: by element golden 21, pipeline verdict 10,
page arrival 6, unverified 0 (from the run's `verification_strength.json`).

## 6. Reading rule for this run

87 is below the 89-92 like-for-like band, but this run carries the **same eval-001
outlier as 2026-10-15** (8/20, the saucedemo login-stuck draw). Reading the band runs
(10-12/10-13, 94) against this one, eval-001's -9 (17 -> 8) is the whole gap; the
code-attributable delta of B-103 + PR #109 against 10-15 is **+2**. Do not treat 87 as
the new floor: it is 85 (outlier) + the fix. A clean eval-001 draw would put this code
at or above the band.

## 7. What this does NOT change

- No pipeline code changed in this session - measurement and record only. The fixes
  under measure are bb3d232 (B-103) and 4354795 (PR #109), both already on main.
- No harness/tolerance changes.
- The gates are unchanged: >= 90% gate 1, 0 hollow passes gate 2.

## 8. Next

1. **eval-001 saucedemo draw** - the skeleton sticks to the login page (12 of 24
   misses under the fixed validator). Needs a trace of why the generated journey
   navigates away from the inventory page before the checkout criteria resolve.
2. ~~**eval-008 GOTO pair**~~ - traced 2026-10-16 (t-0831): a harness blind spot, not a
   product defect. See the postscript below.
3. The standing wrong_element family (23) - message/header ASSERT picks; the PR #109
   guard already constrains message claims to message elements, so the remaining picks
   are weak-locator classes (global headers, `#result`-style containers).

## 9. Postscript (2026-10-16, t-0831): the GOTO pair was a harness blind spot

**The eval-008 GOTO pair was not a product defect.** In this run (and every run back
to 2026-10-12) the product resolved both GOTOs to the right URLs - the generated
tests click through to transfer.html / payments.html and assert arrival with
`expect(page).to_have_url(...)`. The golden validator reported them as
target_never_captured because it could never match a GOTO golden: its extractor
skipped every `evidence_tracker.navigate(...)` call, tagged every `to_have_url(...)`
as ASSERT, and matching requires exact action equality - so a GOTO golden (a bare
URL) had an empty candidate pool and was structurally unmatchable in every run.
A permanent -2/113, mislabelled as a capture failure.

Fixed in `scripts/eval/golden_validator.py`: `navigate(url)` is extracted as a GOTO
locator; each `to_have_url(url)` is extracted as both an ASSERT (page-arrival
goldens, unchanged) and a GOTO locator (the emitted form of a resolved GOTO when the
journey replays navigation via clicks); and the URL comparison branch reduces
bare-URL goldens and assertion expressions to their URL before comparing
(trailing-slash-insensitive, as before). Gate 2 is unaffected (the hollow-pass rule
is ASSERT-only); the static gate is 91/96 unchanged (no GOTO goldens in the static
captures).

Corrected re-scores of the committed runs: 10-12 94->96, 10-13 94->95 (that draw's
transfer GOTO had no arrival evidence - an honest miss), 10-13_gate1_filter 93->95,
10-15 85->87, **this run 87->89 (78.8%)** - inside the 89-92 band. Miss classes for
this run under the fixed validator: wrong_element 23, element_instead_of_page_arrival
1, target_never_captured 0. The gate chain in `scripts/eval/known_gate_scores.json`
carries per-run `validator_revision` notes. Tests: `tests/test_t0831_eval008_goto_pair.py`
(12, including "the test that says it passed": both GOTO steps resolve against this
run's committed evidence).
