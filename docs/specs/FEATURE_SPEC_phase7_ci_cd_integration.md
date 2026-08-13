# Feature Spec — Phase 7: CI/CD Integration (GitHub Action)

**Feature ID:** Phase 7
**Created:** 2026-08-13
**Status:** Draft
**Priority:** Medium-High (Tier 5 — Commercialization; roadmap "deferred" until now)
**Depends on:** AI-028 (Evidence Export — JUnit XML, shipped), AI-029 (Workspace & Storage — shipped), AI-011 (Run History — flaky markers, shipped), AI-020/AI-022 (heatmap + evidence bundle, shipped), export-gate golden-fixture pattern (`scripts/export_gate.py`, shipped)
**Roadmap ref:** `docs/plans/ROADMAP_ROADTO_PRODUCTION.md` Tier 5 §14
**Estimated sessions:** 2-3 (MVP = 1)

---

## 1. Problem Statement

Teams don't run test-generation tools manually — they want generation, execution, and results in their existing pipeline. Today the tool has:

- A Streamlit UI and an **interactive-only** CLI (`src/cli/main.py` is menu-driven; every path funnels through `input()` prompts — verified 2026-08-13, no `argparse` flags, no `[project.scripts]` entry points).
- Standard exports (AI-028: CSV / NDJSON / **JUnit XML**) that *nothing consumes*.
- A mature evidence chain (sidecars, HTML report, coverage heatmap AI-022, flaky detection AI-011, workspace isolation AI-029) — all locked inside the Streamlit app.

**The gap:** no headless, scriptable entry point and no CI integration. The JUnit exporter (AI-028's flagship CI format) has zero consumers. Enterprise adoption ("automated test generation in CI") is the stated impact of this roadmap item and it doesn't exist.

---

## 2. Philosophy: CI-Native, Hermetic, Self-Testable

1. **Standard artifacts only.** The Action's outputs are JUnit XML, an evidence bundle (HTML + screenshots), and a PR comment. No proprietary formats, no repo lock-in.
2. **Hermetic by default.** Generation targets the caller's staging site, not a live production site (see §9). The Action's own self-test runs against the **mock-site family** (`mock_sites/banking|ecommerce|lv_insurance`) — deterministic localhost, never decays — plus a **fake LLM fixture** so the generate path is exercisable with zero external services.
3. **Reuse the shared orchestration, not the menus.** Generation goes through `src/ui_pipeline.run_pipeline()` — the same function Streamlit and the CLI already call — via a new thin headless driver. No new pipeline logic.
4. **The Action is a thin wrapper.** All behaviour lives in this repo (scripts + Docker image) so it's testable with pytest, not only via GitHub.
5. **Referee by default, human at the decision points.** CI executes automatically but never mutates silently: no self-healing and no learning (defaults), and verified adaptation is *offered* after a failure, never auto-applied. **Environment topology decides the mode** (resolved in grilling 2026-08-13): isolated per-tester envs want the pure referee (failures = your change; adaptation would hide regressions); shared envs (many testers, one staging) want verified adaptation to filter others' churn — the env is already non-deterministic there, so adaptation *restores* determinism instead of destroying it.

---

## 3. Goals

| # | Goal | Criteria |
|---|------|----------|
| 1 | **Headless generation driver** | `scripts/ci_generate.py --story story.md --url https://staging... --workspace <dir>` runs the full pipeline (spec-analyze → plan → skeleton → scrape → resolve → emit) without any `input()` prompt; exits 0/non-zero; writes a `generated_tests/` package. |
| 2 | **GitHub Action: `generate-only` mode** | `uses: AI-Playwright-Test-Generator/ai-test-generator@v1` with `mode: generate-only` produces a generated test package as a build artifact, no test execution. |
| 3 | **GitHub Action: `generate-and-run` mode** | Generates, runs pytest with the evidence tracker, produces JUnit XML + evidence bundle, posts a PR comment with pass/fail summary, and uploads artifacts. |
| 4 | **GitHub Action: `run-existing` mode** | Runs a checked-in / previously generated package (`tests` input path) through pytest with evidence; JUnit + comment. No LLM needed. |
| 5 | **JUnit XML output** | Consumable by GitHub Actions' `dorny/test-reporter` / Jenkins / GitLab. Use AI-028 `export_junit_xml()` for enriched evidence (condition/story refs); `pytest --junitxml` as the raw fallback. |
| 6 | **PR comment** | Markdown summary: pass/fail/skip counts, flaky-test markers (AI-011 history), link to evidence bundle artifact. Comment is idempotent (one comment per commit, updated). |
| 7 | **Cache generated tests** | `actions/cache` keyed on story-hash + model name + prompt fingerprint; `generate-and-run`/`run-existing` reuse cache; cache miss regenerates. |
| 8 | **Workspace isolation** | Each job writes to its own AI-029 workspace (e.g. `$RUNNER_TEMP/ai-test-workspace`) — parallel jobs never collide; no `generated_tests/` pollution of the checked-out repo. |
| 9 | **Hermetic self-test** | A CI workflow in this repo runs the Action against the mock sites + fake LLM and asserts: exit codes, JUnit well-formedness, artifact presence, comment payload shape. Mirrors `export_gate.py`'s golden pattern. |
| 10 | **GitLab CI template** (Phase 7c) | `.gitlab-ci.yml` include template with the same three modes, using the same headless driver. |
| 11 | **Verified adaptation (`adapt`)** | Locator-class failures only; patch + re-run; patch kept only if the test's own assertions still pass; reported transparently. Never default — offered post-failure (`/adapt`) or configured repo-level (`adapt: true`) for shared-env teams. |
| 12 | **Ignore list (`.ai-test-ignore.yml`)** | Versioned known-benign failures recorded in-repo; CI reports "N known-benign ignored". Human-recorded, reviewable, zero test mutation. **`reason` is required per rule** (the anti-rug rule — an ignore without a recorded why is rejected at parse time; the report surfaces every ignore, never silently). |
| 13 | **Learning opt-in (`learn`)** | Write patterns from passing runs into the cached flow-memory/RAG store (generate mode only — improves future generation, never touches test code). Default off. |

---

## 4. Non-Goals

- **Not a SaaS backend.** The Action is user-hosted; no cloud account of ours is required (Phase 6 is the separate SaaS track).
- **No new generation logic.** Pipeline behaviour (skeleton, resolution, self-heal) is unchanged; this feature only adds a scriptable front door + CI packaging.
- **No product rename.** The Action name below is provisional — the P0 repo/PyPI rename is deferred to launch readiness (AI-039). When the repo renames, the Action's owner reference updates with it.
- **No automated test-fixing in CI.** Self-healing stays interactive; CI only reports.
- **No cross-CI runners beyond GitHub + GitLab template** (GitHub first, GitLab as template).
- **No Docker image distribution outside the Action** (the existing `Dockerfile` is reused as the Action's image).

---

## 5. Architecture

### 5.1 The missing piece: a headless driver

Verified 2026-08-13: `src/cli/main.py` is a menu loop (30+ `input()` call sites), the root `cli/main.py` is a shim into `src.cli.main`, and `pyproject.toml` has **no** `[project.scripts]`. There is no scriptable generation entry point.

**Solution — `scripts/ci_generate.py`** (thin, ~150 lines, no pipeline changes):

```
story file(s) ──► Session-like config  ──► src.ui_pipeline.run_pipeline(...) ──► package dir
                  (dataclass: url, mode,  (shared orchestration —              (generated_tests/
                   pom, consent, provider,  identical code path the UI/CLI use)   <workspace>/...)
                   model, workspace, …)
```

- Reuses the same `Session` dataclass fields the CLI seeds from the settings store (B-036 Phase 4), so provider/model/workspace come from the same precedence chain (settings store → env → defaults).
- `--json` output on stdout: `{package_dir, test_count, skeleton_count, duration_s, resolutions: {resolved, skipped}}` — parseable by the Action wrapper.
- Exit codes: `0` generated, `1` generation error, `2` config error (no LLM endpoint, bad story path).
- Also gains `--list-stories` to render a story template (documented input format) — the Action's `story` input can be an inline string or a path.

### 5.2 Action packaging: Docker action

**`action.yml`** — a Docker action whose image is built from the repo's existing `Dockerfile` base (`mcr.microsoft.com/playwright/python`, already used for Phase 4), with `uv` + Playwright chromium preinstalled. Docker actions give deterministic deps/browser versions and need zero per-runner Python setup. The entrypoint script (`entrypoint.sh`) is a small orchestrator over `scripts/ci_generate.py` + pytest + the exporter.

### 5.3 Inputs (`action.yml`)

| Input | Default | Purpose |
|-------|---------|---------|
| `mode` | `generate-and-run` | `generate-only` \| `generate-and-run` \| `run-existing` |
| `story` | *(required for generate modes)* | Inline story markdown or path to a story file in the repo |
| `tests` | *(required for `run-existing`)* | Path to an existing generated test package or test file(s) |
| `url` | *(required for generate modes)* | Target site URL — **staging only** (see §9) |
| `danger-zone` | `false` | Explicit override to target a non-allow-listed URL (prod smoke/load testing). Reviewable in the workflow file; org governance is the real control (branch protection, env approvals). |
| `allowed-domains` | *(empty)* | Deliberate extension of the safe allow-list (internal staging names like `app.internal.company.com`). |
| `environment` | *(empty)* | Optional GitHub `environment` name (e.g. `ai-testgen-prod`) — routes prod-targeting runs through GitHub's human-approval gate (the "ticket required" path). |
| `pom` | `false` | Page Object Model mode |
| `provider` | `openai` | `openai` (cloud) \| `openai-local` \| `lm-studio` \| `ollama` |
| `model` | *(provider default)* | Model name |
| `llm-base-url` | *(provider default)* | OpenAI-compatible base URL (for local endpoints) |
| `llm-api-key` | `''` | Secret input — passed from `secrets.` |
| `credential-profile` | `''` | Login credentials for sites that require a session (JSON or path; feeds the existing credential-profile machinery) |
| `workspace` | `$RUNNER_TEMP/ai-test-workspace` | AI-029 workspace dir |
| `pytest-args` | `-q --tb=short` | Extra args to the generated-suite run |
| `cache` | `true` | Enable `actions/cache` on generated packages |
| `comment` | `true` | Post PR summary comment |
| `adapt` | `false` | Verified adaptation: locator-class failures are patched + re-run; keep only if assertions still pass. Never default — enabled per-run via `/adapt` or repo-level (`adapt: true`) for shared envs. |
| `ignore-file` | `.ai-test-ignore.yml` | Path to the versioned ignore list (repo root default); `none` disables. |
| `learn` | `false` | Write patterns from passing runs into the cached flow-memory/RAG store (generate mode only — improves future generation, never mutates tests). Requires store caching. |
| `junit` | `true` | Emit JUnit XML artifact |
| `evidence-bundle` | `true` | Emit HTML report + screenshots artifact (AI-020/022) |

### 5.4 Pipeline inside the Action (generate-and-run)

```
checkout (contents: read)
   │
   ├─ [generate modes] run ci_generate.py --story … --url … --workspace …
   │        │  (LLM endpoint from inputs; fails fast with clear message if unreachable)
   │        ▼
   │   package dir  ◄── actions/cache (key: story-hash + model + prompt-fingerprint)
   │
   ├─ pytest <package> --junitxml=junit.xml  (with generated_tests/conftest.py evidence teardown)
   │
   ├─ [generate-and-run] export_junit_xml() from sidecars  →  junit-evidence.xml  (AI-028)
   │        (sidecars > pytest raw: condition/story refs, per-step failures)
   │
   ├─ evidence bundle: HTML report (PipelineReportService) + coverage heatmap (AI-022)
   │
   └─ PR comment (see §6)  ──► upload artifacts (junit.xml, junit-evidence.xml, evidence-bundle/)
```

### 5.5 Platform seam (GitHub ↔ GitLab, and future platforms)

The **driver + reporting core is platform-neutral** (`ci_generate.py`, JUnit generation, ignore-list, summary computation, adaptation engine — zero GitHub imports). The **platform surface** — comment posting, slash-command loop, caching, artifacts, danger-zone/approval gates — sits behind thin adapters (`ci/platform/github.py`, `ci/platform/gitlab.py`) so a second (or third) platform is a skin swap, not a fork. This is the insurance that makes GitLab parity cheap and future-proofs against further platform churn (resolved in grilling 2026-08-13: GitHub reputation risk — GitLab is a hedge, not an afterthought).

---

## 6. PR Comment Format

One idempotent comment per commit (looked up by `## 🤖 AI Test Generator` marker; edited, not duplicated — same pattern `scripts/cli_walkthrough.py` uses for markers).

```markdown
## 🤖 AI Test Generator — results

**Mode:** generate-and-run · **Site:** https://staging.example.com · **Model:** gpt-… 

| Metric | Value |
|---|---|
| Tests | 12 (11 passed · 1 failed · 0 skipped) |
| Conditions | 12/12 skeletonized |
| Resolved placeholders | 34/36 |
| Duration | 148s |

**Flaky (last 3 runs):** test_checkout[chromium] (2 failures) — [history](…)  ← AI-011

<details><summary>📸 Evidence bundle</summary>
[html-report](artifact) · [junit.xml](artifact) · heatmap preview
</details>

**Failed tests:** `test_08_checkout[chromium]` — Locator '…' not found …

**Repair candidates** (offered, never auto-applied): 2 failures are locator-class — mechanical, often environment churn in shared environments. One line: reply with a command, or open the package in the app for full interactive repair (see `docs/ci.md` for when adaptation is right):
- `/adapt` — apply verified adaptation (re-run; keep only if assertions still pass)
- `/ignore` — record this failure in `.ai-test-ignore.yml` as known-benign
- open in the tool → [link] (the product's interactive repair / self-heal flow)
```

Sources: pass/fail counts from the JUnit; resolution stats from `ci_generate.py --json`; flaky markers from AI-011 run-history (same-suite name matches across the job's cached history); heatmap/HTML from the evidence bundle.

---

## 7. Caching

- **Key:** `sha256(story + url + model + provider + prompt-fingerprint)` where the prompt fingerprint is a constant bumped whenever generation prompts change (the AI-042-F4 lesson — prompt changes are regeneration-sensitive; a stale cache keyed only on story would mask regressions).
- **Scope:** `generate-and-run` and `run-existing` restore the generated package before pytest; `generate-only` writes it for the artifact upload.
- **Default on**, `cache: false` to disable (users who want fresh generation every run).

---

## 8. Delivery Phases

| Phase | Scope | Sessions |
|-------|-------|----------|
| **7a — MVP (1 session)** | `scripts/ci_generate.py` headless driver (+ `--json`, exit codes, story template); `action.yml` Docker action with `generate-only` + `run-existing`; JUnit artifact (pytest-native + AI-028 export); workspace isolation; `.ai-test-ignore.yml` parse/validate; **repair-candidates marking in the report** (no adaptation execution); hermetically self-tested against the mocks + fake LLM fixture. | 1 |
| **7b — Full loop (1 session)** | `generate-and-run` wiring; PR comment with summary + flaky markers + evidence bundle upload; actions/cache; **slash-command loop** (`/adapt`, `/ignore`); **verified adaptation engine** (locator-only patch → re-run → assertion gate → keep-or-reject, transparent reporting). | 1 |
| **7c — GitLab parity (1-1.5 sessions, same milestone)** | `.gitlab-ci.yml` include template (same three modes) + GitLab platform adapter (MR note comments, slash-commands, `cache:`/`artifacts:`, protected-environment approvals). Built **after** GitHub proves the pattern end-to-end, shipped in the **same release** — not deferred to launch. Tested against a real GitLab.com project (credentials available) mirroring the GitHub self-test. `docs/ci.md` (modes, when to adapt — shared vs isolated envs, ignore-list format, education; configuration reference, not the Tier-7-gated user guide). | 1-1.5 |

---

## 9. Security & Guardrails

1. **Generated tests are untrusted code; test *execution* may be destructive.** Generated tests fill forms, submit orders, and can mutate the target site's data. The Action MUST run against **staging/non-production URLs** — enforced by an **allow-list** (`localhost`, `127.0.0.1`, `*.staging.*`, `*-dev.*`, `*.test.*`): any other URL fails fast unless the caller sets `danger-zone: true` **or** deliberately extends the list via `allowed-domains` (for internal env names). An optional `environment` input routes prod-targeting runs through GitHub's human-approval gate. **The Action is not a security boundary** — anyone who can edit the workflow file can set `danger-zone: true`; the real controls are org policy: branch protection on `.github/workflows/`, required reviewers, and environment approval gates (the "only certain users / ticket required / doesn't need to be immediate" path). `danger-zone: true` is documented as the legitimate route for **read-only smoke / load testing against real environments** (verify real connections behave as expected); guidance: prefer read-only stories (navigate + assert) for prod, keep mutating stories (checkout/payment) in staging.
2. **Fork PRs are unsupported, never `pull_request_target`.** The example workflow runs `workflow_dispatch` + `push` (trusted branches) and, for private/same-repo teams, `pull_request`. Fork PRs (public Action repo post-launch) run an attacker-controlled workflow file — explicitly unsupported and documented as such; `pull_request_target` never appears (it runs the base-branch file with secrets, dangerous if it ever checks out PR code). GitHub withholds secrets from fork-PR runs, which is the property that makes the exclusion safe.
3. **Token scopes:** recommend `contents: read`, `pull-requests: write` (comment), `actions: read` (cache). Minimal by default.
4. **LLM keys:** passed as secret inputs, never logged; `ci_generate.py` redacts `Authorization` headers in its debug output (the `[llm_client]` stderr-routing fix from 2026-08-02 is the precedent).
5. **No secrets in the comment or artifacts**: the evidence bundle and comment contain URLs/descriptions only; the settings store and RAG store stay in the workspace, not in uploaded artifacts (AI-035 §4 privacy precedent).
6. **Adaptation is assertion-gated.** Only `LocatorNotFound`-class failures are ever auto-adapted; assertion failures always surface. A patch survives only if the test's own assertions still pass after re-run. Weak assertions ⇒ weak verification (AGENTS.md §13) — the locator-only restriction is the hard boundary.
7. **No silent mutation.** Every adaptation/ignore is recorded in the PR thread and/or `.ai-test-ignore.yml` (versioned, reviewable) — CI never changes tests without a visible, explicit human action (or a repo-level `adapt: true` commit).

---

## 10. Testing Plan (hermetic, mirrors export-gate)

| Gate | Command / trigger | Asserts |
|------|-------------------|---------|
| Unit | `pytest -q tests/test_ci_generate.py tests/test_ci_ignore.py` (27 tests) | Driver arg parsing, exit codes (0/1/2), `--json` shape, danger-zone allow-list, config-error paths, ignore-list parse/validate — all offline, default suite |
| **Fake-LLM E2E** | `pytest -m slow tests/test_ci_generate.py::test_e2e_generate_against_mock_with_fake_llm` | Full generate against `mock_sites/ecommerce` with the canned-skeleton fake LLM → package emits, exit 0, JSON contract, workspace isolation, 8 tests. **Marked `slow` + `integration`** (implementation finding 2026-08-13: a real browser pipeline costs ~2.5 min — journey discovery ~45s + stateful upgrade ~64s, the product's own documented profile; belongs in the slow lane beside the learning-loop E2E, not the default suite). Hermetic: fake LLM + localhost mock, `RAG_ENABLED=0`/`FLOW_MEMORY_ENABLED=0` |
| **Action self-test** | `.github/workflows/ci-cd-action.yml` — runs the Action itself against the mocks + fake LLM | Exit codes; JUnit well-formed; artifacts exist; comment payload shape (asserted via a stub step, not a real PR). Mirrors `scripts/gate_full.py` layering. |
| **GitLab parity test** (7c) | Mirror the self-test in a real GitLab.com project (free tier; credentials available): the `.gitlab-ci.yml` template runs the driver + fake LLM against the mocks | Same asserts as the GitHub self-test, plus MR-note comment shape |
| **Export gate parity** | Existing `scripts/export_gate.py` still green | No regression to the golden export pipeline the Action's run path shares |

The fake LLM fixture (`scripts/fake_llm.py`) serves OpenAI-compatible `/v1/chat/completions` returning canned skeletons keyed on story content — the same trick the repo's `llm_client` tests use, promoted to a long-running server. This is what makes generate-mode self-testable in CI with zero external services.

---

## 11. Open Questions (for grilling session)

**Resolved during grilling 2026-08-13** (all folded into the body above):
- **Self-healing in CI:** OFF, never — the interactive tool only (false-negative risk; CI is the referee).
- **Learning:** OFF default; `learn: true` opt-in (generate mode only; needs store caching; writes the "diary", never operates).
- **Verified adaptation:** never default; offered post-failure (`/adapt` slash command + link to the tool's interactive repair — `HealingReport.interactive_repair_candidates` is the existing precedent); `adapt: true` repo-level opt-in for shared-env teams; locator-only + assertion-verified + transparent.
- **Ignore list:** `.ai-test-ignore.yml`, versioned, human-recorded — the safe "buttons moved but still works" mechanism.
- **Education:** one-line hint in the report; full why/when in `docs/ci.md` — CI is where you act, docs are where you learn.
- **Danger-zone:** Option C — allow-list + `danger-zone: true` + `allowed-domains`; the Action is friction/visibility, org governance (branch protection, env approval gates) is enforcement; `danger-zone: true` is the legitimate route for prod smoke/load testing.
- **Action repo layout:** two-stage — in this repo now (private, self-tested); thin public Action repo installing from PyPI at launch (Phase 8, with AI-039 rename); keep `ci_generate.py` imports package-relative.
- **Flaky-marking source:** the Action's own cached per-branch run history into the existing AI-011 detection (branch-scoped with default-branch fallback; caveat documented in `docs/ci.md`).
- **PR event scope:** `workflow_dispatch` + `push` defaults; `pull_request` same-repo/private only; fork PRs unsupported; `pull_request_target` never.
- **GitLab timing:** parity in 7c, same milestone (GitHub first to prove the pattern, GitLab immediately after with real-account testing) — platform-risk hedge, not an afterthought.

No open questions remain.

---

## 12. Definition of Done

- `scripts/ci_generate.py` + fake-LLM fixture + mock-site E2E test (27 default-suite tests + 1 slow-lane E2E).
- `action.yml` Docker action; `generate-only` / `generate-and-run` / `run-existing` all exercised by the self-test workflow.
- JUnit artifacts (raw + evidence-based) validated well-formed; PR comment posted from a real local run against a mock.
- `scripts/gate_full.py` offline gates green; ruff + mypy clean; no `slow`/`integration` markers on the new default-suite tests.
- GitLab parity (7c): `.gitlab-ci.yml` template + platform adapter tested against a real GitLab.com project (self-test mirrored).
- Roadmap Phase 7 → `[x]` with session doc in `docs/sessions/`.

---

## 13. Licensing & Commercial Model (open-core, recorded 2026-08-13)
- The repo is **Apache 2.0** — the code (including the Action) is free forever; anyone may legally adapt a copy. This is a deliberate choice: it is the portfolio/building-in-public asset and it makes the Action the free adoption on-ramp.
- **The Action carries zero license logic.** License keys / usage metering / tier enforcement (roadmap Phase 6 items) belong **only in the SaaS layer** (server-side, enforceable); in client code they would be theater under Apache 2.0.
- **Paid CI features, if ever needed**, are delivered as the Action calling the SaaS API (a server-side meter) — one seam, same enforcement story.
- **Cloud-fork risk is real only at traction.** Revisit licensing at Phase 8 (alongside AI-039 rename): levers are AGPL (network copyleft), source-available (ELv2/BSL), or keeping moats (RAG corpus, eval datasets) server-side. The RAG corpus/eval datasets are Apache-licensed today — the candidate asset to move server-side if a moat is wanted.
