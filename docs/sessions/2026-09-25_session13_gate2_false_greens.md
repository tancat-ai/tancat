# Session 13 — Gate 2: the false-green metric was measuring the wrong thing (and hiding its own bugs)

**Date:** 2026-09-25 · **Branch/worktree:** `fix/b093-false-greens` @ `.worktrees/b093-false-greens` (off `main` e719d30)
**Question (handoff):** gate 2 — the 16 false greens reported by Session 10's held-out re-measure.
**Answer:** **3 false greens**, all in one story (`eval-006` ecommerce_mock), and they are genuine wrong-element
resolutions. The count was never 16 in the sense the number implied: the metric asked "did the test use the
golden's selector?", which is not "did the test verify the condition". And the harness had a second, worse
problem: its per-test outcome parser silently returned nothing, so **every run it scored reported 0 false greens**.

---

## 1. What shipped

| Change | File | Why |
|---|---|---|
| Page-mismatch now FAILS the step (was record-only) | `src/evidence_tracker.py` | A check that "passed" on a page other than the one its locator was resolved against verified nothing. New `PageMismatchError`; guards in `fill`/`click`/`assert_visible`/`assert_hidden` so the failure is recorded once, never re-recorded. |
| Per-test false-green attribution | `scripts/eval/eval_runner.py`, `eval_metrics.py` | A false green requires the criterion's OWN test to have passed. An unmatched ASSERT in a skipped or failed test is an honest outcome. |
| Per-test outcomes from JUnit XML | `scripts/eval/eval_runner.py` | Console scraping returned `{}` under xdist (see §4). XML is machine-readable; console parsing is a fallback. |
| Missing per-test map falls back LOUDLY | `scripts/eval/eval_runner.py` | A parse failure must never read as "nothing to report". Unknown → conservative story-level rule + warning. |
| Partial-run detection | `scripts/eval/eval_runner.py`, `eval_harness.py` | A story whose regeneration raised (e.g. LLM generation timeout) produced empty-code rows and a normal-looking report. Now: banner + exit code 3. |
| `.env` loaded by the harness; provider default fixed | `scripts/eval/eval_harness.py`, `src/llm_providers/__init__.py` | The harness never loaded `.env`, so a worktree run relied on port auto-detection; and the env fallback default was `ollama`, contradicting AGENTS.md §5. |
| `criterion_kind` + verification split | `scripts/eval/dataset/*.json`, `golden_validator.py`, `eval_metrics.py` | Records, per ASSERT, whether it was verified **by element** (golden answer or distinctive element), **by page arrival** (URL assertion on the criterion's page), or **unverified** — instead of "matched the golden's selector or not". |

Gate 1 (resolution accuracy vs the golden answer) is deliberately **unchanged and strict**: it still counts only
the golden locator or a tolerance selector, measured over the whole file. Gate 2 asks a different question, so it
is measured a different way.

## 2. Why the metric had to change

The golden is a human judgement, not an oracle. Two examples from `eval-001` (saucedemo) where the golden is the
**weaker** test:

| Criterion | Golden expects | Generated test did |
|---|---|---|
| Verify the added item appears in the cart | `[data-test="cart-list-container"]` — *a list container exists* | `assert_visible('#remove-sauce-labs-backpack')` — *the backpack is in the cart* |
| Verify success (Thank You page) | `[data-test="title"]` — *saucedemo's shared page header, present on every page* | `to_have_url(".../checkout-complete.html")` — *the order actually completed* |

Both generated checks were counted as false greens. For navigation criteria the generated form is a URL
assertion; the golden demanded an element. That is a convention conflict, not an unverified pass. The customer
question is "did this step prove its claim?", so the metric now answers that.

The guard against over-permissiveness is strict: an assertion against a **global container** (`body`, `#content`,
`main`, `main:has-text(...)`, `#root`, `.container`) can never verify anything, no matter what text it contains.

## 3. Numbers (held-out, live, 9 stories, 113 placeholders)

Re-scored by re-executing the emitted tests (`scratch/rescore.py`; no LLM, so results are reproducible):

| Metric | Value |
|---|---|
| Resolution accuracy (gate 1) | **82/113 = 72.6%** — vs 86/113 (76.1%) on Session 12's generation; different LLM draw, not a like-for-like regression |
| ASSERT verification | golden 14 · distinctive element 2 · page arrival 6 · **unverified 15** |
| Tests executed / passed | 62 / 35 (56.5%) |
| **False greens (gate 2)** | **3** — all `eval-006` |

Pass-count noise floor: `eval-002` (live automationexercise) went 6→5 across two identical re-scores of the
same emitted file. The false-green count was stable at 3 in both.

The three, precisely:

| crit | test | outcome | golden wants | asserted | verdict |
|---|---|---|---|---|---|
| 3 | `test_04_go_to_cart` | PASSED | URL `cart.html` | `#place-order` | false green — that button exists **only** on `checkout.html` |
| 5 | `test_06_proceed_checkout` | PASSED | URL `checkout.html` | `#place-order` | borderline — page-unique to checkout, so it arguably proves arrival; the harness cannot know page-uniqueness without the DOM inventory, so it reports conservatively |
| 7 | `test_08_verify_order_success` | PASSED | `#success-title` | `#place-order` | false green — asserted a checkout button for the order-success claim |

Root cause: the resolver picked `#place-order` for **every** later-step assert in that story. That is a resolver
defect (gate 1), not a metric artefact.

## 4. Measurement-integrity defects found in the harness itself

These matter more than the product fixes — each one made a broken thing look green.

1. **Per-test outcomes were unparseable, so gate 2 always read 0.** `pytest.ini` enables `-n 4`; under xdist the
   outcome prints *before* the node id (`[gw0] [ 33%] PASSED path::test_01_x[chromium]`), so a line-anchored
   regex matches nothing. Fixed by reading `--junitxml`. The two runs I made before this fix reported
   "False positives: 0" — that zero was the bug, not a result.
2. **A missing outcome map implicitly meant "clean".** Now unknown → conservative story-level counting + warning.
3. **A failed regeneration produced a normal-looking report.** `eval-002/004/007/010` had timed out during
   generation and the report still presented "51.3%" as a score. Now: banner + exit 3.
4. **The harness ignored `.env`.** A worktree run silently depended on port probing; `create_provider_from_env`
   defaulted to `ollama` against AGENTS.md §5.

Also: `run_full_validation`'s own `pytest_timeout` default is 120s while the CLI passes 700s — a caller that
omits it kills healthy multi-test suites (this bit the first re-score, and is the same class as B-061).

## 5. Incidents

- **Machine restart.** I ran `pytest -n 4` concurrently with a live eval run (model + Milvus + mock server +
  browsers). That is what crashed the box. Not repeated: tests run before or after an eval, never during.
- **LLM generation timeouts** (600s) killed `eval-002/004/007/010` in one pass and `002/006` in another; the
  server was measurably slow under load while a `AITEST_RESOLUTION_TIMEOUT`-driven 120s batch-ranker cap turned
  several placeholders into honest skips (`cart badge updated`, `product name/price`, `dashboard loaded`,
  `transfer form loaded`, `payment success message`). Causes are capacity, not code; the failures are now loud.
- The launcher's `$KV_CACHE` comment ("f16 at 256k doesn't fit") is stale — confirmed by the user. Not a factor.

## 6. What this does and does not close

- Gate 2 is no longer "16". The honest number is **3**, and the metric now demands more than the old one in the
  place where it matters (global containers never verify).
- Remaining real defects are all visible in the unverified list: `#place-order` for cart/checkout/success in
  ecommerce, `main:has-text(...)` for balances, `#transfer-error`/`#payment-error` for *success* messages,
  `.text` for a form title, and criteria with **no assertion emitted at all** (eval-006 crit 2/4).
- `#transfer-error` for "transfer success message" is worth calling out: it shares the word "transfer" and was
  being blessed as verified. That is now blocked by a polarity guard (success wording vs error element).

## 7. Next

1. **Resolver wrong-element class** (gate 1): `#place-order` stickiness, `main:has-text` containers, and
   error-vs-success siblings (`#transfer-error` for a success criterion). This is now the single biggest
   measurable defect.
2. **Golden-quality audit** (watch item): `[data-test="title"]` and container-for-content expectations are weak;
   the dataset is a 2026-07 snapshot and AGENTS.md schedules re-validation every 3–6 months.
3. **B-097** — per-test `pytest.skip` granularity (one unresolved placeholder still hides every resolved step).
4. **The product should report its own verification strength** (it knows at resolution time whether a locator came
   from the expected page's scrape). That turns "every pass names what it checked" into a customer-visible claim
   and would let the harness stop guessing.
5. Promote `scratch/rescore.py` into `scripts/eval/` — re-scoring a metric change currently needs no LLM run.
6. CI runs `pytest tests/` only; the eval harness's own suite lives in `scripts/eval/*_test.py` and is **not** in CI
   (a compact CI guard now lives in `tests/test_eval_gate2_metric.py`).

**Gates:** 3399 pytest / 3 skipped · smoke 39/39 · ruff clean · mypy clean except the pre-existing B-079 error in
`eval_runner.py` · eval static 97.9% (unchanged).
**Artifacts:** `scratch/rescore3.log` (final re-score), `scratch/rescore.py`, `scratch/story_falsegreen_detail.py`,
`scratch/golden_audit_criterion_kind.py`, `scratch/gate2_out2/`, `scratch/gate2_out3/`.
