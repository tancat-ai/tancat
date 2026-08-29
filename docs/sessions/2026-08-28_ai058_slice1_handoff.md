# AI-058 Session Handoff — Slice 1 shipped (contrastive learned store)

**Date:** 2026-08-28
**Branch / commit:** `main` @ `281e1bb` (+ the two untracked handoff docs from the previous pause)
**Status:** AI-058 Slice 1 shipped and CI-green. Next step is **Slice 2** (this handoff's subject) — hand it to a fresh context via `AI-058_Slice2_opening_prompt.md`.

---

## 1. TL;DR

- **This session (2026-08-27→28) shipped, in order:** AI-059 D2 continuation (`c2af997`), **AI-061** project-scoped RAG identity (`c0b8820`), **AI-062** effect trace (`2e0f936`) → measured decisive-rate ~0% → **fastpath rebalance** (`d15d66c`), and **AI-058 Slice 1** — the contrastive learned store (`9aa8bbc`). All pushed, CI green, BACKLOG/kanban current.
- **AI-058 Slice 1** gives the learned store a **`learned_negative`** entry type (confirmed-wrong locators) and a **net-scoring** rule so the resolver down-weights what failed before. Nothing is wired end-to-end yet — that's Slice 2.

## 2. Why Slice 1 (the reframe the feature depends on)

The learned store was positive-only and ingested ONLY passed steps → it can only *reinforce* what the pipeline already gets right; it structurally cannot fix the error mass (spec: learned descriptions have ~0% overlap with golden keys; measured byte-identical accuracy at learned=0 vs learned=380). The objective is NOT golden-key fidelity; it is **test-progress depth** (`mean_pass_depth`, `first_pass_green_rate`) measured by the AI-059 harness. Slice 1 builds the mechanism; Slice 2 measures it.

## 3. Slice 1 design (the fresh context's base — read before editing)

### Store — `src/rag_store.py`
- `RetrievedPattern` gained `hit_count: int = 0` and `last_seen: float = 0.0` (recency tie-break).
- Protocol `VectorStoreBackend` + `MilvusLiteBackend`: new `find_negative(action_type, description, site_hash)` (mirror of `find_learned`, `entry_type == 'learned_negative'`).
- `RAGStore.upsert_negative_pattern(pattern)` — dedup on `(action_type, description, site_hash)` (selector NOT in the key — **one row per description-key per polarity**), `hit_count` + `last_seen`; repeats bump `hit_count` and refresh `last_seen` (Milvus `increment_learned_hit` also sets `last_seen`).
- `retrieve()` maps `source` from `entry_type` (so negatives arrive as `source="learned_negative"`) and populates `hit_count`/`last_seen`. `counts_by_type`/`delete_learned` were already generic.

### Recording — `src/rag_learn.py`
- `_LOCATOR_FAILURE_CATEGORIES = {FailureCategory.LOCATOR_TIMEOUT}` — `classify_failure` maps BOTH Playwright "TimeoutError … waiting for …" AND the product's `Locator '…' not found` fast-fail to `LOCATOR_TIMEOUT`. Everything else (assertion, strict-violation, navigation, unknown) is excluded — **infra flakes can never poison the store**.
- `_step_to_negative_pattern(step)` — failed step + locator-class + resolved `locator` + site identity → `LearnedPattern(source="learned_negative", confidence=0.9)`.
- `learn_negatives_from_evidence(steps, store=None) → {inserted, exists}` — best-effort.
- `learn_from_patch(...)` now ALSO upserts a negative for `_selector_from_code(old_text)` (self-heal replacement pairs = the highest-precision contrastive signal).

### Scoring — `src/placeholder_scorers.py`
- Constants: `LEARNED_NEGATIVE_BONUS = 5`, `LEARNED_NEGATIVE_MAX_HITS = 8` (|penalty| = 5·8 = 40 < +80 structural tier).
- `_learned_negative_penalty(element, patterns, site_hash)` — mirror of `_learned_pattern_bonus` (full −5·conf, substring −2·conf) × min(hit_count, MAX_HITS).
- `_learned_net_evidence(element, patterns, site_hash) -> int` — ONE net signal per `(desc, selector, site)`: positives−negatives; majority by `hit_count`; **tie → recency (`last_seen`) wins, conservative bias** (a wrong pick costs the test; a skip is self-heal-recoverable). Used on BOTH the slow and the fast (AI-062) scoring paths, replacing the `_learned_pattern_bonus` calls there. RAG-off mode is byte-identical (no patterns/site_hash → no-op).
- `_learned_pattern_bonus` still exists (used by `RAGRetriever.pattern_usage` + existing tests). **Note:** the Deliverable-2 usage trace still reports POSITIVE-only bonuses — negatives show as `source="learned_negative"` with `bonus:0` in the trace. Slice 2 may reconcile if desired.

### Design decisions recorded (carry forward)
- **Same locator in both stores** → majority by hit_count; tie → more recent wins; ambiguity biases negative; recovery is automatic (later passing run re-adds positive hits).
- **Context scenarios** (back buttons, multi-vehicle "add driver"): negatives are per `(description, selector, site)`, so vehicle-1's button is never penalized for vehicle-2's failure. Systematic mis-scoping is a resolution-time concern → **BACKLOG AI-063** (candidate scoping via `section_scoper`/prior steps). Do NOT add context tokens to store keys (evidence fragmentation).
- "Description" = the placeholder/step intent label ("Add to cart"), the durable key across tests/runs — not the whole step.

## 4. What Slice 2 must do (the fresh session's task)

1. **Wire negative recording into the evidence sidecar sweep** — `src/rag_learn.learn_from_evidence_sidecars` currently processes ONLY passed-test sidecars (`test.status == "passed"`). Extend it (or add a sibling sweep) to scan FAILED-test sidecars and call `learn_negatives_from_evidence` on their steps (locator-class gate already excludes flakes). Keep the passed-only positive path unchanged.
2. **Harness A/B — negatives-on vs negatives-off on the mocks**, judged by the AI-059 metric-first gate:
   - Metrics already exist: `src/learning_metrics.py` `LearningImpactMetrics.mean_pass_depth / first_pass_green_rate / false_positive_rate` via `analyze_sidecars`.
   - Harness: `src/learning_impact.py` `ControlledBaselineRunner` + legs; `rebuild_warm_store_from_evidence` currently tags ONLY positives with the lab sentinel (`AI059_LAB_SITE_HASH` / `lab_site_identity`) — Slice 2 needs a **negative-aware warm-store rebuild** (learned_negative entries tagged with the sentinel, hit_count/last_seen intact) and the measurement legs (warm-positives vs warm+negatives).
   - The judge: does `warm+negatives > warm` on `mean_pass_depth`? That is the feature's acceptance metric (BACKLOG AI-058).
3. Only if the A/B shows a need: description-keyed swap at scoring (BACKLOG AI-058 Slice 3).

## 5. Verification gates (all must pass before any commit)

- `python scripts/smoke.py --json` (39 checks)
- `python -m ruff check .` + `python -m ruff format --check .`
- `python -m mypy src/ cli/` — AND the pre-commit mypy checks `tests/` too: **any `VectorStoreBackend` fake must implement every protocol member** (`find_negative`, `query_dedup_keys`…) — the 3 fakes in `tests/test_learning_impact.py`, `tests/test_rag_retriever.py`, `tests/test_rag_store.py` were already updated for Slice 1.
- `python -m pytest tests/ -q` (currently **2886 passed**)
- `python scripts/eval/eval_harness.py run --mode static --min-accuracy 79` (baseline **97.9%**)
- `python scripts/maintenance/kanban.py` whenever `BACKLOG.md` changes (pre-commit `kanban-freshness` gate aborts the commit otherwise).

## 6. Gotchas (learned the hard way this session)

- **Pre-commit `ruff format` modifies files → commit aborts** ("files were modified by this hook"). Re-`git add` the files and commit again.
- Pre-commit hooks are the full gate: ruff, format, mypy (incl. tests), eval-accuracy (97.9%), kanban-freshness. Each failure `git commit` exits 1 with the failing hook in the log.
- `classify_failure` regexes are literal: the timeout path needs `timeouterror` (case-insensitive) AND `waiting for`; "locator not found" is regex'd separately. Test fixture errors must match realistically (e.g. `"TimeoutError: Timeout 5000ms exceeded.\nwaiting for locator('…')"`).
- Dedup invariant is **one row per `(action, description, site_hash)` per polarity** — the same physical selector in both stores is the "conflict" case the recency rule handles.
- The `AITEST_RAG_SCOPE` (AI-061) and `AITEST_STORAGE_ROOT` env vars control scope/static store — mocks run on `localhost:8785` (ecommerce) / `8786` (banking) locally, `:8781` inside the eval harness.

## 7. Commit trail (this session, all pushed to main)

```
281e1bb docs(backlog): header updated for 2026-08-28 ships; regen kanban
f518df3 docs(backlog): AI-058 Slice 1 shipped; regen kanban
9aa8bbc feat(ai-058): contrastive learned store slice 1 (learned_negative + net scoring)
01b43d1 docs(backlog): AI-062 resolved — fastpath shipped, magnitude rejected; kanban
d15d66c fix(ai-062): apply RAG golden/learned bonus on the haystack fast path
a100171 docs(backlog): AI-062 measured — decisive-rate ~0% (saucedemo)
713cfef docs(backlog): AI-062 effect-trace item; kanban
2e0f936 feat(ai-059): RAG effect trace — decisive counterfactual diagnostic
b90713a docs(backlog): AI-061 Complete; kanban
c0b8820 feat(ai-061): opt-in production project-scoped RAG identity
6c8f0d3 docs(backlog): AI-059 D1–2 Complete; kanban
c2af997 feat(ai-059): RAG resolver usage trace (eligible/matched/bonus)
```

## 8. Companion

- `docs/sessions/AI-058_Slice2_opening_prompt.md` — paste-ready opening message for the fresh context.
- Previous pause's handoff: `docs/sessions/AI-059_Deliverable2_opening_prompt.md` (24-08-27) — Deliverable 2 is DONE; only consult for the usage-trace shape.
- BACKLOG items: **AI-058** (slices + METRIC-FIRST gate), **AI-062** (done), **AI-061** (done), **AI-063** (context scoping — build only if Slice 2's A/B shows systematic mis-scoping).

---

*Leave this file + the opening prompt untracked (they belong to the fresh context, not a commit).*