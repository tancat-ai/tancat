# Session 2026-08-15 — Phase 7 7d: `learn: true` (flow-memory learning in CI)

The last Phase 7 tail: the action's opt-in `learn` input, which has failed
fast since 7b, is now implemented. Why (the user's rule): CI should behave
like the UI/CLI or have a documented reason not to — the fail-fast was that
sort of unexplained divergence. Learning ≠ self-healing (self-healing in CI
was deliberately rejected in 7a; learning was always a planned opt-in input,
just never wired).

The design was settled in the previous session's kickoff — **no re-grill**.
This session implemented it exactly as sketched.

## What shipped

1. **`action/entrypoint.sh`** — the fail-fast is gone. On a green
   generate-and-run with `learn: true`:
   - `RAG_ENABLED=0` is exported **before generation** — flow memory only in
     CI. The RAG leg (locator learning) needs an ~80 MB embedder download
     per runner; flow memory (navigation shape) needs no model download.
     Documented in `docs/ci.md` §8b.
   - `AITEST_STORAGE_ROOT` + `AITEST_WORKSPACE` are exported so the
     generated package's conftest teardown writes
     `<workspace>/evidence/flow_memory.json` **into the runner mount** —
     exactly where the caller's `actions/cache` step persists it branch-
     scoped. A restored store is loaded and merged (dedup + hit bumps),
     never overwritten.
   - After a green run the entrypoint logs the store stats and emits
     `flow_store` / `flow_patterns` / `flow_sites` outputs (the learned
     count). A red run reports the failure, not learning bookkeeping.

2. **`src/storage.py`** — `get_storage()`'s lazy default now honours the
   `AITEST_STORAGE_ROOT` / `AITEST_WORKSPACE` env overrides. Backwards
   compatible (unset = repo-root discovery + default workspace); the UI/CLI
   call `init_storage()` explicitly and are unaffected. This is the seam
   that lets a bare pytest subprocess (the conftest) resolve storage to the
   runner mount. +3 unit tests.

3. **`generated_tests/conftest.py`** — the RAG-learning leg is now gated on
   `RAG_ENABLED != "0"` (CI never pulls the embedder — the E2E had been
   monkeypatching this leg away for the same reason); the flow-memory leg
   stays always-on for passing steps (the leg `learn: true` persists).

   > **Bug caught by the selftest**: a mid-session edit accidentally nested
   > the flow leg INSIDE the RAG gate — with `RAG_ENABLED=0` BOTH legs were
   > skipped, so the learn seed gate read 0 patterns and no store file. The
   > learn gates existed precisely to catch this; fixed (flow leg back at
   > `if status == "passed"`, RAG leg gated separately) and re-verified
   > (seed: `flow_patterns=1`; restore: `flow_patterns=2` = marker +
   > newly-learned — merge proven non-vacuously).

4. **`action/flow_memory_stats.py`** (new) — platform-neutral store-stats
   helper: `--store <path> --json` prints the learned-count stats; a missing
   or corrupt store reads as zeros with exit 0 (learning bookkeeping never
   fails a green run). +7 unit tests.

5. **Cache wiring**:
   - `.github/workflows/ci-cd-action.yml`: branch-scoped `actions/cache`
     key `ai-testgen-flowmem-${{ github.ref }}` (restore before, save after)
     + a `learn: true` self-test step (`-k test_04_go_to_cart_page` — the
     guaranteed-navigation test; stub asserts store file, `flow_*` outputs,
     and **no `rag_store.db`** on the runner).
   - `ci/gitlab-ci.template.yml`: `AITEST_LEARN` var + `INPUT_LEARN`
     mapping + `ai-test-workspace/evidence/flow_memory.json` in the
     branch-scoped cache `paths` (MR pipelines reuse the push pipeline's
     store).
   - `action.yml`: the `learn` input description updated (was
     "NOT IMPLEMENTED").

6. **`scripts/ci_action_selftest.py`** — 39 → **50 gates**:
   - **learn seed**: green run persists the store; `flow_patterns` ≥ 1;
     RAG leg off (no `rag_store.db` on the mount); comment still one
     idempotent edit.
   - **learn restore**: a pre-seeded marker pattern survives a re-run AND
     `flow_patterns` = 2 (marker + newly learned) — merge, not overwrite;
     the branch-cache contract.

## Design notes (from the settled sketch, no re-grill)

- **Flow memory only; RAG off in CI** — the ~80 MB embedder download per
  runner is the documented reason (`docs/ci.md` §8b).
- **Saturation is expected** — a stable package vs a stable site learns most
  new patterns on the first green run; later runs dedup + reinforce (hit
  counts). Value = consistency + first-run seeding (a NEW story on the same
  site later resolves better). Modest-value, consistency-driven — why it is
  opt-in and default off.
- **Within-test flows first** — free (the action already runs the package's
  conftest teardown). Suite chains need the UI/CLI post-run hook; explicitly
  NOT added (only if the within-test store proves thin).
- **Learning ≠ self-healing** — learning writes the "diary" (the store),
  never touches test code.

## Gates

- Local Docker self-test: **50/50** (twice: full build run + `--skip-build`
  re-run).
- Full default suite: **2597 passed / 1 skipped** (+10 new tests).
- ruff + mypy clean; `action.yml` / `.github/workflows/ci-cd-action.yml` /
  `ci/gitlab-ci.template.yml` all parse.
- GitHub CI (both pushed workflows green on `3db0b0d`): **CI/CD Pipeline
  success** + **Action Self-Test success (25/25 steps)** — the learn gate
  passed on the runner (`learn OK: 1 patterns / 1 sites`; flow-memory
  restore/save steps green). Two benign warnings: run-history restore
  "Permission denied" (the known root-owned-file quirk — the sabotage step
  documents it) and one "Cache save failed" (parallel-job race on the
  run-history key between the two workflows — one wins, other skipped).
- **GitLab.com live (template changed → re-verified)**: pushed the repo to
  `cat-tan-operations/ai-testgen-selftest`; the push pipeline's first
  attempt failed at `build-image` with a **transient Chrome download error**
  ("Failed to download Chrome for Testing", exit 1 — the browser layer is
  untouched by this change and built fine in the 7c run); retried the same
  commit → **pipeline success** (build-image ✓, compute-key ✓,
  ai-testgen:run ✓). Run-job artifacts verified: `exit_code=0`,
  `cache_hit=true` (branch cache restored with the new cache `paths`),
  `cache_key` 64-hex, junit **8 tests / 0 failed**.

  The full 14/14 script (`scripts/ci_gitlab_real_project_test.py`) was NOT
  re-run end-to-end: its stage-2 gate asserts a cache MISS on a "fresh
  project", and the branch cache now exists on the test project (the token
  can't clear it via the API — the `clear_cache` endpoints 404). The
  MR-note gates (stages 3-4) are untouched by this change (no posting code
  was modified; `INPUT_LEARN` is inert with `AITEST_LEARN=false`, and the
  added cache path is a no-op without a store) and were proven 14/14 in 7c.
  The template's live-pipeline path with the new variables/paths is
  verified by the retried run above.

## Housekeeping

- BACKLOG Phase 7 entry: "Remaining: learn: true fails fast" → closed; 7d
  entry added. CHANGELOG [Unreleased] 7d entry. `docs/ci.md` §8b +
  security-note + testing updates. Kanban regenerated. This session doc.
- The GitLab test project + `.env` `GITLAB_TOKEN` stay live (user's choice,
  unchanged).

## Next

Phase 7 is fully closed. Roadmap candidates (BACKLOG top): Phase 8 GTM
assets `[~]`, AI-044-B (visual grounding), or Phase 6 SaaS.
