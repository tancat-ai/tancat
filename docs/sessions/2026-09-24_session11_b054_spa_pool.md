# Session 11 — B-054/B-055: the multi-step SPA candidate-pool defect (fix record)

**Date:** 2026-09-24 · **Branch/worktree:** `measure/session10-gates-1-3` @ `.worktrees/session10-gates-1-3`
**Trigger:** the Session 10 held-out gate re-measure (`docs/sessions/2026-09-24_session10_heldout_gates.md`).
**Outcome:** lv_insurance resolution **9/24 → 16/24 (38% → 67%)**; 3440 tests pass.

---

## 1. The finding — the diagnosis in the backlog was wrong

B-054 said "the specific target never enters the candidate pool" (banking mock, one text block).
B-055 said "steps resolved against the wrong page's candidate pool".

On the held-out set neither was the mechanism. Measured on `lv_insurance` (the worst story, 15 of 32
misses), a multi-step SPA served at **one URL**:

| Check | Result |
|---|---|
| Are the golden elements scraped? | **Yes** — all 162 elements for the page, including `#startDate`, `#mainLicenseNumber`, `#vehicleReg`, `#ncdYears` |
| Does journey discovery find them? | **Yes** — `Selected '#startDate' (score=50)`, `'#mainLicenseNumber' (score=23)` |
| What does the emit-time resolver see? | The same 162-element pool for every placeholder |
| What did it return? | `#email` for "start date", `#addDriver*` for "license"/"occupation" |

So the target **is** captured, and there is no second page. The pool is right; two filters inside
candidate selection throw the target away.

### Root cause 1 — hidden elements are hard-dropped (`src/placeholder_resolver.py:394`)

`rank_candidates` skipped every `is_visible is False` element for non-ASSERT actions. On a multi-step
form the later steps are `display:none` **at scrape time**, so every later-step field was removed
before scoring:

| selector | is_visible |
|---|---|
| `#email`, `#lastName`, `#postcode` (step 1) | `True` |
| `#startDate`, `#scheme`, `#mainLicenseNumber`, `#mainOccupation`, `#vehicleReg`, `#ncdYears` (later steps) | `False` |

The resolver then fell back to a **visible step-1 field** — that is why 15 criteria all resolved to
`#email`. Note the contradiction: `PlaceholderScorer._hidden_element_penalty` (−30) exists precisely
for this SPA case, but the hard drop made it dead code.

### Root cause 2 — the two `_is_fillable` implementations disagree (`src/intent_matcher.py:68`)

`PlaceholderScorer._is_fillable` (whose docstring claims the role sets are "aligned") accepts
`date`/`time`/`spinbutton`; `IntentMatcher._is_fillable` did not. So even after root cause 1, a
`role='date'` input (`#startDate`) was filtered out of FILL resolution.

## 2. The fix

- `rank_candidates`: a hidden element is **kept only when the description is literally present in its
  own text**. That is decisive evidence of intent, and it leaves the existing contract intact — a
  generic hidden overlay control (a "Confirm" button behind a modal) has no such text match and stays
  excluded. The pre-existing test `test_rank_candidates_skips_invisible_elements_for_click` still passes.
- `IntentMatcher._is_fillable`: added `search_box`, `spinbutton`, `date`, `time` so the two
  implementations agree.

Diff: `src/placeholder_resolver.py` (+17), `src/intent_matcher.py` (+4).
Regression test: `tests/test_b054_spa_hidden_step.py` (3 tests).

## 3. Verification

| Gate | Result |
|---|---|
| Local matcher sweep on the real lv page (8 descriptions) | **2/8 → 5/8** correct |
| Live lv_insurance re-run (`eval_harness run --regenerate --mode full`) | **9/24 (38%) → 16/24 (67%)**, wrong-element mappings 38%→67% correct, 0 false greens |
| Resolver/scorer test subset (214 tests) | pass |
| Full suite | **3440 passed / 1 skipped** |
| smoke | 39/39 |
| eval static (captured) | 97.9% (0.0pp drift) |
| ruff + mypy | clean |

## 4. What is left (honest residual)

- **3 of 8 descriptions still resolve wrong.** `years licensed` / `occupation` pick the `addDriver*`
  twin instead of the `main*` one (the page has both), and `vehicle registration number` is won by
  `#vehicleMake` in **pass 1**. That is pass-1 first-match ordering plus same-page similar-field
  disambiguation — a different class from the pool defect. → **B-096**.
- **lv still reports 0/10 tests passed** even at 67% resolution, because one unresolved placeholder
  emits a top-of-test `pytest.skip` that skips every step in the test. The skip is honest, but its
  granularity is per-test, not per-step — worth a separate decision.
- **Gate 1 re-scored (full 9-story held-out re-run, same command, worktree code + `PYTHONPATH`)**:
  **75/113 → 82/113 (66.4% → 72.6%)**. The whole gain is lv_insurance (9/24 → 16/24); every other
  story is byte-for-byte identical, so the change is surgical and regressed nothing. Gate 1 is still
  **FAIL** (needs ≥90%); gate 2 unchanged at **16 false greens** (FAIL); tests passed 49/63 unchanged.
  Log: `scratch/gate1_rescore.log`, emitted tests `scratch/gate1_out2/`.

## 5. Session 10 harness traps (must not be repeated)

- `eval_harness.py` does **not** put the checkout on `sys.path`. From a worktree it silently imports the
  **main repo's installed `src`**; a worktree fix is invisible unless `PYTHONPATH=<worktree root>` is set.
  → **B-095**.
- Two stories on one site overwrite each other's emitted test file (eval-007/008). → **B-094**.
- `eval_resolver.py --mode live` scrapes without login and is not a gate measure; `--mode static` is a
  RAG benchmark, not the gate.
