# 2026-08-15 — Phase 7 7c: GitLab parity (MR comment, cache, slash-commands, verified adaptation)

**Roadmap:** Tier 5 §14 (Phase 7 CI/CD Integration — Commercialization) → **`[x]` Complete**.
**Spec:** `docs/specs/FEATURE_SPEC_phase7_ci_cd_integration.md` (§8/7c, §5.5 platform seam, §12 DoD).
7a (driver + Docker action + self-test) and 7b (generate-and-run, cache, PR comment, slash-commands, verified adaptation) shipped 2026-08-13/14/15. **This session shipped 7c in full** — the §5.5 seam now has both skins (GitHub + GitLab), the milestone is complete.

## Problem

GitHub proved the pattern end-to-end (7b). GitLab parity per spec §8/7c: `.gitlab-ci.yml` include template (same three modes) + a GitLab platform adapter (MR note comments, slash-commands, `cache:`/`artifacts:`, protected-environment approvals), the same milestone — platform-risk hedge, not an afterthought. All decisions were closed in the 7a grilling; the 7b session's nine gotchas were the input contract (not re-derived).

## What shipped

| Component | Purpose |
|---|---|
| `ci/platform/gitlab.py` | The GitLab surface behind the §5.5 seam, mirroring github.py: MR notes under `/projects/:id/merge_requests/:iid/notes` (list / find-by-marker / create / **PUT**-edit — GitLab edits are PUT, not PATCH), `PRIVATE-TOKEN` auth, project as numeric id **or** URL-encoded `group%2Fproject` path, injectable base URL + `client_from_env` honoring both GitLab-runner-native `CI_*` vars (`CI_PROJECT_ID`/`CI_PROJECT_PATH`/`CI_MERGE_REQUEST_IID`/`CI_API_V4_URL`) and explicit overrides (`GITLAB_TOKEN`/`GITLAB_PROJECT`/`GITLAB_MR_IID`/`GITLAB_API_URL`). `--latest-command` CLI mode (the slash job fetches the newest `/adapt`/`/ignore` MR note). Same markers (`## 🤖 AI Test Generator`) → edit-not-duplicate works identically across platforms. |
| `ci/gitlab-ci.template.yml` | Include template: `ai-testgen:build-image` (docker dind → project registry; `AITEST_SKIP_BUILD` skip), `ai-testgen:compute-key` (the §7 `action/cache_key.py` formula via a **dotenv report** feeding `cache:key` — GitLab evaluates cache:key after collecting `needs`' artifacts, so the dotenv variable is available at cache-restore time; one source of truth with the action's internal key), `ai-testgen:run` (the three modes driven by `AITEST_MODE`; the action's `/entrypoint.sh` with the image entrypoint neutralised via `image: entrypoint: [""]` — GitLab would otherwise append its script lines to the image ENTRYPOINT; underscore `INPUT_*` variables because GitLab CI variable names cannot contain hyphens; `GITHUB_WORKSPACE: $CI_PROJECT_DIR`; `artifacts:reports:junit` → GitLab's **native MR test UI**; cache `key` = branch + run-key + compute-key with `fallback_keys` for the slash loop), and a **manual** `ai-testgen:slash-command` job (free tier has no note-event pipeline trigger — the job lists MR notes via `--latest-command` and posts the reply; manual-first is arguably SAFER than GitHub's auto-trigger: a human reviews the failing test before dispatching). Protected-environment approval gate for the danger zone (`ai-testgen-prod`). |
| `action/entrypoint.sh` | `detect_platform()` — explicit `platform` input (auto default) or auto-detect from the runner env (`GITLAB_CI`/`CI_SERVER_HOST` → gitlab); `post_comment()` gained the gitlab branch (same payload, same marker, maps `gitlab-*` inputs to the adapter's env). GitHub behaviour byte-identical (the 26-gate GitHub half of the selftest is unchanged). |
| `action.yml` | New inputs: `platform` (auto), `gitlab-token`, `gitlab-project`, `gitlab-mr-iid`, `gitlab-api-url`. |
| `tests/test_ci_gitlab_adapter.py` | 14 unit tests against a mock GitLab API server (mirror of the GitHub adapter's mock-server pattern): idempotent create → PUT-edit (one note), find-by-marker, `extract_url_from_comment`, no-token raises, `PRIVATE-TOKEN` header, 404 surfacing, URL-encoded `group%2Fproject` vs numeric id paths, `client_from_env` mapping (CI_* + overrides + defaults), `latest_slash_command_body` (most-recent, within-body, none). |
| `scripts/ci_action_selftest.py` | **26 → 39 gates**: host-side `MockGitLabAPI` (notes store; GET/POST/PUT routes) + three GitLab gates — (6) generate-and-run with `INPUT_PLATFORM=gitlab` posts the §6 payload as an **MR note** (cache HIT reuses the GitHub miss gate's seeded package — no duplicate ~2.5 min generation; asserts notes-endpoint path `/projects/org%2Fproject/merge_requests/42/notes`, `PRIVATE-TOKEN` header, §6 shape); (7) slash `/adapt` sabotages the **cached** package → verified adaptation keeps it → reply posted as a note; (8) slash `/ignore` reply posted as a note (3 notes total). |
| `docs/ci.md` | The configuration reference: modes, quick start (GitHub + GitLab), when to adapt (shared vs isolated envs — the topology rule), ignore-list format, cache, slash commands, danger zone + approval gates, security notes, testing. |

## Gotchas found this session (for the next platform skin / 7c follow-ups)

1. **GitLab CI variable names cannot contain hyphens** — `INPUT_GITLAB-TOKEN` can't be declared in `.gitlab-ci.yml`. The template sets the underscore spellings; the entrypoint's `get_input` hyphen→underscore fallback (written in 7b for exactly this) resolves them. Verified: `INPUT_GITLAB_TOKEN` reaches `get_input GITLAB-TOKEN`.
2. **GitLab runs script lines through the image's ENTRYPOINT by default** — a Docker action image's `ENTRYPOINT [/entrypoint.sh]` would swallow the job's script as args (the action runs, the script's env-prep never executes). The fix is `image: {name: …, entrypoint: [""]}` per job + explicit `/entrypoint.sh` in `script:`.
3. **`cache:key` can't run python** — GitLab evaluates keys from the job env, not shell. The §7 formula lives in `action/cache_key.py`; the template's `compute-key` job exports it as a **dotenv report** (`artifacts:reports:dotenv`), which is collected before cache restore in `needs`' jobs. (To be validated live — see the real-project gate.)
4. **GitLab edits MR notes with PUT, not PATCH** — the adapter's `edit_note` uses PUT; the mock + unit tests assert it.
5. **Project ids are numeric OR paths** — `CI_PROJECT_PATH` (`group/project`) must be URL-encoded (`group%2Fproject`) in the REST path; `CI_PROJECT_ID` passes through. `_encode_project` handles both.
6. **Dotenv/story inputs and multi-line values** — GitLab CI variables can hold multi-line values but dotenv reports and shell interpolation make inline stories fragile; the template uses a **story FILE** (`AITEST_STORY_FILE`, versioned in-repo) and hashes the path string (consistent between compute-key and the action — both hash the same representation).
7. **`needs: []`** — the compute-key job must not wait for the image build (it only needs the repo checkout + pure-stdlib `cache_key.py`); the run job `needs` both build + compute-key.
8. **The selftest's cache-key import** — the host selftest needs `action/cache_key.py` to locate the seeded package for the GitLab gates: `sys.path.insert(0, PROJECT_ROOT)` (running a script puts `scripts/` on sys.path, not the repo root).
9. **MSYS path mangling in bash-driven docker** — container-side paths starting with `/` get rewritten to `C:/Program Files/Git/...` by Git Bash; the python-driven selftest is immune, ad-hoc `docker run` from bash needs `MSYS_NO_PATHCONV=1`.

## Verification

- **Local Docker selftest: 39/39 gates** (was 26) — the full GitHub sequence unchanged + three GitLab gates (~15 min cold / ~11 min no-build incl. the new ~1.5 min GitLab sequence; the GitLab gates reuse the GitHub miss gate's seeded cache — no duplicate generation).
- **Pre-flight (targeted):** slash-command `/ignore` through the gitlab platform branch against a host mock — MR note 1 posted, payload rendered. Confirmed the bash plumbing before the full run.
- **Unit gates:** full suite **2587 passed / 1 skipped** (measured; incl. the 14 new GitLab adapter tests), smoke 38/38, ruff + mypy clean.
- **GitHub CI:** both workflows green on `0ed06b5` — **CI/CD Pipeline 9/9** (PyTest+Coverage, Ruff, MyPy, Eval Static, Graph/Kanban/Docs freshness, Smoke, Sanitizer) and **Action Self-Test 21/21** (generate-only → run-existing → cache → generate-and-run miss → sabotage → `/adapt` → `/ignore`). The entrypoint platform refactor (detect_platform + gitlab branch) left the GitHub path byte-identical in behaviour — verified by the GitHub self-test, not just the local mirror.

## Real GitLab.com gate (DoD §12 — passed 2026-08-15)

Ran `scripts/ci_gitlab_real_project_test.py` against a real GitLab.com project (`cat-tan-operations/ai-testgen-selftest`, private, shared runners) with a PAT (`api` scope). **14/14 checks verified live** across three pipelines:

| Gate | Result |
|---|---|
| push pipeline (default branch) | **success** — build (dind) + compute-key + run all green |
| action-state exit_code | 0 |
| cache miss on fresh project | `cache_hit=false` |
| junit.xml artifact | 8 tests, 0 failed |
| MR pipeline (feature/selftest → main) | **success** — §6 **MR note posted (1)**, marker + metric table |
| edit-check (2nd commit on the branch) | **success** — `cache_hit=true` (package reused), **note still ONE** (edited, never duplicated) |

Account-level blockers found + cleared along the way: (1) GitLab.com **identity verification** is required before new accounts can run CI on shared runners — the account needed a phone number added (avatar → Preferences → Account); 2FA alone does not lift it. (2) The commits API will not auto-create a branch — `POST /repository/branches` first. (3) MR pipelines report `ref: refs/merge-requests/<iid>/head`, not the source branch — wait on the MR's own pipelines endpoint. (4) `rules:` rejects an `artifacts:` key — per-mode artifacts need separate jobs (the `extends` restructure). Template fixes from the live run: `AITEST_IGNORE_FILE` defaults empty (a missing file fails generation), `INPUT_SELF_TEST` mapping, `CI_COMMIT_REF_NAME` cache keys (CI_COMMIT_BRANCH is empty on MR events), run-history in cache paths, `.gitlab-ci.yml` + `ai-test-story.md` added to the repo.

## Housekeeping

- BACKLOG top entry: 7c complete, **real GitLab.com gate passed** (DoD §12 closed — 14/14 live checks on `cat-tan-operations/ai-testgen-selftest`); remaining = `learn: true` (fails fast until store-caching).
- CHANGELOG [Unreleased] 7c entry; kanban regenerated; scripts/README.md (selftest 39 gates + GitLab gates list); ROADMAP Phase 7 → `[x]` + Tier 5 §14 status + session-tracking rows; ARCHITECTURE.md gained the CI/CD Integration Layer subsection.
- **DoD status:** all spec §12 items met except the live GitLab.com run — the `.gitlab-ci.yml` template + adapter are built and hermetically tested (mock-API gates carry the MR-note shape asserts); a real-project run mirrors the GitHub self-test once a `GITLAB_TOKEN` (api scope) is provided. No GitLab credentials exist on this machine or in the repo env.

## Notes for the next session

- **Real GitLab.com gate (the only open DoD item):** create a throwaway test project via the API, push the template + `ai-test-story.md` (the ecommerce story), set `AITEST_URL` to the mock-site port with `INPUT_SELF-TEST: "true"` (the image bundles `mock_sites/` + `scripts/fake_llm.py` — the pipeline boots them inside the runner, exactly like the GitHub self-test), trigger the pipeline via `POST /projects/:id/pipeline`, poll, then assert: pipeline success, junit artifact, MR note posted with the §6 shape (open an MR first). The template's `AITEST_RUN_KEY: "$CI_PIPELINE_ID"` gives the deterministic cache-miss parity with GitHub's `github.run_id`.
- **`learn: true`** remains the only Phase 7 tail (fails fast, never silent) — store-caching learning after Phase 7.
- Pre-commit ruff is v0.16.0 (aligned with CI) — untouched this session.

---

## Fresh-context kickoff message (next session)

> **Phase 7 tail — real GitLab.com gate + `learn` (only open items).**
>
> 1. The full 7c deliverable is shipped and hermetically tested: `ci/platform/gitlab.py` (+14 unit tests vs a mock API), `ci/gitlab-ci.template.yml` (build/compute-key/run/slash jobs; dotenv-fed cache key; protected-env approval gate), entrypoint `detect_platform` + gitlab post_comment branch, `docs/ci.md`, selftest 39/39 gates (incl. 13 GitLab gates with a host-side mock GitLab API — MR-note REST shape, PRIVATE-TOKEN, cache-hit reuse, adapt/ignore replies).
> 2. **The one open DoD item needs a `GITLAB_TOKEN` (api scope).** No GitLab credentials exist on this machine. Ask the user for a token (or have them set it), then: create a throwaway project via `POST /projects`, push `ci/gitlab-ci.template.yml` + a `.gitlab-ci.yml` include + `ai-test-story.md`, open an MR, trigger the pipeline with `AITEST_RUN_KEY=$CI_PIPELINE_ID` + `INPUT_SELF-TEST=true`, poll, assert success + junit artifact + §6 MR note (1 note, edited not duplicated on re-run).
> 3. Session doc: `docs/sessions/2026-08-15_phase7_7c_gitlab_parity.md` (the 9 gotchas — especially GitLab's variable-name hyphen ban, the image-entrypoint neutralisation `entrypoint: [""]`, and the dotenv→cache:key pattern).
