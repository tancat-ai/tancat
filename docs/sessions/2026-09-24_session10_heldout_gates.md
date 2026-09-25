# Session 10 — held-out re-measure of the Part C gates (record)

**Date:** 2026-09-24 · **Branch/worktree:** `measure/session10-gates-1-3` @ `.worktrees/session10-gates-1-3` (off `main` b11ee8f)
**Question:** do gates 1–2 pass once measured on a **held-out** set, live regeneration, not the landing page?
**Answer:** **No. Gate 1 = 66.4% (needs ≥90). Gate 2 = 16 false greens (needs 0).**

The Session 7 landing-page numbers (0 wrong-element mappings, 0 false greens) were **site-specific**.
They do not generalize to the golden dataset.

---

## 1. Method

- Runner: `python scripts/eval/eval_harness.py run --regenerate --mode full --dataset scripts/eval/dataset`
  (worktree code, `--no-persist`, `--test-output scratch/gate1_out`).
- Held-out set: the 9 committed golden stories (`scripts/eval/dataset/eval-001…010`) — 6 sites,
  62 conditions, 113 placeholders. None of these sites was used to build the B-086/088/090/092 fixes.
- Live regeneration + live scrape + pytest execution against the real sites; mocks auto-served on :8781
  by `eval_runner`. Model: Qwen3.8-27B-UD-Q4_K_XL_v2, LM Studio :8080, `thinking=off` (B-091 default).
- Wall clock: ~44 min total (regeneration 21:18→21:46, execution 21:46→22:02).
- Log: `scratch/gate1_full.log`. Emitted tests: `scratch/gate1_out/`.

## 2. Result

| Metric | Value | Gate |
|---|---|---|
| Resolution accuracy | **75/113 = 66.4%** | gate 1 ≥90% → **FAIL** |
| False greens (wrong ASSERT locator on a passing test) | **16** | gate 2 = 0 → **FAIL** |
| Tests executed / passed | 63 / 49 (77.8%) | — |
| Skeleton completeness | 100% | ✅ |
| Mean generation duration | 172.7s / story | — |

### Per-story breakdown

| Story | Site | Placeholders | Accuracy | Tests | False pos |
|---|---|---|---|---|---|
| eval-001 | saucedemo | 20 | **75%** | 6/6 | **5** |
| eval-002 | automationexercise | 8 | **100%** | 6/6 | 0 |
| eval-003 | demoqa | 8 | 88% | 5/6 | 1 |
| eval-004 | theinternet | 7 | 86% | 5/5 | 1 |
| eval-005 | lv_insurance | 24 | **38%** | 0/10 | 0 |
| eval-006 | ecommerce_mock | 16 | **69%** | 8/8 | **4** |
| eval-007 | banking_mock | 13 | **54%** | 9/9* | **3** |
| eval-008 | banking_mock | 13 | **77%** | 9/9* | 1 |
| eval-010 | ambiguous_mock | 4 | **50%** | 1/4 | 1 |

\* see §4 — eval-007 and eval-008 share one emitted file, so one of them did not run its own tests.

## 3. What the numbers mean

- **The worst classes are the multi-step / form-heavy mocks** (lv_insurance 38%, ambiguous_mock 50%,
  banking_mock 54%). These need a later-step DOM that the stateful scrape does not reach — the
  B-054 / B-055 / AI-064 family, not the landing-page classes.
- **Pure static public sites are fine**: automationexercise 100%, demoqa 88%, theinternet 86%.
- **False greens are not fixed in general.** B-090/B-092 added `PageFactAssertion` /
  `document_assertion` families keyed to landing-page wording. On the held-out set, a passing test
  still frequently rests on an ASSERT whose locator is not the golden element → 16 of 49 passes.
- Per-story example (theinternet, `tc04` "Accept the JavaScript alert popup"): the emitter checks
  `assert_visible('#content', label='alert accepted')`. `#content` is the page container, always
  visible. It proves nothing. `tc05` adds a second weak assert (`h3 "JavaScript Alerts"` labelled
  "alert accepted"); the harness counter caught only one of the two.

## 4. Harness defect found while measuring (new item B-094)

`eval-007` and `eval-008` are two stories on the **same site** (`banking_mock`). Both regenerated to
`test_banking_mock.py`; the later write won. The file on disk holds eval-008's 9 tests (TC-01…TC-09).
The runner then executed that same file **twice** — once labelled eval-007, once eval-008 — so:

- eval-007's own 8 tests never ran;
- "Tests executed: 63" is inflated by ~9;
- eval-007's pass/fail verdicts are really eval-008's.

The resolution metrics are unaffected (static validation uses each story's own code map).

## 5. Method notes / dead ends (so the next session does not repeat them)

- `eval_resolver.py --mode live` is **not** a gate-1 measure: it scrapes without login, so auth-gated
  pages (cart/checkout) resolve to the login DOM. It reported 15.9%.
- `eval_resolver.py --mode static` in the main repo is a **RAG on/off benchmark**, not the gate metric
  (35.4% with RAG off). The documented 97.9% is `eval_harness --mode static` (captured code vs golden),
  a different metric again.
- A worktree has none of the gitignored captures (`scraped_pages/`, `captures/`), so run `--mode pipeline`
  to regenerate, or use the harness `--regenerate` path.
- The harness `false_positive_rate` counts **wrong-locator ASSERTs on passing tests** — it is a fair
  proxy for false greens, but it only fires when the locator differs from the golden key. A weakened
  assert on a *matching* locator still reads zero.

## 6. Verdict against the Part C gates

| # | Gate | Result | Verdict |
|---|---|---|---|
| 1 | Live resolution accuracy ≥ 90% on a held-out set | 66.4% | **FAIL** |
| 2 | Zero false greens | 16 | **FAIL** |
| 3 | Self-healing fixes ≥ 30% | not exercised (all reds are assertion reds) | still unmeasured |
| 4 | Prose story + headings never truncate | not exercised | unchanged |
| 5 | 50-test suite ≤ 5 min | not measured (63 tests in 16 min incl. live sites) | — |
| 6 | Stranger can buy | unchanged | **NO** |

## 7. Recommended next step

Fix the **multi-step mock class** (lv_insurance / banking / ambiguous) — it dominates the gate-1
deficit. **36 of the 38 missed placeholders** are on the stateful / auth-gated stories
(lv 15, banking 6+3, ecommerce 5, saucedemo 5, ambiguous 2). That is a capture/scoping
problem (B-054/B-055/AI-064), not an emit problem.

Then re-run this exact command and re-score. Do not touch the landing page again.
