# `src/rag_learn.py`

## High-Level Purpose

The **self-learning RAG write path** (AI-035 core + B-036 Phase 3 trigger).
When a generated test step **passes** against the live site, the resolved
`(action, description, locator, site)` pair is verified — `learn_from_evidence`
converts passed evidence steps into `LearnedPattern` entries and writes them to
the RAG store, deduped on `(action_type, description, site_hash)`.

```
generated test step passes (evidence status=passed)
    └─ learn_from_evidence(steps)
        └─ _step_to_pattern(step)   # type/label/locator/url → LearnedPattern
        └─ RAGStore.upsert_pattern()  # dedup: repeat bumps hit_count, no new row
    → next generation for the same site retrieves it → +SAME_SITE_LEARNED_BONUS
```

**Privacy (AI-035 §4):** only the one-way `sha256(domain)` hash is stored —
never full URLs, story text, credentials, or screenshots. All learning is local.

## Module Metadata

- **Lines:** ~135
- **Imports:** `hashlib`, `logging`, `urllib.parse`, `src.rag_bundled`, `src.rag_store`
- **Specs:** `docs/specs/FEATURE_SPEC_AI035_self_learning_rag.md`, `docs/specs/FEATURE_SPEC_B036_consumer_config.md` §5/§8-Phase-3
- **Shipped:** 2026-08-03

## Functions

### `site_hash(domain: str) -> str`
One-way sha256 hex of a site domain (first 16 chars). Deterministic and
case-insensitive; the domain can never be recovered from the hash.

### `domain_from_url(url: str) -> str`
Host (no port, lowercase) from a URL, or `""` when absent/unparseable.
`https://www.saucedemo.com:8080/x.html` → `www.saucedemo.com`.

### `_step_to_pattern(step: dict[str, Any]) -> LearnedPattern | None`
Maps one evidence step to a `LearnedPattern`. Returns `None` (skipped) when the
step has no action mapping (`navigate`/unknown), no label or locator
(URL/state assertions), or no page URL (no site to scope to).

### `learn_from_evidence(steps: list[dict[str, Any]], *, store: RAGStore | None = None) -> dict[str, int]`
Batched write (one call per test file teardown). Only steps with
`result.status == "passed"` are learned (`partial_pass`/failed are skipped —
a fallback-used locator is less certain). Returns
`{"inserted": N, "exists": M}` where repeats count as hits (store bumps
`hit_count`). `store` is injectable for tests; defaults to the production store.

## Evidence Step → Pattern Mapping

| Evidence `type` | Action | Notes |
|-----------------|--------|-------|
| `fill` | `FILL` | locator required |
| `click` | `CLICK` | locator required |
| `assertion` | `ASSERT` | locator required |
| `select` | `SELECT` | locator required |
| `navigate` | — | skipped (no locator; URL step) |
| anything else | — | skipped (unknown) |

`label` → `description`, `locator` → `selector`, `url`'s domain → `site_hash`.
Confidence is `0.9` (verified by execution, below self-healing's `1.0`);
`source` is `"evidence"`.

## Depended On By

- `generated_tests/conftest.py` — teardown hook calls `learn_from_evidence`
  after a passing run (guarded: learning never breaks the run)
- `src/placeholder_orchestrator.py` — imports `site_hash`/`domain_from_url`
  to scope the learned-pattern bonus to the current site

## Notes

- AI-035's original write trigger (self-healing patches,
  `source="self_healing"`, `confidence=1.0`) is **not wired yet** — deferred
  follow-up; the shared machinery (`upsert_pattern`, dedup) is what this
  module and `RAGStore` provide.
- A failed learning call is swallowed by the conftest guard and retried on the
  next run (no marker/state to corrupt).
