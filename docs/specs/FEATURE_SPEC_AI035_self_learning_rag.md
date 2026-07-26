# AI-035 — Self-Learning RAG (Local Pattern Write-Back)

**Created:** 2026-07-26
**Status:** Spec
**Depends on:** Phase 2b Self-Healing (shipped), Phase 3 RAG (shipped)

---

## 1. What This Is

RAG becomes a **learning system** instead of a static knowledge base. When the self-healing loop fixes a broken locator, the corrected `(description, locator)` pair is written back to the RAG store. On the next generation for the same site, the learned pattern boosts resolver accuracy automatically.

```
User generates tests → runs them → fails → self-healing fixes locator
    → (description, corrected_locator) upserted to local RAG store
    → tagged with site domain hash
    → next generation retrieves the learned pattern
    → accuracy improves with usage
```

---

## 2. What Gets Learned

Only **resolver feedback** — the specific locator replacements that self-healing verified as correct:

| Field | Source | Example |
|---|---|---|
| `action_type` | Placeholder action | `CLICK`, `FILL`, `ASSERT` |
| `description` | Placeholder description | `"Add to cart button"` |
| `locator` | Corrected locator from self-healing | `#add-to-cart` |
| `site_hash` | SHA-256 of base URL domain | `a1b2c3...` (not reversible) |
| `confidence` | `1.0` (verified by self-healing) | Self-healing only writes confirmed fixes |
| `source` | `"self_healing"` | Distinguishes from manual golden patterns |

**What is NOT learned:**
- User story text
- Test code
- Credentials
- Screenshots
- Page content
- Full URLs (only domain hash)

---

## 3. Architecture

### 3.1 Write path (self-healing → RAG)

```
SelfHealingRunner.heal()
    └─ patch applied successfully (replace_locator strategy)
        └─ _learn_from_patch(patch, base_url)
            └─ extract: description from placeholder, corrected locator from patch
            └─ compute: site_hash = sha256(domain)
            └─ upsert: RAGStore.upsert_pattern(LearnedPattern(...))
```

`SelfHealingRunner` already has access to the test file, the error message, and the applied patch. It extracts the placeholder description from the original skeleton and the corrected locator from the patch.

### 3.2 Read path (RAG → resolver)

```
PlaceholderOrchestrator.resolve()
    └─ RAGRetriever.retrieve(description, action_type)
        └─ filters: prefers same-site patterns (site_hash match)
        └─ returns: golden patterns + learned patterns
    └─ PlaceholderScorer.compute_element_score()
        └─ _golden_pattern_bonus() — already applies to both sources
```

No changes needed to the read path — `_golden_pattern_bonus()` already works on any pattern retrieved from RAG. Learned patterns are just another source of `RetrievedPattern` objects.

### 3.3 Store schema extension

New collection/table in the RAG store alongside golden patterns:

```python
@dataclass
class LearnedPattern:
    action_type: str          # "CLICK" | "FILL" | "ASSERT"
    description: str          # placeholder description text
    locator: str              # corrected locator
    site_hash: str            # sha256(domain) for scoped retrieval
    confidence: float          # 1.0 for self-healing verified
    source: str               # "self_healing"
    created_at: float          # unix timestamp
    hit_count: int             # how many times this pattern was retrieved
```

### 3.4 Deduplication

Before upserting, check if a pattern with the same `(action_type, description_hash, site_hash)` already exists. If so, increment `hit_count` and update `created_at`. This prevents flooding the store with duplicate patterns.

---

## 4. Privacy Design

**All learning is local by default.** The RAG store lives at `evidence/rag_store.db` in the user's workspace — same as today. No data leaves the machine.

The store is:
- **On disk**: SQLite + Milvus Lite vector index in the user's workspace
- **In memory**: loaded at pipeline start, updated during self-healing
- **Never transmitted**: no network calls, no telemetry, no cloud sync

Users can delete their learned patterns at any time by rebuilding the store (`python scripts/rag_ingest.py --golden --docs`). The base golden patterns and Playwright docs are always restorable.

---

## 5. Future: Federated Pattern Sharing (AI-036)

As a separate, future feature, users who **opt in** can share anonymized learned patterns with the community. This is NOT part of AI-035.

**What could be shared (opt-in only):**

| Shared | NOT shared |
|---|---|
| `(action_type, description, locator, site_hash)` | URLs, stories, credentials, code |
| Description is sanitized — no PII detection | Screenshots, page content |
| Site hash is one-way — can't recover the URL | IP addresses, user identity |

**Safety properties:**
- Opt-in via explicit user action (checkbox in settings, CLI flag)
- Transparent preview: "You're about to share 12 anonymized locator patterns" before sending
- Review queue: community patterns are reviewed before inclusion in the base RAG store
- Can be disabled per-workspace or globally
- Users who NEVER opt in still get the full local learning benefit

This is modelled on VS Code's telemetry and Homebrew's analytics — opt-in, transparent, privacy-first. But it's future work. AI-035 ships local-only.

---

## 6. Implementation Plan

### Phase 1 — Core write-back (0.5 sessions)
- `src/rag_learn.py` — `learn_from_patch()`, `upsert_pattern()`, deduplication
- `src/rag_store.py` — add `upsert_pattern()` method to `RAGStore`
- Wire into `SelfHealingRunner.heal()`: call `learn_from_patch()` after each successful `replace_locator` patch
- 10+ unit tests

### Phase 2 — Scoped retrieval (0.5 sessions)
- `src/rag_retriever.py` — prefer same-`site_hash` patterns in retrieval results
- Boost: learned patterns from the same site get a +5 bonus over general patterns
- 5+ unit tests

### Phase 3 — Store management (0.25 sessions)
- CLI: `python scripts/rag_ingest.py --stats` — show learned pattern counts per site
- CLI: `python scripts/rag_ingest.py --prune-learned` — remove all learned patterns, keep golden/docs
- Streamlit: "Learned Patterns" section in settings showing counts

**Total: 1.25 sessions**

---

## 7. Measurement

Run the resolver eval BEFORE and AFTER self-healing on the same site:

1. Generate tests for a site without any learned patterns → measure baseline accuracy
2. Run tests, trigger self-healing fixes, let patterns write back
3. Clear the RAG cache, rebuild store with learned patterns
4. Re-generate tests for the same site → measure new accuracy

Expected: accuracy improves on the second run because the resolver retrieves the corrected locators from the previous self-healing session. Self-healing + RAG write-back = self-improving system.
