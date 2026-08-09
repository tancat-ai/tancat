# Handoff: Ecommerce Skeleton Regen + Resolve (2026-08-09)

## What was running

`/tmp/ecom_regen.py` launched 2026-08-09 ~10:05 (local), background PID 4329,
log at `/tmp/ecom_regen.log`. Estimated 2-2.5h.

Scope: **only the 5 `ecommerce_mock` stories** from
`training_data/synthetic_stories.jsonl`. It calls `resolve_and_learn` with
`rag_modes=[True, False]` (RAG on + cold-start, 2x resolution data).

## Why this run exists

The pre-fix skeleton prompt taught the LLM to invent login steps
(`{{FILL:username:admin}}` in the EXAMPLE OUTPUT). 55 hallucinated-login rows
were dropped from the training datasets by `build_finetune_dataset.py --clean`.
The 5 ecommerce stories were the most affected (28 resolved rows dropped).
This run regenerates their skeletons with the **fixed prompt** (`b4d6709` —
removed login teacher, added DO NOT INVENT AUTH), resolves against the mock
(port :8781, ecommerce dir), executes, and learns passing steps into RAG.

## What to check when it finishes

**DONE 2026-08-09 ~12:14 local.** Results:
- 7 new resolved rows appended (89 -> 96), ecommerce now 24 rows total, **0 hallucinated login**
- 6 passed / 4 failed (failures were legit edge cases: empty-cart checkout-link check, products-page nav)
- New rows are clean guest flows (`.add-to-cart.btn[data-product-id="1"]`, real product text, 0-2 skips)
- RAG store unchanged (83/27/5) — the known B-047 lock: parent held Milvus, subprocess learn hooks blocked

1. **Log tail** — `tail -40 /tmp/ecom_regen.log` — look for:
   - `Resolved-code fine-tuning rows: N added` (should be ~10-25, appended not
     overwritten — the append-dedupe fix is in place)
   - `TOTAL: N passed, N failed`
   - `ecommerce_mock: N passed, N failed`
2. **No login in new rows**:
   ```bash
   python -c "
   import json
   rows = [json.loads(l) for l in open('training_data/playwright_resolved_alpaca.jsonl', encoding='utf-8')]
   ecom = [r for r in rows if \"ecommerce_mock\" in r['instruction']]
   bad = [r for r in ecom if 'standard_user' in r['output'] or 'secret_sauce' in r['output']]
   print(f'ecom rows: {len(ecom)}, with hallucinated login: {len(bad)}')
   "
   ```
3. **RAG store grew** (learning from passing tests):
   ```bash
   .venv/Scripts/python -c "
   from src.storage import get_storage
   from src.rag_store import RAGStore, MilvusLiteBackend, SentenceTransformerEmbedder
   emb = SentenceTransformerEmbedder()
   backend = MilvusLiteBackend(str(get_storage().rag_path()), emb.dimension)
   store = RAGStore(backend, emb)
   print(store.counts_by_type())
   "
   ```
   (Note: this can only be read AFTER the run finishes — the parent holds the
   Milvus lock while running, per B-047 lock analysis. Before: 83 golden / 27
   doc / 5 learned.)

## Dataset state (before this run, after --clean)

| File | Rows |
|---|---|
| `playwright_skeleton_alpaca.jsonl` | 158 |
| `playwright_resolved_alpaca.jsonl` | 89 |
| `playwright_resolution_alpaca.jsonl` | 90 |
| `synthetic_skeletons_alpaca.jsonl` | 58 |
| `synthetic_stories.jsonl` | 35 |

## Commits in this session (all pushed, CI green on b4d6709)

- `cc2753f` — login keyword resolves to real /login page; auth-guard story synth
- `bbc0a08` — --clean filter (55 hallucinated-login rows dropped)
- `b4d6709` — skeleton prompt: remove login teacher, add DO NOT INVENT AUTH

## After the regen: next steps

1. Verify per above, then run `git add training_data/` + commit the new rows.
2. Optionally regen the other login-less sites (lv_insurance, demoqa) the same
   way if balance is wanted — same script pattern, swap the site filter.
3. Then the corpus is clean + balanced for the Unsloth training run.
