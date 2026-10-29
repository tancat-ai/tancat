# Session - held-out re-measure on current main with the negation-aware polarity floor (2026-10-15, t-0826)

**Question:** does the t-0825 negation-aware polarity floor (PR #106, merged as `42cf9dd`) flip
eval-010 c3 ("order success message"), and where does the held-out gate sit now?

**Answer: gate 1 = 85/113 = 75.2% (FAIL, needs >= 90%), gate 2 = 0 hollow passes (PASS).** The
85 is an **outlier low draw** (the same-settings band is 89-92/113), dominated by a bad eval-001
(saucedemo) generation draw - not a t-0825 regression. The polarity floor worked on eval-010 c3
(the `#order-error` trap no longer wins) but was **not sufficient**: the criterion still misses
`#order-success-title` because of a separate journey page-cursor defect (below).

## 1. Method

- Branch/worktree: `task/heldout-remeasure-3` @ `.worktrees/maker`, off `origin/main` at `42cf9dd`
  (the PR #106 merge carrying the t-0825 fix).
- Command (the documented held-out harness; not a new one):

  ```bash
  python scripts/eval/eval_harness.py run --regenerate --mode full \
    --dataset scripts/eval/dataset \
    --test-output scratch/gate1_out_t0826 \
    --evidence-dir scratch/eval_runs/2026-10-15_heldout
  ```

- Held-out set: the 9 committed golden stories - 6 sites, 62 conditions, 113 placeholders.
- Settings, identical to the 2026-10-12/2026-10-13 baselines: model
  `Qwen3.8-27B-UD-Q4_K_XL_v2.gguf`, provider `openai-local` at `http://127.0.0.1:8080/v1`,
  thinking off (default), temperature 0.0, RAG on with the bundled pack, harness mode
  `full --regenerate`, identical committed golden dataset. The only differences are the code
  commit (the t-0825 fix) and the unseeded LLM draw.
- Wall clock: ~59 min (22:00:26 -> 22:59:16 local; mean generation 291.9s/story). No stall, no
  partial run.
- Evidence kept: `scratch/eval_runs/2026-10-15_heldout/` (raw, gitignored), and the minimal
  re-score input committed at `fixtures/heldout_runs/2026-10-15/`. Re-scored with no model:
  `python scripts/eval/rescore.py --run-dir fixtures/heldout_runs/2026-10-15` -> **85/113, 0**
  (identical).

## 2. Gate 1 - resolution accuracy

**85/113 = 75.2%** (need >= 90%). Down from 94 on the 2026-10-13 run - see the per-story table:
the entire -9 is eval-001.

| Story | Site | 2026-10-13 | 2026-10-15 | Tests passed |
|---|---|---|---|---|
| eval-001 | saucedemo | 17/20 | **8/20** | 2/6 |
| eval-002 | automationexercise | 6/8 | 5/8 | 4/6 |
| eval-003 | demoqa | 7/8 | 7/8 | 6/6 |
| eval-004 | theinternet | 4/7 | 5/7 | 5/5 |
| eval-005 | lv_insurance | 21/24 | 21/24 | 0/10 |
| eval-006 | ecommerce_mock | 14/16 | 14/16 | 7/8 |
| eval-007 | banking_mock | 13/13 | 13/13 | 5/8 |
| eval-008 | banking_mock | 10/13 | 10/13 | 7/9 |
| eval-010 | ambiguous_mock | 2/4 | 2/4 | 1/4 |

**Why the eval-001 collapse (17 -> 8) is a draw, not a t-0825 regression:**

1. The t-0825 change is hard-scoped to message-like ASSERTs: both call sites of
   `_message_outcome_conflict` are `action == "ASSERT"` gated (the floor at
   `compute_element_score`, the bonus in `_assert_message_bonus`). FILL and CLICK resolutions are
   unreachable from it.
2. The 2026-10-15 eval-001 skeleton is structurally different and worse: it navigates to
   `cart.html` directly instead of clicking through, resolves "Checkout" to
   `#react-burger-menu-btn` (the burger menu) and "First Name"/"Last Name"/"Zip Code" to
   `.product_sort_container` (a sort dropdown), and resolves "Continue"/"Finish" to
   `#react-burger-menu-btn`. All of those are FILL/CLICK picks from a different LLM skeleton.
3. The deterministic static gate (`eval_harness.py run --mode static`) is 91/96 = 94.8% both
   before and after the t-0825 change (it covers 0 of eval-010's 4 placeholders, so it is blind
   to this fix by design).
4. The documented same-settings band is 89-92/113; 85 sits below it as an outlier low draw.

**Reading rule for this run:** do not treat the 85 as the new baseline. The like-for-like band is
89-92; the code-attributable delta of t-0825 against this run is **0** (eval-010 unchanged, all
other stories unchanged or draw-noise).

## 3. Gate 2 - hollow passes

**0** (PASS). Unchanged. ASSERT verification: by element golden 20, pipeline verdict 9, page
arrival 7, unverified 1 (from the run's `verification_strength.json`).

## 4. eval-010 c3: the floor worked, but was not sufficient

The golden wants `#order-success-title` (tolerance `#order-success-message`, `h1`) on
`success.html`.

- **2026-10-13 (pre-fix):** `assert_visible('#order-error', ..., expected_page=...index.html)`
  - the hidden error trap won; the polarity floor was negation-blind.
- **2026-10-15 (post-fix):** `assert_visible(':has-text("Item Blue Top ... could not be
  completed ...")', ..., expected_page=...index.html)` - **the trap no longer wins** (the floor
  rejected it), but the resolver fell back to a degraded full-page `:has-text(...)` locator.

**The remaining defect (new, for triage):** the journey discovery for `test_04_verify_success_message`
replays the "Place Order" click **while already on success.html** (the journey: index.html ->
click `#place-order` -> success.html -> fill quantity -> click "Place Order" ->
`#back-to-store` -> **index.html** -> scrape "order success message"). `success.html` **was**
scraped and enriched (7 elements, including `#order-success-title`), but the page cursor at
resolution time is index.html, so the success element was out of scope. The 2026-10-13 run has
the same `expected_page=index.html` on this assert - the cursor defect predates t-0825; the fix
only changed which wrong answer it produced (trap -> degraded locator).

This is the same class as the 3 `target_never_captured` misses: the target exists in the scraped
pool but the journey leaves the page that holds it before the criterion resolves.

## 5. What this does NOT change

- No code change this session - measurement and record only.
- No harness/tolerance changes (the two string-strict artifacts from the 2026-10-13 triage stay
  with B-101).
- The gates are unchanged: >= 90% gate 1, 0 hollow passes gate 2.

## 6. Next

1. **Journey page-cursor defect** (the real eval-010 c3 blocker and likely the
   `target_never_captured` class): trace why the journey replays the "Place Order" click on
   success.html, why the resolver scores `#back-to-store` 8 for it, and how the deferred ASSERT's
   page scope should stay on (or return to) the page that holds the target.
2. After that fix ships: another held-out re-measure (same settings) - the first one where
   eval-010 c3 can actually move, and which re-draws eval-001.
3. B-101 for the two string-strict artifacts, with a stated reason per tolerance change.
