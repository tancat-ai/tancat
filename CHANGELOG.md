# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Version numbers follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

### Added
- **3D architecture map viewer (2026-08-12)**: `scripts/3d map/viewer.html` — self-contained Cosmograph renderer (ESM via esm.sh, `@cosmograph/cosmograph@1.4.2`, classic `new Cosmograph(container, config)` + `setData(nodes, links)` API); nodes colored by architecture layer, always-on labels for the top 60 hubs, hover labels, legend + stats. `generate_3d_map.py` fixes: `graphify-out` added to SKIP_DIRS (removed ~1,500 hashed AST-cache nodes: 4,681 → 3,167) and unmapped `.py` files now group as `Other` instead of `utility` (utility 1,965 → the real 14 src/ modules). Viewer gotchas documented: v1 key is `nodeLabelAccessor` (not `nodeLabel`), unpkg is CORS-blocked (use esm.sh), and the library sends a metrics ping to its Supabase on setData.
- **Testing hardening (2026-08-12)**: CI coverage gate (`--cov-fail-under=65` — measured 67%), page-state ASSERT flow-fallback tests (which uncovered + fixed a real gap: the sequential B-021 ASSERT branch never used flow memory, so URL asserts couldn't be flow-rescued in the real pipeline — now they can), and static guards (`tests/test_script_hooks.py`) that keep the `verify_production`/`synthesize_stories` suite-chaining hooks wired. Learning-loop E2E tracked in BACKLOG as a non-roadmap item.
- **AI-042-F2 — flow stats + prune in the Streamlit sidebar (2026-08-12)**: `SidebarConfig._render_flow_memory()` — "Flow Memory" subheader with `format_flow_stats_summary()` (patterns / sites / cross-site / suite chains — the F3 source split surfaces here) + two-step prune → `FlowMemoryStore.clear()`, mirroring the RAG "Learned Patterns" section; empty store degrades to a hint. Pure `format_flow_stats_summary` helper + 2 stubbed-UI tests. F-series complete (F1/F2/F3 shipped; F4 deferred).
- **AI-042-F3 — cross-test flow chaining (2026-08-12)**: `chain_suite_transitions()` + `FlowMemoryStore.learn_suite_flows()` chain adjacent fully-passing tests (name order) into GOTO transitions — terminal page of test N → entry page of test N+1, description = destination route name. Same-site pairs only (mixed evidence dirs never chain), home/no-movement dropped, pre-B-033 sidecars fall back to navigate values. `FlowPattern.source` (within_test/suite_chain) + `stats()` split. Wired into all run paths: `synthesize_stories.py` sweep, `PipelineRunService.run_saved_test` (UI + CLI), `verify_production.py`. Re-seed: 24 new suite-chain patterns (89 → 113, cross-site 5 → 8) incl. cart↔checkout↔products on 2 sites; holdout strict cross-site 1/11 → 2/11. 13 new tests (47 total).
- **AI-042-F1 — GOTO eval dimension + navigation corpus (2026-08-12)**: `docs/rag_corpus/playwright/04-navigation.md` (curated navigation reference — corpus previously had one navigation section; Playwright treats navigation as first-class), `scripts/eval/dataset/eval-008_goto_navigation.json` (GOTO-flavored banking story with `expected_page` from-contexts), flow path wired into `eval_resolver._resolve_placeholder` (GOTO/URL/url_assertion resolve via `flow_resolved_url`), 3 hermetic tests, stateful banking-mock scraped pages (login-wall + session-gated, localStorage auth). Banking resolver accuracy 9/26 → 13/26; overall resolver 32.1% → 35.8%; holdout eval 3/7 → 6/11; static gate unchanged 97.9%.
- **Cross-site flow memory — AI-042 session 2: eval holdout + route canonicalization (2026-08-12)**: `scripts/eval/flow_holdout_eval.py` measures flow transfer with holdout integrity (target site hash excluded) + from-context reachability. Finding: flows only transfer when sites share route vocabulary → `_ROUTE_ALIASES` in `normalize_route` (view_cart/basket/shopping_cart→cart, inventory→products, signin/sign-in/auth→login — exact whole-route match; step pages stay distinct). Result: **0 → 3/4 non-home URL asserts holdout-resolvable** (automationexercise products/cart via saucedemo+mock flows; ecommerce cart strict cross-site). Store re-seeded: 89 patterns / 5 cross-site.
- **Cross-site flow memory — AI-042 session 1 (2026-08-12)**: `src/flow_memory.py` — learns navigation *shape* from passing evidence (locators don't transfer across sites — only ~3% overlap — but login→browse→cart→checkout does). `normalize_route` (URL → route keyword, never raw URLs — AI-035 §4 privacy), `flow_transitions` (passed-only, same-page dropped, per-step site identity), `FlowMemoryStore` (JSON `evidence/flow_memory.json`, atomic writes, dedup + site diversity + `min_sites` cross-site guardrail), `flow_resolved_url` consumption hook wired as step 2.5 in the orchestrator's GOTO/URL-assertion chain (site-specific resolution always runs first). Learning wired into the conftest teardown hook + `synthesize_stories.py` parent sweep; `FLOW_MEMORY_ENABLED=0` hermetic gate in tests. 33 tests; seeded from 908 real sidecars → 64 patterns / 6 sites / 4 cross-site flows.
- **Output artifact validation — AI-043 Layer 3, live overlay alignment (2026-08-11)**: `src/heatmap_alignment.py` — renders the suite heatmap and asserts, in a real browser, that every overlay box centre hits the element it claims on the live page (locator-scoped `elementFromPoint` + ancestor/descendant containment in one evaluate; live document-size mapping catches wrong-frame drift when the page changed between steps; `missing`/`hidden` catches stale locators). `scripts/validate_report_artifacts.py --full` opens each recorded URL and runs Layer 3 (exit 1 on misalignment); offline mode unchanged. 18 offline unit tests + 3 live tests against the ecommerce mock (real chromium + real tracker metadata math; one shared browser per module to avoid Windows paging-file exhaustion under xdist). AI-043 marked complete on the roadmap. Also: doc audit — AI-034 stale checkboxes ticked, Phase 1 Multi-Agent checklist split into done vs NOT BUILT (dormant scope), BACKLOG Phase 4 Export TODO cleared.
- **Baseline comparison tool (2026-08-10, AI-041 support)**: `scripts/eval/compare_model_baselines.py` diffs two `eval_model_baseline.py` outputs in one command — auto-discovers `training_data/model_baseline_*.json` (older = before), per-story attribution via `story_head`, aggregate deltas (valid-skeleton rate, criteria cover, hallucinated login, skip lines, placeholders, errors), `--json` output, exit 0/2/1 (no-regression/regression/usage).
- **Output artifact validation — AI-043 Layers 1+2 (2026-08-10)**: `src/artifact_validation.py` — deterministic invariants for heatmap/Gantt/Plotly artifacts (heatmap points must be document-% in [0,100]; HTML payloads parseable/finite; aggregated counts consistent; Gantt durations finite ≥0; no NaN/None/empty series), `scripts/validate_report_artifacts.py` CLI (exit 1 on errors), golden fixtures in `fixtures/report_golden/` (good / legacy-pixel / NaN-duration), and 3 new Gate-0 checks in `scripts/smoke.py`. Running it over all 51 production evidence dirs caught real off-page markers (negative y).
- **Roadmap items AI-042/043/044 (2026-08-09/10)**: cross-site flow memory, output artifact quality gate, visual grounding — in `docs/plans/ROADMAP_ROADTO_PRODUCTION.md` Tier 3/4 + summary checklist.
- **Strix Halo 27B QLoRA field guide (2026-08-10)**: `docs/sessions/2026-08-10_strix_halo_27b_qlora_field_guide.md` — the working 4-bit training recipe on a 64 GB Windows Strix Halo box + a graveyard of 12+ dead ends (Studio's 4-bit→16-bit flip, BIOS modes, expandable_segments crash, batch/context OOM combos).

### Changed
- **B-047 residual: golden +20 bonus is now site-scoped (2026-08-10)**: `GoldenPattern.site_hash` seeded from dataset base_url (mock sites use canonical :8781/:8782/:8783 ports), stored in Milvus metadata, and enforced in both `_golden_pattern_bonus` and `scoring_bonus_for`. Also fixed a pre-existing round-trip bug — `site_hash` was missing from `MilvusLiteBackend.search` output_fields, which silently disabled the learned +5 bonus in production; real-Milvus round-trip regression tests added. Store rebuilt with site-scoped goldens (96 patterns, 7 distinct site hashes).
- **RAG learning lock fix (B-047 deferred, 2026-08-10)**: `learn_from_evidence_sidecars()` in `src/rag_learn.py` — the parent process sweeps `evidence/*.evidence.json` after each site's executions in `resolve_and_learn` (the pytest-subprocess hook is lock-blocked by the Milvus parent hold). Batch runs now actually learn (verified: 275 passing sidecars / 1120 learnable steps on disk).
- **Evidence coordinates are document-relative (2026-08-10)**: `_get_element_metadata` adds scroll offsets to the viewport-relative bbox before computing document-% `viewport_pct` (clamped to [0,100]) — fixes off-page heatmap markers for elements above the viewport (found by the AI-043 validator, e.g. y=-4.02 in production sidecars).
- **AI-041 training run: ❌ failed/closed (2026-08-11)**: Qwen3.6-27B trained successfully (4-bit QLoRA, loss 0.94→0.081, 15 steps/2h) but the GGUF export never completed — the 16-bit merge needs ~55 GB memory + ~110 GB disk peak that a 64 GB Windows box can't provide, and `merge_and_unload` doesn't exist on the Qwen3.5 arch. All artifacts deleted; runbook marked SUPERSEDED; see field guide.

### Added
- **Model-level baseline measurement (2026-08-09, AI-040/AI-041)**: `scripts/eval/eval_model_baseline.py` scores the live LLM's Phase-1 skeleton generation on the 35 synthetic stories through production's validation gates, capturing a full reproducibility envelope (model path, llama.cpp /props: n_ctx/temp, git commit + dirty flag). Baseline captured for `Qwen3.6-27B-UD-Q4_K_XL.gguf`: valid skeleton 100%, criteria cover 100%, hallucinated login 0%, 1504 placeholders; pipeline eval static 97.9%. After fine-tuning, re-run the same script for a trustworthy before/after.
- **Training runbook + backlog (2026-08-09, AI-041)**: `docs/sessions/2026-08-09_unsloth_training_runbook.md` — AMD/Strix-Halo capability summary, model selection (safetensors only; NVFP4 is NVIDIA-only, 27B bnb-4bit doesn't exist yet), Studio settings table, GGUF export + model-swap flow (no .env edit — pipeline auto-detects via /v1/models), and baseline comparison steps. BACKLOG tracks the training run as AI-041.
- **`--resolve-and-learn` full combo (2026-08-08, AI-040)**: `synthesize_stories.py` Stage 4 resolves pre-generated skeletons against live/mock sites (production `TestOrchestrator.run_pipeline`), executes them, and auto-learns passing steps into the RAG store via the conftest hook. `--rag-both` runs RAG-assisted + cold-start passes (2× resolution data); append-mode dedupe persists story → resolved-code rows into `training_data/playwright_resolved_alpaca.jsonl` (112 rows across all 7 sites, 3464 resolved evidence calls). Mock sites auto-start per-site servers on :8781-8783 (repo-root for lv_insurance, `mock_sites/<site>` for banking/ecommerce). Full combo run: mocks × RAG on+off 56 passed/6 failed, live × RAG on 20 passed/23 failed.
- **Fine-tuning dataset generation tooling (2026-08-07, AI-040)**: `scripts/build_finetune_dataset.py` converts pipeline artifacts (`scrape_manifest.json`, eval golden keys) into Alpaca-format JSONL for Unsloth Studio — (story → skeleton) rows plus (placeholder → locator) resolution rows; `scripts/synthesize_stories.py` LLM-synthesizes new stories per eval site (anchored to a real element inventory), runs the offline Phase-1 skeleton generator through production's validation gates, and merges passing rows (`--mode linear|graph|both`; graph is deterministic temp=0, linear is stochastic). Seed corpus in `training_data/`: 172 skeleton rows + 90 resolution rows. Also surfaced a llama-server config issue (156K context → Vulkan OOM on the 48 GB Strix Halo UMA; relaunched at 9072).
- **Test-pack split: contract/adversarial/resilience layers** (2026-08-07, work item 2): `tests/contract/` (6 tests — mock artifact/schema/import/route/behaviour contracts), `tests/adversarial/` (7 tests — 404-page pollution, overlay injection, broken-locator, modal scoping), `tests/resilience/` (6 tests — corrupt DB, reload-safe RunResult, sidecar-without-teardown, concurrent opens, corrupt settings). Default pytest runs them offline via `-m "not slow and not integration"`; they run in CI.
- **`scripts/gate_full.py`** (2026-08-07, work item 3): one-command verification chain smoke → unit pytest → eval-static → verify_production → export_gate, exit non-zero on first failure; `--offline` (gates 1-3, CI-able), `--skip N`, `--pytest-args`.
- **Banking mock site + eval-007** (2026-08-07): `mock_sites/banking/` — 7-page static banking target (sign-in → dashboard → account detail → transfer → pay bills → success pages), localStorage session/balances, injectable consent/ad overlay, route aliases. Eval dataset eval-007 (8 criteria, 13 golden placeholders): **static 13/13 (100%), execution 8/8 passed**. Priority-2 mock in the catalog; the first auth-gated mock.
- **Run & Fix page** (2026-08-06): the app is now a 3-page workflow — Test Generator (setup/generate only), Run & Fix (generated code → run → repair → evidence → export), Evidence & Reports (history + compare). Results/repair/evidence/export moved off the generator page; empty-state with handoff; sidebar-loaded packages surface immediately (hydration) and auto-restore across sessions (`SETTING_LAST_PACKAGE`).
- **Package dropdown labels** (2026-08-06): the Load-package selector now shows readable date · site · story snippet · run counts instead of raw `test_YYYYMMDD_<slug>` names.
- **Run comparison** (`src/ui/ui_run_comparison.py`, 2026-08-06): pick a package + two runs on Evidence & Reports → per-test delta table + Changed/Fixed/Regressed metrics (filtered per-package — `load_all_run_results` ignores its directory arg).
- **Self-heal honesty** (2026-08-06): a no-results test run (timeout/collection) surfaces `run_error` instead of "✅ All tests pass"; LLM-reviewer failures name the affected tests instead of silently counting them unfixable; `heal()` resolves package-directory `saved_path` to the test file; pytest timeout raised 300s → 600s (`PIPELINE_TEST_TIMEOUT`, matching the app's runner).
- **Re-run Failed merge** (2026-08-06): `merge_rerun_results()` keeps passing tests in the table after a failed-only rerun (previously they were dropped).

### Fixed
- **Skeleton prompt taught login hallucination (2026-08-09, root cause of 55 bad rows)**: the Phase-1 prompt's EXAMPLE OUTPUT showed `{{FILL:username:admin}}` / `{{CLICK:submit button}}` unconditionally, so the LLM invented login steps for guest-flow sites (ecommerce/lv_insurance/demoqa). Example now shows a guest cart flow + a DO NOT INVENT AUTH rule (only emit auth steps when criteria reference them). Both byte-identical templates updated (`src/prompt_builder.py` t-string, `src/prompt_utils.py` legacy).
- **`login` keyword resolved to seed URL instead of the login page (2026-08-09)**: `UrlResolver.build_mapping` hard-pre-mapped `login` → seed, so `{{GOTO:login}}` landed on the homepage and fills like `username` failed (their DOM lives on `/login`), skip-marking whole tests even though locators had resolved. `login` now flows through normal keyword matching (scraped `/login` wins; SPA sites fall back to seed). Regression tests added.
- **Training-data poison: hallucinated-login rows (2026-08-09)**: `build_finetune_dataset.py --clean` drops rows containing login steps (`standard_user`/`secret_sauce`/`{{FILL:username}}`) on login-less sites. 55 rows removed across skeleton/resolved/synthetic sets; ecommerce skeletons regenerated with the fixed prompt (7 clean rows appended). Corpus now 0 hallucinated-login rows.
- **MockServer cwd pollution (B-039 note)** (2026-08-07): `MockServer._start()` did `os.chdir(served_dir)` and never restored it, breaking relative paths for any caller after auto-start (eval `--dataset <relative>`, a second server start in one process). The server now serves via the handler's `directory` kwarg — the caller's cwd is never mutated.
- **Banking-mock pipeline gaps (B-045)** (2026-08-07): five site-agnostic resolver/executor bugs the new mock made deterministic — (1) HTTP-404 pages surviving `_drop_dead_pages` (stdlib error body scrapes to 5 elements, above the 3-element dead-shell threshold; its "Error code: 404" text won ASSERT matching) now dropped via a content-based `_is_error_page()`; (2) login-click transition vocabulary was ecommerce-only (`inventory`/`products`) so auth-gated journeys never left the sign-in page — extended to `dashboard/accounts/home/overview`; (3) submit-success page transitions missing (form submits have no href, so success-message asserts resolved against the form's own submit button/error paragraph) — added transfer/payment submit→success inference; (4) role-worded descriptions ("pay bill button") fast-matched header nav links in Pass 1/2 before scoring — new `_named_role_in_description()` role gate + exact-text pre-sweep + submit-intent bonus + fillable-element CLICK penalty; (5) `fill()` crashed on native `<select>` (Playwright rejects it) and the LLM's fill value rarely equals the option `value` — `EvidenceTracker.fill()` probes the tag and routes to `select_option()` with value→label→substring fallbacks. Also: golden validator `_normalize_locator()` strips leading tags from class selectors (`p.account_balance` ≡ `.account_balance`), lifting eval-006 12/16 → 14/16 and eval-007 to 13/13. Eval static overall 95.2% → **97.9%**.
- **Locator-repair dedent crash (B-042)** (2026-08-07): a "🔧 Fix Locator" patch could silently break the whole suite at COLLECTION time — `apply_patch` rebuilt the patched line from regex groups that excluded the leading indentation, so a repaired line inside a test function landed at module scope (`NameError: evidence_tracker` → 1 error, 0 tests). The reconstruction now re-applies the original line's indent; an empty `original_locator` (which previously matched every line and mangled the file via `str.replace`) now raises `LocatorRepairError` instead.
- **Sidebar/CLI package dropdown "0 runs" (B-043)** (2026-08-07): package run counts came from manifest fields only bumped by CLI runs, so evidence-bearing UI runs (persisted to the workspace SQLite DB) never showed — a package with 13 real runs displayed `(1 test, 0 runs)`. `find_existing_packages` now reconciles against real run history via the new `run_stats_by_package()` (`GROUP BY test_package`), with legacy per-package counting and manifest values as fallbacks.
- **Run results silently vanishing (B-044)** (2026-08-06): Streamlit's module watcher reloads `src` modules mid-session, creating a NEW `RunResult` class — stored instances then failed `isinstance`, hiding results/evidence (this caused the recurring "results disappeared" reports, misattributed to UI toggles). New `is_run_result()` duck-type check (`TypeGuard`) replaces all 12 `isinstance(RunResult)` gates.
- **Reports showed 0.00s durations** (2026-08-06): sidecars never wrote a per-test duration; `evidence_serializer` + `evidence_tracker` now record `duration_s` (real wall-clock).
- **Reports showed "6. 6. [T06]" titles** (2026-08-06): the criterion's own enumeration was duplicated by the report's index; `report_builder` strips the leading "N. " prefix.
- **Reports written to the wrong directory** (2026-08-06): `build_report_bundle` did `Path(saved_path).parent`, mis-resolving when `saved_path` is a package directory (sidebar loads) — reports landed in `generated_tests/` instead of the package.
- **POM double blocks** (2026-08-06): the LLM skeleton emitted duplicated page-object imports/instantiations (`home_page` ×3 per test); `deduplicate_pom_lines()` (wired into the orchestrator) keeps one per page object.
- **Evidence screenshots captured mid-load** (2026-08-06): product grids showed blank images; `_record_step` now waits (bounded, 4s cap) for in-flight images before capturing, plus a 500ms post-navigate settle.
- **Click steps had no evidence** (2026-08-06): clicks only screenshotted on failure; success captures added (direct, hover-fallback, and scoring-fallback paths).

### Changed
- **3-page navigation** (2026-08-06): Test Generator / Run & Fix / Evidence & Reports (was 2 pages with results mixed into the generator).
- **Export panel** moved to Run & Fix (2026-08-06) so you export the package you can see.
- **HTML report embeds failed-step screenshots** (2026-08-06) — base64, self-contained; passing galleries stay on the Evidence page.
- **Living Test Plan UX** (2026-08-06): `Reviewed` moved to the far right (away from the headerless delete checkboxes), delete-row caption, flagged-condition warning + tooltip.
- **This-run evidence gating** (2026-08-06): stale sidecars from previous sessions no longer appear as "this run" — evidence renders only after a real session run.
- **`SETTING_MODEL_NAME`** now used by `streamlit_app.py` (2026-08-06) — the persistence existed via a literal key; the dead constant is wired in for clarity.
- **B-039 — Self-healing unblocked on real failures** (`src/pytest_output_parser.py`, `src/failure_classifier.py`, discovered live during AI-035 Tier-1 verification): (1) the failures-block name regex rejected `[chromium]`-suffixed headers, so `error_message` was always empty for parameterized tests — self-healing classified every real failure as OTHER and pre-screened it as unfixable; the header regex now tolerates param suffixes and strips them before the lookup. (2) `failure_classifier` now recognizes the evidence-tracker fast-fail (`_LocatorNotFoundError: Locator '...' not found on current page`) as `LOCATOR_TIMEOUT` with locator extraction, so the LLM reviewer actually sees the product's most common failure mode. Verified live: broken locator → self-heal → `fixed: 1, learned: 1, remaining: 0`, store gains `CLICK 'Cart link' → a[href="/cart.html"]` with `source=self_healing, confidence=1.0`, re-heal dedups (hit_count bump, one row).
- **B-036 Phase 4 Tier-2 walkthrough** (`streamlit_app.py`): the settings-persistence acceptance was verified live against the real Streamlit app (Playwright) — POM mode, provider, consent mode, OCR backend and workspace all round-trip across app restarts via `~/.ai-test-gen/settings.enc`, and the RAG Store panel shows the learned-pattern stats. The walkthrough also closed the last migration gap: the Streamlit UI now persists `provider_base_url` + `model_name` (save-on-change + seed-on-load), completing the "provider/model selection" migration from the spec.
- **AI-035 self-healing write-back** (`src/rag_learn.py` + `src/self_healing.py`): when the self-healing loop applies a verified `replace_locator` patch, the corrected `(description, locator)` pair is written back to the RAG store — `pattern_from_patch` maps the patched code line to a `LearnedPattern` (`confidence=1.0`, `source="self_healing"`), recovering the placeholder description from the failing test's evidence sidecar (matching the failed selector to its step label, `{{CLICK:view cart link}}` → `view cart link`), scoped by `site_hash(domain)`. `learn_from_patch` is guarded (never breaks healing); `HealingReport.learned` + CLI/UI display the count. This closes AI-035's original trigger — the self-healing lever and the learning loop are fully wired. +27 tests (2256 total).
- **B-036 Phase 4 — Settings store + field migration** (`src/settings_store.py`): consumer-grade settings that survive restarts, on the `secure_config` pattern — Fernet-encrypted `~/.ai-test-gen/settings.enc` (machine-keyed, corruption-tolerant, never crashes a run; separate file from `config.enc` so key storage and settings storage can't clobber each other). API: `SettingsStore` class + module-level `load_setting/save_setting/save_settings/get_all_settings/reset_settings`. Migrated sidebar state consumers actually set: `pom_mode`, `consent_mode`, `provider`/`model_name`, `workspace` — Streamlit sidebar (`SidebarConfig.render()`) and CLI `Session` (`create_session()` seeds from the store; settings win, env is fallback). `JIRA_PROJECT_KEY` env read removed from `src/config.py` (constant default `TEST`) — it's now an **export-time field**: Streamlit export panel + CLI menu (`Session.jira_project_key`), feeds `JiraReportGenerator` test-case IDs and a `Project:` header line in the Jira report (`PipelineReportService.build_reports(jira_project_key=...)`). `OCR_BACKEND` → persisted setting (default `pymupdf`); env read in `get_ocr_backend()` is now a fallback only. `LANGGRAPH_ENABLED` removed outright (dead flag — `--use-graph` is the supported path; `generate_skeleton(use_graph=...)` replaces the env read; orchestrator/eval-runner env reads deleted). Streamlit "Learned Patterns" settings section folded in (`SidebarConfig.render_settings()` — RAG store stats via `store_stats()` + guarded prune button). +30 tests (2229 total); eval static 95.2% unchanged.
- **B-036 Phase 3 — Evidence auto-learn (AI-035 core)** (`src/rag_learn.py`): when a generated test step passes, the verified `(action, description, locator, site)` pair is written back to the local RAG store — `RAGStore.upsert_pattern()` dedups on `(action_type, description, site_hash)` (repeat bumps `hit_count`, store stays bounded); teardown hook in `generated_tests/conftest.py` learns from passing runs (guarded, batched, never breaks a run). Site-scoped scoring: `SAME_SITE_LEARNED_BONUS = 5` for same-site learned patterns, **0** for cross-site (anti-poisoning), threaded orchestrator → matcher → resolver → scorer. Privacy: only one-way `sha256(domain)` stored — no URLs/PII. Plan: `docs/plans/AI-035_B036_P3_plan.md`. Verified live against the e-commerce mock (dedup'd learned patterns with hit counts); eval static 95.2% unchanged.
- **B-036 Phase 1 — Always-on RAG** (`src/orchestrator.py`, `src/rag_retriever.py`): the retriever now builds by default — no `RAG_ENABLED=1` needed; `RAG_ENABLED=0` remains a transitional opt-out. Graceful degradation keeps behavior identical to the pre-RAG pipeline: empty store ⇒ no patterns ⇒ no bonus; any store/embedder failure (offline model download, corrupt DB) returns no patterns instead of raising, so RAG can never block generation (warning logged once per retriever). Unit tests made hermetic: the default suite forces `RAG_ENABLED=0` so machine-local store state can't change test outcomes; resolution accuracy is exercised by the eval harness.
- **B-036 Phase 2 — Bundled golden pack + auto-seed** (`src/rag_bundled.py`): ships the eval golden keys (`scripts/eval/dataset/eval-001..006`, 83 patterns incl. both mocks) + curated Playwright docs (27 chunks). First generation run seeds the store automatically with an idempotent marker (`evidence/.rag_bundled_seeded.json`, versioned); re-runs are a no-op. `rag_ingest.py --bundled` (re-seed, `--force` to force), `--stats` (per-type counts), `--prune-learned` (drop learned patterns, keep golden/docs — active once learning lands). `RAGStore` gains `counts_by_type()` / `delete_learned()`.
- **E-commerce mock site** (`mock_sites/ecommerce/`): deterministic, offline, localhost test target mirroring the automationexercise DOM classes the pipeline already knows (`#cartModal`, `.btn-success.close-modal`, `a.check_out`, `.add-to-cart`, `#empty_cart`). 6 static pages (home → products → product details → cart → checkout → success), localStorage cart, offline SVG product images, and an **injectable consent/ad overlay** (`?overlay=consent|ad`) that reproduces the B-029 click-swallow race on demand. **Route aliases** (`mock_routes.json` + `scripts/mock_server.py` 302-redirects) map the pipeline's keyword vocabulary (`/view_cart`, `/products`, `/checkout`, `/basket`…) to canonical files so journey discovery and cart-seeding reach cart/checkout *with items*, and page URLs stay canonical for `to_have_url`. Eval dataset **eval-006** (8 criteria, 16 golden placeholders, full checkout/payment leg — the eval-002 gap) + committed capture. Measured: execution **8/8 passed** against the mock.
- **FEATURE_SPEC_B036 consumer config** (`docs/specs/FEATURE_SPEC_B036_consumer_config.md`): always-on RAG (degradation already built), bundled golden pack auto-seed, evidence auto-learn (builds on AI-035 — the separate `learned_patterns` SQLite table is explicitly superseded), settings store on the `secure_config` pattern, Jira key → export-time field, `LANGGRAPH_ENABLED` removal. ~3 sessions.
- **Roadmap Tier 6 — Product Expansion** (FC-02 API, FC-03 .NET, FC-04 dashboard testing): beyond-browser-E2E directions on the kanban (23 roadmap items), with the guardrail that discover/resolve/emit/execute stay swappable seams.
- **Roadmap Tier 7 — User Documentation & Onboarding** (UD-01 user guide, UD-02 option-explanation UI revisit): records that the product ships with zero user-facing docs, inventories the Streamlit-vs-CLI option asymmetry (found in the B-036 Tier-2 walkthrough — e.g. OCR backend and workspace are Streamlit-only, the CLI reads them from the store but can't set them from the menu), and is **explicitly deferred** until the paid/free tier split (Phase 6/8) so docs aren't written twice. Now 24 roadmap items on the kanban.
- **Offline-suite guard** (`tests/test_no_live_network_in_default_suite.py`): static AST guard that fails if any unmarked test executes a navigation call (`goto`/`navigate`/`scrape_url`/`scrape_all`/`run_pipeline`/`attempt_login`) with a live-site URL literal — makes the `-m "not slow and not integration"` contract (default pytest is deterministic and offline) durable against new code. Skips tests that explicitly mock the network layer. Verified: planted live-goto/scrape/pipeline offenders are flagged; mocked + config-assertion tests are not.
- **Eval static in CI** (`.github/workflows/ci.yml`): new `eval-static` job runs `eval_harness.py run --mode static --min-accuracy 79` (offline, ~0.5s, exit 2 below floor) in parallel with lint/type-check — free resolver/scorer/prompt regression protection on every push.
- **Export gate** (`scripts/export_gate.py`): the export analogue of `verify_production.py` — exports a package in both flat + POM modes, validates artifacts (no evidence remnants, no stub bodies, POM pages shipped, run-history DB copied), collects both suites, then runs them and asserts pass. Default source is a bundled golden fixture (`fixtures/golden_package/`) mirroring a real generated package (arg-carrying evidence decorators, POM pages, run-history DB) that targets a tiny localhost site — deterministic, no external network, CI-able. `--source <pkg>` validates a real package; `--run-remote` adds live execution. Exit 0/1.
- **Golden export fixture** (`fixtures/golden_package/` + `fixtures/golden_site/`): minimal POM-mode package (evidence-aware POMs, `@pytest.mark.evidence(condition_ref=..., story_ref=...)` decorators, `evidence/run_results.sqlite`) targeting a 2-page static site served by the gate on `127.0.0.1:8123`.
- **Step-through test debugger** (`scripts/debug_step_through.py`): runs real generated test functions in a headed Chromium window, pausing after every tracker step and printing the live overlay/modal state the auto-dismissal logic hides (add-to-cart modal, FreeCmp consent dialog, Google vignette, cart-link count, URL). `--auto`/`--headless` for non-interactive runs. Surfaces the invisible `EvidenceTracker.click()` dismissals.
- **Mock-site catalog** (`mock_sites/README.md`): plan for a local catalog of deterministic test targets across 8 product types (e-commerce, banking, insurance, booking, healthcare, HR, widgets, security) — no ad/consent overlay noise, CI-capable, golden keys never decay. E-commerce mock is build priority #1 (exercises the B-029/B-030 bug classes).
- **BACKLOG audit (2026-08-03 CLI review)**: logged B-029→B-036 — false-pass clicks w/o navigation verification, `#do_action` wrapper-div resolution, broken export suites, AI-012 orphaned DB copy, evidence gaps (no failure screenshots), corrupted `evidence/run_results.sqlite`, end-only sidecar persistence, consumer config architecture (env-var gates → always-on/UI). Plus test-pack restructure strategy (contract/adversarial/resilience layers, eval static in CI) and the mock-site catalog.

### Fixed
- **E-commerce mock resolver gaps (B-037)**: `#empty_cart` was winning "product name and price" (empty-state text now excluded from content ASSERTs via `_assert_empty_state_rejects` — the B-016 negation gate only ran in pass-1, not scoring); the "cvc" FILL was unresolvable against the "CVV" field and skipped the whole checkout test (cvc↔cvv↔cvv2 synonyms added); "card number" filled the Cardholder Name field (`name="card_name"` shared the word "card" and won the pass-1 tie — mock now uses `cardholder_name`, and CSS classes participate in `_structural_bonus` so `.cart_total_price` matches "price"). Eval-006 execution: **6/8 → 8/8 passed** (full checkout + payment leg executes). +9 regression tests. Remaining static misses are LLM skeleton/ranking nondeterminism (the AI-037 class), now isolated from site variance by the deterministic mock.
- **Golden fixture run-history DB schema** (`fixtures/golden_package/evidence/run_results.sqlite`): regenerated to exactly mirror the real `SQLitePersistence` schema (`runs` + `test_results` + indexes, verified column-by-column) — the export gate copies this DB, and a consumer opening it with the real app previously hit a made-up schema.
- **Exports are now runnable and validated (B-031)**: POM-mode export globbed `pages/po_*.py` but generated pages are `home_page.py`/`cart_page.py` — glob now matches all `*.py` (minus `__init__.py`) so the pages that tests import are shipped. POM-mode export now preserves POM structure (imports, instantiations, method calls) instead of silently producing flat output with a dead `pages/` dir (`strip_evidence_from_test_code(..., preserve_pom_calls=True)`). `@pytest.mark.evidence(condition_ref=..., story_ref=...)` decorators are stripped in all forms (bare, arg-carrying, multi-line, whitespace variants) — previously only the bare form was removed, leaking `PytestUnknownMarkWarning` into exports. The B-020 assert family (`assert_hidden`, `assert_disabled`, `assert_enabled`, `assert_checked`, `assert_empty`, `assert_text`, `assert_text_contains`, `assert_value`, `assert_count`) is now converted to Playwright `expect()` in both test code and POMs — `assert_hidden` was the live gap (survived exports → runtime `NameError`). Exporting an all-stub / all-skip / test-less source package now raises `ValueError` instead of silently producing a non-runnable suite (34 of 35 historical exports were stubs). Same-second same-slug exports no longer overwrite each other (unique `_1`, `_2`… suffixes).
- **Export run-history copy fixed (B-032)**: export copied `evidence/playwright_tests.db` — a name nothing in the repo creates — so the run-history copy was a silent no-op since AI-012. It now copies `evidence/run_results.sqlite` (legacy `playwright_tests.db` fallback for old packages; WAL/SHM follow the found name). Same fix in `pipeline_artifact_manager._count_run_results` (also fixed a Python-2 `except A, B:` that worked by accident).

### Fixed
- **False-pass clicks now fail truthfully (B-029)** (`src/evidence_tracker.py`): a "successful" click on a link whose URL never changes is now detected — overlays are dismissed and the click retried once, then the recorded step is amended from `passed` to `failed` instead of silently continuing on the wrong page (the cause of the checkout-cluster failures). Unscoped `button.btn-success.close-modal` dismissal scoped to modal containers.
- **Failed steps always carry evidence (B-033)**: fast-fail steps (locator missing/hidden) now capture a screenshot + failure note (previously skipped), every step records its `url`, and screenshot-capture failures log a warning instead of being silently swallowed. The enshrined test asserting `screenshot is None` on fast-fail was flipped to the new contract (+3 new B-029 contract tests).
- **Evidence sidecar persists incrementally (B-035)**: `_record_step` writes the sidecar on the first step and on any failed/partial step, so a killed/timed-out test leaves real evidence instead of orphaned PNGs.
- **Corrupt evidence database self-heals (B-034)**: `SQLitePersistence` recreates a corrupt database file at construction; `EvidenceIndex` recovers + retries on `DatabaseError` (never drops a healthy DB), and the live `evidence/run_results.sqlite` was healed + rebuilt (359 sidecars indexed). Also fixed the Python-2 `except A, B:` syntax in `evidence_index.py` (worked by accident). +2 corruption-resilience tests.
- **"Check Out" no longer resolves to a wrapper div (B-030)** (`src/placeholder_scorers.py`): the B-025 "clickable container" bonus (+10) outranked the real button's interactive bonus (+5), so `{{CLICK:Check Out}}` emitted `#do_action` (a div whose click does nothing) over `.btn.btn-default.check_out`. Container bonus now +3 — below link/button (+3 role +2 href) — so interactive elements win when both match; containers still win text-only matches. Eval static 100% (no regression) + 2 regression tests.

---

### Added
- **Soft-404 SPA recovery** (`src/scraper.py`): saucedemo (SPA on GitHub Pages) serves every `.html` path as HTTP 404 from an app shell that JS-redirects to the real view. `_scrape_url_sync_result` now proceeds when the final URL differs from the requested one (`_is_soft_404`), instead of bailing with `HTTP 404` and zero elements.
- **Site-agnostic stateful routing** (`src/url_utils.py`): `is_stateful_cart_checkout_path()` replaces the automationexercise-hardcoded `{/view_cart, /checkout}` path set — covers saucedemo's `/cart.html`, `/checkout-step-one.html` etc.
- **Concept-driven URL candidates re-enabled** (`build_common_path_candidates`): same-domain candidates from the shared route vocabulary (mirrors `journey_scraper.keyword_routes`); SPA sites have no hrefs for journey discovery, so cart/checkout URLs previously never entered the scrape set.
- **Dead-page + redirect-duplicate filters** (`src/placeholder_orchestrator.py`): <3-element SPA 404/login-wall shells and pages whose stateless scrape redirected to another page with duplicated content are dropped before resolution.
- **Navigation-intent fallback**: cart/basket navigation descriptions ("cart icon", "shopping cart") that fail element matching (SPA icons have no accessible name) re-resolve as GOTO to the verified page URL, keeping page context advancing through cart → checkout.
- **Post-login ASSERT mapping**: "logged in"/"login successful" assertions resolve to the inventory/products page, not the login page.
- **Semantic alias matching** (`src/url_resolver.py`): generic keyword→route aliases (products → `/inventory.html`, cart → `/basket`, login → `/signin`) — no per-site lists.
- **B-024g field matching** (`src/element_matcher.py`): separator-normalized word-subset fallback for FILL — "zip code" matches placeholder "Zip/Postal Code"; `normalise_element_text` now includes placeholder as last-resort text source.
- **`verify_production` saucedemo credentials**: env-overridable `SAUCEDEMO_USERNAME`/`SAUCEDEMO_PASSWORD` (default `standard_user`/`secret_sauce`, mirroring eval) passed to `TestOrchestrator`.
- **Modal-close no-op** (`src/evidence_tracker.py`): clicking a modal-close control whose modal is already dismissed records a satisfied no-op instead of failing (generated "close popup" steps collide with the tracker's pre-click auto-dismiss).

### Fixed
- **Journey subprocess dropped credentials**: `run_journey_subprocess_entry` serialized `credential_profile` in the payload but never read it back — auth-gated journeys silently ran without a session (saucedemo hit the login wall). Profile is now reconstructed and passed to `JourneyScraper`.
- **Journey scraper never logged in**: `JourneyScraper` now calls `attempt_login` at the starting URL when a `CredentialProfile` is present.
- **B-015 ghost (3 places)**: `_dismiss_modals`, `_dismiss_confirmation_modals`, and the repair setup script clicked `button:has-text("Continue Shopping")` globally — saucedemo's cart-page button navigated journeys and generated tests back to inventory, so `cart.html` was never captured and `#checkout` never clicked. Text-based dismissal is now scoped to modal/dialog containers.
- **Dead candidate URLs won ASSERT resolution**: guessed `/basket`, `/checkout`, `/inventory.html` keys (2-element shells or redirect-to-home duplicates) out-ranked real pages — dropped by the new filters; GOTO resolution now searches all verified pages, not the scoped current page.
### Added
- **Eval harness full-regenerate test execution**: `EvalRunner._persist_regenerated_tests()` writes just-generated code to `generated_tests/test_<site>.py` so `--mode full --regenerate` actually runs the tests — "Tests executed: 0" (every run) is now 33 executed / 17 passed (51.5% pass rate) with per-site breakdown and false-positive estimation.
- **Dialog-action scoping (Pass D)**: `ElementMatcher.pass_dialog_action()` — descriptions implying dialog/dismiss/confirm intent (ok/okay/close/dismiss/confirm/cancel/accept/done/continue/got it) resolve against in-modal interactive elements (`in_modal` flag / dialog role), preferring the modal's dismissal control (close-modal class semantics). Generic ARIA-based — no site-specific lists. Plus CLICK fast-path hygiene (`_hidden_element_penalty` + `_click_text_penalty` in the haystack fast path) and pass-2 hidden/role gates + ≥3-char substring containment ("OK" can no longer match "csrfmiddlewareTOKen").
- **Assertion-state polarity**: `polarity_assertion_type()` (closed/gone/disappeared/removed/hidden/dismissed/vanished/no longer/not visible/not shown) → `toBeHidden` → `EvidenceTracker.assert_hidden()` (`wait_for(state="hidden")` — hidden OR detached). Hooked at both ASSERT resolution paths.
- **`Session.story_slug`** property (slugify of the pasted story) — fixes the export flow's AttributeError.
- **CLI walkthrough `reject:` capability** — a step now fails when rejected text (e.g. "Export failed") appears in output, catching errors the loose "Press Enter" markers previously swallowed.

### Fixed
- **Page-load assertions**: `_is_page_state_assertion` no longer vetoes "title" — `<page> page title` routes to `to_have_url` (matches the golden encoding; "practice form page title" stays element-level). `resolve_url` root-path substring bug (a bare root URL no longer matches every multi-word description, e.g. "cart page loaded" → home URL). Golden validator compares `to_have_url` URLs trailing-slash-insensitively (production emits `https://host/`, goldens hold the bare form).
- **CLI tables truncated at 50 chars**: Living Test Plan and Test Table now wrap text to the full terminal width (`shutil.get_terminal_size` + `textwrap`) with continuation lines.
- **CLI log/menu interleaving**: `LLMClient._debug` and `TestOrchestrator._debug` (plus the short-response warnings) now print to stderr — `[llm_client]`/`[pipeline]` lines no longer pollute menu/table output under `PIPELINE_DEBUG=1`.
- **Export Clean Package produced empty suites**: `pipeline_saved_path` holds the test-FILE path (ui_pipeline) but export treated it as a directory — file→parent-dir normalization; export now carries the tests ("Tests: 1").
- **Flat export left broken POM references**: `strip_evidence_from_test_code` now removes POM imports/instantiations and converts `_page.click/fill(label, selector='sel')` → `page.locator('sel').click()/fill(...)`; `expect` import is idempotent (no more `import Page, expect, expect`). Exported flat tests are valid, runnable Playwright.
- **CLI walkthrough heal-flow staleness**: step markers updated for the "2 test(s) still failing. → Choice:" outcome (was a 1200s timeout).

### Changed
- **Skeleton prompts (all four templates)**: page-state ASSERT form added — "For 'verify <page> loads/opens' use `{{ASSERT:<page> loaded}}` (→ URL check). Do NOT write `{{ASSERT:<page> title}}`." Plus a polarity rule: "For disappearance checks ('popup closed', 'item removed') describe the ABSENCE." Legacy `prompt_utils.py` templates kept byte-identical to the t-string versions.

### CLI walkthrough driver
- **CLI walkthrough driver** (`scripts/cli_walkthrough.py`): marker-driven subprocess driver that exercises every CLI menu button — `--pass nav` (41/41, ~1 min) and `--pass full` (60/60 with real LLM + live site, ~15 min). Documents Windows pipe gotchas (use `read1()`, one write per `input()`, paste terminates on first blank line). Full logs to `scripts/archive/cli_snapshots/`.

### Fixed
- **CLI "Load Existing Generated Tests" crash** (`PermissionError`): `load_package_manifest()` was handed a package directory instead of the manifest file; now resolves `<dir>/package_manifest.json` or reconstructs, and both CLI callers pass `reconstruct=True` (legacy/`verify_*` packages have no manifest). 4 new tests.
- **CLI POM Mode / Consent Mode invisible toggles**: State block now shows `Consent : …` / `POM Mode : ON/OFF`; toggle handlers pause with a visible confirmation (also fixes a stray-Enter msvcrt bug that re-selected menu item 1).
- **POM mode dropped resolved selectors** → generated tests skipped at runtime: `home_page.click('product name link')` relied on a fuzzy runtime matcher that requires 2-word `_ELEMENTS` overlap. `get_pom_method_call` now emits `click(label, selector='…')`/`fill(..., selector='…')` and generated POMs click the resolution-phase selector directly (runtime matching is the fallback). Generic `fill()` added to generated POMs (previously absent → would skip).
- **Consent-overlay pollution**: OneTrust class-based markup (`.fc-*`, `#onetrust-*`) stayed in the DOM hidden and drowned scrapes (1,448/2,328 elements on automationexercise); consent removal matched only ID-based selectors. Added class-based selectors — POMs shrank 1806 → ~520 lines.
- **URL trailing-slash mismatch**: `expect(page).to_have_url("https://host")` failed after sites canonicalize to `host/`. `normalize_url()` applied at every URL emission point (GOTO steps 1-4, both ASSERT batch paths).
- **FILL resolved to a container div** (saucedemo `[data-test="login-container"]` reports accessible_name 'Username' by wrapping the input): fillability gate added to `pass1_text_match` (already present in `rank_candidates`).
- **Evidence-tracker post-navigation hang**: after a click that navigates, `_record_step` re-queried the now-dead locator's metadata — each un-timed Playwright call waited the 30s default (≈120s/test), blowing suite timeouts. `_record_step` accepts pre-captured `element_metadata=`; suites complete in ~140-175s.
- **verify_production timeout message + salvage**: printed the literal expression `{max(60, min(180, len(test_funcs) * 25))}s`; now shows the real value and saves partial pytest output + evidence count on timeout (`timed out after 180s — 1/6 tests completed`). Suite cap raised to `min(300, tests*30)`.
- **AI-037 Phase 3 — skeleton journey-structure guidance**: JOURNEY STRUCTURE rules added to both skeleton prompts (`build_skeleton_prompt` + `build_single_condition_prompt`, t-string and legacy byte-identical) — fill all fields on the current page before navigating; never place a step after the navigation that leaves its page; no `pytest.skip` for unplaced steps; use exact story labels. `JourneyScraper._scrape_current_page` now reveals SPA hidden sections before capture (mirrors the frozen-capture methodology — fixes hidden-section CLICK/FILL targets being hard-skipped as `is_visible=False`). Golden validator `_locators_match` now treats `:has-text()` needles as substring-equivalent (Playwright semantics). LV regeneration 15/24 → **19/24 (79.2%)**; ideal-skeleton live pipeline 21/24 → **24/24**; static eval 100% all sites.
- **AI-037 resolver fixes**: radio/checkbox label capture (scraper), clickable-div-with-id capture, `<strong>` display capture, synthetic-ARIA marker, radio `input[name][value]` locator format, quote-agnostic locator normalisation, camelCase splitting in `SemanticMatcher.get_words()`, Pass 1 synthetic-container skip, proportional text-content bonus + punctuation normalisation. LV Insurance resolver 23/24 → **24/24 (100%)**; regeneration 54% → **62.5%**. 15 new tests. `scripts/eval/refresh_lv_capture.py` reproduces the frozen LV eval data in journey state.
- **PEP 750 t-string PromptBuilder**: `src/prompt_builder.py` — structured prompt assembly that keeps trusted static structure separate from untrusted interpolated values. Per-field transforms (truncation) keyed by interpolation expression; `RenderedPrompt.to_log_entry()` emits a JSON-serialisable audit record (fields, truncation, static-vs-dynamic split). Templates: `build_skeleton_prompt()`, `build_single_condition_prompt()`. 13 tests.
- **Phase 1 Multi-Agent Architecture (LangGraph)**: Complete document-driven pipeline with three specialized agents (Ingestion, QA Director, Script Synthesizer). Supports dual-path execution (linear or graph via `LANGGRAPH_ENABLED`). See `docs/specs/FEATURE_SPEC_phase1_multi_agent.md`.
- **Document input mode**: Parse PDF and Markdown specs via pluggable OCR backends (`src/ocr_backends.py`). Extracts change deltas from headings, routes by persona role (QA lead, developer, product owner, operations), generates impact maps and consolidated reports.
- **OCR backend adapter**: `src/ocr_backends.py` with `PyMuPDFBackend` (CPU, default) and `UnlimitedOCRBackend` (GPU, 3B vision model). Auto-detects GPU/ROCm availability, configurable via `OCR_BACKEND` env var.
- **Journey URL inference**: When the journey scraper can't find a click target, probes common URL patterns (cart, checkout, finish) via HEAD requests and navigates there. SauceDemo checkout pages now reachable (5 pages scraped, was 2).
- **Mock server for eval**: `scripts/mock_server.py` uses `ThreadingHTTPServer` with daemon threads and error suppression. Auto-starts in eval runner for lv_insurance (eval-005).
- **AI-034 Test Table**: `src/test_table.py` — `TestRow`/`TestTable` data model with CRUD (add/remove/update/confirm), `TestTableExpander` (LLM expansion of conditions into concrete test rows; 1-row-per-condition fallback on LLM failure; cap 10 rows/condition), `table_to_conditions()` (confirmed rows → generation conditions). Test Table editors in both UIs: Streamlit `🧪 Test Table` expander (data editor + confirm-all) and CLI "Expand into Test Rows" menu flow. Living Test Plan gains a "Tests" column showing rows per condition. One skeleton function per confirmed row (`reviewed_conditions` in Streamlit, `_select_conditions_for_generation` in CLI). UAT: 2 conditions → 8 rows → 8 skeleton functions (1:1). `scripts/uat/uat_test_table.py`.

### Changed
- **AI-037 scoring/scraper behaviour**: synthetic ARIA-only containers no longer win Pass 1 fast-text or the B-025 container bonus for CLICK; text-content bonus now scales with overlap and normalises punctuation (`excess:` ≡ `excess`).
- **Prompt assembly migrated to t-strings**: `TestGenerator._generate_skeleton_single_call` and `Orchestrator._generate_single_condition_fragment` render prompts via `PromptBuilder` (byte-identical output to legacy `.format()`; verified by UAT). Both paths log structured `llm_call=... fields={...}` audit entries. Single-condition prompt now renders `{CLICK:...}` single-brace placeholders consistently with the main skeleton prompt (was literal `{{CLICK:...}}`).
- **Deterministic skeleton generation**: Planner and Generator agents now use `temperature=0` for reproducible graph pipeline output. Skeleton self-consistency: 55.6% → 100% (byte-for-byte identical across runs).
- **LLM provider temperature support**: `LLMProvider.complete()` and `LLMClient.generate()` now accept optional `temperature` parameter. Backward compatible — defaults to None (provider default).
- **PipelineGraph entry routing**: `PipelineState` now supports `input_mode`, `document_source`, `persona_role` fields. Document mode routes through `_parse_document` node before `ingest`.
- **AGENTS.md protected files**: Added `src/agents/` to protected files list.
- **Pre-commit mypy version**: `.pre-commit-config.yaml` mypy `v1.15.0` → `v2.3.0` (was crashing with INTERNAL ERROR on `src/agents/generator.py`).

### Fixed
- **B-028 fixed — journey discovery selects the cart nav link for product/add-to-cart actions** (see BACKLOG.md for full detail). Root causes: discovery passed lowercase actions to the scorer (all action bonuses silently disabled — "View Cart" won generic descriptions at score=1); hidden modals always present in e-commerce DOM crushed every real candidate with the modal penalty; POMs emitted hallucinated `text=<description>` locators; quantity inputs (role=number) were considered non-fillable; `tag` was missing from scraped elements (killing ASSERT display scoring). Fixes: action normalisation, visibility-aware modal penalty, product/category/dismiss context hints, DOM-existence index in generated POMs (`_ELEMENTS`), hidden-element exclusion from POM methods, `_is_fillable` aligned with `IntentMatcher`, `tag` added to `_build_element_dict`, FILL-quantity → +/- stepper fallback. Journey now visits product pages and reaches a non-empty cart (verify_production execution completes in ~65-75s; was 600s timeout; 12/13 gates). Full eval live-regenerate: 53.7% → 65.7% resolution accuracy; static 100% unchanged.
- **Batch placeholder fallback searches ALL scraped pages**: it was scoped to the seed URL, leaving elements on other scraped pages (e.g. `Proceed To Checkout` on view_cart) permanently unresolved. Per-journey resolution stays scoped for precision.
- **EvidenceTracker click fast-fail + proactive dismissal**: clicks on missing/hidden locators now fail in 0.0s with a clear error (was a 148s fallback marathon per click that blew the whole suite's timeout); hidden elements (CSRF inputs) and overlay-covered clicks are handled before the 5s wait. Consent/ad/confirmation-modal dismissal now runs proactively before each click (~2s vs 8-30s per blocked click).
- **Module-level LLM statement leaks stripped**: skeletons sometimes leaked bare calls (`home_page.click(...)`) outside test functions, crashing pytest at COLLECTION time. `normalise_generated_code` now strips module-level executable statements.
- **Structural assembler** (`src/test_structure_assembler.py`): the generated test file is rebuilt from the parsed journey model — the pipeline owns imports/decorators/def shells (built with a PEP 750 t-string); module-level leaks are structurally impossible. Wired into `run_pipeline` as the final pass.
- **LLM runaway generation capped**: providers now send `max_tokens`/`num_predict` (default 4096, `LLM_MAX_TOKENS`) — a runaway skeleton call no longer burns the full 600s request timeout.
- **Per-test pytest timeout**: UI/UAT/verify run commands now pass `--timeout=120` so a stuck test fails instead of hanging the suite.
- **LangGraph step count reduced 2.5x**: ScriptSynthesizerAgent now generates one skeleton fragment per condition (like linear pipeline) instead of all at once. Prevents cumulative prerequisite chaining where test N repeats all previous N-1 steps. LV Insurance: 137 → 52 placeholders, matching linear's 53.
- **B-027 re-fixed (properly)**: multi-concern unstructured requirements collapsed into a single condition. The 2026-07-24 comma-splitter fix had been reverted as too aggressive; the real fix adds SPLITTING RULES to the SpecAnalyzer prompt, routes wrapped single-item criteria ("1. <story>") to the LLM path, retries once with a CORRECTION on JSON parse failure, gates partial salvage (never silently drop corrupted objects), and falls back to sentence-boundary splitting (never mid-sentence commas). Verified: 1 story → journey + 2 boundary conditions. 10 new tests.
- **SpecAnalyzer JSON robustness**: LLM quoting story text verbatim inside `source` broke JSON parsing — prompt forbids embedded quotes, retry-once on parse failure, salvage gate.
- **Run Generated Tests UI**: `PIPELINE_TEST_TIMEOUT` default 300s → 600s (live-site suites exceeded 5 min). Run failures now render inline in the Run Generated Tests section (`run_tests_error`) instead of the off-screen `pipeline_error` slot near "Run Intelligent Pipeline".
- **LangGraph docs corrected**: pipeline is dormant (not wired into user flow — linear `run_pipeline` is the production path); `langgraph` is a core dependency and its tests run locally and in CI (71/71 pass).
- **LV Insurance SPA scraper fix**: Added `_reveal_hidden_sections()` to journey_scraper. Hidden SPA form sections (display:none) are now made visible before interaction via page.evaluate(). LV Insurance regeneration: 0% → 54%.
- **Eval captures at 100% resolution accuracy**: Fixed incorrect locators and assertions in pre-generated capture files (`scripts/eval/captures/`). AutomationExercise 50%→100%, DemoQA 88%→100%, TheInternet 86%→100%, SauceDemo 90%→100%. All 5 sites now at 100% static resolution accuracy.
- **LangGraph dependency handling**: Moved langgraph from optional `[langgraph]` extra to core dependency. `uv sync --upgrade` no longer silently drops it. Added `pytest.importorskip` guards to 3 test files for graceful degradation.
- **openai client pin**: Changed `openai==2.48.0` → `openai>=2.48.0` (was over-pinned during cherry-pick; it's just an HTTP client library). Updated to 2.50.0.

### Added
- **Cloud Provider Support**: `openai-compatible` and `openrouter` provider names for OpenRouter, Together AI, Groq, etc. via `OPENAI_COMPATIBLE_*` env vars. Uses existing `OpenAIProvider` with `is_openai_compatible` flag.
- **T-String Prompt Safety** (`src/agents/prompt_safety.py`): `safe_prompt()` wraps dynamic user input in `<user_input>` XML tags using Python 3.14 t-strings (PEP 750). Prevents prompt injection.
- **Graph Golden Keys** (`scripts/eval/dataset/graph/`): graph-specific evaluation keys extracted from captures via `scripts/eval/extract_graph_keys.py`.
- **POM Extraction in Validator**: `scripts/eval/golden_validator.py` now extracts POM calls (`inventory_page.click(...)`) alongside `evidence_tracker` calls.
- **Semantic Comparison Mode**: `python scripts/eval/eval_harness.py run --mode semantic` for locator-level comparison.
- **Phase 1 Multi-Agent Architecture (a-c)**: LangGraph-based `PipelineGraph` with three agents:
  - `IngestionAgent` — wraps `SpecAnalyzer` for criteria extraction + RAG domain enrichment
  - `QADirectorAgent` — priority assignment, prerequisite chaining, ambiguity flagging
  - `ScriptSynthesizerAgent` — delegates to `SkeletonGraph` for skeleton generation
  - Human-in-the-loop checkpoint: graph pauses after QA Director for test plan review
  - Enabled by default when langgraph installed (`pip install ai-playwright-generator[langgraph]`)
  - Graceful degradation to linear pipeline when langgraph not available
  - `LANGGRAPH_ENABLED=0` to force linear mode
  - 31 new tests, 1790 total, zero failures
- **AI-035 spec**: Self-Learning RAG — local pattern write-back from self-healing to RAG store
- **AI-030 Ingestion Agent**: `src/pdf_ingest.py` — PyMuPDF-based PDF extraction (heading detection, table extraction, chunking). `rag_ingest.py --pdfs` ingests domain PDFs into the RAG vector store. 3 real LV Insurance policy PDFs ingested → 66 chunks. RAG accuracy 53.7 → 64.2% (+10.5pp).
- **Phase 2b Self-Healing**: Rule-based pre-screening (`_pre_screen_failure()`) skips LLM call for assertion/navigation/other failures (cost optimization). Interactive repair fallback via `interactive_repair_candidates` in `HealingReport`.
- **Semantic scraper (B-032)**: Three-layer hybrid extraction — BS4 (structure) + CDP AX tree (accessible_name) + `page.aria_snapshot(boxes=True)` (placeholder, value, bbox, groups). Enabled by default; `SCRAPER_BACKEND=bs4` to disable.
- `src/aria_parser.py` — Parse Playwright's `aria_snapshot()` YAML output into standard element dicts (33 tests, all ARIA roles).
- `src/element_matcher.py` — Resolver accuracy improvements (B-024/B-025):
  - Pass1 word-ratio relax for short descriptions matching long element text
  - Pass1 heading skip for CLICK actions (headings are display elements, not click targets)
  - Pass1 id/name prefix match for FILL actions (e.g. "overnight" → `id="overnightLocation"`)
  - Pass1 word-boundary check for single-word containment (prevents "year" ⊆ "(years)" false positives)
- `src/placeholder_scorers.py` — Heading penalty (-20) for CLICK on elements without ID + container bonus (+10) for generic/div elements with ID (B-025)
- `scripts/eval/golden_validator.py` — Locator normalization: `#foo` ≡ `[id="foo"]`, `[data-test="bar"]` ≡ `.class[data-test="bar"]` (B-026)
- `docs/specs/FEATURE_SPEC_semantic_scraper.md` — Full design document for the semantic scraper transition
- `CONTEXT.md` — Updated architecture section with three-layer scraping + resolver pipeline
- `README.md` — Added "Semantic Scraper" feature bullet
- `docs/ARCHITECTURE.md` — Updated `PageScraper` description + added `aria_parser.py`

### Changed
- **Resolver accuracy improved**: 53.7% → 58.2% (+4.5pp, RAG off). LV Insurance: 83.3% → 95.8% (+12.5pp).
  - `_build_haystack`: added `id`, `accessible_name` + camelCase splitting
  - `_structural_bonus`: single-word ID match bonus (+15), `ref`→`reference` expansion, fixed camelCase ordering
  - `_split_camel_case()`: splits `quoteRef`→"quote Ref", `usageType`→"usage Type"
- **B-004, B-019 closed**: both fixed by architecture evolution (skeleton-first pipeline + semantic scraper)
- Self-healing: `HealingReport` gains `interactive_repair_candidates` field for Phase 2b fallback
- Roadmap hygiene: AI-028/AI-029/Phase 3 RAG/B-021 sub-checkboxes ticked, Phase 5 dataset expansion marked done, dual-tier eval marked `[R]` removed
- lv_insurance eval-005: **54.2% → 79.2%** (+25.0pp)
- Static eval harness: **79.1% → 88.1%** (+9.0pp vs baseline)
- `SCRAPER_BACKEND` env var now defaults to ARIA-hybrid; set to `bs4` for old behavior
- **Refactor 2026-07-11 — Journey scraper split:** `journey_scraper.py` (896→617 lines) split into 3 focused modules:
  - `src/journey_enrichment.py` — `capture_element_visibility_sync`, `capture_a11y_snapshot_sync` (deduplicated from `journey_executor.py`)
  - `src/cart_seeding_scraper.py` — `CartSeedingScraper` class (resolved circular import with `journey_scraper.py`)
  - `src/journey_subprocess.py` — `run_journey_subprocess_entry` subprocess entry point
- **Refactor 2026-07-11 — Placeholder orchestrator split:** `placeholder_orchestrator.py` (2,047→862 lines) split into 4 focused modules:
  - `src/role_mapper.py` — `DISPLAY_ROLES`, `_TAG_TO_ROLE`, `is_display_role`, `normalise_element_text`
  - `src/element_matcher.py` — Pass 0–3 matching engine, `ElementMatcher` class, B-020 semantic ASSERT resolution
  - `src/skip_manager.py` — consolidated skip insertion, placeholder line removal
  - `src/pom_helpers.py` — POM artifact generation, imports, instantiation, method calls

### Added
- CI/CD: parallelised quality gates — lint, type-check, sanitizer, and graph-freshness now run concurrently instead of sequentially (~15s saved per push)
- CI/CD: `graph-freshness` gate — warns when `graphify-out/graph.json` commit hash diverges from `HEAD`
- CI/CD: `docs-coverage` gate — warns when `markdown_docs/.sweep_progress.json` has pending files
- README.md: linked interactive call-flow diagram (`graphify-out/callflow.html`)
- README.md: added "Self-Documenting" feature bullet
- CONTRIBUTING.md: added Security section linking to SECURITY.md
- `scripts/maintenance/project_sanitizer.py`: replaced dead `links.csv` orphan audit with knowledge graph freshness check (reads `graphify-out/graph.json` `built_at_commit` vs `git HEAD`)
- `normalize_whitespace()` in `src/code_normalizer.py` — converts tabs to spaces and normalizes line endings (\r\n → \n) before other normalization transforms, preventing SyntaxError when LLMs emit tab-indented code
- `tests/test_code_normalizer.py` — 9 unit tests for `normalize_whitespace`, pipeline integration, and `ensure_test_navigation`
- AI-027 Session 2 screenshot capture during scraping: `ScrapeResult`, in-memory screenshot bytes, and interactive element bounding boxes for later vision enrichment.
- AI-027 Session 3 vision enrichment service: element crop, vision LLM call path, structured response parsing, and scraper enrichment bridge.
- **Refactor 2026-05-10 (Parts 1-7)** — Modular extraction reducing `streamlit_app.py` from 918 → 362 lines (60% reduction) per REFACTOR_PLAN_2026-05-10.md
  - `src/ui_pipeline.py` — Pipeline execution helpers extracted from `streamlit_app.py` (business logic, no rendering)
  - `src/ui_renderers.py` — Streamlit rendering helpers extracted from `streamlit_app.py` (pure UI, no business logic)
  - `src/evidence_serializer.py` — Evidence JSON serialization extracted from `evidence_tracker.py`
  - `src/screenshot_capture.py` — Screenshot capture utilities extracted from `evidence_tracker.py`
  - `src/state_tracker.py` — DOM state tracking extracted from `journey_scraper.py`
  - `src/form_detector.py` — Form detection and selector constants extracted from `journey_scraper.py`
  - `src/semantic_matcher.py` — Token-based semantic similarity extracted from `placeholder_resolver.py`
  - `src/intent_matcher.py` — Intent-based element filtering extracted from `placeholder_resolver.py`
  - `src/code_normalizer.py` — Code normalization transforms extracted from `code_postprocessor.py`
  - `src/llm_reasoning_filter.py` — LLM reasoning text detection extracted from `code_postprocessor.py`
  - `src/url_inference.py` — URL transition inference extracted from `placeholder_orchestrator.py`
- `CONTRIBUTING.md` — contributor guide with dev setup and coding standards
- `SECURITY.md` — private vulnerability reporting policy
- `CHANGELOG.md` — this file
- `CODE_OF_CONDUCT.md` — Contributor Covenant v2.1
- GitHub issue templates for bug reports and feature requests
- `src/analyzer.py` — CLI analysis module (replaces `cli/story_analyzer.py`)
- `src/config.py` — `AnalysisMode` and `ReportFormat` enums for CLI
- `src/code_postprocessor.py` — code string transformation helpers (extracted from `orchestrator.py`)
- `src/url_utils.py` — pure URL manipulation helpers (extracted from `orchestrator.py`)
- `src/report_builder.py` — report data preparation (extracted from `report_utils.py`)
- `src/report_formatters.py` — standard report renderers (extracted from `report_utils.py`)
- `src/evidence_report.py` — annotated screenshot/heatmap/journey generators (extracted from `report_utils.py`)

### Changed
- `cli/story_analyzer.py` → `cli/analyzer.py` — renamed for clarity
- `src/orchestrator.py` — extracted URL helpers to `src/url_utils.py` and code postprocessors to `src/code_postprocessor.py`
- `src/report_utils.py` — replaced with backwards-compatible re-export shim; logic moved to `report_builder.py`, `report_formatters.py`, and `evidence_report.py`

### Removed
- `cli/story_analyzer.py` — replaced by `cli/analyzer.py` + `src/config.py`
- `src/page_context_scraper.py` — deleted (deprecated, caused selector hallucination)
- Deprecated test files: `tests/src/`, `tests/example_test.py`, `tests/uat_pipeline_test.py`

### Fixed
- **Tab indentation SyntaxError** — LLMs emitting tab-indented code now normalized to spaces via `normalize_whitespace()` before `ensure_test_navigation()` injects 4-space indented navigation lines, preventing "unindent does not match" SyntaxErrors
- Pass 1 text match added to `PlaceholderOrchestrator._find_best_element_for_current_page()` — resolves nav links by element text before scoring, eliminating Products link tie bug
- Pass 1 text match added to `JourneyScraper._find_selector_for_step()` — journey discovery now navigates to correct pages (e.g. /products not /brand_products/*)  
- `resolve_all()` diagnostic replaced with regex scan of final_code — eliminates 25+ LLM timeout calls post-pipeline (runtime: 1263s → 165s)
- `src/journey_scraper_clean.py` dead file deleted (0% coverage, not imported)
- Punctuation stripping added to Pass 1 description normalisation — handles LLM-generated tokens like `'Products' link` with embedded quotes
- UAT saucedemo: 5/6 tests passing against real site with browser automation
- mypy `import-untyped` for pandas via `pandas-stubs` dev dependency
- mypy `import-untyped` for plotly via per-module override in `pyproject.toml`
- pre-commit hook failures from variable shadowing in `generate_3d_map.py` via mypy override
- Fix skeleton prompt generation to inject the exact expected test count into the LLM prompt.
- Improve placeholder postprocessing to unwrap `evidence_tracker.xxx({{...}})` wrappers with optional whitespace.
- Placeholder resolution now collects candidates across ALL scraped pages before selecting the global best match, preventing low-quality matches from early pages when a much better match exists on a later page (e.g., finding a cart page element for "username input" instead of the login page element). Added `tests/test_global_best_resolution.py` with 5 regression tests.

---

## [0.3.0] — 2026-04-10

### Added
- Multi-provider LLM support (`src/llm_providers/`) — Ollama, OpenAI, Anthropic, OpenRouter
- Pipeline architecture (`src/orchestrator.py`, `src/pipeline_models.py`, `src/pipeline_writer.py`)
- Anchor link extraction in page context scraper
- `src/coverage_utils.py` — coverage display-mapping logic extracted from `streamlit_app.py`
- `src/run_utils.py` — test command construction with re-run-failed-only support
- `src/semantic_candidate_ranker.py` — context candidate prioritisation
- `src/placeholder_resolver.py` — resolves LLM-generated placeholders in test output
- `src/skeleton_parser.py` — handles skeleton test scripts
- Credential profile selection persistence in Streamlit session state

### Fixed
- Migration from `pip` to `uv` as the sole package manager
- Coverage map now correctly reflects run outcomes (B-008)
- Structured failure tracking (`failed_pages`) with backward compatibility

---

## [0.2.0] — 2026-03-29

### Added
- `src/user_story_parser.py` — parses Gherkin, Jira AC bullets, numbered, and free-form stories
- `src/code_validator.py` — `ast.parse()` validation guard before saving generated tests (B-009)
- Multi-page scraping Phase A — `scrape_multiple_pages()`, `MultiPageContext`, `ScraperState`
- `.env.example` updated with correct `OLLAMA_TIMEOUT=300` default

### Fixed
- Parser banner incorrect on mixed pass/fail runs (B-006) — added 2 regression tests
- Duplicate error panels in run results UI (B-007)
- `src/pytest_output_parser.py` missing from repo (BREAK-1)
- Session state wipe blanking run results panel (BREAK-2)

---

## [0.1.0] — 2026-03-13

### Added
- Streamlit UI (`streamlit_app.py`) as primary entry point
- `src/page_context_scraper.py` — subprocess-based Playwright DOM scraper
- `src/pytest_output_parser.py` — parses pytest stdout into structured `RunResult`
- `src/report_utils.py` — generates local, Jira, and standalone HTML evidence bundles
- `src/file_utils.py` — test file save, rename, and newline normalisation helpers
- `src/llm_client.py` — Ollama API client with configurable timeout
- `src/test_generator.py` — core test generation pipeline
- Three report download formats: `local.md`, `jira.md`, `standalone.html`
- Ollama model selector in sidebar (live fetch via `ollama list`)
- Auto-save generated tests to `generated_tests/`
- Coverage tab with number-based test-to-criterion matching
- Run Now flow with pytest subprocess execution
- `pytest.ini` with `testpaths = tests` (generated tests excluded from default run)
- `launch_ui.sh` and `launch_dev.sh` startup scripts

### Fixed
- LLM generates async tests instead of pytest sync format (B-001)
- LLM output occasionally has all imports on one line (B-002) — `normalise_code_newlines()`
- Generated tests not saved automatically (B-003)
- Mock server startup incorrectly bundled into general launch script (B-005)

---

[Unreleased]: https://github.com/lacattano/AI-Playwright-Test-Generator/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/lacattano/AI-Playwright-Test-Generator/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/lacattano/AI-Playwright-Test-Generator/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/lacattano/AI-Playwright-Test-Generator/releases/tag/v0.1.0
