# Feature Spec — Phase 6 (Part 1): Per-Company Deployment & Commercialisation

**Feature ID:** Phase 6 (Part 1)
**Created:** 2026-08-17
**Status:** Draft — **6a + 6b shipped 2026-08-17** (SSRF guard + egress audit; embedding stamp + reindex — §6 table); remaining phases build from §6 — grill §9 before 6e
**Priority:** Medium (deferred) — the commercialisable v1
**Depends on:** AI-029 (Workspace & Storage — shipped), Phase 7 (headless driver `scripts/ci_generate.py` + Docker action — shipped), AI-028 (Evidence Export — shipped), AI-035 (Self-Learning RAG — shipped), decisions D1–D5 (`docs/plans/RESEARCH_SAAS_AND_LAUNCH.md`), pricing/free-tier answers + open-core decision (`docs/plans/RESEARCH_COMPETITIVE_LANDSCAPE.md` §4.2/§4.4), AI-045 readiness list (`BACKLOG.md`, full audit in `RESEARCH_SAAS_AND_LAUNCH.md` §8)
**Roadmap ref:** `docs/plans/ROADMAP_ROADTO_PRODUCTION.md` §13 (Phase 6, two-part plan; Part 1 = per-company deployment)
**Estimated sessions:** Part 1 total 7–9. SSRF guard + egress audit alone (6a) = **1** — the fallback session if this spec is too big to build in one sitting.
**Product name:** "TanCat" (AI-039 rename deferred to Phase 8 — this spec uses the current repo name throughout)

---

## 1. Problem Statement

The product is a working, self-hosted AI test generator (Streamlit UI + headless CI driver, BYO-LLM via `src/llm_providers/`), but it is **not yet sellable**:

1. **The #1 sales argument is false today.** Competitive research settled the positioning: *"The AI test generator that never touches your data"* — the only defensible differentiator in a crowded market (testRigor/Mabl/QA Wolf are all cloud SaaS; **nobody sells BYO-LLM test generation**). But nothing in the codebase blocks scraping `169.254.169.254` or private IPs, and no audit proves "no data leaves your deployment" is literally true. The pitch cannot be made honestly until this lands. (AI-045 #1; escalated in `RESEARCH_SAAS_AND_LAUNCH.md` §2.)
2. **No commercial surface exists.** No license key, no tiers, no free-tier metering, no first-run "check my LLM" onboarding. The roadmap's Phase 6 was gated on this spec (NOT WRITTEN as of 2026-08-17) with the free-tier number ("3 generations") known to be wrong (comparables meter by **runs/credits** — Mabl 500 runs/mo; the value moment is story → generate → run → evidence → export, and a generation-count limit truncates it).
3. **Readiness gaps sit between "works" and "enterprise-trustworthy".** The §8 audit (2026-08-17) found: embedding-model change silently corrupts retrieval (no model stamp, no reindex); Milvus Lite is single-writer (risky for a team deployment); scanned insurance PDFs yield nothing (no OCR wiring); screenshot password redaction unverified; no published latency number; eval breadth is one site (saucedemo).

**This spec is the build plan for Phase 6 Part 1** — the per-company deployment a customer installs on their infra, pointed at their LLM, handling their data. It specs the SSRF guard **first** because it gates the pitch, then the commercial surface (health check → license → tiers → free tier), then the readiness list in §8.7 priority order. Part 2 (true multi-tenant SaaS) is explicitly out of scope (D3).

---

## 2. Philosophy

1. **Privacy/air-gap is the product, not a feature.** Every design decision in this spec is tested against one question: *does this weaken "no data leaves your deployment"?* License validation is offline; metering is local; nothing phones home — ever.
2. **Client-side license keys are an entitlement marker, not DRM.** The repo is Apache-2.0; a modified fork can remove any client-side check. That is accepted and documented (Phase 7 spec §13): the key's real value is ToS/support entitlement, honest tier enforcement for the 99% who run stock builds, and the air-gap premium bundle (onboarding, golden-key tuning, support SLA) that OSS can't bundle. Revisit at Phase 8 if traction creates a cloud-fork risk (levers already listed: AGPL / source-available / server-side moats).
3. **The customer's LLM is the boundary.** D1: the deployer's LLM does the work. No rate limiting, no concurrency control, no observability of *their* model — those re-enter scope only with Part 2 (customer-ops/customer-LLM boundaries match how every rival actually sells — `RESEARCH_COMPETITIVE_LANDSCAPE.md` §5.2).
4. **One model per deployment in v1.** Per-agent model config is dormant Phase 1 scope, deliberately not built. Simpler, and matches "one server, one workspace" (D2).
5. **The SSRF guard composes with, but is not the same as, the Phase 7 danger-zone.** Phase 7's allow-list decides *which hosts are legitimate test targets* (staging vs prod). The SSRF guard decides *which targets are safe to fetch at all* (public vs private/link-local/metadata). They stack: danger-zone can promote a public prod host; it cannot demote a link-local metadata endpoint.
6. **Free-tier limit is perceived value, not cost.** COGS ≈ £0 (customer's LLM). Meter runs/credits so the full value moment completes; the limit is the upgrade nudge.
7. **Security claims get tests.** "No egress", "screenshots don't leak passwords", "SSRF blocked" are each a test, not a paragraph.

---

## 3. Goals

| # | Goal | Acceptance criteria |
|---|------|---------------------|
| 1 | **SSRF guard** (AI-045 #1) | Scraping a URL whose host resolves to a private/link-local/metadata IP is refused with a clear error, across every navigation entry point (UI, CLI, CI driver, generated-package runs). Scheme restriction: `http`/`https` only. Explicit config to enable private networks for internal deployments. `169.254.169.254`-class metadata endpoints **never** scraped. Unit tests + mock-site regression. |
| 2 | **Egress audit + gate** | Exhaustive, reviewable inventory of every runtime outbound-HTTP call site; a static audit script that fails CI if an unrecognised outbound call site is added; a published "no data leaves your deployment" verification note in the docs. |
| 3 | **BYO-LLM health check** | `scripts/llm_health_check.py` + Streamlit onboarding step: probe endpoint (list models), run a ~5-token completion, warn on unreachable endpoint / invalid key / too-small model; machine-readable JSON output. Recommended-model list documented (minimums per use case). |
| 4 | **Offline signed license key** | ed25519-signed token (expiry, grace period, deployment id, tier claims), validated at startup and before CI runs, **zero network calls**; key file in the settings dir, env override for CI; clear failure UX (expired / invalid / grace). |
| 5 | **Per-deployment tiers + runs/credits free tier** | Tier config maps license claims → feature toggles; per-deployment usage meter (runs, evidence exports, storage, LLM tokens) readable by the customer's own ops; free tier = N runs + evidence exports per month, hard-stop with upgrade prompt at the limit. No per-seat logic (D2). |
| 6 | **Credential policy verified + shipped** | CI reads credentials from the platform secret store via env (audited, both GitHub + GitLab); a test proves screenshots don't capture filled passwords (redaction pass built **only if** the test fails); ToS clause drafted; learning stores provably never learn credential→element maps. |
| 7 | **Embedding model stamp + reindex** (AI-045 #2) | Collection metadata records embedder name + dim; on mismatch, retrieval refuses with an actionable error; `rag_ingest.py --reindex` re-embeds golden+docs. Changing the model can no longer silently corrupt retrieval. |
| 8 | **Team-deployment concurrency** (AI-045 #3) | Documented v1 team shape = one server, one process; pipeline runs serialised by file lock; UI and CI writes isolated by AI-029 workspaces; Milvus single-writer constraint stated in the deployment docs. |
| 9 | **PDF OCR wiring** (AI-045 #4) | `src/ocr_backends.py` wired into `src/pdf_ingest.py`; image-only pages produce content; doc-chunk dedup key added (re-ingest no longer duplicates). |
| 10 | **Screenshot credential redaction** (AI-045 #5) | Automated test fills a password field → screenshots contain no password material; redaction pass implemented if not already masked. |
| 11 | **Latency benchmark + LLM cache** (AI-045 #6) | Published E2E latency table per model tier; target < 2–3 min per 6-criteria story on consumer hardware; LLM-call cache in the pipeline. |
| 12 | **Multi-site eval dataset** (AI-045 #7) | Golden datasets for automationexercise + LV mock (in addition to saucedemo), re-validated on live sites; eval harness is the published honesty signal. |

---

## 4. Non-Goals

- **No true multi-tenant SaaS (D3).** Per-tenant isolation of the three learned stores (run_results.sqlite, RAG, flow memory), central auth, S3, shared sandbox — all Part 2, deferred until Part 1 is selling. `RESEARCH_SAAS_AND_LAUNCH.md` §3 stays research-only.
- **No pricing plumbing.** Payment processing (Stripe etc.), invoicing, tax — Phase 8 GTM, after pricing is validated by pilots. This spec ships the *entitlement* (license claims → feature toggles), not the *billing*.
- **No product rename (AI-039).** TanCat branding, PyPI name, repo rename, Action owner reference — one coordinated Phase 8 launch batch. This spec references current names.
- **No observability/uptime alerting, no concurrency/rate-limiting on our infra.** Customer ops watches their box; the customer's LLM is their rate-limit boundary (D1) — until Part 2.
- **No new generation logic.** Pipeline behaviour (skeleton, resolution, self-heal) is untouched; the SSRF guard wraps navigation, it does not change what navigation does.
- **No cloud account of ours required by any feature in this spec** — including license validation and metering (both offline/local).

---

## 5. Architecture

### 5.1 SSRF guard — FIRST (AI-045 #1, §8.4 of the audit)

**Current state (verified 2026-08-17):** no private-IP/link-local/metadata blocklist exists anywhere in `src/` or `scripts/`. The nearest seam is `src/url_utils.py::filter_urls_to_allowed_domain` (domain-string comparison against seed domains — it stops the LLM hallucinating cross-site URLs, but a `169.254.169.254` or `10.x` hostname matching the seed domain pattern is not addressed, and hostnames are never resolved to IPs). Playwright navigations happen at `src/scraper.py` (~L348), `src/stateful_scraper.py` (~L105/L176, subprocess), `src/journey_scraper.py`, `src/cart_seeding_scraper.py`; the headless driver is `scripts/ci_generate.py` (Phase 7, already has its own danger-zone allow-list). **The v1 per-company promise "warning + cheap blocklist" (`RESEARCH_SAAS_AND_LAUNCH.md` §3) has not been built.**

**Design — `src/url_guard.py` (new, pure stdlib, no network at import):**

```
validate_target_url(url, *, allow_loopback=True, allow_private_networks=False) -> SafeTarget
    |-> 1. SCHEME: http/https only (reject file:, ftp:, data:, gopher:, javascript:)
    |-> 2. HOSTNAME: reject empty; parse netloc (strip userinfo)
    |-> 3. RESOLVE: socket.getaddrinfo(host) — take ALL A/AAAA records
    |-> 4. ALWAYS-BLOCK list (refuse regardless of config):
    |       - 169.254.0.0/16, fe80::/10      (link-local — includes 169.254.169.254 cloud metadata)
    |       - 0.0.0.0/8, 255.255.255.255     (unspecified/broadcast)
    |       - 224.0.0.0/4, ff00::/8          (multicast)
    |       - IPv4-mapped IPv6 (::ffff:0:0/96) — normalise to IPv4 before classifying
    |-> 5. LOOPBACK: 127.0.0.0/8, ::1 — BLOCKED BY DEFAULT in CI/team contexts, but
    |       AITEST_ALLOW_LOOPBACK defaults ON for local/UI use: the product's own
    |       mock-site family and local dev servers live on loopback, and loopback
    |       traffic never leaves the deployment (the no-egress claim is about external
    |       egress). CI driver: loopback permitted only for allow-listed hosts
    |       (localhost mock) — same host source as the Phase 7 allow-list.
    |-> 6. PRIVATE networks: 10/8, 172.16/12, 192.168/16, fc00::/7 — BLOCKED BY DEFAULT;
    |       allowed ONLY with allow_private_networks=True (env AITEST_ALLOW_PRIVATE_NETWORKS,
    |       settings-store toggle, or CI input) — for customers whose staging sites
    |       legitimately live on an internal network; surfaced as a prominent warning
    |       in the UI and in CI logs
    |-> 7. Return SafeTarget(resolved_ip, port, hostname) — callers navigate to the
    |       RESOLVED IP (with Host header = hostname) so a DNS-rebinding race between
    |       check and connect is closed for the first hop
```

- **Redirects:** Playwright follows redirects; a target can start public and redirect to a private address. v1: on each redirect the guard is re-applied (`page.on("response")` / route interception is overkill — simplest correct-enough v1: attach a `page.on("request")` handler in the scraper that calls the guard for every request host and aborts blocking targets; documented limitation). Full mitigation (sandboxed egress proxy) is Part 2.
- **Where it's wired:** a single `guard = UrlGuard()` used by (a) the orchestrator's URL intake (`src/orchestrator.py` ~L268 `_starting_url`/`target_urls`), (b) every scraper's `goto` (scraper, stateful_scraper subprocess, journey_scraper, cart_seeding_scraper), (c) `scripts/ci_generate.py` (via the same intake path — the guard sits *under* the Phase 7 danger-zone check: `danger-zone: true` may promote a public prod host, it never unblocks a link-local/metadata address), (d) `generated_tests/conftest.py` navigation helper if one exists (verify at build time).
- **Composition with Phase 7 allow-list:** order is (1) Phase 7 danger-zone/domain allow-list decides *is this a legitimate target at all*, then (2) SSRF guard decides *is it safe to fetch*. `--danger-zone` cannot bypass the guard's ALWAYS-BLOCK list; internal-network staging behind private IPs uses `allow_private_networks: true`, not `danger-zone`.
- **LLM endpoints are NOT guarded by this** — a BYO-LLM deployment legitimately points at `http://localhost:11434` (D1). The guard applies to *scraped target URLs* only. (The LLM base URL is covered by the egress audit instead: it must be the customer's configured endpoint and nothing else.)

### 5.2 Egress audit — proving "no data leaves your deployment"

**Current state (verified 2026-08-17):** runtime outbound-HTTP call sites are all in `src/`:
- `src/llm_providers/__init__.py` — `httpx.Client` chat completions (base_url = user-configured), `auto_detect_provider` 1s probes (localhost defaults), model-list probes.
- `src/cli/menu_renderer.py` (~L300) — provider model-list probes (2s), user-configured URL.
- `src/llm_client.py` — probes/`list_models` through the same providers.
- `scripts/ci_*` hit GitHub/GitLab APIs — but these are **dev/CI tooling in this repo**, not the product runtime; the customer's CI uses the Action, whose outbound traffic is LLM endpoint + their own platform APIs (deliberate, documented in Phase 7 spec §9).

Nothing sends telemetry, update checks, or PyPI/uv calls at runtime (verified by inspection; needs the gate below to stay true).

**Design:**
- `scripts/audit_egress.py` (new): statically scans `src/` + `generated_tests/conftest.py` + product entrypoints for outbound-HTTP primitives (`httpx`, `urllib`, `requests`, `socket` connect, subprocess curl/wget), and asserts every site is either (a) a user-configured endpoint (base_url/provider URL from config/env — i.e. the customer's LLM) or (b) on a documented allow-list of literal hosts (e.g. localhost mock defaults). Exits non-zero on any unrecognised call site. Runs in CI (`smoke.py`-adjacent, Gate 0).
- Output: a machine-readable manifest (JSON) of call sites → target provenance, rendered into `docs/security/egress-audit.md` (new) — the public verification note the sales claim cites (`RESEARCH_SAAS_AND_LAUNCH.md` §5.4 milestone 1).
- **Constraint this enforces:** the free tier, license validation, and metering added by this Phase 6 spec must introduce **zero** new outbound calls (they don't — validation is offline, metering is local).

### 5.3 BYO-LLM health check ("check my LLM")

**Current state:** `LLMClient.list_models(timeout=5)` exists (`src/llm_client.py` ~L197); `auto_detect_provider` probes with 1s timeouts; `menu_renderer` probes with 2s timeouts. There is no structured first-run check, no model-capability warning, and no documented minimum-model recommendation.

**Design — `scripts/llm_health_check.py` (thin CLI) + `src/llm_providers/health.py` (testable core):**
1. Probe endpoint: `list_models` (5s) → endpoint reachable / key valid / models returned.
2. Capability probe: one ~5-token completion on the selected model (`LLM_MAX_TOKENS` floor respected).
3. Model-size warning: known-small-model heuristic (e.g. <7B params, no context-length metadata) → amber "recommended models" note, not a hard block. Documented recommended list: per-use-case minimums (the §1 "quality floor" research item — resolved as a doc + warning, not an enforcement).
4. Output: JSON `{provider, endpoint, reachable, models[], probe_ok, warnings[], duration_s}` + human text; exit 0 ok / 1 unusable / 2 config error. Streamlit onboarding step calls the same core (a "Test connection" button on the provider form — no new UI framework).
5. **One model per deployment** (philosophy #4): the check validates the deployment's single configured model; per-agent config stays dormant.

### 5.4 Offline signed license key

**Current state:** nothing exists. `src/secure_config.py` manages `~/.ai-test-gen/config.enc` (Fernet, machine-derived key) — the sanctioned local secret store. Env-var override pattern already used throughout (`AITEST_*`, `LLM_*`).

**Design:**
- **Token:** ed25519-signed JWT-ish payload (no JWT library needed — hand-rolled base64 + `cryptography` ed25519, matching the existing dependency): `{deployment_id, tier, claims[], issued_at, expires_at, issuer}`. Signing key held by Cat Tan Operations (issuer); the public key ships in the deployment (vendored constant — the trust root for all stock builds, deliberately not customer-settable, B-050; rotation ships with a product release).
- **Validation:** at app startup and before any CI generate/run (`scripts/ci_generate.py` gets `--license` or reads env `AITEST_LICENSE_KEY`/`AITEST_LICENSE_FILE`). **Zero network calls.** Checks: signature, expiry, tier claims well-formed.
- **Grace period:** expired → 7-day grace with a visible banner + log warning; after grace, new generations and CI runs blocked, evidence/export stays read-only. (Number is a proposal — grill.)
- **What it authorises:** tier + feature claims (see 5.5), deployment id (surfaced in the UI "About" and in evidence report headers), expiry. **No seat counts** (per-deployment pricing, D2).
- **Failure UX:** invalid/expired key → one clear message + pointer to the purchase/contact path; the app still runs in "unlicensed" mode showing the free tier (see 5.5) — license presence is an *upgrade*, never a lockout of the OSS core (open-core: the core stays usable; the paid claims gate premium features).
- **Honesty note (philosophy #2):** document in the spec + ToS that this is entitlement/support marking; a modified fork can strip it. The enforcement story for cloud-fork risk is the Phase 8 lever set, not client DRM.

### 5.5 Per-deployment tiers + runs/credits free tier + usage visibility

**Pricing (answered 2026-08-17, `RESEARCH_COMPETITIVE_LANDSCAPE.md` §4.2):** per-deployment, not per-seat. Free / Self-serve $99–149 / Pro $299–499 / Air-gap premium $1–3k (or per-deployment perpetual + maintenance). Free tier = **runs/credits** framing, NOT "3 generations" (roadmap wording updated when this spec lands).

**Design:**
- **Tier config:** `src/licensing/tiers.py` (new): a single table `{tier: {claims: {...}, limits: {...}, label}}`. Proposed claim split (proposal — grill): Free = core generation, evidence export (CSV/JSON/HTML), N runs/mo; Self-serve = +Jira export, +mock-site family; Pro = +POM mode, multi-site, CI Action (`ci_generate.py` licensed runs); Air-gap premium = +self-healing/RAG entitlements, +support/onboarding bundle, private-network support. The **feature toggles** are enforcement points already in the code (POM flag, RAG/self-heal enable, export formats) — the tier config gates them.
- **Meter:** `src/usage_meter.py` (new) reading the existing `evidence/run_results.sqlite` (run history already persisted) + evidence-export log. A "run" = one pytest execution of a generated package (the value moment). Counters per deployment: runs (monthly window), evidence exports, storage used, LLM tokens (from provider usage, where available). Written locally; no telemetry.
- **Free tier:** N runs + M evidence exports per 30 days; at the limit, new runs block with an upgrade prompt (generate stays free — the OSS core). Configurable for self-hosting (`AITEST_FREE_TIER_RUNS`), since the free tier is also the trial.
- **Usage visibility:** the meter powers a "Usage" panel (Streamlit + `ci_generate.py --json` gains a usage section) — the customer's own ops view (roadmap item), and the honest data behind license renewal.

### 5.6 Credential policy (D4 — verified + shipped)

**Current state:** `credential_profile` machinery exists (per-step profiles in journey models); Phase 7 Action passes `llm-api-key` as a secret input and `credential-profile` as JSON/path. Unverified: whether evidence screenshots mask filled password fields (fields are filled via `fill()`).

**Design (verification-first):**
1. **CI secret audit (GitHub + GitLab):** confirm the Action reads credentials from `INPUT_*`/env and never writes them to disk (`ci/` + `scripts/ci_generate.py`); GitLab template uses masked/protected variables. Output: a checkmark in the audit doc, or a fix.
2. **Screenshot redaction test** (AI-045 #5): new test fills a password field on a mock site, screenshots, asserts no password material is present (input `value` never captured by evidence tracker; rendered pixels are dots for `type=password` — verify, don't assume). If it fails → redaction pass (post-screenshot mask on evidence sidecars).
3. **ToS clause (draft in spec):** "you are responsible for any credentials you grant to the environments TanCat runs against" + the TanCat-side rule: **never selects credentials automatically; learning stores (flow memory, RAG, self-healing) never learn which login unlocks which element** — navigation shape + locators only, no raw URLs, no credential text, no role-to-element maps; a failing admin test is never re-run under a different user. This rule is already the design intent (research D4); this spec adds the verification tests that make it enforceable.

### 5.7 Embedding model stamp + reindex (AI-045 #2)

**Current state (audit §8.3):** `SentenceTransformerEmbedder._DEFAULT_MODEL = "all-MiniLM-L6-v2"`, `dimension` returns literal `384`; Milvus collection schema fixed at dim=384 on first creation; no embedder identity recorded; no reindex command.

**Design:**
- Collection metadata (or a sidecar `rag_store` table) records `embedder_name + dim` at creation.
- On open: if stored embedder ≠ configured embedder or dim mismatch → **refuse retrieval with an actionable error** ("embedding model changed since index creation — run `python scripts/rag_ingest.py --reindex`"), never silently return garbage.
- `rag_ingest.py --reindex`: re-embed golden + docs, reset learned patterns, rewrite collection metadata. Idempotent.

### 5.8 Team-deployment concurrency (AI-045 #3)

**Current state (audit §8.1):** Milvus Lite is single-writer; the stores (`get_storage()` singleton, RAG, flow memory) are process-global; a per-company team (D2: N employees, one workspace) risks concurrent writes (two Streamlit sessions, or UI + CI Action on the same box).

**Design (v1 decision — cheap, no DB swap):**
- **One server, one process** per deployment (the Docker image already runs one Streamlit server; documented shape). 
- **Pipeline serialisation:** a cross-process file lock (`filelock` or `fcntl`/`msvcrt` shim) around pipeline runs writing to the shared workspace; UI shows "another run in progress" instead of corrupting state.
- **UI vs CI isolation:** AI-029 workspaces already separate the CI runner mount from the UI workspace — keep; document that UI + CI on the same deployment serialise on the lock.
- Milvus single-writer constraint stated in the deployment docs; a DB swap (ChromaDB/hosted Milvus via `VectorStoreBackend` — one-file change) is the documented escape hatch if the team shape outgrows it.

### 5.9 PDF OCR wiring (AI-045 #4)

**Current state (audit §8.2):** `src/pdf_ingest.py` (PyMuPDF) skips image-only pages; `src/ocr_backends.py` exists, unwired; doc chunks have no dedup key (re-ingest duplicates).

**Design:** wire `ocr_backends` into the ingest path (image-only pages → OCR, behind the existing `[pdf]` extra + an `AITEST_PDF_OCR` opt-in); add a dedup key to doc chunks (content hash — re-ingest is idempotent like `--bundled`); chunking stays heading-boundary (~2000 chars/250 overlap) — tokenizer-aware splitting is a later polish, not a blocker.

### 5.10 Latency benchmark + LLM call cache (AI-045 #6)

**Current state (audit §8.5):** timeouts 5s probe / 30s list-models / 45s semantic rank / 300s default / 600s max; no E2E benchmark, no SLO, no cache.

**Design:** a benchmark script producing a published table per model tier (target: < 2–3 min per 6-criteria story on consumer hardware); an LLM-call cache (key = prompt hash + model + temperature; TTL'd, stored in the workspace `cache/`) for the expensive calls (skeleton retries, semantic-rank batches). Cache is the same pattern as the Phase 7 package cache — one key function, no new infra.

### 5.11 Multi-site eval dataset (AI-045 #7)

**Current state (audit §8.6):** `scripts/eval/baseline.json` = 100% resolution on 67 resolutions — **one site (saucedemo), 6 stories**. Not an enterprise-trustworthy claim.

**Design:** extend `scripts/eval/` with golden datasets for automationexercise + LV mock (mirroring the saucedemo pattern), re-validate against live sites, keep the harness as the published honesty signal; AGENTS.md §12 eval commands unchanged.

---

## 6. Delivery Phases (build order = audit §8.7)

| Phase | Scope | Sessions | Gates |
|-------|-------|----------|-------|
| **6a — SSRF guard + egress audit** (AI-045 #1) — **✅ SHIPPED 2026-08-17** | `src/url_guard.py`, wiring into orchestrator/scrapers/CI driver, `scripts/audit_egress.py` + CI gate, `docs/security/egress-audit.md`; unit tests + mock-site regression + a local metadata-endpoint integration test. **Unblocks the pitch.** | 1 | ✅ smoke 39/39 (incl. egress gate), full suite 2641/4 skipped, ruff + mypy clean, fake-LLM E2E green. `verify_production.py` needs LM Studio (:8080) — not run this session. |
| **6b — Embedding stamp + reindex** (AI-045 #2) — **✅ SHIPPED 2026-08-17** | embedder stamp sidecar (dim always-refused, embedder mismatch refused, legacy migrated for default model), RAGStore actual-embedder cross-check, `rag_ingest.py --reindex`, loud refusals (retriever/orchestrator/CLI) | 1 | ✅ suite 2654/4 skipped, eval static 97.9%, smoke 39/39, ruff + mypy clean; legacy migration verified on the real store |
| **6c — Team concurrency** (AI-045 #3) | file-lock serialisation, workspace isolation docs, deployment-shape docs | 0.5–1 | pytest + two-process race test |
| **6d — BYO-LLM health check** | `src/llm_providers/health.py` + `scripts/llm_health_check.py` + Streamlit "Test connection", recommended-models doc | 1 | pytest (offline, fake endpoint), UI smoke |
| **6e — License + tiers + free tier** | ed25519 key machinery (vendor-side `scripts/license_gen.py` + runtime validation), tier config + toggles, usage meter + free-tier cap + Usage panel | 1.5–2 | pytest (sign/verify/expiry/grace), offline — no network in tests |
| **6f — Credential policy** (AI-045 #5) | CI secret audit (GH + GL), screenshot redaction test (+ pass if needed), ToS draft section | 0.5–1 | pytest redaction test, audit doc |
| **6g — PDF OCR** (AI-045 #4) | OCR wiring + dedup key | 0.5–1 | pytest with a generated image-only PDF fixture |
| **6h — Latency + LLM cache** (AI-045 #6) | benchmark script + published table, pipeline LLM-call cache | 1 | benchmark run, pytest cache unit tests |
| **6i — Multi-site eval** (AI-045 #7) | automationexercise + LV golden datasets, live re-validation | 1 | eval harness green, baseline update |

**Ordering rationale:** 6a first because it gates the sales claim and is the fallback one-session build. 6b/6c before 6d/6e because data-corruption risk and team shape precede onboarding/commercial features. 6d before 6e so the onboarding moment ("check my LLM" → license → tier) has its check already built. 6f–6i are product-readiness, sequenced by §8.7 priority. **Not in Part 1:** per-deployment user auth (streamlit-authenticator — roadmap item, needs its own decision on identity backend), Docker production-shape polish (exists; verified by Phase 7 image work), payment/invoicing (Phase 8).

---

## 7. Security & Guardrails

1. **SSRF guard is layered, not absolute.** The v1 guard is resolve-and-check per request with a request-level redirect hook; it is the documented "cheap blocklist + warning" promise. A fully sandboxed egress proxy is Part 2 (multi-tenant). `169.254.169.254` and the whole link-local range are **unconditionally** blocked; private ranges are blocked by default and configurable for legitimate internal-network staging; loopback is blocked by default in CI/team contexts but default-on for local/UI use (the mock-site family lives there, and loopback never leaves the deployment).
2. **`--danger-zone` does not bypass the SSRF guard.** Phase 7's override promotes targets within the *domain* policy; the SSRF guard's ALWAYS-BLOCK list stands. Internal-network scraping uses `allow_private_networks: true`, a different, explicit setting with a visible warning.
3. **Nothing phones home.** License validation offline; metering local; free tier local. The egress audit gate (6a) enforces this against regression.
4. **Credentials never touch learning.** The D4 rule ("never learn which login unlocks which element") gets verification tests in 6f. CI secrets stay in the platform secret store (audited GH + GL).
5. **Screenshots are redaction-tested**, not assumed masked (6f).
6. **License is entitlement, not DRM.** Open-core honesty documented in spec + ToS; enforcement levers for cloud forks are the Phase 8 set (AGPL/source-available/server-side moats) — out of scope here.
7. **Free tier is a nudge, not a trap.** Generate stays free (OSS core); only *runs* are capped, with a clear upgrade path; the cap is configurable for self-hosters.

---

## 8. Testing Plan

| Gate | Command / trigger | Asserts |
|------|-------------------|---------|
| Unit — SSRF | `pytest tests/test_url_guard.py` (default suite) | scheme rejection; every always-block range incl. `169.254.169.254`, IPv4-mapped IPv6, multicast; private-block-default vs `allow_private_networks=True`; redirect hook blocks second hop; DNS-rebinding first-hop pinning (resolved-IP navigation) |
| Integration — SSRF | slow-lane test: local mock site + a fake "metadata endpoint" at `127.0.0.1`/`169.254.x` — assert scrape of the bad target is refused with the guard error; mock-site regression still green | guard wired at every entry point (UI path, `ci_generate.py`, generated-package navigation) |
| Egress gate | `scripts/audit_egress.py` (runs in CI Gate 0 with `smoke.py`) | manifest of call sites; unknown outbound primitive → non-zero exit |
| Unit — license | `pytest tests/test_license*.py` (offline; no network in tests) | sign→verify roundtrip, tampered payload rejected, expiry + 7-day grace, tier claims parse, unlicensed = free tier |
| Unit — health check | fake OpenAI-compatible endpoint (reuse `scripts/fake_llm.py` pattern) | probe OK / unreachable / bad key / small-model warning, JSON contract |
| Unit — meter | seeded `run_results.sqlite` fixture | monthly run counts, export counts, free-tier hard stop + upgrade prompt, `--json` usage section |
| Redaction test (6f) | mock site password field → evidence screenshot | no password material in screenshot/evidence (DOM value + rendered pixels) |
| Embedder drill (6b) | change embedder → open store | retrieval refuses with actionable error; `--reindex` fixes |
| Concurrency race (6c) | two processes run pipeline concurrently | second waits on the file lock; no store corruption |
| OCR (6g) | generated image-only PDF fixture | content extracted via OCR backend; re-ingest dedups (idempotent) |
| Eval (6i) | `python scripts/eval/eval_harness.py run --mode static` | multi-site golden datasets green; baseline updated |
| Full product | `python scripts/verify_production.py` + `python scripts/smoke.py` after every phase | product still works end-to-end |

---

## 9. Open Questions (for grilling)

1. **Feature/claim split across tiers** (§5.5 proposal: Free = core + evidence export + N runs; Self-serve adds Jira + mock family; Pro adds POM/multi-site/CI; Air-gap adds self-heal/RAG + support bundle). Is this the right split, or should self-healing/RAG stay in the OSS core (retention reason) with only support/onboarding paid? Phase 7 spec §13 warns the Action carries zero license logic — does the *CI driver* participate in tier gating, or is it free forever as the adoption on-ramp?
2. **Grace period** (§5.4: 7 days after expiry, then block new generation + CI, keep exports read-only). Right numbers? Right degradation?
3. **Free tier size** (N runs/M exports per 30 days). Comparable anchors: Mabl 500 cloud runs/mo. Proposal: 25 runs + 10 exports/mo — sanity-check against the value moment (a 6-criteria story ≈ 1 run).
4. **Loopback + private-network defaults**: link-local/metadata is unconditionally blocked (proposal). Loopback is default-ON for local/UI use (the mock family + the product's own self-test depend on it; it never leaves the box) but blocked in CI unless the host is allow-listed (Phase 7 already allows `localhost`). Private ranges (10/8, 172.16/12, 192.168/16) block-by-default with `allow_private_networks: true` (proposal) vs warn-only. Air-gap customers commonly target internal staging — does block-by-default on private ranges create onboarding friction that outweighs the security posture? (Recommendation: block-by-default; the health-check onboarding step surfaces the setting.)
5. **License key authorisation surface**: deployment id + tier + claims + expiry (proposal). Should it also carry a deployment *size* (e.g. max workspaces or max concurrent runs) for Pro-to-premium upsell? (Per-deployment, not per-seat — seats stay out.)
6. **Usage visibility scope**: runs, exports, storage, LLM tokens (proposal). Token counting depends on provider `usage` fields — acceptable that some providers report none (unknown)?
7. **Per-deployment user auth** (roadmap item, not in the 6a–6i build order): streamlit-authenticator on the customer's instance? LDAP/SSO for premium? Needs an identity decision before it's scheduled — is it its own session after 6i?
8. **Egress audit scope line**: `scripts/` dev/CI tooling excluded (they deliberately hit GitHub/GitLab). Confirm the line is "product runtime = `src/` + generated-package runtime + product entrypoints", not "everything in the repo".

---

## 10. Definition of Done

- **6a** shipped: `src/url_guard.py` + wiring at every navigation entry point (UI, CLI, CI driver, generated-package path), redirect hook, `scripts/audit_egress.py` + CI gate, `docs/security/egress-audit.md` published; unit + integration + regression tests green; `verify_production.py` green.
- **6b–6i** each shipped with its §6 gate (this is the *definition of done*, not a status record — as of **2026-09-05 all of 6a–6i are code-verified**: 6a/6b/6f/6g shipped 2026-08-17+ and 6c/6d/6e/6h/6i built + gated this session; the remaining Part-1 gap is per-deployment user auth, spec §9 Q7 — an identity decision, deliberately outside 6a–6i). **Canonical status lives in `BACKLOG.md` AI-045 + the roadmap Phase 6 item — this spec does not track shipped-ness.** Free-tier wording updated in `ROADMAP_ROADTO_PRODUCTION.md` §13 ("3 generations" → runs/credits).
- License machinery: vendor-side `scripts/license_gen.py` + runtime validation, fully offline, with an end-to-end license test.
- No new outbound-HTTP call sites introduced by Part 1 (audit gate enforces).
- Open questions §9 grilled and resolved (folded into the spec body or recorded as decisions).
- Session docs in `docs/sessions/` per phase; kanban regenerated.

---

## 11. Commercial Model (recorded — open-core, from 2026-08-17 research)

- **Revenue model: open-core, NOT donations** (`RESEARCH_COMPETITIVE_LANDSCAPE.md` §4.4): free Apache-2.0 core = distribution/credibility/community; revenue from the per-deployment license tier (air-gap compliance, evidence, self-healing+RAG, support/onboarding).
- **The differentiated revenue is the air-gap premium tier** — everything in this spec (SSRF, egress audit, offline license, no-egress free tier) optimises for that buyer first.
- **License key honesty** (Phase 7 spec §13): client-side entitlement is a support/ToS marker under Apache-2.0, not DRM; cloud-fork enforcement levers re-examined at Phase 8 if traction warrants (AGPL / source-available / server-side moats — RAG corpus + eval datasets are the candidate assets to move server-side).
- **Prerequisite human task (not code, not this session):** validate the air-gap wedge with 3–5 insurer/fintech QA-lead conversations (`RESEARCH_COMPETITIVE_LANDSCAPE.md` §8) — the highest-value unknown; the spec's tier/feature split in §5.5 should be revisited with that evidence before 6e ships.
