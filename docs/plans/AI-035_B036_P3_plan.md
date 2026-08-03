# Session Plan: AI-035 + B-036 Phase 3 — Self-Learning RAG

**Created:** 2026-08-03
**Status:** Plan (multi-session, see Decision Log)
**Backlog refs:** `AI-035` (Self-Learning RAG), `B-036 Phase 3` (Evidence auto-learn)
**Specs:** `docs/specs/FEATURE_SPEC_AI035_self_learning_rag.md`, `docs/specs/FEATURE_SPEC_B036_consumer_config.md` §5/§8-Phase-3

---

## 1. Goal

Make RAG a **learning system**: when a resolution is verified (a test step
passes against the live site), the `(action, description, locator, site)`
pair is written back to the local RAG store as a *learned pattern*. The next
generation for the same site retrieves it and resolves faster/more accurately
— with zero config, zero manual ingestion, local-only (B-036's consumer story).

```
generate → execute → step passes → learn_from_evidence(step)
    → upsert_pattern(LearnedPattern, dedup by action+description+site_hash)
    → next generation retrieves same-site learned pattern → +5 bonus
    → accuracy improves with use
```

**What ships with this effort:**
- AI-035 Phase 1 **core** (`rag_learn.py`, `RAGStore.upsert_pattern`, dedup) — the shared machinery
- B-036 Phase 3 trigger (`learn_from_evidence()` + teardown hook) — the consumer-facing write path
- AI-035 Phase 2 (scoped retrieval: same-site preference, +5 bonus)
- AI-035 Phase 3 CLI (`--stats` / `--prune-learned`): **already shipped** in B-036 Phase 2 — nothing to do

**Deferred (decision log):**
- AI-035 self-healing patch wiring (`_learn_from_patch` in `SelfHealingRunner.heal()`) — follow-up micro-session
- Streamlit "Learned Patterns" settings section — fold into B-036 Phase 4 (sidebar settings rework)

---

## 2. Decision Log (2026-08-03)

These were pinned before implementation so a later session can pick this up
without re-deriving them.

| # | Decision | Choice | Rationale |
|---|----------|--------|-----------|
| D1 | Write-path trigger scope | **Evidence first** (`learn_from_evidence`); self-healing patch wiring deferred | Evidence is the consumer-facing path (B-036 acceptance); self-healing needs fiddly patch→(description, locator) extraction. Machinery 90% shared. |
| D2 | Dedup semantics | One row per `(action_type, description, site_hash)`; on repeat **skip insert, increment `hit_count`**; `created_at` = first-seen, immutable | Store has no natural key (Milvus auto-id) → without dedup every consumer run re-learns the same facts: unbounded growth, duplicates flooding top-k retrieval. |
| D3 | Site scoping | Learned patterns tagged `site_hash = sha256(domain)`; **same-site learned → +5**, **cross-site learned → +0** (never boost — could be actively wrong) | Main anti-poisoning guard. A saucedemo-learned `username → #user-name` must not win ties on a foreign site. |
| D4 | Golden patterns | **Stay unscoped** (+20 applies on any site, unchanged) | Scoping them = regression: on a new consumer site (not in the 6-site pack) scoped goldens would earn 0 bonus → accuracy drops vs today. Unscoped = zero behavior change, eval-static 95.2% baseline preserved. |
| D5 | Streamlit learned-patterns UI | **Defer** to B-036 Phase 4 | No immediate consumer value vs. cost; CLI `--stats`/`--prune-learned` covers power users. |

**Spike (must land before implementation):** verify Milvus-lite supports a
multi-field AND metadata query (`entry_type == 'learned' AND action_type ==
'FILL' AND description == 'username' AND site_hash == 'abc'`). We know
single-field dynamic queries work (`counts_by_type`). If ANDed dynamic-field
filters fail: fallback = query all rows for that site_hash, filter in Python
(fine at our scale, revisit if store grows).

---

## 3. Data Model

### 3.1 `LearnedPattern` (src/rag_store.py — new dataclass)

```python
@dataclass(slots=True)
class LearnedPattern:
    action_type: str  # CLICK | FILL | ASSERT | GOTO | SELECT
    description: str  # placeholder description / evidence step label
    locator: str  # verified locator from the passing step
    site_hash: str  # sha256(domain) — one-way, no URL stored
    confidence: float  # 0.9 (evidence-verified; self-healing would be 1.0)
    source: str  # "evidence" (AI-035 uses "self_healing")
```

### 3.2 Store metadata (Milvus dynamic fields)

Same shape as golden patterns so the read path is uniform:
- `text` = `"ACTION: description"` (matches `GoldenPattern.query_text` → vector retrieval works identically)
- metadata: `entry_type="learned"`, `action_type`, `description`, `selector`, `site_hash`, `confidence`, `source`, `hit_count` (int), `created_at` (float)

### 3.3 Read path

`RAGRetriever.retrieve(description, action_type, site_hash=None)`:
- `RetrievedPattern` gains `site_hash: str = ""` (golden patterns keep `""` — they're not scoped)
- Learned patterns carry their stored `site_hash` through to the scorer
- No store-query change needed (vector similarity already returns both sources) — scoping is a **post-filter + bonus** decision, not a hard filter (cross-site patterns are returned but unbounded)

`PlaceholderScorer`: new `SAME_SITE_LEARNED_BONUS: int = 5` alongside
`GOLDEN_PATTERN_BONUS = 20`. Applied when `pattern.source == "learned"` and
`pattern.site_hash` matches the current site's hash. Golden patterns: unchanged.

---

## 4. Implementation Order (suggested session split)

### Session A — Core machinery (≈ 0.5 session)
1. **Spike**: milvus multi-field metadata query for dedup (see §2). ~15 min.
2. `src/rag_store.py`: `LearnedPattern` dataclass + `RAGStore.upsert_pattern(LearnedPattern)` — dedup query → skip-or-hit_count; returns `("inserted" | "exists", hit_count)`. Tests: in-memory backend + real-Milvus (`TestMilvusLiteBackend` pattern).
3. `src/rag_learn.py` (new): `site_hash(domain) -> str`, `learn_from_evidence(steps, base_url) -> int` — batch-converts passed evidence steps (type/label/locator/url/status) into dedup'd LearnedPatterns; skips steps with no locator (navigate/URL asserts). Tests: 5-8.

### Session B — Write path hook + scoped retrieval (≈ 0.5 session)
4. `generated_tests/conftest.py`: teardown — after `tracker.write(status)`, when `status == "passed"`: `learn_from_evidence(tracker.steps, base_url=...)` wrapped in try/except (learning must never break a run). Batch = one call per test file run. Test: unit-test the hook function with a fake tracker.
5. `src/rag_retriever.py`: `retrieve(..., site_hash=None)`; `RetrievedPattern.site_hash`; pass-through in `RAGRetriever`.
6. `src/placeholder_orchestrator.py`: thread current-site hash (from `current_url`) into retrieval; `src/placeholder_scorers.py`: +5 same-site learned bonus. Tests: 4-6 (retriever scoping, scorer bonus, cross-site → 0).

### Session C — Measurement + hardening (≈ 0.5 session)
7. **eval-006 mock loop** (acceptance): generate eval-006 → execute (mock server, currently 8/8) → learn from evidence → `--prune-learned`/fresh store → regenerate → compare static resolution vs. 12/16 baseline. Expect lift on the 4 static misses.
8. **Poisoning check** (B-036 §10): confirm a passing-but-wrong locator does NOT get boosted cross-site (+0) and same-site poisoning is bounded by confidence 0.9 + prune reset.
9. Full chain: smoke → ruff → mypy → pytest → eval static → pre-commit hooks.

---

## 5. Target Files

| File | Action |
|------|--------|
| `src/rag_store.py` | Modify — `LearnedPattern`, `upsert_pattern()` |
| `src/rag_learn.py` | **New** — `site_hash()`, `learn_from_evidence()` |
| `src/rag_retriever.py` | Modify — `site_hash` param/field |
| `src/placeholder_scorers.py` | Modify — `SAME_SITE_LEARNED_BONUS = 5` |
| `src/placeholder_orchestrator.py` | Modify — thread site hash into retrieval |
| `generated_tests/conftest.py` | Modify — teardown learn hook |
| `tests/test_rag_learn.py` | **New** — site_hash, learn_from_evidence, dedup |
| `tests/test_rag_store.py` / `test_rag_retriever.py` / scorer tests | Modify — +10-15 tests total |
| `scripts/rag_ingest.py` | No change (`--stats`/`--prune-learned` shipped) |

---

## 6. Measurement & Acceptance (B-036 §8 Phase 3)

> Run a suite against the e-commerce mock twice — second run's resolution for
> previously-failed placeholders improves (measured via eval-006 static).

Procedure:
1. `eval_harness.py run --regenerate --mode full` against eval-006 (mock server + LM Studio) → baseline static 12/16
2. Execute the generated tests (mock) → 8/8 pass → evidence written → teardown learns patterns
3. `rag_ingest.py --stats` → `learned` count > 0
4. Re-generate eval-006 → compare static accuracy (expect > 12/16)
5. Cross-site check: learned saucedemo patterns must NOT boost on the mock (`--stats` shows per-site; resolution on mock unchanged by foreign patterns)

**Requires:** mock server (`scripts/mock_server.py`), LM Studio on :8080.

### Measurement finding (2026-08-03, Session C)

**Learning loop verified live end-to-end:** eval-006 mock execute → 8/8 pass →
teardown learned 3 dedup'd, site-scoped patterns (`Add to cart`, `product added
confirmation`, `Cart link` — all hashed to the mock domain) with `hit_count`
incrementing on repeat runs. Eval static stayed 95.2% with those patterns in
the store.

**Expected eval-006 lift ≈ 0, and that's by design:** every eval-006 golden key
is already in the bundled pack (auto-seeded), so golden +20 wins every
resolution the learned patterns could help; the 4 static misses are
*skeleton-level* LLM nondeterminism (ASSERTs emitted as URL checks, one
LLM-picked card field) that never reaches resolution. Learned patterns only
produce a measurable lift on **golden-uncovered sites** — the actual consumer
case. Measuring that needs a scenario outside the eval dataset; the mock-loop
acceptance above is a mechanism check, not a lift number.

**Caveat for anyone running the procedure:** reading the store from the same
process that runs pytest gives stale Milvus row counts (client caches) and can
hold a file lock that makes the subprocess's learning fail silently — do the
read in a separate process from the run.

---

## 7. Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| **Learned-pattern poisoning** (passing test with wrong-but-working locator writes a bad pattern — the B-037 `card number → #card-name` class) | Confidence 0.9, same-site +5/cross-site +0 scoping, `--prune-learned` reset, deterministic mock to *measure* poisoning before shipping |
| Evidence step `label` ≠ exact placeholder description (e.g. "Login" vs "login button") | Vector similarity tolerates phrasing differences; learned entries are their own rows, not golden replacements |
| Milvus dedup query unsupported | Spike first; Python-filter fallback (fine at our scale) |
| Learning overhead in teardown | One batched call per test file; try/except guard; embedder already loaded |
| `--regenerate` measurement nondeterminism (LLM skeletons) | Use the mock (B-037 lesson: isolate LLM variance from site variance); measure delta, not absolute |

---

## 8. Done Definition (per session)

- All code fully typed (AGENTS.md §5)
- `scripts/smoke.py` → `ruff check .` + `ruff format --check .` → `mypy src/ cli/` → `pytest tests/` (default suite, offline, hermetic — conftest `RAG_ENABLED=0`)
- Eval static ≥ 95.2% (no regression on shipped baseline)
- New unit tests: 10-15 (dedup, site_hash, learn_from_evidence, scoping bonus, conftest hook)
- Measurement loop (Session C) shows a measurable delta on eval-006
- Pre-commit hooks green before commit (mypy covers tests — the 2026-08-03 lesson)

### Progress (2026-08-03)

- ✅ **Session A — core machinery**: spike (Milvus multi-field AND filter
  confirmed), `LearnedPattern` + `RAGStore.upsert_pattern()` (dedup on
  action+description+site_hash, hit_count bump), `src/rag_learn.py`
  (`site_hash`, `domain_from_url`, `learn_from_evidence`). 23 new unit tests.
- ✅ **Session B — write hook + scoped retrieval**: teardown learn hook in
  `generated_tests/conftest.py` (best-effort, guarded); `RetrievedPattern.site_hash`;
  `PlaceholderScorer.SAME_SITE_LEARNED_BONUS = 5` (same-site learned only,
  cross-site = 0); `site_hash` threaded orchestrator → matcher → resolver →
  scorer. 14 new tests. Live: learning loop verified against the e-commerce mock.
- ⏭ **Session C — lift measurement**: mechanism verified; eval-006 lift ≈ 0 by
  design (golden pack already covers the mock — see §6 finding). Remaining
  golden-uncovered-site measurement is out of scope.

---

## 9. Follow-ups (explicitly out of scope)

- **Self-healing write path** (`_learn_from_patch` in `SelfHealingRunner.heal()`): AI-035's original trigger — `source="self_healing"`, `confidence=1.0`. Needs patch→(description, locator) extraction; ~0.25 session once evidence path is stable.
- **Streamlit learned-patterns section**: fold into B-036 Phase 4.
- **Federated sharing (AI-036)**: opt-in, separate feature, explicitly not this work.
- **`created_at` vs last-seen**: hit_count increments only; if "last seen" reporting is ever wanted, add a `last_seen_at` field at that point.
