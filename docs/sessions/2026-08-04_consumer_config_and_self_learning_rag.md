# Session: 2026-08-04 — Consumer Config (B-036 Phase 4) + Self-Learning RAG (AI-035) + Live Tier-1/Tier-2 Verification

**Branch:** `main` · **Commits:** `982d0cd`, `2118b54`, `8913ec4`, `427eee1` (all CI green, 9/9)

## What this session covered

Closed out the consumer-config backlog: B-036 Phase 4 (settings store + field migration), AI-035's last deferral (self-healing write-back), then **live verification** of both against the e-commerce mock (Tier 1) and the real Streamlit app (Tier 2) — which surfaced and fixed two pre-existing bugs (B-039) and one migration gap.

## Commit 1 — `982d0cd` B-036 Phase 4: settings store + field migration

- **`src/settings_store.py`** (new): `SettingsStore` on the `secure_config` pattern — Fernet-encrypted `~/.ai-test-gen/settings.enc` (machine-keyed, corruption-tolerant, best-effort writes; separate file from `config.enc` so key storage and settings storage never clobber each other). API: class + `load_setting/save_setting/save_settings/get_all_settings/reset_settings`.
- **Sidebar state migrated** (consumers' actual settings): `pom_mode`, `consent_mode`, `provider`/`model_name`, `workspace` — Streamlit sidebar + CLI `Session` seeding (settings win, env is fallback).
- **`JIRA_PROJECT_KEY`**: env read removed from `src/config.py` (constant `TEST`) → export-time field (Streamlit export panel + CLI menu); feeds `JiraReportGenerator` test-case IDs + a `Project:` header in the Jira report.
- **`OCR_BACKEND`** → persisted setting (default `pymupdf`); env read is now a fallback only.
- **`LANGGRAPH_ENABLED` removed** (dead flag) — `generate_skeleton(use_graph=...)` replaces the env read; `--use-graph` is the supported path.
- Streamlit **"Learned Patterns"** section folded in from the AI-035 deferral (RAG store stats + guarded prune).

## Commit 2 — `2118b54` AI-035: self-healing write-back (the last deferral)

`SelfHealingRunner` now writes corrected locators back to the RAG store after each successful `replace_locator` patch:
- `src/rag_learn.py`: `pattern_from_patch` / `learn_from_patch` — code line → `LearnedPattern` (`confidence=1.0`, `source="self_healing"`), description recovered from the failing test's evidence sidecar (failed selector → step label, `{{CLICK:view cart link}}` → `view cart link`), site-scoped via `sha256(domain)`.
- `src/self_healing.py`: `_learn_from_patch` hook (guarded, never breaks healing), `_evidence_context` (sidecar + manifest fallback), `HealingReport.learned` surfaced in CLI + UI.
- Learning loop fully closed: generate → execute → fail → self-heal → learn → next generation resolves better.

## Commit 3 — `8913ec4` B-039: self-healing blind to its own most common failure mode (Tier-1 discovery)

Live Tier-1 verification (mock: force a locator failure → heal → check store) revealed the loop could never fix a real generated test:

1. **`pytest_output_parser._FAILURE_NAME_RE` rejected `[chromium]`-suffixed failures-block headers** — all generated tests are parameterized, so `error_message` was **always empty** → `classify_failure("")` → OTHER → pre-screened unfixable. Fixed: `^_+ (\S+?) _+` + strip param suffix before the results lookup.
2. **`failure_classifier` didn't recognize the evidence-tracker fast-fail** (`_LocatorNotFoundError: Locator '...' not found on current page`) — now `LOCATOR_TIMEOUT` with locator extraction, so the LLM reviewer sees the product's most common failure.

Also fixed `pattern_from_patch` selector extraction for the **evidence-tracker API** (`evidence_tracker.click(sel, label=...)` first-arg) in addition to `page.locator(...)`, with quote-backreference matching.

**Verified live:** broken locator → heal → `fixed: 1, learned: 1, remaining: 0`; store gained `CLICK 'Cart link' → a[href="/cart.html"]` (`source=self_healing, confidence=1.0`); re-heal dedups (hit_count bump, one row). Eval-006 regenerate + execute: 8/8 skeletons, 12/16 static, **8/8 execution passed**.

**Noted (not fixed):** `MockServer._start()` does `os.chdir(directory)` on the whole process — relative `--dataset` paths silently yield 0 stories (eval harness works because its defaults are absolute). Fixing = save/restore cwd.

## Commit 4 — `427eee1` B-036 Tier-2 walkthrough: persist provider_base_url + model_name

Playwright-driven walkthrough of the real Streamlit app: toggled POM, switched provider, consent, OCR backend, workspace, model — **killed + restarted the app twice** — everything round-tripped via `settings.enc`. The walkthrough surfaced the last migration gap: the UI saved the provider key but not base URL + model name (spec: migrate "provider/model selection"). Fixed: save-on-change + seed-on-load for both fields. Test settings reset afterwards (machine left clean); the Tier-1 learned pattern left in the mock-scoped store as a demo artifact.

## Verification chain (all 4 commits)

smoke ✅ · ruff ✅ · mypy ✅ · pytest **2263 passing** · eval static **95.2%** (no regression) · pre-commit hooks ✅ · CI **9/9 green**

## Housekeeping

BACKLOG (B-036 → Shipped, B-039 added), CHANGELOG [Unreleased], ARCHITECTURE §9 (Consumer Settings), B-036 spec status → Shipped, AI-035 plan progress + §9 follow-ups marked done, markdown_docs (`settings_store.py.md` new; `rag_learn.py.md` / `self_healing.py.md` updated), kanban regenerated, knowledge graph updated (15593 nodes).
