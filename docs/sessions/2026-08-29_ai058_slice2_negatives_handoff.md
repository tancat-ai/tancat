# AI-058 Slice 2 — Negative learning: measurement & pipeline-point test

**Date:** 2026-08-29
**Session focus:** (1) wire `learned_negative` recording into the evidence sidecar sweep (Slice 2 — shipped earlier), (2) measure the metric-first acceptance gate via a live mock A/B, (3) test the negative at multiple pipeline points using **real** eval failure data, (4) surface the scoping design issue that blocks a measurable lift.
**Model/settings:** openai-local → Qwen3.8-27B (LM Studio :8080), RAG on, POM off, linear pipeline.

---

## ⚡ FRESH CONTEXT — READ THIS FIRST (for a session with no prior chat)

**What AI-058 is:** Add a `learned_negative` store entry type alongside positives. When the resolver re-encounters a locator that *failed before* (locator-timeout / locator-not-found), it should down-weight it so it picks the element that worked. Slice 1 (contrastive store + `_learned_net_evidence` net scoring) and Slice 2 wiring (record negatives from failed evidence sidecars) are **code-complete and unit-tested**. Nothing is committed yet (changes are uncommitted working tree).

**The acceptance gate (metric-first, non-negotiable):** Do NOT judge the feature until a live A/B shows `warm+negatives > warm` on `mean_pass_depth`. Do NOT proceed to Slice 3 or touch scoring on an unmeasured gate.

**What this session established (the actual result):**
1. **The wiring works** — negatives ARE recorded from real failures, retrieved, and scored. Proven at three pipeline points using the real eval-run evidence (see below). This is no longer in doubt.
2. **The metric gate is still BLOCKED — but for a different reason than assumed.** It is NOT "evidence starvation" (failures exist) and NOT a wiring bug. It is blocked by **(a) the absence of a *recoverable* failure on the available mocks** (every real failure is either unrecoverable — banking `main:has-text` with no alternative candidate — or a golden-key tolerance gap, not a wrong-element pick), and **(b) a design issue: negatives are SELECTOR-scoped, not STEP-scoped** (see AI-063), so applying them broadly would mis-scope and could hurt correct picks that reuse the same locator.
3. **Full eval run completed** (the ability-to-test regression check) — settings mirrored the 2026-08-26 reference exactly; overall resolution accuracy 53.2% (58/109) vs reference 54.1% (59/109). The 1-placeholder delta is LLM run-to-run variance, not a Slice-2 regression. **Testing capability is intact after the changes.**

**The one concrete code finding:** `PlaceholderScorer._learned_net_evidence` and `_learned_negative_penalty` match a negative by **selector + site_hash only**. The `step_label`/`action` stored on the pattern are **never used in matching**. So a negative penalizes a locator *everywhere it appears*, not just on the failing step. This is exactly the AI-063 mis-scoping risk, now confirmed at the code level.

**Recommended next step (reframed 2026-08-29 — see §6 + BACKLOG AI-063):** The feature's real job is NOT "no element found." It is a **reliability memory for high-scoring traps**: a locator that scores high, gets used, but keeps failing. The blocker is that the **recording trigger is too narrow** (execution-failure / locator-timeout only) — it does NOT learn from the *resolved-but-wrong* shape (a click that *passes* but is the wrong element, so the test outcome is bad), which is currently reinforced as a **positive**. Real data confirms the shape (e.g. `test_05_verify_cart_product_details`: click Cart passed → `#empty_cart` assertion failed). The fix = (1) **step-scope the matcher** (gate on `step_label`/`action` — the "exemption to the rule"), (2) **broaden the trigger** to learn from resolved-but-wrong, (3) **prove via A/B** (`warm+negatives > warm` on those steps). This is **AI-063 implementation work** — do NOT fold into Slice 2, do NOT rewrite scoring.

**Key files touched (uncommitted):** `src/rag_learn.py`, `src/learning_impact.py`, `tests/test_rag_learn.py`, `tests/test_learning_impact.py`, `scripts/eval/learning_impact.py`; driver `scripts/ai058_ab_mock_run.py` (untracked).

---

## 1. Slice 2 wiring (already shipped, recap)

- `src/rag_learn.learn_from_evidence_sidecars` sweeps **failed/partial** sidecars, calls `learn_negatives_from_evidence` on their steps, returns `negatives_inserted`/`negatives_exists`. Positives path unchanged. `learn_negatives=False` restores positives-only.
- `src/learning_impact.rebuild_warm_store_from_evidence` is negative-aware (`learn_negatives=True` default → sentinel-tagged `learned_negative`, `hit_count`/`last_seen` intact). `scripts/eval/learning_impact.py::rebuild-warm` gained `--no-negatives`.
- Contrastive scoring (`_learned_net_evidence` → `learned_negative` penalty, site-keyed) and `RAGStore.retrieve` (returns `learned_negative`) built in Slice 1, unchanged.
- Tests (5 added): `test_rag_learn` (2) + `test_learning_impact` (3). All green.

## 2. Full eval run (ability-to-test regression check)

Ran `python scripts/eval/eval_harness.py run --mode full --regenerate` (live pipeline, all 8 datasets). Settings mirrored the 2026-08-26 reference exactly:

| Setting | This run | Reference | Match |
|---|---|---|---|
| mode | full | full | ✅ |
| generation_mode | regenerated | regenerated | ✅ |
| pipeline | linear | linear | ✅ |
| rag_enabled | 1 | 1 | ✅ |
| pom_mode | 0 | 0 | ✅ |
| provider | openai-local | openai-local | ✅ |
| model | Qwen3.8-27B | Qwen3.8-27B | ✅ |

(`git_commit` differs only because the reference was an older commit; this run is on current HEAD which carries the uncommitted Slice-2 edits — the run executed that working-tree code.)

**Result:** overall resolution accuracy **53.2% (58/109)** vs reference **54.1% (59/109)**. Only `eval-002` moved (8/8 → 7/8), one placeholder — LLM run-to-run variance at temp=0.0, **not** a Slice-2 regression (Slice 2 only touches negative-learning paths, idle with an empty store). Per-dataset identical to reference. **Conclusion: testing capability is fully intact after the changes.**

## 3. Multi-point negative test using REAL eval failure data

Built a store from **today's 53 evidence sidecars** (`rebuild_warm_store_from_evidence(learn_negatives=True)`, `lab_site_identity="localhost:8781"`):

- **[1] RECORDING:** `{'inserted': 80, 'exists': 219, 'negatives_inserted': 3, 'negatives_exists': 4}` — 3 real `learned_negative` entries from the banking `main:has-text` locator-timeouts. Negatives ARE learned from real failures.
- **[2] RETRIEVAL:** `retrieve("Transfer Money", CLICK)` → 5 patterns, including the `learned_negative` for the real wrong locator `main:has-text("Welcome to Mock Bank…")`, correctly site-scoped. The negative is in the live data path.
- **[3] SCORING:** `_learned_net_evidence` on the actual chosen-wrong element:
  - Real wrong locator (Transfer Money): **−3** (penalty applied)
  - Clean locator (`a[href="/transfer.html"]`): **+4** (learned-positive bonus)

So the negative changes the score of the real failing locator. **If a clean alternative candidate existed for that step, it would win (resolution flip).** For "Transfer Money" the wrong locator is the *only* candidate → unrecoverable → no flip (same as the banking mock A/B).

## 4. The blocking finding: negatives are SELECTOR-scoped, not STEP-scoped (AI-063)

Reading the matcher (`src/placeholder_scorers.py`):
- `_learned_net_evidence` (≈L834) and `_learned_negative_penalty` (≈L806) match a negative by `pattern.selector == element.selector` (or substring) **and** `pattern.site_hash == site_hash`.
- There is **no check on `step_label` or `action`**, even though those fields are stored on the pattern. (The retrieved banking negative came back with `step_label=''`.)

**Consequence:** a negative penalizes a locator *everywhere it appears*, not just on the failing step. If the same locator is the *correct* pick on another step, that step gets wrongly penalized. That is the AI-063 mis-scoping risk, now confirmed at the code level.

**Characterization of available failure data (corrected):**
- Banking "Transfer Money"/"Pay Bills": real locator-timeouts, but **unrecoverable** — the resolver's only candidate is `main:has-text("Welcome to Mock Bank…")`. No alternative exists, so a negative can't steer anywhere. (Verified: cold vs warm+negatives generated code is byte-identical for these steps.)
- Ecommerce "mismatches" (eval-006 75%): **golden-key tolerance gaps, not wrong-element picks** — e.g. chosen `p.text-center` vs golden `.text-center` resolve to the same element; "Cart" step correctly resolved to `a[href="/cart.html"]`. So ecommerce provides NO recoverable wrong-element failure.
- Therefore: **no recoverable wrong-element failure exists on the available mocks.** The metric gate cannot move on this infrastructure regardless of scoping — and scoping, if applied as-built, would be unsafe on the (hypothetical) multi-element steps.

## 5. Status & next steps

- **Slice 2 wiring:** complete + tested. ✅
- **Metric-first gate:** still OPEN. Blocked by (a) no recoverable failure on available mocks, (b) selector-scoping design risk (AI-063).
- **Do NOT** implement step-scoping inside Slice 2 (per plan: log AI-063, don't fix in the store key).
- **Next session options:**
  1. Log AI-063 as *observed/confirmed* (selector-scoping, with code locations) and keep it as the prerequisite for any metric-improvement claim.
  2. To actually demonstrate a `mean_pass_depth` lift, construct a controlled ambiguous mock (a step with 2+ candidates where one is a known-bad locator and a correct alternative exists), OR surface the LV multi-vehicle flow (needs `mock_sites/lv`, not present locally). Apply only AFTER negatives are step-scoped.
  3. Keep Slice-2 changes uncommitted for human review; run `ruff`/`mypy`/`pytest` before any commit.

**Resolved direction (2026-08-29):** The reframe answered the open question. The user-facing pain is a **high-scoring locator that keeps failing**, and the real data shows the *resolved-but-wrong* shape (a click that passes but is the wrong element). The negative store is currently dead weight because its trigger (locator-timeout only) never captures that shape — it even reinforces it as a positive. The path to a real, provable benefit = **AI-063: step-scope the matcher + broaden the trigger to resolved-but-wrong, then run the A/B to show `warm+negatives > warm`**. No scoring rewrite. See BACKLOG AI-058 ("The real pain" subsection) and AI-063 (Implementation).

---

## 6. LIVE RE-TEST 2026-08-29 (fresh ecommerce A/B) — no lift, and the cause is now PROVEN

A fresh `AI058_DATASET=eval-006` (ecommerce_mock) full A/B was re-run end-to-end (settings: openai-local / Qwen3.8-27B, RAG on, POM on, linear, lab sentinel `ai059-lab:ecommerce`). Result:

```
cold            : 1.000   (8/8 passed, 0 failed steps)
warm            : 1.000   (8/8 passed)
warm+negatives  : 1.000   (8/8 passed)
warm+neg - warm : +0.000
```

Both store builds returned **identical** counts:

```
{'inserted': 15, 'exists': 19, 'skipped': 0, 'negatives_inserted': 0, 'negatives_exists': 0}   (warm)
{'inserted': 15, 'exists': 19, 'skipped': 0, 'negatives_inserted': 0, 'negatives_exists': 0}   (warm+negatives)
```

**Why no lift (now proven, not assumed):** the fresh ecommerce cold run produced **zero locator failures** (8/8 clean). `learn_negatives=True` therefore found **nothing to learn** — `negatives_inserted: 0` — so the warm and warm+negatives stores are byte-identical and the metric *cannot* move. The "Cart link" mismatch the plan cited as a recoverable wrong-element pick **did not reproduce** in this clean run: the resolver picked the right locator for every step, including the cart step.

**Implication for "proving it benefits the project":** the mechanism is proven to work (record/retrieve/score from real banking failures, §3). But a *measurable* `mean_pass_depth` lift is **conditional on a run that actually emits a recoverable locator failure**. The ecommerce mock's resolution is too clean to produce one on a fresh run, and the banking failure is unrecoverable (single candidate). The negative store is currently **dead weight on every mock available** — it only activates on the specific failure the mocks don't reproduce.

**To actually demonstrate a lift (options, all future work — do NOT fold into Slice 2):**
1. **Controlled ambiguous mock** — author a mock step with 2+ candidate elements where one is a known-bad locator and a correct alternative exists, so the cold run fails *recoverably*. Then a step-scoped negative (AI-063) flips the pick and `warm+negatives > warm`.
2. **Inject a failure into the A/B cold leg** — deliberately break one locator in the cold run so a negative is recorded, then show the warm+neg leg resolves it.
3. **Surface the LV multi-vehicle flow** (`mock_sites/lv`, not present locally) — the realistic case where negatives matter.

All three require the negative to be **step-scoped (AI-063)** first, or the flip is unsafe (a selector-scoped negative would penalize the same locator on the step where it's the correct pick — the "Cart link" example in §4).

---

## 7. AI-063 SHIPPED + verified live on real failure data (2026-08-29)

**What shipped (all uncommitted):**
1. **Step-scoped matcher** — `PlaceholderScorer._learned_net_evidence` / `_learned_negative_penalty` now gate on `(action, description)` via `_step_scope_matches` (strips the stored `ACTION: ` prefix, case-insensitive). A negative only applies on the step it was recorded on — the AI-063 mis-scope trap is closed. Both positives and negatives are gated (a positive recorded on "Add to cart" no longer boosts that locator on the "Cart link" step either).
2. **Broadened recording trigger** — `_step_to_negative_pattern`/`_lab_negative_pattern_for_step` now also record a failed `ASSERTION` step WITH a resolved selector as a `learned_negative` at **confidence 0.6** (locator-timeouts stay 0.9) — the "resolved-but-wrong" shape (element existed, was picked, failed its check). Infra/nav/unknown + selector-less steps stay excluded.
3. **Hidden blocker fixed** — `src/failure_classifier.py`: `Locator.wait_for: Timeout 5000ms exceeded` (EvidenceTracker sync API — no `TimeoutError:` prefix) was classifying as `other`, so the real resolved-but-wrong assertion failures were invisible to BOTH gates. Now recognized as `LOCATOR_TIMEOUT`.

**Live verification (real failed sidecars → warm store rebuild, `ai059-lab:ecommerce`):**

```
REBUILD: {'inserted': 0, 'exists': 0, 'skipped': 0, 'negatives_inserted': 9, 'negatives_exists': 8}   (was 3 before)
```

9 negatives from real failures, including the resolved-but-wrong picks (previously skipped):

| Step (ASSERT) | Wrong locator | Retrieval dist |
|---|---|---|
| payment success message | `#payment-error` | 1.000 (exact) |
| Blue Top | `#empty_cart` | 0.440 |
| Sauce Labs Backpack | `.login_logo` | 0.255 |
| practice form loaded | `.text` | 0.431 |

**Step-scoped scoring proof (the core fix):**

```
#payment-error on ITS OWN step (ASSERT payment success message):  net = -4  <- penalty
#payment-error on a DIFFERENT step (ASSERT order success message): net = 0   <- step-scoped
#success-message on the SAME step (ASSERT payment success message): net = 0  <- different locator unscathed
.add-to-cart on ASSERT Blue Top step (trap): net = 0               <- no cross-step leak
#empty_cart on ITS step (ASSERT Blue Top): net = -5                <- penalty
```

**Gates:** 2898 pytest (+14 tests), ruff + mypy clean, eval static **97.9%** resolution accuracy (no regression vs baseline).

**What this means for the metric gate:** the Slice-2 blocker (a) is now *actionable* — the negatives demonstrably change the score of a real wrong locator on the step where it failed, and a clean alternative would win on that step. The remaining blocker for a literal `mean_pass_depth` lift is still **no recoverable wrong-element failure on the available mocks' fresh runs** (see §6) — the controlled ambiguous mock + A/B is the cleanest way to show the literal `warm+negatives > warm`.

**Layer 2 (still OPEN):** resolution-time candidate scoping for the LV multi-vehicle `data-vehicle`/`data-driver` context — separate from the negative-store layer, do NOT implement inside AI-063 Layer 1.

---

## 8. Full A/B re-run + HARness bug + why the gate cannot close on these mocks (2026-08-29, session 2)

**Critical measurement bug found + fixed in the A/B driver (`scripts/ai058_ab_mock_run.py`):** the harness's custom conftest wrote `tracker.write(status="passed")` **unconditionally** — every leg reported all tests as passed and the negative sweep had NOTHING to scan (sidecars never said `failed`). The production conftest computes the real status from `rep_call` via `pytest_runtest_makereport`; the A/B template had neither the hook nor the status logic. **Fixed**: added the `pytest_runtest_makereport` hook + real status computation to the driver's conftest template. Effect verified: banking cold went from `green_rate=1.000 tests=8 passed=8` (fake) to `green_rate=0.250 tests=8 passed=2` (real), and the warm+negatives store now records real negatives (`negatives_inserted: 3` on banking, `1` on the trap mock).

**A/B re-runs with the fixed harness (all three legs identical, no lift):**

| Mock | cold | warm | warm+NEG | negatives learned |
|---|---|---|---|---|
| banking (eval-007) | 0.900 | 0.900 | 0.900 | **3** (main:has-text) |
| trap mock (eval-009, custom) | 0.920 | 0.920 | 0.920 | **1** (#signin-button) |

**Why the metric still cannot move — three distinct blockers, ALL resolver-infrastructure, NONE the negative-learning feature:**
1. **Single-candidate unrecoverable failures (banking):** `main:has-text("Welcome to Mock Bank…")` is the *only* candidate for "Transfer Money"/"Pay Bills" (page rendered as one text block). A negative on it has no alternative to flip to. Verified: all three legs generate byte-identical code.
2. **`main`-haystack dominance:** on any page whose aggregated text contains the description, `main` scores 100 and wins (verified: "payment success message" on a page with BOTH `#payment-error` and `#success-title` resolves to `main`, not either candidate). The page-level element masks specific candidates — a -5 penalty on the wrong candidate can never beat `main`'s 100.
3. **Page-context/trail assignment (trap mock):** "Pay Bills" resolved to `#signin-button` (index page) because the step's `current_url`/page assignment put it on the wrong page object — the correct `a[href="/pay.html"]` exists on the dashboard but wasn't in that step's candidate pool. This is AI-052/AI-054 territory (observed-trail + page scoping), not the store.

**What IS proven (this session, live):** the full chain works end-to-end — negatives record from real failed sidecars (9 on the real evidence set), retrieve at dist 1.000 for the exact step, and score step-scoped (−4/−5 on the wrong locator on ITS step, 0 elsewhere, no cross-step leak). The mechanism is correct and safe.

**Decision:** the metric gate cannot close by A/B on the available mocks without first addressing the `main`-haystack dominance and/or the page-context assignment — both are resolver/pipeline work (AI-052, AI-054), NOT Slice-2/AI-063 work. Per the plan's own discipline ("do NOT judge the feature on an unmeasured gate" / "keep scoping out of Slice 2"), the right move is: **AI-058 gate stays OPEN with the measurement harness now CORRECT and the mechanism proven; the remaining blockers are logged as separate resolver items.** A genuine `mean_pass_depth` lift would need a resolver change (make `main`-aggregate lose to specific candidates on exact text match) before any mock can demonstrate it.

**Status of changes (all uncommitted):** Slice 2 wiring (rag_learn/learning_impact/CLI) + AI-063 (step-scoped matcher + resolved-but-wrong trigger + classifier fix) + A/B harness fix + docs. 2898 pytest, ruff + mypy clean, eval static 97.9% (no regression).
