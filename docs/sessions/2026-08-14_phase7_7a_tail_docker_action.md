# 2026-08-14 — Phase 7 7a tail: Docker action (generate-only + run-existing) + hermetic self-test

**Roadmap:** Tier 5 §14 (Phase 7 CI/CD Integration — Commercialization).
**Spec:** `docs/specs/FEATURE_SPEC_phase7_ci_cd_integration.md` (grilled, all decisions closed).
7a core shipped 2026-08-13 (headless driver, fake LLM, ignore list, workspace fix); **this session shipped the 7a tail** — the Docker action and its self-test. 7a is now complete; 7b next.

## Problem

The 7a core gave the product its first headless entry point (`scripts/ci_generate.py`), but nothing consumed it from CI. The tail per spec §8/7a + §10: package the action (`action.yml` Docker action with `generate-only` + `run-existing`), emit JUnit artifacts (pytest-native + AI-028 evidence), mark repair candidates in the report (no adaptation execution — that's 7b), and hermetically self-test it against the mock sites + fake LLM. Implementation notes from the parent session: the action needs its own image (product Dockerfile's CMD runs Streamlit); run-existing lives in the action, not the driver; Docker must be available locally, GitHub verifies.

## What shipped

| File | Purpose |
|---|---|
| `action.yml` (repo root) | Docker action metadata — 16 inputs (mode/story/tests/url/workspace/pom/provider/model/llm-*/credential-profile/ignore-file/danger-zone/allowed-domains/pytest-args + internal `self-test`). `generate-and-run` fails fast with a clear message — arrives in 7b. |
| `Dockerfile.action` (repo root) | Action image: uv-built **3.14** venv on `python:3.14-slim`; Chromium installed from the venv's own playwright (browser version always matches uv.lock). |
| `action/entrypoint.sh` | Thin orchestrator over the driver. `generate-only` (driver + JSON contract + `GITHUB_OUTPUT`); `run-existing` (pytest `--junitxml` + AI-028 evidence JUnit + report; **referee exit code** = pytest's). Self-test mode boots mock site + fake LLM inside the container. |
| `action/report.py` | Platform-neutral core: JUnit → counts + **repair-candidate marking** (locator-class failures only; 7a scope = marking, no adaptation); writes `report.json` + `report.md` in the §6 comment shape. |
| `action/export_evidence_junit.py` | Platform-neutral core: AI-028 evidence sidecars → enriched JUnit (condition/story refs, per-step failures). |
| `.github/workflows/ci-cd-action.yml` | Hermetic self-test: generate-only → stub asserts (exit code, driver JSON contract, package artifact) → run-existing → stub asserts (junit + evidence-junit well-formed, report payload shape). Artifacts uploaded. |
| `scripts/ci_action_selftest.py` | The same 9-gate self-test **locally via Docker** (GitHub's `INPUT_*`/`GITHUB_WORKSPACE` env surface, hyphenated inputs). |
| `scripts/ci_generate.py` | Gained `--storage-root` (action passes `$GITHUB_WORKSPACE` so artifacts persist to the runner mount). |
| `.dockerignore` | Hardened: measured **7.3 GB → 20 MB** build context (heavy history, docs/tests/dev tooling, root strays). |

Tests: +16 (2 storage-root, 11 report, 5 parametrized repair-pattern cases, 3 evidence-junit). Full suite **2526 passed / 1 skipped**, smoke 38/38, ruff + mypy clean, eval static 97.9%.

## GitHub-side findings (only GitHub's own runner could catch these)

Each was found by the self-test workflow failing, fixed with a targeted commit, re-verified. **All four are gotchas the 7b/7c sessions must not re-derive:**

1. **`action.yml` must live at the repo root** for `uses: ./` — the action root is the repo root; a file in `action/` is silently ignored (GitHub falls back to the root `Dockerfile` + default `entryPoint`/`args` inputs).
2. **GitHub builds a Docker action's image with the Dockerfile's own directory as the build context** (not the repo root) — so the image is `Dockerfile.action` at the root, where `COPY pyproject.toml/src/...` resolves. Verified empirically from the workflow log's `docker build -f ...` line.
3. **Input env vars are hyphenated, not underscored**: GitHub sets `INPUT_SELF-TEST`, `INPUT_LLM-BASE-URL`, etc. (spaces → `_`, hyphens preserved). Parameter expansion can't reference hyphenated names — the entrypoint reads them via a `get_input()` helper (`printenv` on the hyphen form, `_` form fallback for local runs). The local Docker self-test sets the hyphen forms so local == GitHub.
4. Two workflow bugs of my own: the workspace dir is `ai-test-workspace` (no leading dot) everywhere, and stub-2's count check must include skipped tests (`passed+failed+errors+skipped == total`).

**Image-build fixes (also latent in the product `Dockerfile` — documented in BACKLOG, product image NOT touched):**
- `uv sync` before `src/` exists builds an **empty project wheel** (no `src` importable) → two-phase sync: `--no-install-project` first, `COPY . .`, then sync again with `src` present.
- uv prefers its **managed CPython** by default; the venv's `bin/python` symlinks into `/root/.local/share/uv/python/...` which doesn't exist in the runtime stage → `UV_PYTHON_PREFERENCE=only-system` + explicit `--python /usr/local/bin/python3` on both syncs.
- The mcr playwright/python image ships **python 3.10**; the repo requires ≥3.14 (PEP 758 exception syntax) → runtime is `python:3.14-slim` with `playwright install --with-deps chromium` from the venv (browser matches uv.lock = 1.61.0, not the image's stale 1.50).
- `ENV PATH` inside a `RUN` can't be relied on → use explicit `/app/.venv/bin/python` in the Dockerfile; the entrypoint also re-prepends the venv to PATH itself.

## Verification

- Local: `scripts/ci_action_selftest.py` **9/9** (image build + generate-only 8 tests/~138s + run-existing 8 tests 6 passed 2 skipped, junit + evidence-junit well-formed, report shape OK) — run repeatedly after each fix.
- GitHub (final commit `b993959`): **CI/CD Pipeline ✓** (all 9 gates) and **CI/CD Action Self-Test ✓** (~8 min; both artifacts uploaded: `generated-tests`, `run-existing-artifacts`).

## Housekeeping

- BACKLOG top entry: 7a → complete (core + tail), remaining = 7b then 7c. CHANGELOG [Unreleased], kanban.html regenerated, scripts/README.md (new scripts), graphify update, `.gitignore` (both workspace spellings), gitignored root strays deleted (`nul`, 0-byte `run_results.sqlite`, `streamlit*.log`).
- History: 7 commits on main (`16c94d3` feature + 6 fixes). **Squash offer still open** — requires force-push to main (explicit permission needed per AGENTS.md).
- `fix.sh` + `notebook_upload.md` are intentionally tracked (earlier sessions) — left in the repo, excluded from images only.

## Notes for 7b (next session)

- **Wiring point:** `action/entrypoint.sh` — the `generate-and-run` mode branch currently fails fast ("arrives in Phase 7b").
- `action/report.py` already emits the §6 comment payload (report.json/report.md) — 7b posts it as the idempotent PR comment (`## 🤖 AI Test Generator` marker, edit-not-duplicate — same pattern `scripts/cli_walkthrough.py` uses).
- Keep the platform seam (§5.5): report/export cores have zero GitHub imports; the GitHub surface stays in entrypoint.sh. GitLab adapter (7c) reuses the cores unchanged.
- The self-test workflow is the template: 7b additions (comment assertion via stub, cache, slash-commands) slot in alongside.
- Flaky markers (AI-011) come from the action's own cached per-branch run history; `learn`/`adapt`/`cache` inputs exist in the spec but are 7b. Ignore-list matching against failures is also 7b (`src/ci_ignore.py` matcher is already implemented).

## Next session (7b)

Spec §8/7b: `generate-and-run` wiring; PR comment with summary + flaky markers + evidence bundle upload; `actions/cache` (key = story-hash + model + prompt fingerprint); slash-command loop (`/adapt`, `/ignore`); **verified adaptation engine** (locator-only patch → re-run → assertion gate → keep-or-reject, transparent reporting). Then 7c: GitLab parity (`.gitlab-ci.yml` template + platform adapter + `docs/ci.md`).

---

## Fresh-context kickoff message (7b)

> **Phase 7 7b — generate-and-run: PR comment, cache, slash-commands, verified adaptation.**
>
> Start here:
> 1. `docs/specs/FEATURE_SPEC_phase7_ci_cd_integration.md` — read §5.3/§5.4 (generate-and-run inputs + pipeline), §6 (PR comment format), §7 (caching key), §8 (7b row = exactly this scope), §11 (grilled decisions), §12 (DoD). All decisions closed — nothing left to grill.
> 2. `BACKLOG.md` top entry — 7a complete; 7b scope + session context.
> 3. `docs/sessions/2026-08-14_phase7_7a_tail_docker_action.md` — the previous session's record + the four GitHub gotchas you must not re-derive (action.yml at repo root; Dockerfile build context = its own dir; hyphenated INPUT_* env vars; workspace dir name).
>
> Reference files:
> - `action/entrypoint.sh` — the `generate-and-run` mode branch currently fails fast ("arrives in Phase 7b") — that is the wiring point. Self-test mode + `get_input()` helper + GITHUB_OUTPUT pattern already there.
> - `action/report.py` — already emits the §6 comment payload (report.json/report.md, repair candidates) — 7b posts it (idempotent `## 🤖 AI Test Generator` marker, edit-not-duplicate; see `scripts/cli_walkthrough.py`).
> - `action/export_evidence_junit.py` — AI-028 evidence → JUnit, done.
> - `src/ci_ignore.py` — ignore matcher already implemented; wiring failures against it lands in 7b.
> - `.github/workflows/ci-cd-action.yml` + `scripts/ci_action_selftest.py` — the hermetic self-test pattern; extend, don't fork.
> - `src/run_history_cli.py` / AI-011 run history — flaky-marker source (cached per-branch history, default-branch fallback).
>
> Implementation notes so you don't re-derive them:
> 1. Keep the platform seam (§5.5): comment posting, cache, slash-command loop live behind the GitHub surface in entrypoint.sh / a `ci/platform/github.py` adapter; report/export cores stay GitHub-free (GitLab parity is 7c and must reuse them unchanged).
> 2. The action's PR comment needs `pull-requests: write` token scope — currently the workflows are `contents: read` only; that's a deliberate diff to make.
> 3. `actions/cache` key = sha256(story + url + model + provider + prompt-fingerprint) — a constant bumped when generation prompts change (AI-042-F4 lesson). Cache restore before pytest; `cache: false` input to disable.
> 4. Verify locally via `scripts/ci_action_selftest.py` (Docker present) before pushing; the self-test workflow verifies on GitHub. Never silent-degrade an unimplemented mode — fail fast with a clear message (the existing `generate-and-run` branch is the precedent).
> 5. DoD: self-test asserts the comment payload shape via a stub step (no real PR); verified adaptation is assertion-gated and locator-only (spec §9.6) — never default, `/adapt` or repo-level `adapt: true` only.
