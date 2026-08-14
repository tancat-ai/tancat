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
| `scripts/ci_action_selftest.py` | Now **28 gates** (was 9): generate-only, run-existing, generate-and-run **cache miss** (generate + seed + comment POSTED to a host-side **mock GitHub API** via `host.docker.internal`), generate-and-run **cache hit** (no regeneration, comment EDITED — still 1), **sabotage → `/adapt`** (patch → re-run → keep), **`/ignore`** (YAML reply) — 3 comments total, real POST/PATCH traffic asserted. Windows console encoding fix for 🤖 output. |

Tests: +45 (cache-key 5, flaky-history 5, slash-commands 10, GitHub adapter 7 against a mock API server, adaptation engine 13 incl. the tracker-error shape + patch-when-new-locator-already-present, report flaky/context 5). Full suite **2571 passed / 1 skipped**, smoke 38/38, ruff + mypy clean.

## Gotchas found this session (so 7c doesn't re-derive them)

1. **JUnit XML escapes quotes** — the junit failure message stores `a[href=&quot;…&quot;]`, but the adapt engine parses the *escaped* message then patches the *source* file (unescaped) — no issue there; the real trap was my own `patch_locator` guard: bailing when the NEW locator already exists in the file. A sabotaged package legitimately still contains the good locator on other lines — the guard must only check the OLD locator (replacement of the quoted form is inherently idempotent).
2. **Playwright locators contain quotes of the other kind** (`a[href="/x"]` inside `'…'`) — a `[^'"]+` character class breaks. Use a backreference to the opening quote: `(['"])(.*?)\1`.
3. **Two locator message shapes** — Playwright native (`waiting for locator('…')`) AND the evidence_tracker's own fast-fail (`Locator '…' not found on current page (…)`). The report's repair-candidate classifier already matched the tracker shape; the adapt engine's locator extractor must match both.
4. **`os.environ` is not exported to heredoc python** — bash vars aren't visible in `python - <<'PY'` children; pass argv or export.
5. **Windows console cp1252 crashes on 🤖** — `sys.stdout.reconfigure(encoding="utf-8", errors="replace")` in the selftest.
6. **`actions/cache` key shape**: a run-specific prefix (`github.run_id`) makes the self-test restore deterministically MISS (so `cache_hit=false` is assertable on GitHub); the hit path is proven locally + by adapter unit tests. The slash-command workflow uses a branch prefix + `restore-keys` fallback.

## Verification

- Local: `scripts/ci_action_selftest.py` **28/28 gates** (image build + generate-only 8 tests/138s + run-existing 8 tests 6 passed 2 skipped + cache miss/hit with mock-API comment POST/EDIT + sabotage→adapt kept + ignore YAML reply). Ran repeatedly through the fixes above.
- Unit gates: **2571 passed / 1 skipped** (was 2526), smoke 38/38, ruff + mypy clean.
- GitHub (to follow this push): **CI/CD Pipeline** (default gates) + **CI/CD Action Self-Test** (generate/run/cache/comment/adapt/ignore phases, stub-asserted).

## Housekeeping

- BACKLOG top entry: 7a + 7b → complete; remaining = 7c (GitLab parity) + `learn` (fails fast until store-caching lands). CHANGELOG [Unreleased] 7b entry, kanban.html regenerated, scripts/README.md (selftest 28 gates + new `ci_slash_commands.py`).
- History: feature + fix commits on main. The 7a squash offer (force-push) is still open — requires explicit permission per AGENTS.md.

## Notes for 7c (next session)

- **Reuse unchanged** (the §5.5 insurance): `action/report.py`, `action/adapt.py`, `action/flaky_history.py`, `action/cache_key.py`, `scripts/ci_slash_commands.py`, `scripts/ci_generate.py` — zero GitHub imports. Only `ci/platform/github.py` is GitHub-specific; 7c writes `ci/platform/gitlab.py` (MR note comments, `/adapt` `/ignore` replies, `cache:`/`artifacts:`, protected-environment approvals) + `.gitlab-ci.yml` include template + `docs/ci.md` (modes, when to adapt — shared vs isolated envs, ignore-list format).
- The internal `slash-command` mode + the slash workflow are the pattern to mirror for MR notes.
- Flaky markers already flow from the branch-scoped run-history cache; GitLab's `cache:` keys should mirror the same `sha256(story+url+model+provider+fingerprint)` formula (import `action/cache_key.py`).
- Roadmap Phase 7 → `[x]` when 7c lands; spec §12 DoD item "PR comment posted from a real local run against a mock" is met via the mock GitHub API gate.

---

## Fresh-context kickoff message (7c)

> **Phase 7 7c — GitLab parity: MR comment, cache, slash-commands, verified adaptation.**
>
> Start here:
> 1. `docs/specs/FEATURE_SPEC_phase7_ci_cd_integration.md` — §8 (7c row), §5.5 (platform seam — the adapters),
>    §12 (DoD: `.gitlab-ci.yml` template + platform adapter tested against a real GitLab.com project).
> 2. `BACKLOG.md` top entry — 7a + 7b complete; 7c scope.
> 3. `docs/sessions/2026-08-15_phase7_7b_generate_and_run.md` — this session's record + the six gotchas
>    (junit quote escaping + patch guard, quote-backreference locators, two locator message shapes,
>    heredoc env, Windows cp1252, cache-key shapes) you must not re-derive.
>
> Reference files:
> - `ci/platform/github.py` — the adapter to MIRROR for GitLab (find-by-marker → edit-not-duplicate, reply
>   posting, `extract_url_from_comment`). Its unit tests (mock HTTP server) are the template.
> - `action/entrypoint.sh` `slash-command` mode + `.github/workflows/ci-slash-commands.yml` — the loop pattern.
> - `action/adapt.py`, `action/report.py`, `action/flaky_history.py`, `action/cache_key.py`,
>   `scripts/ci_slash_commands.py` — **zero GitHub imports, reuse unchanged** (the §5.5 insurance).
> - `scripts/ci_action_selftest.py` + `.github/workflows/ci-cd-action.yml` — the hermetic self-test pattern.
>
> Implementation notes:
> 1. The GitLab surface: `ci/platform/gitlab.py` (MR note REST: list/find-by-marker/create/edit, replies;
>    the GitLab.com API base is injectable for hermetic tests, same as github.py). Reuse the same markers
>    (`## 🤖 AI Test Generator`) so edit-not-duplicate works identically.
> 2. `.gitlab-ci.yml` include template: same three modes (generate-only / generate-and-run / run-existing)
>    + the internal slash-command job; `cache:` key = the `action/cache_key.py` formula (import it);
>    `artifacts:` for junit.xml / junit-evidence.xml / evidence bundle; protected-environment approvals for
>    the danger-zone path.
> 3. Test against a real GitLab.com project (credentials available), mirroring the GitHub self-test. Keep the
>    mock-API gate pattern for MR-note shape assertions.
> 4. Write `docs/ci.md` (modes, when to adapt — shared vs isolated envs, ignore-list format, education).
> 5. DoD: Roadmap Phase 7 → `[x]`, session doc in `docs/sessions/`, both workflows green.
