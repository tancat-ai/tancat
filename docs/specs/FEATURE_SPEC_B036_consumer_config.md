# FEATURE_SPEC_B036 — Consumer Config Architecture

**Created:** 2026-08-03
**Status:** Spec
**Backlog ref:** `## 🔴 Open Bugs` → B-036
**Depends on:** AI-035 (Self-Learning RAG — spec, not yet implemented), Phase 3 RAG (shipped), secure_config (shipped), mock-site catalog + eval-006 (shipped 2026-08-03)

---

## 1. What This Is

The product is a **consumer tool** (Streamlit UI + CLI). Feature toggles must not
require `.env` edits — that is a developer workflow, and it silently disables
capabilities for the exact audience the product is built for. Four changes make
the configuration surface consumer-grade:

| # | Change | Today | After |
|---|--------|-------|-------|
| 1 | RAG | Off unless `RAG_ENABLED=1` | **Always-on** with graceful degradation (empty store ⇒ no bonus ⇒ identical behavior) |
| 2 | Golden patterns | Manual `rag_ingest.py --golden --docs` | **Bundled + auto-seeded** on first run |
| 3 | Learning | AI-035 spec (self-healing write-back) | Auto-learn from **successful evidence resolutions** too |
| 4 | Settings | `.env` vars + `st.session_state` (lost on restart) | **Persisted config store** (secure_config pattern) + UI fields |

The end state: a consumer installs the tool, runs a story, and the resolver
improves with use — no environment variables, no manual ingestion, no config
files to discover.

---

## 2. Current State (verified 2026-08-03)

### 2.1 Env-var gates and where they're read

| Env var | Read in | User-facing? | Verdict |
|---------|---------|--------------|---------|
| `RAG_ENABLED` | `src/orchestrator.py:_build_rag_retriever()` (gates retriever construction; missing ⇒ `None`) | ❌ | **Remove** — flip to always-on (Change 1) |
| `LANGGRAPH_ENABLED` | `src/agents/__init__.py`, `eval_runner` pipeline detection | ❌ (graph is dormant — not wired into the user-facing path) | **Remove** — dead flag |
| `OCR_BACKEND` | `src/ocr_backends.py:get_ocr_backend()` | ❌ (document-mode agents only) | Move to a persisted setting (document mode), default `pymupdf` |
| `JIRA_PROJECT_KEY` | `src/config.py` → `cli/report_generator.py` (test-case ID prefix) | ❌ | **Export-time UI field** (Change 4) |
| `PIPELINE_DEBUG` | `journey_scraper`, `llm_client`, `orchestrator` | dev-only | **Keep** (developer tool) |

### 2.2 What already exists (reuse, don't rebuild)

- **Graceful degradation is already implemented**: `_build_rag_retriever()`
  wraps RAG init in try/except and returns `None` on failure (logs a warning).
  Always-on is a **default flip**, not new machinery.
- **`secure_config.py`**: Fernet-encrypted store at `~/.ai-test-gen/config.enc`
  with `save_key/load_key/delete_key/list_stored_providers` — the persistence
  pattern for Change 4.
- **AI-035 (`FEATURE_SPEC_AI035_self_learning_rag.md`)**: defines the learned
  pattern write-back — `LearnedPattern(action_type, description, locator,
  site_hash, confidence, source, created_at, hit_count)`, `upsert_pattern()`
  with dedup on `(action_type, description_hash, site_hash)`, local-only
  storage in the RAG store, and a read path that needs **no changes**
  (`_golden_pattern_bonus()` already applies to any retrieved pattern).
  Status: **spec only** — Phase 1 (write-back) is not yet implemented.
- **Golden pattern sources**: `scripts/eval/dataset/*.json` (eval-001..006)
  plus the mock-site golden keys — bundled, versioned, **never decay**.

### 2.3 Design note: where learned patterns live

AI-035 already decides the store: the **RAG store** (Milvus Lite + metadata
filtering), not a new SQLite table. A separate `learned_patterns` SQLite table
was floated during the 2026-08-03 review but is **superseded by AI-035** — one
store, one dedup key, one read path. This spec follows AI-035; do not add a
parallel table.

---

## 3. Change 1 — Always-on RAG with graceful degradation

**Goal:** consumers get RAG resolution boosts by default; nothing to configure;
failure is invisible (identical behavior to today, not a crash).

**Implementation:**
- `src/orchestrator.py:_build_rag_retriever()`: treat missing `RAG_ENABLED` as
  enabled. Keep the existing try/except → `None` path. Accept `RAG_ENABLED=0`
  as a documented opt-out during a transition window (see §7), then remove the
  env read entirely.
- **First-run model download**: the embedder (`SentenceTransformerEmbedder`,
  all-MiniLM-L6-v2, ~80 MB) downloads on first use. Degradation already covers
  "download failed ⇒ no RAG, no bonus". Spec behavior: attempt quietly in the
  background on first run; never block generation on the download.
- **Lazy build**: construct the retriever only when a resolution actually
  needs it (already the case — `_build_rag_retriever` runs at orchestrator
  init; keep, but make the embedder lazy so `--help`/offline paths don't touch
  the network).

**Acceptance:** with `RAG_ENABLED` unset, eval static resolution is unchanged
(store empty ⇒ zero bonus); with a seeded store, the +bonus applies.

---

## 4. Change 2 — Bundled golden patterns, auto-seeded

**Goal:** no manual `rag_ingest.py`. A consumer's first run seeds the store
from patterns that ship with the product.

**What ships (the "golden pack"):**
- All golden keys from `scripts/eval/dataset/eval-001..006` (incl. the
  e-commerce mock — mock keys never decay, unlike live-site keys).
- Curated Playwright docs chunks (already in the repo, `docs/rag_corpus/`).
- Versioned: a `patterns_version` marker so future releases can upgrade the
  bundled set without duplicating entries.

**Implementation:**
- Packaging: a `rag_ingest.py --bundled` mode (or a `src/rag_bundled.py` helper
  reading a small manifest) that seeds exactly the packed set.
- Auto-seed trigger: first successful generation run (or first app start) when
  the store is empty — a `seeded` marker in the store (or `evidence/` flag)
  prevents re-seeding. Idempotent: re-running is a no-op.
- The existing `--golden --docs --pdfs` CLI stays for power users; it gains
  `--bundled`, `--stats`, `--prune-learned` (from AI-035 §6).

**Acceptance:** fresh workspace → run a story → store contains the bundled
patterns with no user action; eval static sees the golden bonus.

---

## 5. Change 3 — Auto-learn from successful resolutions

**Goal:** the consumer's own successful runs teach the resolver, locally.

**Trigger (new, beyond AI-035):** after a generated test executes and a step
**passes** (evidence sidecar status `passed`), the resolved
`(action, description, locator, page_url)` pair is a *verified* resolution.
Feed it to the store as a learned pattern with `source: "evidence"`,
`confidence: 0.9` (verified by execution, slightly below self-healing's 1.0).

**Mechanism:** reuse AI-035 exactly:
- `RAGStore.upsert_pattern(LearnedPattern(...))` with dedup on
  `(action_type, description_hash, site_hash)` — `site_hash = sha256(domain)`
  (one-way, no URL stored).
- Retrieval: `RAGRetriever` prefers same-`site_hash` patterns (+5 bonus for
  same-site learned patterns, per AI-035 §3.2/Phase 2).
- Privacy: local-only, same guarantees as AI-035 §4. No network, no telemetry.
- The `learned_patterns` SQLite table from the review discussion is **not**
  built — AI-035's RAG-store design covers it (§2.3).

**Write path:**
```
EvidenceTracker / conftest teardown (status=passed)
    └─ learn_from_evidence(test_file, evidence_sidecar)
        └─ for each passed step with a resolved selector:
            └─ extract (action, description, locator), compute site_hash
            └─ RAGStore.upsert_pattern(...)  # dedup by description_hash+site_hash
```
Batched at teardown (one write per test, not per step) to keep overhead near zero.

**What is NOT learned:** story text, credentials, screenshots, full URLs —
mirror AI-035 §2's exclusions.

**Acceptance:** run a suite against the e-commerce mock twice — second run's
resolution for previously-failed placeholders improves (measured via eval-006
static, see §8).

---

## 6. Change 4 — Persisted settings + export-time fields

**Goal:** settings survive restarts; no env vars for user-facing features.

- **Settings store**: extend the `secure_config.py` pattern with a general
  `settings` namespace (encrypted file already exists at
  `~/.ai-test-gen/config.enc`; add `save_setting/load_setting` or a small
  `SettingsStore` alongside it). Migrate the sidebar state that users actually
  set: `pom_mode`, consent mode, provider/model selection, workspace.
- **`JIRA_PROJECT_KEY`** → an **export-time field** in the Streamlit export
  panel and CLI export menu (default "TEST"); feeds `report_generator` test-case
  IDs. Removed from `src/config.py` env read.
- **`OCR_BACKEND`** → a document-mode setting (default `pymupdf`), stored in
  the settings store; the env read in `get_ocr_backend()` becomes a fallback
  for the transition window only.
- **`LANGGRAPH_ENABLED`** → removed outright (dead flag — graph not in the
  user-facing path; eval's `--use-graph` keeps working without the env).

---

## 7. Removal matrix & backwards compatibility

| Env var | Removal | Back-compat |
|---------|---------|-------------|
| `RAG_ENABLED` | Remove read after transition | `RAG_ENABLED=0` honored as opt-out for one release, then ignored; never errors |
| `LANGGRAPH_ENABLED` | Remove immediately | `--use-graph` CLI flag is the supported path |
| `OCR_BACKEND` | Env read becomes fallback | Setting wins; env still honored if set |
| `JIRA_PROJECT_KEY` | Remove from `src/config.py` | Export UI field carries it; default `TEST` |
| `PIPELINE_DEBUG` | Keep | dev-only |

**Guardrail:** no behavior change when env vars are absent today becomes a
behavior change after removal — each removal is gated by the eval harness
(static + one full run) and the smoke test.

---

## 8. Implementation plan

### Phase 1 — Always-on RAG (0.5 sessions)
- Flip `_build_rag_retriever` default; lazy embedder; `RAG_ENABLED=0` opt-out
  note. Verify: unset env ⇒ eval static unchanged; seeded ⇒ bonus applies.

### Phase 2 — Bundled golden pack + auto-seed (0.5 sessions)
- `rag_ingest.py --bundled` + manifest of eval/mock keys + docs chunks;
  first-run auto-seed with idempotent marker. `--stats`/`--prune-learned` CLI
  (AI-035 §6 carry-over).

### Phase 3 — Evidence auto-learn (1 session; requires AI-035 Phase 1 first)
- Implement AI-035 Phase 1 (`rag_learn.py`, `upsert_pattern`, dedup) if not
  already landed; add `learn_from_evidence()` + conftest/teardown hook;
  batch write. +10-15 unit tests.

### Phase 4 — Settings store + field migration (1 session)
- `SettingsStore` on the secure_config pattern; migrate pom_mode/consent/
  provider/workspace; JIRA key → export UI; OCR backend setting; remove
  `LANGGRAPH_ENABLED`. +10 unit tests.

**Total: 3 sessions** (+1 session if AI-035 Phase 1 hasn't landed).

---

## 9. Measurement

- **Always-on**: eval static with `RAG_ENABLED` unset must equal the current
  baseline exactly (no surprise bonus, no regression). CI eval-static gate stays.
- **Bundled pack**: fresh-workspace run seeds ≥N patterns; `rag_ingest --stats`
  shows the counts; re-run is idempotent.
- **Auto-learn**: mock-based loop — run eval-006 generation, execute, learn,
  regenerate → resolution delta on previously-missed placeholders. Expect the
  deterministic mock to make the lift measurable (the B-037 lesson: isolate LLM
  variance from site variance).
- **Settings**: restart the app → sidebar choices persist; export produces the
  configured JIRA prefix.

---

## 10. Risks

- **Embedder first-run download** (~80 MB) could be seen as "why is my machine
  doing network on first run" — mitigate: background/quiet, documented in
  quickstart, degradation path means generation never blocks on it.
- **Learned-pattern poisoning**: a passing test with a *wrong-but-working*
  locator (the B-037 `card number → #card-name` class) writes a bad pattern.
  Mitigation: confidence 0.9 (below self-healing's 1.0), same-site scoping,
  `--prune-learned` reset, and the mock gives us a deterministic testbed to
  measure poisoning risk before shipping.
- **Store growth**: dedup on description_hash+site_hash bounds rows; per-site
  caps if needed (out of scope initially).

---

*Last updated: 2026-08-03*
