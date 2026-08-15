# 2026-08-15 — Phase 7 7c tail: real GitLab.com gate (DoD §12 closed)

**Roadmap:** Tier 5 §14 — **Phase 7 fully complete** (all `FEATURE_SPEC_phase7` §12 DoD items now closed).
**Spec:** `docs/specs/FEATURE_SPEC_phase7_ci_cd_integration.md` §8/7c + §12 ("`.gitlab-ci.yml` template + platform adapter tested against a real GitLab.com project (self-test mirrored)").
7a/7b/7c shipped 2026-08-13/14/15 with hermetic gates (39/39 local, both GitHub workflows green); the one open DoD item was the **live GitLab.com run**. This session closed it.

## Problem

7c's adapter + template were verified hermetically (mock GitLab API gates), but the spec's live gate — the template running end-to-end on real GitLab.com shared runners — was pending because no GitLab account/credentials existed. The user created the account and a PAT (`api` scope), and this session ran the full live gate.

## What happened (the arc)

1. **Account + token**: user created a GitLab.com account and a PAT. First attempt hit the new **granular token UI** (which requires attaching a resource and surfaced a confusing "Secrets Management API JWT" option) → switched to a **project access token** on the test project (classic scope list incl. `api`). Token goes in the local `.env` (gitignored — never for the pipeline itself, which uses a masked CI/CD variable `AITEST_GL_TOKEN`).
2. **Token verified**: `GET /api/v4/user` → `lacattano`; project `cat-tan-operations/ai-testgen-selftest` reachable (private, shared runners on, registry on).
3. **`scripts/ci_gitlab_real_project_test.py`** — the live gate: configure (registry + masked variables + hermetic self-test config) → force-push main → wait push pipeline (assert success, exit 0, cache miss, junit.xml) → feature branch + MR via the API → wait MR pipeline (assert §6 MR note) → second commit → assert note EDITED not duplicated + cache hit.
4. **Account blocker**: every pipeline failed instantly with zero jobs — `"Identity verification is required in order to run CI jobs"`. GitLab.com requires **phone (or card) verification** for new accounts to use shared runners; email confirmation and 2FA do **not** lift it (verified). User added a phone number (avatar → Preferences → Account → Identity verification) → pipelines created.
5. **Template bugs found by the live run** (fixed + committed): see gotchas 2-6.
6. **Live run: 14/14 checks passed.**

## Gotchas found this session (live-run specific — for the next platform skin / GitLab work)

1. **GitLab.com identity verification gates CI for new accounts** — pipelines fail at creation with zero jobs and the base error "Identity verification is required in order to run CI jobs". Phone number (or card) in avatar → Preferences → Account is required; 2FA alone is not enough.
2. **`rules:` rejects an `artifacts:` key** ("rule config contains unknown keys") — per-mode artifacts must be separate jobs. The template now splits `ai-testgen:run` (generate-and-run + run-existing, junit reports) and `ai-testgen:generate-only` (package artifact) sharing a hidden `.ai-testgen:base` via `extends`.
3. **The commits API will not auto-create a branch** — "You can only create or edit files when you are on a branch". `POST /projects/:id/repository/branches` first, then commit on it.
4. **MR pipelines report `ref: refs/merge-requests/<iid>/head`**, not the source branch — wait on the MR's own pipelines endpoint (`GET .../merge_requests/:iid/pipelines`), and skip already-seen pipeline ids after pushing a commit (a fast poll otherwise latches onto the previous run).
5. **`CI_COMMIT_BRANCH` is empty on MR pipelines** — branch-scoped cache keys must use `CI_COMMIT_REF_NAME` (source branch for MR events, branch for push events) or push and MR pipelines never share a cache.
6. **GitLab cache works as designed**: fresh project → miss; same branch + same §7 key re-run → **hit** (`cache_hit=true` verified on the edit-check pipeline). The compute-key dotenv → `cache:key` pattern holds on real GitLab.
7. **The artifacts API returns a ZIP** (raw bytes) — not JSON; the gate script's `job_artifacts` uses `raw=True`.
8. **Token hygiene**: a `gglpat-` typo (extra g) broke the first auth check; PATs start with exactly `glpat-` and are shown once at creation. `.env` is gitignored; the pipeline token lives in a masked CI/CD variable.

## Verification

**Real GitLab.com gate — 14/14 live checks** (`cat-tan-operations/ai-testgen-selftest`, private, shared runners):

| Gate | Result |
|---|---|
| push pipeline (default branch) | **success** — `ai-testgen:build-image` (docker dind), `compute-key`, `run` all green |
| action-state exit_code | `0` |
| cache miss on fresh project | `cache_hit=false` |
| junit.xml artifact | 8 tests, 0 failed |
| MR pipeline (feature/selftest → main) | **success** — **§6 MR note posted (1)**: marker + metric table |
| edit-check (2nd commit on the branch) | **success** — `cache_hit=true` (package reused, no regeneration) — **note still ONE** (edited, never duplicated) |

Local/CI gates unchanged and green: Docker selftest **39/39**, full suite **2587 passed / 1 skipped**, smoke **38/38**, ruff + mypy clean, GitHub workflows green (CI/CD Pipeline 9/9 + Action Self-Test 21/21 on `0ed06b5`).

## Housekeeping

- Commits (this continuation): `7cbcd48` (template gaps: `AITEST_IGNORE_FILE` empty default, `INPUT_SELF_TEST` mapping, api/trigger workflow rules) → `5085d2c` (gate script + `.gitlab-ci.yml` include + `ai-test-story.md`) → `fa67331` (`rules:artifacts` → extends split + typo `aio-testgen` → `ai-testgen`) → `93eb302` (MR-pipeline wait race + explicit branch create) → `bea1831` (docs: gate recorded, DoD closed).
- BACKLOG/CHANGELOG/ROADMAP (`[x]` + session rows)/`docs/ci.md`/kanban updated; `scripts/ci_gitlab_real_project_test.py` documented in `scripts/README.md`.
- **Test project kept live** (user's choice): `cat-tan-operations/ai-testgen-selftest` is a working demo of the template (branch `feature/selftest`, MR !1 with the posted note). Token remains in local `.env` (gitignored) and as a masked `AITEST_GL_TOKEN` CI/CD variable on the project. Revoke the token / delete the project when no longer wanted.
- The one remaining Phase 7 tail: `learn: true` (fails fast, never silent — store-caching learning arrives after Phase 7).

## Notes for the next session

- **Phase 7 is fully done** — every §12 DoD item closed. Do not re-derive the hermetic/live gates; re-run `scripts/ci_gitlab_real_project_test.py` only if the GitLab-side code changes (it is idempotent: reuses MR !1, force-pushes main, re-runs the note/edit gates).
- **`learn: true`** is the only Phase 7 tail — implementing it means designing the store-caching the action would persist (the action's existing cache-dir + run-history are the pattern; the entrypoint currently fails fast with a clear message — keep that until the cache write path exists).
- The GitLab test project + `.env` token are live if further GitLab work (e.g., the webhook→trigger automation for the slash job, or a docs example repo) needs a real project.
- Pre-commit ruff is v0.16.0 (aligned with CI) — untouched.

---

## Fresh-context kickoff message (next session)

> **Phase 7 is DONE — all DoD closed, including the real GitLab.com gate (14/14 live checks).**
>
> State: `scripts/ci_gitlab_real_project_test.py` passed 14/14 against
> `cat-tan-operations/ai-testgen-selftest` (push pipeline → junit 8/8 → cache
> miss; MR §6 note posted; edit-check: `cache_hit=true`, note edited not
> duplicated). GitHub CI green (Pipeline 9/9, Action Self-Test 21/21); local
> 39/39 selftest; 2587 passed / 1 skipped. The test project + `.env`
> `GITLAB_TOKEN` are kept live (user's choice) — revoke/delete when unwanted.
>
> Reference files:
> - `docs/sessions/2026-08-15_phase7_7c_gitlab_parity.md` + this doc — the 7c
>   delivery + the live-gate gotchas (identity verification gate, `rules:`
>   rejects `artifacts:`, commits API needs an explicit branch, MR pipeline
>   `ref: refs/merge-requests/<iid>/head`, `CI_COMMIT_REF_NAME` cache keys).
> - `docs/specs/FEATURE_SPEC_phase7_ci_cd_integration.md` — spec (all sections
>   now satisfied).
> - `docs/ci.md` — the user-facing configuration reference (modes, when to
>   adapt, ignore-list format, GitLab specifics).
> - `scripts/ci_gitlab_real_project_test.py` — re-runnable live gate.
>
> The only Phase 7 tail: **`learn: true`** (fails fast until store-caching
> lands — the action's cache-dir/run-history are the pattern to persist a
> learned store). Otherwise the next item is yours to pick (BACKLOG top entry
> is Phase 7-closed; roadmap candidates: Phase 8 GTM assets `[~]`, AI-044-B,
> or Phase 6 SaaS).
>
> **NEXT SESSION = `learn: true` (decided with the user 2026-08-15).** Why:
> CI should behave like the UI/CLI or have a documented reason not to — the
> fail-fast is that sort of unexplained divergence. Note: learning ≠
> self-healing (self-healing in CI was deliberately rejected; learning was
> always a planned opt-in input, just never wired).
>
> Settled design:
> - **Flow memory only; RAG off in CI** (the RAG leg needs an ~80 MB embedder
>   download per runner — document the reason in `docs/ci.md`).
> - **Saturation is expected** (user-derived, correct): a stable package vs a
>   stable site learns most new patterns on the first full green run; later
>   runs dedup + reinforce (hit counts). Value = consistency + first-run
>   seeding (a NEW story on the same site later resolves better). Modest-
>   value, consistency-driven — why it is opt-in and default off.
> - **Within-test flows first** (free — the action already runs the package's
>   conftest teardown); **suite chains** need the UI/CLI post-run hook — add
>   one explicit entrypoint call only if the within-test store proves thin.
>
> Implementation sketch: (1) `action/entrypoint.sh` — replace the fail-fast:
> on a GREEN generate-and-run with `learn: true`, ensure `RAG_ENABLED=0`, let
> the conftest teardown write `evidence/flow_memory.json` in the workspace,
> log/emit the learned count; (2) `.github/workflows/ci-cd-action.yml` — a
> branch-scoped `actions/cache` step for the store (like run-history);
> (3) `ci/gitlab-ci.template.yml` — add the store path to cache `paths`;
> (4) `action.yml` — update the `learn` input description; (5) selftest learn
> gate (seed on a passing run, restore on a re-run — reuse the miss/hit
> structure); (6) docs (`docs/ci.md`, session doc, BACKLOG).
>
> Read first: `src/flow_memory.py` (store format + consumption hook),
> `generated_tests/conftest.py` (the teardown learning leg; how the action's
> provisioned conftest differs), `scripts/ci_action_selftest.py` (miss/hit
> gate structure to mirror).
