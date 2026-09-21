# FEATURE SPEC — AI-068 Laya decision scorer for placeholder ranking

**Status:** Proposed (spike — prove value before integrating)
**Created:** 2026-09-21
**Item type:** Feature / experiment → roadmap item (`ROADMAP_ROADTO_PRODUCTION.md`)
**Priority:** Low–Medium — quality upside on the wrong-ASSERT class; no demo blocker
**Depends on:** `src/placeholder_scorers.py`, `src/rag_retriever.py`, `src/rag_store.py`,
`scripts/eval/eval_harness.py`, `scripts/verify_production.py`
**Related:** AI-066 (ColBERT late-interaction RAG spike), AI-058 / AI-064 / B-054 / B-055
(the open wrong-ASSERT class), B-047 residual (selector-drift on golden patterns)

---

## 0. Workspace rule (read first)

**This work is done in a separate branch and git worktree. Never on `main`.**

```bash
# from the main checkout
git worktree add ../tancat-ai068 -b experiment/ai068-laya-scorer main
cd ../tancat-ai068
uv sync && .venv/Scripts/activate && playwright install chromium
```

Why:

- It is a throwaway experiment. If the Phase 1 gate fails, the worktree is
  deleted and `main` never saw it.
- It will re-record measurement baselines (`eval_harness baseline`,
  `verify_production --save-baseline`). Those must not land on `main` by accident.
- `main` is currently dirty (modified `src/spec_analyzer.py`,
  `src/user_story_parser.py`, `streamlit_app.py`, tests; untracked
  `training_data/*.json`). A worktree keeps this spike off that in-progress work.

### Protected files — checked 2026-09-21

**This change does not need any protected file.** It lives in
`src/placeholder_scorers.py` (the bonus terms), `src/rag_retriever.py`, and a new
`src/laya_scorer.py` — none are on the protected list.

The ranking path was traced to confirm it:

```
placeholder_orchestrator.py -> rank_candidates() -> compute_element_score()
  callers: element_matcher.py, placeholder_resolver.py, journey_scraper.py
```

| Protected file | Needed? | Why not |
|----------------|---------|---------|
| `src/test_generator.py` | No | Imports no ranking module. |
| `src/llm_client.py` | No | Laya is a scorer, not an LLM call. |
| `src/llm_providers/` | No | Only if Laya became a selectable provider. It is not an LLM. Out of scope. |
| `src/agents/` | No | `ingestion.py` uses the RAG retriever for story-level pattern enrichment only, not the placeholder bonus. Out of scope. |
| `.github/workflows/ci.yml` | No | Tests mock Laya; no server needed in CI. |

If a later phase turns out to need one of these, **stop and record the decision
first** (AGENTS §3). Do not assume it.

Do not delete the worktree until the final decision (Phase 6) is recorded.

---

## 1. Problem statement

Our ranking has three layers:

| Layer | File | Signal |
|-------|------|--------|
| 1. In-code weights | `src/placeholder_scorers.py` | ~20 hand-tuned terms (`+20` product-ID, `+10` role, `-12` submit-verb, container/hidden/prose penalties). Structural `+80`, hidden `-40`. |
| 2. RAG bonus | `src/rag_retriever.py` → `src/rag_store.py` | Embed-search top-k, then the bonus is decided by **selector string equality** (`pattern.selector == element.selector` → `+20`; substring → half). No semantics. |
| 3. LLM ranker | `src/semantic_candidate_ranker.py` | Qwen, shortlist only. Slow, but the accurate tier. |

Layer 1's semantic part is token overlap
(`len(desc_words ∩ element_words)` in `SemanticMatcher`). Layer 2's memory
bonus is exact-string match. Both fail in the same way: **when the wording or
the selector changes, a previously-correct memory stops matching**, even
though the element is semantically the same. That is the RAG payoff we are
not collecting.

### Concrete failure mode

A golden/learned pattern was recorded for `#confirm-order`. The site is
re-deployed and the element is now `#place-order-btn` with text "Place order".
String match fails → bonus `0` → the resolver falls back to token overlap and
may pick a different element. Layer 3 (Qwen) sometimes rescues it, but it is
slow and it is the same call that produces the open wrong-ASSERT failures.

### Why Laya

Laya is an open-source (Apache-2.0), local "System One" decision model.
322M params, ~650 MB, ~21 ms/decision, 0 tokens. You send a state and typed
questions; it returns typed answers with probabilities. It is a
**classification/scoring model, not a generator and not an embedder**. That is
exactly the shape of the RAG bonus decision: "does this element match this
remembered description?" → `noul` (yes/no probability).

It is local and offline, so it fits the local-first rule
(`LLM_PROVIDER=openai-local`). No data leaves the machine.

> Vendor claims (200× faster, 21 ms) are **unverified**. Phase 0 measures them
> on our hardware. Laya's own site states it is **less accurate than JEV out of
> the box**, is **wording-sensitive**, and **cannot read numbers**.

---

## 2. Non-goals

- **Not** a replacement for Qwen. Layer 3 stays. Laya is a middle tier.
- **Not** a replacement for the RAG retriever/embedder. Laya ranks retrieved
  candidates; it does not rank vectors. Do not touch `rag_store.retrieve`.
- **Not** for anything numeric. `toHaveCount`, `expected_value`, hit counts,
  thresholds stay in code.
- **Not** JEV. Hosted + closed weights = data leaves the machine. Rejected.
- **Not** in `streamlit_app.py`. Testable helpers go in `src/` (AGENTS §2).
- **Not** the agent pipeline (`src/agents/`) — that is a **separate follow-on**, and it is
  **classification, not ranking**. The spots are `QADirectorAgent` priority /
  ambiguity / prerequisite refs (`src/agents/director.py` — its own docstring names
  the LLM-reasoning gap) and the change-delta categories in
  `src/agents/ingestion.py::_extract_change_deltas`. Out of scope here for two
  reasons: `src/agents/` is **protected**, and it needs its own fixture and gate
  (a text-classification bench, not the selector-drift bench). Its RAG use
  (`ingestion.py:77` → `domain_terms`) is term enrichment, **not** ranking — Laya
  does not help it. Revisit only if Phase 1 here proves Laya beats a heuristic;
  do not start it before then. Track as a separate item.

---

## 3. Target insertion point

**Phase 2 scope — the RAG bonus only.**

Today:

```python
# src/placeholder_scorers.py
_golden_pattern_bonus(element, golden_patterns, site_hash) -> int   # string match
```

Proposed (flag-gated):

```python
# new: src/laya_scorer.py  — typed, testable, no Streamlit
def score_pattern_match(description: str, element: dict[str, Any]) -> float | None:
    """Return P(element satisfies description) in [0,1], or None if Laya unavailable."""
```

Wire it so that when the string match returns `0` **and** the env flag is set,
Laya is asked, and its probability maps to a **bounded** bonus:

```
bonus = round(LAYA_BONUS_MAX * (p - LAYA_NEUTRAL) / (1 - LAYA_NEUTRAL))   # clamped to [0, LAYA_BONUS_MAX]
```

- `LAYA_BONUS_MAX` must stay below the structural tier. Use `20` (golden tier),
  never above `40` (the learned-negative cap).
- String match always wins when it hits. Laya only fills the gap.
- Flag name mirrors the AI-062 precedent: **`AI068_LAYA_BONUS`** (default off),
  so Phase 3 can A/B without a rebuild.

Phase 5 (optional, only if Phases 1–3 show real gain) widens this to the
token-overlap term in `PlaceholderScorer.score()`.

---

## 4. Phase plan — a gate between every phase

Each phase ends with a **Gate** (a number that decides continue/stop). **Do not
start the next phase until the gate is recorded in the session log.** If the
gate fails, stop and write the phase off — that is a valid result.

---

### Phase 0 — Does Laya run on our hardware? (no repo changes)

**Do**
1. Follow the Laya "run it locally" instructions. Install in the spike worktree
   venv (or a throwaway env). Confirm the actual interface (HTTP? Python?
   CLI?) — **this is unknown and must be discovered, not assumed**.
2. Write `scripts/debug/laya_probe.py`: send ~10 hard-coded
   `(description, element)` pairs, print P(yes) and wall-clock per call.
3. Measure latency on this machine (AMD Strix Halo / Radeon 8060S, no CUDA).

**Gate**
- [ ] Laya runs fully offline on this machine (CPU is acceptable, GPU preferred).
- [ ] Returns a numeric probability for a `noul` question, reliably, 10/10.
- [ ] Median latency measured and recorded.

**Stop if** it cannot run on Windows / AMD without CUDA, or the output cannot be
parsed into a probability. No integration. Archive the probe script.

**Decision (fill in):** `GO / STOP` — latency: `____ ms` — interface: `____`

---

### Phase 1 — Is Laya better than the string match? (offline, frozen fixture)

This is the **"is it worth it" gate**. Pure offline. No product code changes.

**Do**
1. Build a frozen fixture `tests/fixtures/laya_pattern_drift.jsonl`. Each row is
   a `(description, old_selector, new_element)` triple where the element is
   semantically the same but the selector changed — the drift case from §1.
   Source rows from the existing eval golden keys and the banking/ecommerce
   mocks. Aim for 30–50 rows. Hand-label the correct element.
2. Write `scripts/debug/laya_bench.py` that runs three scorers over the fixture:
   - **A** — current behavior (selector string match, `_golden_pattern_bonus`)
   - **B** — Laya `noul`
   - **C** — token overlap (`SemanticMatcher`), the current fallback
3. Report top-1 accuracy for A, B, C, and A+B combined.
4. Run the static eval as a frozen-regression read
   (`python scripts/eval/eval_harness.py run --mode static`) and record the number.

**Gate**
- [ ] Laya (B) beats the string match (A) on the drift fixture by a **pre-agreed
      margin** — proposed: **≥ +15 percentage points top-1** on ≥30 rows.
- [ ] Laya does not lose to the token-overlap fallback (C).
- [ ] A+B combined ≥ A alone (no regression on rows where A already hits).
- [ ] Wording sensitivity quantified: run 3 phrasings of the same question and
      record the spread. If the spread flips the winner, note it.

**Stop if** B does not beat A by the margin, or Laya is so wording-sensitive that
the answer flips per phrasing. Document the numbers and stop — no integration.

**Decision (fill in):** `GO / STOP` — A: `__%` B: `__%` C: `__%` A+B: `__%`

> Note: the golden-key set is nearly saturated at **97.9% (94/96)**, so it is a
> *regression guard*, not an upside measure. The upside lives in the drift
> fixture and in `verify_production`'s wrong-ASSERT class. This is why Phase 1
> builds its own fixture.

---

### Phase 2 — Integrate behind a flag (small, reversible)

**Do**
1. Add `src/laya_scorer.py` — typed, pure-helper module (AGENTS §9), with a
   hard timeout and a `None` return when Laya is down. Laya must **never**
   block generation (mirror the RAG `graceful degradation` contract).
2. Add `tests/test_laya_scorer.py` — mock Laya; cover: probability mapping,
   clamp to `[0, LAYA_BONUS_MAX]`, timeout → `None`, flag off → no call.
3. Wire into `_golden_pattern_bonus` (or its caller) **only when
   `AI068_LAYA_BONUS` is set**. String match still runs first and still wins.
4. Add a cache keyed by `hash(description, selector)` — resolve each pair once
   per run. Batch where the interface allows.
5. None of these files are protected (§0), so no protected-file decision is
   needed. If a protected file appears necessary, stop and record it first.

**Gate**
- [ ] `ruff check` clean, `mypy` clean, `pytest -q` green.
- [ ] Static eval **≥ 97.9%** with the flag on (no regression; record exact).
- [ ] Micro-bench from Phase 1 still positive with the real wiring.
- [ ] Flag off is byte-identical to current behavior (prove with a unit test).

**Stop if** the static eval drops below 97.9%, or the flag-off path is not
identical. Revert.

**Decision (fill in):** `GO / STOP` — eval static: `__%`

---

### Phase 3 — Production regression A/B

**Do**
1. Run the baseline twice, flag off then on:
   `python scripts/verify_production.py --baseline` (off)
   `AI068_LAYA_BONUS=1 python scripts/verify_production.py --baseline` (on)
2. Compare: new gate failures, new failing tests, unresolved-ASSERT count.
3. Inspect the wrong-ASSERT class specifically (AI-058 / AI-064 / B-054 / B-055).

**Gate**
- [ ] 0 new gate failures with the flag on.
- [ ] 0 new failing tests.
- [ ] Unresolved-ASSERT count ≤ the baseline ceiling (record both).
- [ ] Wall-clock added per run recorded (feeds Phase 4).

**Stop if** any new gate failure, any new failing test, or unresolved count rises.
Remove the flag; keep the module only if Phase 2 tests justify it.

**Decision (fill in):** `GO / STOP` — new failures: `__` unresolved: `__ → __`

---

### Phase 4 — Latency and cost control

**Do**
1. Batch all Laya questions for a resolution pass into as few requests as possible.
2. Enforce a per-run budget (question count cap) and keep the timeout.
3. Confirm the cache hits on repeated steps (the batch ranker already groups).
4. Measure: added wall-clock per `verify_production` run, and per eval story.

**Gate**
- [ ] Added wall-clock < **2 s** per full `verify_production` run.
- [ ] Accuracy from Phase 3 unchanged.
- [ ] Cache hit-rate recorded; no unbounded growth.

**Stop if** the latency budget is missed and batching + caching cannot fix it.

**Decision (fill in):** `GO / STOP` — added: `____ s` — cache hit: `__%`

---

### Phase 5 — OPTIONAL: widen to the token-overlap term

Only start if Phase 3 and Phase 4 both passed with a real gain.

**Do** — add a Laya term to the `len(desc_words ∩ element_words)` /
`_structural_bonus` part of `PlaceholderScorer.score()`. Keep the structural
weights (role, hidden, container). Bound the new term.

**Gate** — same as Phase 2 + Phase 3 (static eval ≥ 97.9%, zero new production
failures). Plus: prove the new term does not double-count with the Phase 2 RAG
term on the same element.

**Stop if** it regresses or double-counts. Phase 2's RAG-only win stands alone.

**Decision (fill in):** `GO / STOP`

---

### Phase 6 — Decide, then ship or archive

**If shipped:**
- [ ] Re-record `python scripts/eval/eval_harness.py baseline --save` (after a
      verified improvement — never before).
- [ ] Re-record `python scripts/verify_production.py --save-baseline` only if the
      known-red ASSERT class changed.
- [ ] Add `markdown_docs/src/laya_scorer.py.md` via the `document-manager` skill.
- [ ] Update `CHANGELOG.md` `[Unreleased]`.
- [ ] Update the **owner file only** (roadmap: AI-068; BACKLOG gets a one-line
      pointer). Verify shipped-ness against the code, not the doc.
- [ ] `python scripts/maintenance/kanban.py`.
- [ ] Run the ship-it skill from the spike branch (ruff → mypy → pytest → CI).

**If stopped:** record the failed gate and the numbers in AI-068's owner entry.
Keep `src/laya_scorer.py` only if it is covered by tests and unused-by-default;
otherwise delete it. Remove the worktree.

---

## 5. Test commands

```bash
# offline gates
.venv/Scripts/python.exe scripts/debug/laya_probe.py                 # Phase 0
.venv/Scripts/python.exe scripts/debug/laya_bench.py                 # Phase 1
.venv/Scripts/python.exe scripts/eval/eval_harness.py run --mode static   # Phases 1,2,5
.venv/Scripts/python.exe scripts/eval/eval_harness.py compare         # vs saved baseline

# unit
.venv/Scripts/python.exe -m pytest -q --tb=short tests/test_laya_scorer.py
.venv/Scripts/python.exe scripts/smoke.py
ruff check . && mypy src/ cli/

# production A/B (Phase 3)
.venv/Scripts/python.exe scripts/verify_production.py --baseline
AI068_LAYA_BONUS=1 .venv/Scripts/python.exe scripts/verify_production.py --baseline
```

Note: even `--mode static` pings the local LLM on `localhost:8080`. Start
llama-server before running the eval harness.

---

## 6. Metrics

| Metric | Current | Target | Gate type |
|--------|---------|--------|-----------|
| Eval static resolution accuracy | **97.9%** (94/96) | ≥ 97.9% (guard) | regression |
| Drift fixture top-1 (Phase 1) | n/a (string match baseline) | Laya ≥ +15 pp over string | value |
| `verify_production --baseline` new failures | 0 | 0 | regression |
| Unresolved-ASSERT count | at ceiling | ≤ ceiling | regression |
| Added wall-clock per production run | 0 | < 2 s | budget |
| Skeleton completeness | 79.0% | unchanged | regression |

---

## 7. Rollback

1. Set `AI068_LAYA_BONUS=0` (or unset) — instant revert, no rebuild.
2. If needed, revert the single commit that wired `src/laya_scorer.py` into
   `placeholder_scorers.py`. The module itself is inert without the flag.
3. Laya failing/absent at runtime must degrade to the current string-match path
   (returns `None`, bonus `0`) — never raise, never block generation.

---

## 8. Risks

| Risk | Mitigation |
|------|-----------|
| Laya has no Windows/AMD support | Phase 0 measures this first; CPU fallback accepted before any integration |
| Laya is too wording-sensitive for machine placeholder prose | Phase 1 quantifies the phrasing spread; stop if the winner flips |
| Near-saturated golden set hides a regression or a win | Phase 1 drift fixture + Phase 3 production A/B are the real measures |
| New bonus term breaks weight calibration (`+80` structural, `-40` hidden) | Bound the term at `20`, below the learned cap `40` |
| Per-candidate latency adds up | Phase 4 batching + cache + per-run cap |
| Touching protected files | Separate branch/worktree; record the decision before editing |
| Silently wrong bonus on a new site | Site-gate the bonus exactly as the golden/learned bonuses are (`site_hash`) |

---

## 9. Open questions

1. What is Laya's actual interface — HTTP server, Python package, CLI? Phase 0.
2. Does a Windows/AMD (no CUDA) build exist? Phase 0.
3. Can it answer several questions about one state in one request (JEV can)?
   If not, batching needs separate requests — affects Phase 4.
4. Is a `choice` question (pick from a candidate list) better than N `noul`
   questions? Test both in Phase 1.
5. Does the drift fixture already exist in the golden keys, or is it new? Phase 1.

---

## 10. Session tracking

| Date | Activity | Notes |
|------|----------|-------|
| 2026-09-21 | Spec created | Spike framed: RAG bonus first, drift fixture as the value gate, separate worktree mandatory. Eval static baseline measured at 97.9% (94/96) on this machine. |

---

*Last updated: 2026-09-21*
