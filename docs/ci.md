# CI/CD Integration — configuration reference

> **Status:** shipped — Phase 7 (GitHub Action **7a/7b** + GitLab parity **7c**).
> Spec: `docs/specs/FEATURE_SPEC_phase7_ci_cd_integration.md`. This page is the
> configuration reference (modes, when to adapt, ignore-list format) — the
> one-line education lives in the generated report itself.

The product generates Playwright Python tests from a user story. The CI
integration runs the **same generation pipeline** (the same
`ui_pipeline.run_pipeline()` the UI and CLI use) headlessly inside your
pipeline, executes the generated tests through pytest with the evidence
tracker, and reports results on your pull/merge request. Everything is
hermetic by default: generation targets **staging** URLs only, and the
action's own self-test runs against local mocks with a fake LLM — zero
external services.

Platforms:

| Platform | Surface | Trigger |
|---|---|---|
| **GitHub Actions** | `.github/workflows/` + the Docker action (`action.yml`, `action/entrypoint.sh`) | `workflow_dispatch` / `push` / `pull_request` / `issue_comment` (slash commands) |
| **GitLab CI** | `ci/gitlab-ci.template.yml` include template | MR pipelines / default-branch pushes / manual (slash commands) |

The two platforms share the **same hermetic core** (driver, report, adaptation
engine, cache-key formula, slash-command parser) behind a thin platform seam
(`ci/platform/github.py`, `ci/platform/gitlab.py`) — the §5.5 insurance.

---

## 1. Modes

| Mode | What it does | LLM needed? | When to use |
|---|---|---|---|
| `generate-only` | Generates a test package from the story (no execution). The package is a build artifact. | Yes | You want tests, not a verdict. |
| `generate-and-run` (default) | Generates (or restores from cache) → pytest (**referee** exit) → evidence JUnit → report + flaky markers → PR/MR comment → artifacts. | Yes (first run only — the cache serves repeats) | The full loop; the default. |
| `run-existing` | Runs a caller-provided package (checked-in or previously generated) through pytest + evidence. | No | Regression gate on an existing suite; teams that review generated code before running it. |

**Exit codes** (the referee contract): the job exits with pytest's exit code —
0 green, non-zero when any test fails. Failures are *your change*, not the
tool's opinion. CI never mutates silently.

## 2. GitHub Action

```yaml
- uses: tancat-ai/tancat/ai-test-generator@v1   # (or ./, in-repo)
  with:
    mode: generate-and-run
    story: |
      As a customer, I want to browse products, add them to my cart,
      proceed to checkout, and place an order.
    url: https://staging.example.com        # staging only (allow-list)
    provider: openai-local
    llm-base-url: http://localhost:8080/v1  # LM Studio / llama.cpp
    llm-api-key: ${{ secrets.LLM_API_KEY }} # cloud providers only
    workspace: ai-test-workspace
    # posting (omit to write the payload without posting)
    repo: ${{ github.repository }}
    pr-number: ${{ github.event.pull_request.number }}
    github-token: ${{ secrets.GITHUB_TOKEN }}
```

Key inputs (full list in `action.yml`): `mode`, `story`, `url`, `tests`
(run-existing), `pom`, `provider`, `model`, `llm-base-url`, `llm-api-key`,
`credential-profile`, `ignore-file`, `danger-zone`, `allowed-domains`,
`pytest-args`, `cache`, `cache-dir`, `comment`, `adapt`, `learn`, `platform`.

## 3. GitLab CI (Phase 7c)

```yaml
# .gitlab-ci.yml
include:
  - local: ci/gitlab-ci.template.yml

variables:
  AITEST_STORY_FILE: "ai-test-story.md"   # story markdown, versioned in-repo
  AITEST_URL: "https://staging.example.com"
  AITEST_LLM_BASE_URL: "http://host.docker.internal:8080/v1"
```

Set `AITEST_GL_TOKEN` (GitLab PAT, `api` scope — MR-note posting) as a
**masked project CI/CD variable**. The template provides:

- `ai-testgen:build-image` — builds/pushes the action image to the project
  registry (set `AITEST_SKIP_BUILD: "true"` for repeat runs);
- `ai-testgen:compute-key` — computes the §7 cache key (dotenv report);
- `ai-testgen:run` — the three modes driven by `AITEST_MODE`; MR notes are
  posted idempotently (one note per marker, edited not duplicated); the raw
  pytest JUnit feeds GitLab's **native MR test UI** (`reports:junit`);
- `ai-testgen:slash-command` — **manual** job (see §7).

Differences from GitHub worth knowing:

- **Variables can't contain hyphens.** The template sets the underscore
  spellings (`INPUT_GITLAB_TOKEN`, `INPUT_LLM_BASE_URL`, …) the entrypoint
  falls back to — that's why the hyphen/underscore fallback exists.
- **`GITHUB_WORKSPACE` is a convention, not a GitHub thing.** The template
  sets it to `$CI_PROJECT_DIR`; the action treats it as the repo root.
- **GitLab evaluates `cache:key` after collecting `needs`' artifacts**, so
  the compute-key dotenv feeds the cache key — one source of truth, same as
  GitHub's compute-step.
- **No `issue_comment` pipeline trigger on free tier** → the slash-command
  job is manual (arguably safer: a human reviews the failure before
  dispatching `/adapt`). A note-event webhook can trigger it via the pipeline
  trigger API with `AITEST_SLASH_COMMENT` set.
- **Approval gates** use GitLab's protected environments: set
  `AITEST_ENV_SUFFIX: prod` (with `AITEST_DANGER_ZONE: true`) and protect the
  `ai-testgen-prod` environment → a human approver must approve before the
  runner starts.

## 4. The PR/MR comment

One idempotent comment per commit: looked up by the
`## 🤖 AI Test Generator` marker and **edited, never duplicated** — on both
platforms. Shape (spec §6): mode/site/model context line, a metric table
(tests, conditions, resolved placeholders, duration), flaky markers from the
cached per-branch run history, the evidence bundle, the failed-tests list,
and the repair-candidate block with the `/adapt` + `/ignore` one-liners.

## 5. Verified adaptation — when it's right (the education)

CI never fixes tests on its own. After a failure it offers (never applies)
**verified adaptation**:

> Locator-class failures only. The engine parses the failure, re-resolves the
> step's semantic label with the product's own resolution machinery (no LLM),
> patches the locator, **re-runs only that test**, and keeps the patch only if
> the test's own assertions still pass — otherwise it reverts. Every attempt
> is recorded in `adaptation.json` and surfaced in the thread.

**When to enable `adapt: true` (repo-level) — the environment-topology rule:**

| Environment | Default | Why |
|---|---|---|
| **Isolated** (each tester / change gets its own staging) | Keep adaptation **off** (referee only) | Failures are deterministic and yours. Adaptation would hide real regressions. |
| **Shared** (many testers, one staging box) | Consider `adapt: true` | The env is already non-deterministic (others' in-flight work moves buttons). Adaptation *restores* determinism instead of destroying it. |

Prefer the **`/adapt` slash command** in both cases when the failure is a
one-off — it's the human deciding, per failure, that this is churn.

**The hard boundary:** assertion failures never reach the engine. A patch
survives only if the test's own assertions still pass. Weak assertions ⇒ weak
verification — that's the point of the locator-only rule.

## 6. The ignore list (`.ai-test-ignore.yml`)

The "button moved but still works" mechanism — versioned, human-recorded,
zero test mutation:

```yaml
ignores:
  - test: "test_08_checkout*"
    reason: "checkout button moved into the new header, verified still functional 2026-08-14"
    match: "Locator '.*' not found"   # optional regex on the failure message
```

- `test` — fnmatch glob on the test name.
- `reason` — **required** (the anti-rug rule). An ignore without a recorded
  why fails at parse time; the report surfaces every ignore, never silently.
- `match` — optional regex scoping the ignore to a failure message; empty =
  any failure of a matching test.

CI reports "N known-benign ignored". `/ignore <test>` in the PR/MR thread
renders the exact entry (with a suggested `match`) for you to commit.

## 7. Slash commands

| Command | What happens |
|---|---|
| `/adapt <test>` | Runs verified adaptation on the named test (patch → re-run → assertion gate → keep-or-revert) and posts the result as a reply. |
| `/ignore <test>` | Renders the exact `.ai-test-ignore.yml` entry to commit (reason required) and posts it as a reply. The bot never mutates the repo. |

- **GitHub:** `.github/workflows/ci-slash-commands.yml` — `issue_comment`
  trigger, PR-only, fork-PR guarded (never `pull_request_target`).
- **GitLab:** manual `ai-testgen:slash-command` job — fetches the most recent
  `/adapt`/`/ignore` comment on the MR via the adapter and posts the reply
  (see §3).

## 8. Cache

Generated packages and per-branch run history are cached between runs (the
package cache is the "don't regenerate the same story twice" mechanism;
run history feeds the flaky markers).
Key = `sha256(story + url + model + provider + prompt-fingerprint)` — one
source of truth (`action/cache_key.py`) shared by the workflow's cache steps
and the action's internal cache-dir check. The fingerprint constant bumps
whenever generation prompts change, so a prompt tweak invalidates every
cached package at once (stale cache would mask regressions). `cache: false`
forces fresh generation (CI users who never want a cached package).

- **GitHub:** `actions/cache` — run-specific key for deterministic misses in
  the self-test; branch-scoped run-history key for flaky markers.
- **GitLab:** `cache:key` = branch + compute-key dotenv; `fallback_keys`
  provide the branch snapshot for slash-command runs.

## 8b. Learning (`learn: true`) — the opt-in "diary"

`learn: true` (generate-and-run only, **default off**) writes navigation
flows from **passing** run steps into a flow-memory store so future
generation for the same site resolves better. It is the same learning loop
as the UI/CLI (the generated package's conftest teardown) — CI finally
behaves like the interactive product. It never touches test code: it writes
the "diary" only.

- **Flow memory only; RAG is OFF in CI.** The RAG leg (locator learning)
  needs an ~80 MB embedder model download per runner — a poor trade for a
  runner that will cache anyway. Flow memory (navigation *shape*: login →
  browse → cart → checkout) transfers across sites and needs no model
  download, so that is what CI learns. With `learn: true` the action exports
  `RAG_ENABLED=0` and the conftest's RAG write leg is gated on it too — no
  `rag_store.db`, no embedder download on the runner (the UI/CLI keep RAG
  learning; this is a CI-only policy).
- **Store location:** `<workspace>/evidence/flow_memory.json`. The action
  points the lazy storage singleton at the runner-mount workspace, so the
  conftest writes the store exactly where your cache step persists it:
  - GitHub: branch-scoped `actions/cache` key `ai-testgen-flowmem-${{ github.ref }}`;
  - GitLab: add `ai-test-workspace/evidence/flow_memory.json` to `cache: paths`
    (branch-scoped — MR pipelines reuse the push pipeline's store).
  A restored store is loaded and merged (dedup + hit bumps), never
  overwritten.
- **Saturation is expected.** A stable package vs a stable site learns most
  new patterns on the first green run; later runs dedup and reinforce (hit
  counts). The value is consistency + first-run seeding — a NEW story on the
  same site later resolves better. That modest, consistency-driven value is
  why it is opt-in and default off.
- **Within-test flows only.** Suite-level chains (terminal of test N → entry
  of test N+1) need the UI/CLI post-run hook and are deliberately not
  learned by the action.
- **Reporting:** on a green run the action logs the store stats and emits
  `flow_store` / `flow_patterns` / `flow_sites` outputs (learned-count
  reporting for workflow steps / the self-test). A red run reports the
  failure, not learning bookkeeping.

## 9. Danger zone + approval gates

The action targets **staging only** (allow-list: `localhost`, `127.0.0.1`,
`*.staging.*`, `*-dev.*`, `*.test.*`). Anything else fails fast unless:

- `danger-zone: true` — explicit override, reviewable in the workflow file
  (legitimate for **read-only** prod smoke/load tests — keep mutating stories
  in staging), **and**
- an **approval gate**: GitHub `environment` (protected → human approval) /
  GitLab protected environment (`ai-testgen-prod`).

The action is friction + visibility; org policy (branch protection on
`.github/workflows/`, required reviewers, protected environments) is the real
enforcement.

## 10. Security notes

- **Fork PRs unsupported, never `pull_request_target`** (GitHub) / fork MRs
  excluded by default (GitLab) — fork runs carry no upstream secrets.
- Token scopes: GitHub `contents: read`, `pull-requests: write`,
  `actions: read`; GitLab PAT `api` (masked variable).
- LLM keys are secret inputs, never logged; no secrets in comments/artifacts.
- Adaptation is assertion-gated and recorded; ignores are versioned with a
  required reason. **CI never changes tests without a visible, explicit human
  action** (or a repo-level `adapt: true` commit).
- `learn: true` writes only the flow-memory store (opt-in; see §8b) — it
  never mutates tests or branches, and it is distinct from self-healing
  (which CI deliberately rejects: the referee must not hide regressions).

## 11. Testing & self-test

- Unit tests: `tests/test_ci_*.py` (driver, ignore list, cache key,
  report, flaky history, slash commands, adaptation engine, **GitHub +
  GitLab platform adapters against mock API servers**).
- Hermetic self-test (GitHub CI + locally): `.github/workflows/ci-cd-action.yml`
  and `scripts/ci_action_selftest.py` — the action ITSELF against the mock
  sites + fake LLM, with stub-asserted comment shapes and a host-side mock
  API for real POST/PATCH/PUT traffic (GitLab MR notes included). The
  `learn: true` gates seed the store on a passing run and prove a restored
  store survives a re-run (merge, not overwrite) — the branch-cache
  contract.
  `python scripts/ci_action_selftest.py` (≈15 min cold, ≈10 min no-build).
- **Real GitLab.com gate (passed 2026-08-15)**: `scripts/ci_gitlab_real_project_test.py`
  — runs the template end-to-end against a real GitLab project (needs a
  `GITLAB_TOKEN` with `api` scope in `.env`; the account must pass GitLab's
  identity verification to use shared runners). 14/14 live checks: push
  pipeline + junit artifact + cache miss, MR §6 note posted + edited-not-
  duplicated, cache hit on re-run.
- The eval harness gate (`scripts/eval/eval_harness.py`) covers resolution
  accuracy — run before shipping pipeline/resolver changes.
