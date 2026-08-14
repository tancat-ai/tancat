# 2026-08-15 — Phase 7 7b: generate-and-run (PR comment, cache, slash-commands, verified adaptation)

**Roadmap:** Tier 5 §14 (Phase 7 CI/CD Integration — Commercialization).
**Spec:** `docs/specs/FEATURE_SPEC_phase7_ci_cd_integration.md` (grilled, all decisions closed).
7a shipped 2026-08-13/14 (headless driver, fake LLM, ignore list, Docker action, hermetic self-test). **This session shipped 7b in full** — the loop closes: generate-and-run, actions/cache, the §6 PR comment, the slash-command loop, and the verified adaptation engine. 7c (GitLab parity) next.

## Problem

7a gave the action three entry points (`generate-only`, `run-existing`, and a fail-fast `generate-and-run` branch) but no *loop*: nothing cached, nothing commented, nothing adapted. Per spec §8/7b: wire `generate-and-run` (generate → cache → pytest → evidence → report → comment), add `actions/cache` with the §7 key, post the idempotent §6 PR comment, run the slash-command loop (`/adapt`, `/ignore`), and build the verified adaptation engine (locator-only patch → re-run → assertion gate → keep-or-revert). All decisions were closed in the 7a grilling — nothing to re-grill.

## What shipped

| Component | Purpose |
|---|---|
| `action/cache_key.py` | **Single source of truth** for the §7 key: `sha256(story + url + model + provider + PROMPT_FINGERPRINT)` — pure stdlib so the workflow's `python3` step and the action's internal cache-dir check compute the same key (they can't drift). Fingerprint constant bumps invalidate every cached package at once (AI-042-F4). |
| `generate-and-run` in `action/entrypoint.sh` | The §5.4 pipeline: cache check (miss → generate + seed `<cache-dir>/packages/<key>/`; hit → reuse, no LLM call) → pytest (referee) → AI-028 evidence JUnit → report + **flaky markers** (AI-011 from the action's own cached per-branch run history, merged via `action/flaky_history.py`) → §6 comment payload (`comment.md`, always written) + idempotent posting (only with `repo`+`pr-number`+`github-token` inputs). `adapt: true` repo-level opt-in runs the adaptation engine and applies a **referee-exit override** (all failures adapted + re-run green → exit 0). `learn: true` **fails fast** with a clear message — never a silent no-op. |
| `ci/platform/github.py` | The GitHub surface behind the §5.5 seam: find-comment-by-marker → **edit-not-duplicate**, create/reply, `extract_url_from_comment` (slash runs recover the site from the previous comment). Stdlib urllib, injectable `base_url` → unit tests + the local selftest point it at a mock API. |
| `action/adapt.py` | **Verified adaptation engine** (spec §9.6): parses LocatorNotFound-class failures in **both** shapes (Playwright `locator('…')` and the evidence_tracker's `Locator '…' not found on current page (…)`) → finds the source step → re-resolves the step's semantic label with the product's OWN resolution machinery (`PageScraper` + `PlaceholderResolver`, no LLM, no new deps) → patches → re-runs ONLY that test → keeps only if the test's own assertions still pass, **reverts otherwise** → `adaptation.json` with every attempt + reason. Assertion failures never reach the engine (filtered at the junit gate). |
| `action/flaky_history.py` | Per-branch run-history store (workspace `run-history.json`, persisted by the workflow's branch-scoped `actions/cache`): merge junit results, trim to last 10 runs, AI-011 detection (both pass AND fail across ≥2 runs), `render_flaky_section` → the §6 flaky block. |
| `scripts/ci_slash_commands.py` | Slash-command core (platform-neutral, offline): parse `/adapt <test>` / `/ignore <test>`, render the adapt reply from `adaptation.json`, render the `/ignore` reply with the **exact `.ai-test-ignore.yml` entry** (required `reason` — the anti-rug rule — plus a suggested `match` regex from the failure locator). |
| Internal `slash-command` mode | One mode for both commands: parse (core) → referee pytest (fresh junit) → `/adapt` runs the engine (or `/ignore` renders the YAML reply) → post the reply with the per-command marker (`## 🤖 AI Test Generator — /adapt` / `/ignore`). No token/PR → payload written, posting skipped. |
| `action/report.py` | Gained the §6 context line (`**Mode:** … · **Site:** … · **Model:** …`), the flaky block injection, and public `is_repair_candidate()` (shared with the adapt engine). |
| `action.yml` | New inputs: `cache` (true), `cache-dir`, `comment` (true), `adapt` (false — never default), `learn` (false, fails fast), `comment-body`/`test` (internal), `repo`/`pr-number`/`github-token` (posting). |
| `.github/workflows/ci-cd-action.yml` | Extended: compute-cache-key step → `actions/cache` restore/save (run-specific package key = deterministic miss; branch-scoped run-history key) → generate-and-run phase (stub: cache_hit=false, cache seeded, §6 comment shape, flaky key present) → **sabotage → `/adapt`** phase (stub: kept ≥ 1, reverted = 0, source fixed on disk) → **`/ignore`** phase (stub: YAML entry reply). Permissions now `pull-requests: write` + `actions: read`. |
| `.github/workflows/ci-slash-commands.yml` | **New**: `issue_comment` (created) trigger; PR-only (`github.event.issue.pull_request`), fork guard (`author_association != 'NONE'`, never `pull_request_target`); restores the branch's package cache via `restore-keys` prefix; runs the action's `slash-command` mode with `secrets.GITHUB_TOKEN`. |
| `scripts/ci_action_selftest.py` | Now **25 gates** (was 9): generate-and-run **cache miss** (generate + seed + driver contract + comment POSTED to a host-side **mock GitHub API** via `host.docker.internal`), generate-and-run **cache hit** (single-test referee, no regeneration, comment EDITED — still 1), run-existing (junit/evidence/report shape), **sabotage → `/adapt`** (patch → re-run → keep), **`/ignore`** (YAML reply) — 3 comments total, real POST/PATCH traffic asserted. Per-gate timing printed; `--skip-build` guarded by a stale-image check. Windows console encoding fix for 🤖 output. |

Tests: +45 (cache-key 5, flaky-history 5, slash-commands 10, GitHub adapter 7 against a mock API server, adaptation engine 13 incl. the tracker-error shape + patch-when-new-locator-already-present, report flaky/context 5). Full suite **2571 passed / 1 skipped**, smoke 38/38, ruff + mypy clean.
## Gotchas found this session (so 7c doesn't re-derive them)

1. **Docker actions have no `outputs:` key in action.yml** — the schema rejects it (action fails to load), and the runner NEVER injects `GITHUB_OUTPUT` into container steps. Outputs go through a file the action writes: `echo_github_output` mirrors every value into `<workspace>/results/action-state.txt`, which the hermetic stubs read (local + GitHub use the same file). Declaring outputs in action.yml is a hard error — do not retry.
2. **Container-created files are root-owned** — a `run:` step that edits the action's cache output gets PermissionError. The self-test's sabotage step runs with `sudo` (GitHub runners have passwordless sudo; the workspace is ephemeral scratch).
3. **The cache must seed the package DIRECTORY, not the test file** — the driver's `package` field is the .py path; `cp -r <file> <cache>/` drops `package_manifest.json` + `pages/`, and the adapt engine then has no target URL (`no-url`). Normalize to `dirname` and copy the package root; `adapt._package_url` searches recursively (cache restore nests `<key>/<pkg>/`).
4. **JUnit XML escapes quotes** — no issue parsing, but `patch_locator` must only guard on the OLD locator: a sabotaged package legitimately still contains the good locator on other lines, so a `new_locator in text` bail breaks the patch.
5. **Two locator message shapes** — Playwright native (`waiting for locator('…')`) AND the evidence_tracker's own fast-fail (`Locator '…' not found on current page (…)`). Both must be parsed; a `[^'"]+` character class breaks on locators containing quotes of the other kind — use a backreference `(['"])(.*?)\1`.
6. **`os.environ` is not exported to heredoc python** — pass argv instead.
7. **Windows console cp1252 crashes on 🤖** — `sys.stdout.reconfigure(encoding="utf-8", errors="replace")`.
8. **`actions/cache` key shapes** — a run-specific prefix (`github.run_id`) makes the self-test restore deterministically MISS (`cache_hit=false` assertable); the slash-command workflow uses a branch prefix + `restore-keys` fallback.
9. **Efficiency (measured 2026-08-15)**: the local selftest's floor is the product's real per-test overhead — a full 8-test pytest run is ~3 min, and the browser generation is ~2.5 min. The selftest merges the duplicate generation (generate-only contract is asserted inside generate-and-run's stub), runs the cache-hit gate and slash-command referees with `-k <test>` (single test), and the Dockerfile orders the browser install BEFORE `COPY . .` so code edits don't re-download Chromium. No-build: ~9.7 min (was ~17.5 min cold). `--skip-build` is guarded by a stale-image check (refuses when action/source files are newer than the image). The authoritative check remains the GitHub self-test workflow, which runs in parallel with every push.

## Verification

- Local: `scripts/ci_action_selftest.py` **25/25 gates** (~9.7 min no-build; miss gate generates + runs the suite, hit gate is a single-test referee, slash referees are `-k` single-test). Ran repeatedly through the fixes above.
- Unit gates: **2571 passed / 1 skipped** (was 2526), smoke 38/38, ruff + mypy clean.
- **GitHub (final commit `dbf1d67`): CI/CD Pipeline ✓ AND CI/CD Action Self-Test ✓ — all 20 steps green** (generate-only → run-existing → cache-key → cache restore/save → generate-and-run miss → sabotage → `/adapt` → `/ignore`, each stub-asserted; ~13 min). The workflow needed three GitHub-only fixes before going green — the gotchas below (1-3) are the record.

## Housekeeping

- BACKLOG top entry: 7a + 7b → complete; remaining = 7c (GitLab parity) + `learn` (fails fast until store-caching lands). CHANGELOG [Unreleased] 7b entry, kanban.html regenerated, scripts/README.md (selftest 25 gates + new `ci_slash_commands.py`).
- History on main: `73b35e9` feature + four workflow-only fixes (`a2b2314` GITHUB_OUTPUT/action-state, `3f34abc` remove illegal `outputs:` key, `ddbeba4` sudo sabotage, `dbf1d67` cache-seeds-package-dir + efficiency + pre-commit ruff pin). The 7a squash offer (force-push) is still open — requires explicit permission per AGENTS.md.
- **Tooling: pre-commit ruff pinned v0.15.4 → v0.16.0** (matches `ruff==0.16.0` in pyproject / what CI runs). The v0.15.4/v0.16.0 format disagreement on PEP-758 `except (A, B)` tuples fought every commit; aligned so the local gate matches the CI gate.

## Notes for 7c (next session)

- **Reuse unchanged** (the §5.5 insurance): `action/report.py`, `action/adapt.py`, `action/flaky_history.py`, `action/cache_key.py`, `scripts/ci_slash_commands.py`, `scripts/ci_generate.py` — zero GitHub imports. Only `ci/platform/github.py` is GitHub-specific; 7c writes `ci/platform/gitlab.py` (MR note comments, `/adapt` `/ignore` replies, `cache:`/`artifacts:`, protected-environment approvals) + `.gitlab-ci.yml` include template + `docs/ci.md` (modes, when to adapt — shared vs isolated envs, ignore-list format).
- **GitLab's output channel mirrors action-state.txt** — the action's outputs (cache_key/cache_hit/exit_code) live in `<workspace>/results/action-state.txt`, not a runner-injected file; a GitLab MR-note stub reads the same file.
- The internal `slash-command` mode + the slash workflow are the pattern to mirror for MR notes.
- Flaky markers already flow from the branch-scoped run-history cache; GitLab's `cache:` keys should mirror the same `sha256(story+url+model+provider+fingerprint)` formula (import `action/cache_key.py`).
- Roadmap Phase 7 → `[x]` when 7c lands; spec §12 DoD item "PR comment posted from a real local run against a mock" is met via the mock GitHub API gate.
- Pre-commit ruff is v0.16.0 (aligned with CI) — if 7c touches `.pre-commit-config.yaml` again, keep the versions in lockstep.

---

## Fresh-context kickoff message (7c)

> **Phase 7 7c — GitLab parity: MR comment, cache, slash-commands, verified adaptation.**
>
> Start here:
> 1. `docs/specs/FEATURE_SPEC_phase7_ci_cd_integration.md` — §8 (7c row), §5.5 (platform seam — the adapters),
>    §12 (DoD: `.gitlab-ci.yml` template + platform adapter tested against a real GitLab.com project).
> 2. `BACKLOG.md` top entry — 7a + 7b complete; 7c scope.
> 3. `docs/sessions/2026-08-15_phase7_7b_generate_and_run.md` — this session's record + the **nine gotchas** you must
>    not re-derive: (1) Docker actions reject an `outputs:` key and never get GITHUB_OUTPUT — outputs live in
>    `<workspace>/results/action-state.txt`; (2) container-created files are root-owned (sabotage runs with `sudo`);
>    (3) the cache seeds the package DIRECTORY (manifest) not the test file — adapt URL search recurses;
>    (4) junit quote escaping + patch_locator must guard on the old locator only; (5) two locator message shapes +
>    quote-backreference regex; (6) heredoc python has no bash env — pass argv; (7) Windows cp1252 breaks on 🤖;
>    (8) cache-key shapes (run-specific prefix for deterministic miss; branch prefix + restore-keys for the slash loop);
>    (9) the local selftest floor is the product's own cost (2.5 min generation, 3 min per suite pytest) — merge
>    duplicate generations, use `-k` single-test referees, `--skip-build` is stale-guarded, Dockerfile orders the
>    browser install before COPY.
>
> Reference files:
> - `ci/platform/github.py` — the adapter to MIRROR for GitLab (find-by-marker → edit-not-duplicate, reply
>   posting, `extract_url_from_comment`). Its unit tests (mock HTTP server) are the template. GitLab's MR-note
>   REST differs (notes endpoint, `note` field, `/notes` IDs) — the mock-server test pattern carries over.
> - `action/entrypoint.sh` `slash-command` mode + `.github/workflows/ci-slash-commands.yml` — the loop pattern.
> - `action/adapt.py`, `action/report.py`, `action/flaky_history.py`, `action/cache_key.py`,
>   `scripts/ci_slash_commands.py` — **zero GitHub imports, reuse unchanged** (the §5.5 insurance).
> - `scripts/ci_action_selftest.py` (25 gates, action-state.txt + mock-API pattern) + `.github/workflows/ci-cd-action.yml`.
>
> Implementation notes:
> 1. The GitLab surface: `ci/platform/gitlab.py` (MR note REST: list/find-by-marker/create/edit, replies;
>    the GitLab.com API base is injectable for hermetic tests, same as github.py). Reuse the same markers
>    (`## 🤖 AI Test Generator`) so edit-not-duplicate works identically.
> 2. `.gitlab-ci.yml` include template: same three modes (generate-only / generate-and-run / run-existing)
>    + the internal slash-command job; `cache:` key = the `action/cache_key.py` formula (import it);
>    `artifacts:` for junit.xml / junit-evidence.xml / evidence bundle; protected-environment approvals for
>    the danger-zone path. GitLab runners don't set the GitHub INPUT_*/GITHUB_WORKSPACE surface — the action
>    reads env directly (the entrypoint's get_input already falls back to underscore spellings); the GitLab
>    adapter maps MR variables to the same inputs.
> 3. Test against a real GitLab.com project (credentials available), mirroring the GitHub self-test. Keep the
>    mock-API gate pattern for MR-note shape assertions (GitLab's API is mockable the same way).
> 4. Write `docs/ci.md` (modes, when to adapt — shared vs isolated envs, ignore-list format, education).
> 5. DoD: Roadmap Phase 7 → `[x]`, session doc in `docs/sessions/`, both workflows green (7b's are green on
>    `dbf1d67` — CI/CD Pipeline ✓ + Action Self-Test ✓).
