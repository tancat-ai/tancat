# Phase 6 (Part 1) — 6c / 6d / 6e Handoff (uncommitted working tree)

**Date:** 2026-09-04
**Status:** 🟡 CODE-BUILT + GATES GREEN — **NOT COMMITTED, NOT SHIPPED.** Human reviews the diff before commit (AGENTS.md §11). All status updates in BACKLOG/ROADMAP deferred to the ship-it pass.
**Covers:** Phase 6c (team concurrency), 6d (BYO-LLM health check), 6e (license + tiers + free tier), 6h (latency benchmark + LLM call cache), 6i (multi-site eval re-validation). Spec: `docs/specs/FEATURE_SPEC_phase6_saas.md`.

---

## Why this session happened

The go-live question exposed that Phase 6 Part 1 was only partially built: 6a/6b/6f/6g verified shipped, **6c/6d/6e/6h verified NOT in code** (contradicting the spec's old "6b–6i shipped" DoD line — corrected this session). We continued the build order: 6c → 6d → 6e → 6h → 6i. **Phase 6 Part 1 is now code-complete** (all of 6a–6i built; 6a–6g were pre-existing/shipped earlier in the week).

## Doc corrections (also uncommitted)

- **`AGENTS.md` §10** — replaced "BACKLOG.md is the single source of truth" with the **split of responsibility**: roadmap owns big features/phases; BACKLOG owns fixes/smaller changes. Hard rules: one canonical location per item, the other file carries a one-line pointer only, verify shipped-ness against **code** not docs. This is the anti-muddle rule (the 6b–6i false-ship was the trigger).
- **`FEATURE_SPEC_phase6_saas.md` DoD** — the "6b–6i shipped" line now explicitly says it is a *definition of done*, that only 6a/6b/6f/6g are code-verified, and that canonical status lives in BACKLOG AI-045 + the roadmap item.

---

## 6c — Team-deployment concurrency (AI-045 #3)

**Root cause found:** `RAGStore`/`MilvusLiteBackend` instantiated per call; `MilvusClient` lazily opened per backend → the team shape (N Streamlit sessions + UI run + CI `learn:true`) opens multiple concurrent Milvus clients on one `.db` — the single-writer race the code already dodges locally by skipping `flush()`.

**Built:**
- `src/rag_store_lock.py` — stdlib-only cross-process advisory write lock (msvcrt/fcntl), re-entrant within a process, exclusive across processes, keyed on store path, never unlinks the lock file. Reads unguarded.
- Wired into the three `MilvusLiteBackend` write chokepoints: `upsert` (covers add_patterns/add_docs/upsert_pattern insert), `delete_learned`, `increment_learned_hit`.
- `tests/resilience/test_rag_store_lock.py` — 6 tests (4 hermetic + 2 real `multiprocessing` spawn: cross-process exclusion + reacquire-after-release). The 2 cross-process ones are `@slow`.

Gates: ruff/mypy clean, 156 RAG+lock tests, 6/6 lock tests.

## 6d — BYO-LLM health check (AI-045 §8.5 onboarding)

**Built:**
- `src/llm_health.py` — `check_llm()` (reachability → key → model-in-list → capability probe), `HealthCheckResult` (`ok`, `headline`, per-check flags, errors/warnings), `render_report()`, `build_client()` (reuses the product's own `LLMClient` construction path so "configured" == "probed"), `RECOMMENDED_MODELS` + `min_context_chars()`. Capability probe sends `enable_thinking=False` + `temp=0.0` (avoids the AI-050 thinking-budget false "broken response").
- **Streamlit:** 🩺 **Check My LLM** sidebar button + ✓/✗ banner + report (session-state cached to survive the rerun).
- **CLI:** **Check LLM** menu item → `_check_llm_inline()` using the session's actual provider/base_url/model.
- `tests/test_llm_health.py` — 11 tests (happy, unreachable, model-not-in-list, empty-response thinking-class, transient-list-recovered-by-probe, soft-warning-doesn't-block, probe opts-out-of-thinking, report rendering, build_client returns real `LLMClient`).

Gates: ruff/mypy clean, 60 tests (llm_health+llm_client+provider_config), smoke 39/39 incl. egress audit 0 flagged (no new outbound call sites).

## 6e — License + tiers + free tier (the big one)

**Built:**
- `src/licensing/tiers.py` — data-driven tier table: `free` (core generate + evidence export + self-heal + RAG learning; **limits 25 runs / 10 exports per month**) → `self-serve` (+Jira) → `pro` (+POM, multi-site, CI runs) → `airgap` (+private-network, support). `feature_required_tier()`, `is_paid_tier()`, `limit_for()`, `AITEST_TIERS_JSON` override.
- `src/licensing/license.py` — offline ed25519 validation (JWT-ish `payload_b64.signature_b64`, `cryptography`, no new deps). `LicenseStatus`: unlicensed / valid / expired_grace / expired_blocked / invalid. 7-day grace (`AITEST_LICENSE_GRACE_DAYS`). Keys: `AITEST_LICENSE_KEY` → `AITEST_LICENSE_FILE` → `~/.ai-test-gen/license.key`. Vendored public key (override `AITEST_LICENSE_PUBKEY`). `feature_enabled()` — license presence is an **upgrade, never a lockout** (spec §7.6).
- `scripts/license_gen.py` — vendor-side CLI (`gen-keys` / `sign`), fully offline. **E2E verified**: generated key → signed `pro/30d` token → vendored key rejects (INVALID) → correct key accepts (VALID, POM enabled).
- `src/usage_meter.py` — runs counted from existing `evidence/run_results.sqlite` (30-day window on `created_at`), exports in a local ledger, storage computed, LLM tokens `None` (§9 Q6 accepted). Free-tier cap: `assert_run_allowed()` raises `FreeTierLimitError` with upgrade prompt; `AITEST_FREE_TIER_RUNS` (25) / `_EXPORTS` (10) / `AITEST_ENFORCE_FREE_TIER` configurable; paid tiers unlimited.
- **Wiring:** `PipelineRunService.run_saved_test` (run gate — UI + CLI); `evidence_export` csv/ndjson/junit record each export; `ci_generate.py --json` gains `license` + `usage` sections + `AITEST_ENFORCE_LICENSING=1` opt-in hard gate; Streamlit `SidebarConfig.render_license_usage()` (license banner + Runs/Exports/Storage Usage panel).
- `tests/test_license.py` (20) + `tests/test_usage_meter.py` (12).

### Decisions taken on §9 open questions (recorded, reversible — re-grill at ship-it)
- **Q1 (CI driver tier gating):** CI is the **adoption on-ramp** — `ci_generate` reports license+usage in `--json`, hard-blocks only when `AITEST_ENFORCE_LICENSING=1` AND a present-but-unusable license. The run cap lives in the product funnel.
- **Q2 (grace):** 7 days, then runs/CI blocked, evidence/export stays read-only (via gate messages). 
- **Q3 (free tier size):** 25 runs + 10 evidence exports per 30 days (per-deployment), both env-configurable.
- **Q6 (LLM tokens):** reported as `None` where the provider gives no `usage` (accepted).
- **Q5, Q7, Q8** — unchanged: no seat counts, per-deployment auth stays out of Part 1, egress-audit scope = product runtime (`src/` + generated-package + product entrypoints).

### 6e gates
ruff clean · mypy clean (8 modules) · `tests/test_license.py` + `tests/test_usage_meter.py` = 32 passed · full default suite **3076 passed** (was 3029 at 16b) · smoke 39/39 incl. **egress audit 0 flagged** (license/meter add zero outbound HTTP — spec §5.4 "zero network calls" held) · E2E license round-trip verified.

---

## 6h — Latency benchmark + LLM-call cache (AI-045 #6, spec §5.10)

**Built:**
- `src/llm_cache.py` — disk-backed, TTL'd LLM-call cache. Key = sha256(provider, model, temperature, enable_thinking, system_prompt, prompt) — a hit is only served when every input matches. Lives in the workspace (`evidence/cache`, `AITEST_LLM_CACHE_DIR` override), atomic tmp+replace writes, expiry-on-read + lazy sweep, `AITEST_LLM_CACHE=0` opt-out, `AITEST_LLM_CACHE_TTL_S` (default 1h). `CachingGenerator` wraps any async `generate` (the ranker's protocol).
- **Ranker wiring** (`src/semantic_candidate_ranker.py`, non-protected): constructor gains `cache=`; wraps the generator in `CachingGenerator` **only when it exposes `.model` (i.e. is a real `LLMClient`)** — so product paths cache by default (env: `AITEST_LLM_CACHE`, on) while test fakes stay unwrapped (recording/timeout tests observe the generator directly). The two call sites are untouched; a cache hit returns byte-identical text at temp 0, so resolution results never change — only work is removed. **Skeleton caching is NOT wired** — `src/test_generator.py` is protected; the `LLMCache` module is ready for it and needs protected-file sign-off.
- `scripts/benchmark_latency.py` — the published per-model-tier table producer. Measures through the product's own machinery: `list_models`, skeleton generation (real `TestGenerator`) for a bundled 6-criteria story, single resolution pick (real `SemanticCandidateRanker`) cold + warm (cache-hit delta), and an **estimated story LLM time** (skeleton + ~12 resolution calls) compared against the SLO (180s = <2–3 min/6-criteria story). `--json`, `--save docs/benchmarks/latency.json`, and `--self-test` (in-process null LLM) for a hermetic CI run.
- `tests/test_llm_cache.py` — 11 tests: key stability/uniqueness, get/put, TTL, clear, env opt-out, corrupt-entry miss, default-dir, CachingGenerator hit/miss + disabled bypass, ranker-level second-resolve-is-cache-hit + disabled-still-calls, benchmark `--self-test` subprocess schema.

### 6h gates
ruff + mypy clean · `tests/test_llm_cache.py` + `tests/test_semantic_candidate_ranker.py` = 26 passed · benchmark `--self-test` runs offline and prints the SLO line · full default suite **3088 passed** (was 3076) · smoke 39/39 incl. egress audit 0 flagged (cache is local disk only — no new outbound call sites).

---

## 6i — Multi-site eval dataset: live re-validation + baseline update (AI-045 #7, spec §5.11)

**Findings from the audit:** the automationexercise (eval-002) + LV (eval-005) golden datasets already existed; `baseline.json` was the old **5-story snapshot** (67 resolutions) while the harness's static gate already ran all 9 datasets / 96 placeholders / **97.9%** across 7 sites. Golden keys had not been live-re-validated since 2026-07-14; eval-005 + the mocks had no validation stamp at all.

**Built:**
- `scripts/eval/revalidate_goldens.py` — deterministic golden-key live re-validation: loads each golden's `expected_page`, asserts tolerance selectors resolve (real chromium for live sites; local `MockServer` for the mocks; **OR semantics** matching the eval `golden_validator` — a golden passes when any tolerance matches). **Stateful-page classification** (B-022 class): login-gated / cart-seeded / post-submit goldens are recorded as `stateful-skipped` (validated via the harness execution path), not false decay. Output: `scripts/eval/revalidation/latest.json` recency record + human table. Exit 1 only on real decay; unreachable (no network) never fails CI. `--dataset`, `--json`, `--save`. `--self-test`-style hermetic unit tests (`tests/test_revalidate_goldens.py`, 8) cover OR semantics, stateful classification, origin rewrite, report shape.
- **Golden refreshes (additive, kept stale tolerances):** eval-002 automationexercise Products/Cart link tolerances now include the current live selectors (`a[href="/products"]`, `a[href="/view_cart"]`); eval-004 the-internet `all elements listing` gained `h1.heading`; eval-010 ambiguous mock `Place Order button` had a wrong `expected_page` (success.html → index.html) — fixed.
- **Baseline regenerated** (`eval_harness.py baseline --save`): `scripts/eval/baseline.json` is now the multi-site truth — **9 datasets · 7 sites · 96 placeholders · 97.9% resolution accuracy** (was 5 datasets / 67). `dataset --validate` → 9/9 valid; static gate `--min-accuracy 79` green.

**Live re-validation result (2026-09-04, all 9 datasets):** 8/8 evaluable datasets **passed** — saucedemo 6/6 (+14 stateful), automationexercise 6/6 (+2), demoqa 7/7 (+1), theinternet 7/7, ecommerce_mock 4/4 (+12), banking_mock 3/3 (+10, ×2), ambiguous 4/4; LV insurance honestly `static-only` (no local mock / public site — validated via frozen captures). Real decay found + fixed: saucedemo login/inventory data-test redesign (login-gated → stateful, not decay), automationexercise header markup, the-internet home heading.

### 6i gates
`dataset --validate` 9/9 · static gate `--min-accuracy 79` exit 0 · baseline regen green (97.9%) · `tests/test_revalidate_goldens.py` 8 passed + contract/eval suites green · full default suite **3094 passed** (2 transient DNS flakes in `test_orchestrator.py` — pass in isolation, not a regression) · smoke 39/39.

---

## Working tree (uncommitted — review then ship-it)

```
 M AGENTS.md                                  (split-of-responsibility rule)
 M docs/specs/FEATURE_SPEC_phase6_saas.md     (DoD honesty fix)
 M scripts/ci_generate.py                     (6e: license+usage in --json, opt-in gate)
 M src/cli/main.py                            (6d: Check LLM menu item)
 M src/evidence_export.py                     (6e: export ledger recording)
 M src/pipeline_run_service.py                (6e: free-tier run gate)
 M src/rag_store.py                           (6c: lock wiring)
 M src/ui/ui_sidebar.py                       (6e: render_license_usage)
 M streamlit_app.py                           (6d: Check My LLM btn; 6e: usage panel hook)
?? scripts/license_gen.py                     (6e vendor tool)
?? scripts/benchmark_latency.py               (6h benchmark)
?? scripts/eval/revalidate_goldens.py         (6i live golden re-validation)
?? scripts/eval/revalidation/latest.json      (6i recency record — 2026-09-04, all datasets pass)
?? src/llm_cache.py                           (6h disk cache)
?? src/licensing/                             (6e: tiers.py + license.py + __init__)
?? src/llm_health.py                          (6d)
?? src/rag_store_lock.py                      (6c)
?? src/usage_meter.py                         (6e)
 M src/semantic_candidate_ranker.py           (6h cache wiring)
 M scripts/eval/baseline.json                 (6i multi-site baseline: 9 datasets / 96 placeholders / 97.9%)
 M scripts/eval/dataset/eval-002.json         (6i tolerance refresh: live Products/Cart link selectors)
 M scripts/eval/dataset/eval-004.json         (6i tolerance refresh: h1.heading)
 M scripts/eval/dataset/eval-010.json         (6i expected_page fix: Place Order → index.html)
?? tests/resilience/test_rag_store_lock.py    (6c)
?? tests/test_llm_cache.py                    (6h)
?? tests/test_revalidate_goldens.py           (6i)
?? tests/test_license.py                      (6e)
?? tests/test_llm_health.py                   (6d)
?? tests/test_usage_meter.py                  (6e)
```

### Run B (graph) — clean graph-vs-linear comparison (2026-09-05, reference stack)

`--use-graph` full eval with the mock-parity fix + restored store + reference build:
**45.1% (51/113)** vs Run A linear **54.9% (62/113)** — a −9.8pp graph deficit under identical conditions (same build, store, env, temp 0, `AITEST_LLM_CACHE=0`; `thinking=model-default` on graph stages by design, AI-050). 0 LLM timeouts, 0 connection-refused.

| Dataset | Linear (A) | Graph (B) |
|---|---|---|
| saucedemo | 8/20 (40%) | 9/20 (45%) |
| automationexercise | 8/8 (100%) | 7/8 (88%) |
| demoqa | 7/8 (88%) | **1/8 (12%)** |
| theinternet | 5/7 (71%) | 4/7 (57%) |
| lv_insurance | 9/24 (38%) | 11/24 (46%) |
| ecommerce | 12/16 (75%) | 10/16 (62%) |
| banking ×2 | 4/13, 6/13 | 3/13, 3/13 |
| ambiguous | 3/4 | 3/4 |

Read: graph beats linear on the multi-step form (LV 46 vs 38 — the case AI-054's docs predicted), but loses badly on demoqa (1/8) and banking. Overall **linear still wins by ~10pp** for golden-key resolution. Caveat (AI-037): resolution accuracy is skeleton-shape-driven; graph's per-agent skeletons differ → part of the delta is skeleton shape, not resolver power. Decision remains the user's (AI-054: linear stays the product path; graph dormant); this is the cleanest data point yet for that decision.


### ROOT CAUSE FOUND: the eval accuracy drop was a LOST RAG STORE ASSET, not model variance

**Sequence (this session's repeat-run investigation, 2026-09-05):**
1. Run A (linear repeat, identical settings): **42.5%** (48/113) — *lower* than the first run (48.7%) and far off the Aug band (53.2–54.1%). Per-dataset numbers were **suspiciously identical** between my two runs (LV 7/24 both, saucedemo 8/20 both, ambiguous 3/4 both) — deterministic at temp 0, so NOT sampling noise: a systematic difference.
2. Inspected the RAG store: **zero golden/learned patterns — only 66 docs.** The bundled golden pack (113 patterns, B-036) was missing from every eval since **2026-08-31**, when the store directory was recreated (mtime 2026-08-31 14:43) while the idempotent seed marker (`evidence/.rag_bundled_seeded.json`, `seeded_at 2026-08-20`) SURVIVED — so `ensure_bundled_seeded()` skipped re-seeding forever after.
3. **Wipe source:** `src/learning_impact.py:115` — the AI-059 lab rebuild does `shutil.rmtree(target)` on the store dir; a lab run Aug 30/31 wiped the production store (patterns + docs) without refreshing the marker.
4. **Fix (applied):** `python scripts/rag_ingest.py --bundled --force` → re-seeded **113 golden patterns + docs**, refreshed the marker. Store verified: `{golden: 113, doc: 101}`.
5. Consequence: the Aug reference runs (53.2–54.1%) resolved WITH the golden RAG bonus; today's runs resolved with bonus=0 (pure structural scoring) → systematic −5–11pp. The eval's own `--min-accuracy` static gate (79) never saw it because static mode doesn't use RAG.

**Current server state (cannot finish more runs tonight):** LM Studio crashed once mid-run tonight and is now failing a 40s, 8-token completion probe (`ReadTimeout`). A2 (restored-store linear rerun) generated a degenerate 216-placeholder demoqa skeleton + 19 resolution timeouts before being killed. **Eval runs against tonight's server = measurement garbage.** Baseline untouched (as agreed).

**Next (when the server is healthy):** re-run `eval_harness.py run --mode full --regenerate` (linear, RAG restored) then `--use-graph` (the bells-&-whistles comparison), env as recorded above (`AITEST_LLM_CACHE=0`, temp 0.0). Expect accuracy to recover toward the 53–54% band if the RAG-bonus hypothesis holds — that is the confirmation, not tonight's degraded numbers.

**Housekeeping guard (worth a tracked item):**
**Tracked:** opened **B-048** in BACKLOG.md (RAG-store seeding gap: lab wipe + stale marker). One-line pointer only — full item lives in BACKLOG. the AI-059 lab wipe should be sentinel-scoped to the lab store, or `ensure_bundled_seeded()` should detect a pattern-less store and re-seed regardless of marker. Both are small, real fixes — one line each, outside this session's shipped surface.


### Full eval run (2026-09-04, `run --mode full --regenerate`, all 9 datasets)

**Settings checked before the run** (per user direction — the session added env knobs that a *measurement* must control):
linear pipeline (no `--use-graph`) · pom off · resolution timeout 120 (AI-049 default) · `AITEST_LLM_TEMPERATURE=0.0` · thinking off · RAG on (default) · flow memory on (default) · **`AITEST_LLM_CACHE=0`** (isolate the new 6h cache — measurement is fully cold) · `AITEST_ENFORCE_FREE_TIER=0` (belt-and-braces; the eval executes via raw `subprocess pytest`, so the 6e run gate is **not in the eval path** — verified in `eval_runner.py`).
Notes: `TestOrchestrator.__init__` always constructs LangGraph and logs "LangGraph multi-agent pipeline enabled" — documented harmless (B-036: `--use-graph` is the only selector); the eval calls `run_pipeline()` = linear. `eval-010` included (first full run to include it) — produced a healthy 4-journey skeleton this time.

**Result: Resolution accuracy 48.7% (55/113)** vs the box's stable reference band **53.2–54.1%** (2026-08-23/26/29, all `think=off`, same model Qwen3.8-27B-UD-Q4_K_XL_v2). Only **5 LLM resolution timeouts** (graceful, not the driver).

**Diagnosis — a measurement-environment confound, not a session regression:**
1. **Every session code change either widens acceptance or is outside the measured path.** Cache off ⇒ ranker path byte-identical to reference (`CachingGenerator` only wraps when `cache.enabled`); 6c adds a *write* lock on RAG upserts (regeneration reads the golden store, writes happen in execution); 6e is not in the eval path (raw pytest execution); 6i golden edits added tolerance selectors (acceptance can only widen) + one expected_page fix (eval-010 only). Verified, not asserted.
2. **The LLM server build changed**: `_sampling_identity` records `b10618-eb25b7263` (all Aug reference runs) vs **`b1-c28d538` (today)** — LM Studio was updated/restarted between the reference runs and now, same model + min_p 0.0 + temp 0.0. This is the AI-046/AI-048 confound class, exactly why identity is recorded.
3. **Single-site swings inside documented variance bands**: saucedemo 40% today vs 35–75% across runs (AI-046 documents the exact site), LV 29% vs AI-037's 62–79% regeneration band (skeleton-sampling noise dominates, documented).
4. The eval did its job: honest per-dataset records, 9 results persisted to `eval_runs`, no gate-gaming.

**Honest next step (offer, not auto-run — ~55 min + tokens):** repeat the full run once on a quiet box to measure today's variance band under the new server build. One regeneration run is not signal (AI-046 lesson); two runs pin the band. If the deficit persists across two quiet runs, open a tracked item (e.g. "resolution variance under LM Studio build swaps — re-baseline eval") — do **not** tune anything to chase the number.


### CONFIRMED: restored store + reference build → exact reference accuracy (2026-09-05)

User loaded the **reference LM Studio build `b10618-eb25b7263`** (verified: identical to the Aug record — same model file, n_ctx 262144, speculative True, temp 1.0/0.0, top_k 20, top_p 0.95, min_p 0.0; completion probe 5.2s). Re-ran the eval pair with the pinned env (`AITEST_LLM_CACHE=0`, temp 0.0).

- **Run A (linear, RAG-restored): 59/109 = 54.1%** on the same 8 datasets — the EXACT 2026-08-26 reference number (59/109); 54.9% (62/113) including eval-010. **Root cause hypothesis confirmed decisively**: the wiped store + fork build fully explained the −5–11pp; nothing in the repo was wrong.
- **Run B (graph):** `--use-graph`. **Found + fixed a real eval-harness bug on the fly:** `_regenerate_code_via_graph` never called `_ensure_mock_serves(...)` (the linear path does, line 772). Graph-mode regenerations of mock datasets scraped a dead `:8781` → connection-refused → polluted mock scores (and likely a component of the historical graph-32.8% gap, AI-054). Fix: mirrored the ensure call into the graph path (line 838). Regression guard: `test_graph_regeneration_mock_parity_source_guard` (contract test on both regeneration functions). B restarted post-fix.


### Root-cause on the two questions (2026-09-05 analysis)

**Q1 — was the fork build itself "worse"?** No *clean* evidence: every fork-build eval run (48.7%, 42.5%, 9.7%) was completely confounded with the wiped RAG store. The clean fork-vs-mainline comparison was never run (today's runs are mainline-only). What we DO know: the fork build degenerated on *skeleton generation* twice (216–244 placeholders / 60–61 journeys for 6 criteria — A2 + A3); mainline produces sane 27–51-placeholder skeletons. Degenerate skeletons alone tank the eval regardless of resolver quality. "Faster" is a perf claim (llm-benchmarks t/s), orthogonal to resolution quality. A controlled fork eval (restored store) would likely re-trigger the degenerate skeletons — it's a model-server-behavior difference (tokenizer/sampling kernels at temp 0), not a repo issue.

**Q2 — graph demoqa 1/8 vs linear 7/8: skeleton story-bleed (evidence in `generated_tests/test_demoqa.py`, graph run):** the graph Generator produced a *saucedemo-flavored* skeleton for the demoqa story — every test repeats `navigate → fill #userEmail 'standard_user' (label username/email) → fill #dateOfBirthInput 'secret_sauce' (label password) → click a[href="/login"] (label Login) → …`, and the real demoqa fields (`#firstName`/`#lastName`/`#gender-radio-1`/`#submit`) are never emitted once. `standard_user`/`secret_sauce`/`/login` are eval-001 saucedemo vocabulary — the graph's agents bleed the previous story's flow (saucedemo was processed immediately before demoqa; the generator's story-pin is too weak and/or the agent session carries the prior story). The resolver resolved what it was GIVEN correctly; the skeleton is semantically wrong. Runtime corroboration: `a[href="/login"]` doesn't exist on demoqa → the click would fail. Linear's single-call skeleton stayed on-story (7/8). The graph's Validator agent did NOT catch it (the `#login` submit sailed through).

**Q3 implication — where graph is limited (data):** limitation #1 = skeleton *generation quality control* (story-bleed, pollution) — needs a hard site-context pin + a validator that catches off-story steps. Limitation #2 (historical) = over-ambitious skeletons vs scraper capability. Strengths (this run): graph won the multi-step LV form (46% vs linear 38%). The best-of-both shape: linear's single-call skeleton + proven resolver as the execution core; graph's Planner/QA-Director for story intake/condition routing + graph's Validator as a post-generation integrity gate on the linear output (the AI-052/B-030-style repair seam). No code changes made for this — it's the AI-054 decision record the user asked to build toward.


**Launcher Stop-bug found + fixed (2nd round, 2026-09-05 ~14:30):** user's Stop said 'Stopping…' then flicked back to running. Root cause: the orphan kill's image fallback was GATED on netstat port-pids — a transient netstat miss (proven: 'killed: []' while a dummy listener was up) plus a stale pidfile meant nothing got killed. Fixes in llm-benchmarks/launcher.py + llmctl.py: _port_pids gains a PowerShell Get-NetTCPConnection fallback; the by-image fallback is now UNCONDITIONAL after precise kills; _taskkill_pid surfaces taskkill errors in the /api/stop response; stop_server reports stale pidfiles honestly. Regression (pure orphan, no pidfile): /api/stop -> killed:[pid], port free, exit 0. NOTE: the launcher instance the user was running predated these fixes — restart it to load them.

**CONTROLLED FORK EVAL - the Q1 answer (2026-09-05 14:20-15:30):** fork build b1-c28d538, identical settings to the mainline run (linear, RAG-restored store, temp 0, cache off, 9 datasets). Result: **48.7% (55/113) vs mainline 54.9% (62/113) = -6.2pp**. Sane skeletons this time (6 journeys / 27-51 placeholders - no degeneration), so the deficit is a genuine broad quality drift: small per-site losses across nearly every dataset (saucedemo 8/20 same, automationexercise 8/8->6/8, demoqa 7/8->5/8, ecommerce 12/16->10/16, LV 9/24->8/24, banking similar, ambiguous same), not one collapse. Sampler/kernel differences at temp 0 cost resolution quality. Reconciliation of all fork-era runs: fork+wiped store 42.5-48.7% (within-run variance +-6pp), fork+restored 48.7%, mainline+restored 54.9% = reference band. The RAG-store wipe mattered less than first estimated (~few pp); the fork build itself is the ~6pp cost (the 9.7% outlier was the crashed-server degenerate state). VERDICT: keep mainline b10618-eb25b7263 as the generation engine; the fork remains a perf experiment (speed at ~6pp quality) - the 'faster llama.cpp came back worse' premise is confirmed with a controlled number.

### `verify_production.py` (2026-09-04, LM Studio :8080 — Qwen3.8-27B-UD-Q4_K_XL_v2)

**Run: verdict FAIL — but NOT attributable to this session's changes.**

- **saucedemo (POM, --all-sites): 11/13 gates.** The 2 fails = the known unevidenced-checkout class (guest can't reach login-gated cart/checkout → resolver has no candidates → 2 unresolved placeholders → 2 honest `pytest.skip`; execution 4 passed / 2 skipped). Matches the 2026-08-23 reference shape. **Not a regression.**
- **automationexercise (POM): Pipeline FAIL — scraper subprocess timeout.** Reproduced twice: `journey_scraper --journey-scrape` @ 120s, then `stateful_scraper --stateful-scrape` @ 150s. Root cause is in **untouched** code (`src/stateful_scraper.py:82`, `src/journey_executor.py subprocess_run`): `timeout = max(120, 30×steps|urls)` with `page.goto(..., wait_until="networkidle")` on automationexercise's heavy ad/consent stack → wall-clock exceeds the cap. This is the documented AI-054 class ("journey scraper can't keep up with multi-step SPA forms") + B-029 overlay race. **The session diff touches none of journey/stateful/executor/orchestrator — verified via `git diff --name-only`.**
- Honest position: 6i's surface (datasets, baseline, revalidate tool) is not exercised by the failing gates. Do **not** game the gate by bumping scraper timeouts to go green — that is the tuning-the-gate pattern the project rejects (AI-049: "flat zeros = failure, not tuning"). Options: (a) re-run AE on a quiet box / different time of day (site/CDN variance); (b) if persistent, open a proper item to make the scraper subprocess robust (journey loads away from `networkidle`, or a larger still-bounded wall-clock) — real product work, outside this session.


### Final confound layer (2026-09-05 morning): the ONLY remaining variable is the LM Studio build

Attempted the restorative linear run (A3) — **killed**: the skeleton generator produced a degenerate **244-placeholder / 61-journey** skeleton for saucedemo (pipeline's one retry made it worse: 60→61 journeys), the exact AI-058 documented degenerate mode. Runs cannot be meaningful under this server state.

Eliminated everything else, with evidence:
- **Model file identical** (17.5 GB GGUF, mtime 2026-08-20, `Q4_K - Medium`, same path) — no AI-046-matched-precision swap.
- **Sampling identical to the Aug reference**, per `/slots` (the authoritative source, AI-050): `speculative: True`, temp 0.0 (client-pinned), top_k 20, top_p 0.95, min_p 0.0, seed 4294967295, n_ctx 262144. /props `speculative.types=none` is the per-request default, NOT the slot truth.
- **RAG store restored** (golden 113 + docs) — pending B-048 for the wipe/marker guard.
- Session diff scoped OUT of the generation path (verified repeatedly).

**Conclusion:** the systematic −5–11pp (and the degenerate skeletons) trace to the **LM Studio build change `b10618-eb25b7263` (Aug reference) → `b1-c28d538` (present)** — different llama.cpp tokenizer/sampling kernels produce different greedy output for the same prompts at temp 0. This is external to the repo; the eval band is build-dependent.

**Two paths (user decision — the desktop is theirs):**
1. **Restore the reference build** (`b10618-eb25b7263`) in LM Studio → re-run A (linear, RAG-restored) + B (`--use-graph`) → expect the 53–54% band back. Commands are ready (env: `AITEST_LLM_CACHE=0 AITEST_ENFORCE_FREE_TIER=0 AITEST_LLM_TEMPERATURE=0.0`; `run --mode full --regenerate`, then `--use-graph`).
2. **Keep the new build** → accept that greedy output shifted → this is a re-baseline decision (user said no to that for the bells-and-whistles run; a re-baseline would be a deliberate, separate decision).


## NEXT SESSION — where to pick up (fresh-context entry point)

> Session closed 2026-09-05, 6 commits on main, all CI green, working tree clean
> (only pre-existing untracked `training_data/model_baseline_qwen38_retest_20260904.json` — not from this session).
> This handoff + AGENTS.md are the sources; read AGENTS.md §10/§12b/§12c for doc + search tooling rules.

**High-priority pickups (choose one):**
1. **Hybrid pipeline spec (graph-as-orchestrator)** — the consolidated decision record lives in ROADMAP §12d; write `docs/specs/FEATURE_SPEC_hybrid_pipeline.md` before any build (graph Planner/QA-Director in → linear core → graph Validator integrity gate out). Data: mainline linear 54.9% vs graph 45.1% (clean, mock-parity fixed); demoqa story-bleed is the concrete weakness the validator seam fixes; graph wins the multi-step LV form.
2. **B-048 code guard** (BACKLOG) — the RAG-store seeding gap is repaired manually + tracked; implement one of the two candidate guards (`learning_impact` sentinel-scoped lab store, or `ensure_bundled_seeded` re-seeds when golden count == 0) + verification.
3. **automationexercise scraper-timeout item** — `verify_production` FAILs on AE (untouched code: `stateful_scraper.py:82` / `journey_executor.subprocess_run` networkidle + 120–150s wall-clock caps). Open a BACKLOG bug (B-049) if it persists; candidate fix: journey loads away from `networkidle`, or a larger still-bounded wall-clock.

**Lower-priority / scheduled:**
4. Skeleton-call caching (needs sign-off on protected `src/test_generator.py`; `LLMCache` is ready).
5. 6e doc tails: §9 decisions folded into the spec; recommended-models table (6d tail); seed the published benchmark table.
6. **Golden-key maintenance** (~3–6 months): re-run `scripts/eval/revalidate_goldens.py` (AGENTS.md §12).
7. Eval-informed backlog still open: AI-058 metric gate, AI-054 §5 export gate, AI-065 citation token watch.

**Dev-tool state for the next session:** zvec-grep daemon (`zg server on`, :7999, wired into .mcp.json) + fresh graphify graph (20,605 nodes) — `zg index` / `graphify update .` before trusting either after new code. LM Studio: reference build `b10618-eb25b7263` = the generation engine (fork `b1-c28d538` costs ~6pp).

## Post-ship housekeeping (2026-09-05)

- **Graphify:** full `graphify update .` run — 903/903 files, 20605 nodes / 35876 edges / 1364 communities; `callflow.html` regenerated. graphify was NOT used during the session (all findings came from direct code reading — correct for line-level bugs). AGENTS.md gained §12b "Knowledge Graph — when to use" (orientation tool, never truth; `graphify update .` before querying; gitignored).
- **llm-benchmarks:** launcher/llmctl Stop-bug fixes (log rotation, orphan detection, unconditional image kill, stale-pidfile honesty) remain uncommitted in that repo — user's call to commit there.
- **Untracked debris:** `training_data/model_baseline_qwen38_retest_20260904.json` — not from this session; left for the user.
- **zvec-grep adopted as dev tooling (2026-09-05):** local semantic search layer (ripgrep+BM25+vector, Apache-2.0, zvec-ai/zvec-grep). Trial against this repo: 921 files indexed in 57s (local potion-retrieval-32m, 87 MiB), semantic queries landed exactly on ground truth (rag_store_lock, ensure_bundled_seeded, B-048 note, handoff root-cause). MCP daemon wired into `.mcp.json` (gitignored) as `zvec-grep` (`zg server --stdio`, lazy) on loopback :7999 (agent toolset). `.zvec-grep/` gitignored; AGENTS.md §12c documents usage + guardrail ("hits are leads — verify against code"). Daemon currently running (PID was 30932).
