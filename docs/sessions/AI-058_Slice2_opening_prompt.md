# AI-058 Slice 2 — Opening Message (paste into fresh context)

> Copy everything below the line into a new Pi session to continue AI-058.

---

You are continuing **AI-058 Slice 2** in the `AI-Playwright-Test-Generator` repo (working dir `C:/Users/l_a_c/code/AI-Playwright-Test-Generator`). The repo is clean on top of commit **`281e1bb`**, which already shipped: AI-059 (isolation harness + usage trace + effect trace), AI-061 (project-scoped RAG identity, `AITEST_RAG_SCOPE`), AI-062 (fastpath rebalance — RAG bonus now applied on the haystack fast path), and **AI-058 Slice 1** (contrastive learned store: `learned_negative` entries + net scoring). Read `docs/sessions/2026-08-28_ai058_slice1_handoff.md` FIRST — it carries the full Slice-1 design, decisions, and gotchas.

## Task (AI-058 Slice 2 — wire negatives in, then measure the metric-first gate)

Slice 1 built the mechanism but nothing is wired end-to-end. Slice 2 makes the contrastive store *live* and judges it:

1. **Wire negative recording into the evidence sidecar sweep** — `src/rag_learn.learn_from_evidence_sidecars` currently processes ONLY passed-test sidecars (`test.status == "passed"`). Extend it (or a sibling sweep) to scan **failed-test sidecars** and call `learn_negatives_from_evidence` on their steps. The locator-class gate (`classify_failure` → `LOCATOR_TIMEOUT`, which covers both Playwright "TimeoutError … waiting for …" and the product's "Locator '…' not found") already excludes assertion/navigation/unknown + selector-less steps, so infra flakes never reach the store. Keep the passed-only positive path unchanged.
2. **Harness A/B — negatives-on vs negatives-off on the mocks**, judged by the feature's acceptance metric:
   - `src/learning_metrics.py::analyze_sidecars` already computes `mean_pass_depth` / `first_pass_green_rate` / `false_positive_rate`.
   - `src/learning_impact.py::ControlledBaselineRunner` runs the legs; `rebuild_warm_store_from_evidence` currently tags ONLY positives with the lab sentinel (`AI059_LAB_SITE_HASH` / `lab_site_identity`). Slice 2 needs a **negative-aware warm-store rebuild** (learned_negative entries tagged with the sentinel, `hit_count`/`last_seen` intact) and the legs `warm-positives` vs `warm+negatives`.
   - **The judge: does `warm+negatives > warm` on `mean_pass_depth`?** If yes, Slice 1 is a win → proceed to Slice 3 (description-keyed swap at scoring, self-heal integration). If no, report why (evidence starvation? wrong negatives? penalty too weak?) before touching scoring — the fastpath fix (AI-062) means bonuses/penalties DO reach the fast path now, so scoring changes have teeth.
3. If the A/B exposes **systematic mis-scoping** (e.g. LV-style multi-vehicle "add driver" picking the wrong vehicle's button, or back-button ambiguities) that's **BACKLOG AI-063** (resolution-time candidate scoping via `section_scoper`/prior steps) — log the evidence, do NOT fix it in the store key.

## Design facts to hold (from Slice 1 + this session's decisions)

- Negatives are per `(description, selector, site_hash)` — one row per description-key per polarity (selector NOT in the dedup key). Same locator in both stores → majority by `hit_count`; tie → recency (`last_seen` wins) with a conservative bias.
- "Description" = the placeholder/step intent label (e.g. "Add to cart"), the durable cross-test key.
- The usage trace (Deliverable 2) still reports positive-only bonuses; negatives appear as `source="learned_negative"` with `bonus:0`.
- Mocks: `mock_sites/ecommerce` / `mock_sites/banking` serve on `:8785` / `:8786` locally; the eval harness serves them on `:8781`. `AITEST_STORAGE_ROOT` points a run at a temp store; `AITEST_RAG_SCOPE` scopes identity; `AI059_RAG_DIAGNOSTICS_PATH` enables the opt-in diagnostic trace.

## Gotchas (hard-learned)

- Pre-commit `ruff format` modifies files → commit aborts → re-`git add` + commit again. Full hook gate: ruff, format, mypy (**checks tests too** — any `VectorStoreBackend` fake must implement every protocol member incl. `find_negative`/`query_dedup_keys`), eval-accuracy (97.9%), kanban-freshness (run `python scripts/maintenance/kanban.py` when BACKLOG changes).
- `classify_failure` regexes are literal (`timeouterror` + `waiting for`; "locator not found" separately). Test error fixtures must match (e.g. `"TimeoutError: Timeout 5000ms exceeded.\nwaiting for locator('…')"`).
- Do NOT commit `docs/sessions/2026-08-28_ai058_slice1_handoff.md` or `AI-058_Slice2_opening_prompt.md` (handoff artifacts). The two older `AI-059*` session files are also untracked — leave them.

## Verification (all must pass before any commit)

- `python scripts/smoke.py --json` (39)
- `python -m ruff check .` + `python -m ruff format --check .`
- `python -m mypy src/ cli/` (and pre-commit mypy on staged tests)
- `python -m pytest tests/ -q` (currently 2886 passed)
- `python scripts/eval/eval_harness.py run --mode static --min-accuracy 79` (baseline 97.9%)
- Confirm `tests/test_learning_impact.py` (AI-059/AI-058 home) still passes.

## When done

Run the ship-it skill to commit + push. Update BACKLOG AI-058 (Slice 2 result + the measured `mean_pass_depth` delta) and CHANGELOG, regen kanban. Do NOT commit the handoff docs unless continuing into a follow-up.