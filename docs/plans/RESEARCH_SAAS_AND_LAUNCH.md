# Research Log — SaaS Deployment & Launch Viability

**Created:** 2026-08-17
**Status:** Open — research tasks, not implementation items
**Feeds:** Phase 6 (SaaS), Phase 8 (GTM), BACKLOG AI-039 (rename)
**Cross-referenced with:** `RESEARCH_COMPETITIVE_LANDSCAPE.md` (2026-08-17) — market/
competitive research. Items marked ✅ below are now answered by that doc; see its §9
for the full mapping.
**Why this doc exists:** The Phase 6 checklist is an *infrastructure* list. The gaps
below are architecture/business/legal decisions that must be researched and decided
**before** SaaS work starts — several of them change what the code has to build.

---

## Decisions made (2026-08-17 — from research discussion)

| # | Decision |
|---|----------|
| D1 | **LLM model: BYO.** The deployer's LLM does the work. Local (Ollama/LM Studio) for one user, vLLM/self-hosted OpenAI-compatible server for a team, cloud API key (Anthropic/OpenRouter/etc.) for teams without local GPU. TanCat does NOT host LLMs. |
| D2 | **Deployment model: per-license/per-company v1.** Software deploys to the customer's infra (Docker/CLI), their LLM, their data. Multiple employees = one team deployment sharing one workspace. No cross-user account linking in v1. |
| D3 | **True multi-tenant SaaS (strangers sharing one platform) is tier 2** — not required for v1 commercial viability. Requires per-tenant storage/vector-DB/DB isolation (see §3). |
| D4 | **Credentials:** never persisted by TanCat where avoidable. CI/CD reads credentials from the CI platform's own secret store via env vars at run time. Interactive runs keep credentials in session state. If any persistence is needed, the existing Fernet `settings.enc` pattern is the only sanctioned store. |
| D5 | **Roadmap:** "Regenerate old packages after pipeline upgrades" added to Tier 5 (see ROADMAP_ROADTO_PRODUCTION.md). |

---

## §1. BYO-LLM architecture (decided — remaining research)

**Spec (decision 2026-08-17, WRITTEN 2026-08-17):** the Phase 6 build starts from a spec —
`docs/specs/FEATURE_SPEC_phase6_saas.md` (Draft — §9 open questions to grill before 6a/6e build). It covers: BYO-LLM
architecture (this section → spec §5.3), the free-tier limit (§5 → spec §5.5, resolved 2026-08-17 to runs/credits — the old "3 generations" sandbox number is arbitrary), license key design (§5 → spec §5.4), credential policy (§4 → spec §5.6). The roadmap's
Phase 6 is now a two-part plan: **Part 1 = per-company deployment (the v1)**, **Part 2
= true multi-tenant SaaS (deferred)**.

D1 is settled. Open research:

- [ ] **Provider coverage check:** confirm vLLM, OpenRouter, Anthropic, OpenAI, Google all
      work through the existing OpenAI-compatible path in `src/llm_providers/`.
      Known gap: per-agent model config (dormant Phase 1 scope) — NOT built. Decide if
      v1 needs "one model for the whole deployment" (simpler, recommended) or per-agent.
- [ ] **Quality floor:** what is the minimum model that produces passing tests?
      We have eval data per model — document a "recommended models" list + minimums.
- [ ] **"Check my LLM" health check:** first-run probe — list models, run a 5-token
      completion, warn if the model is too small / endpoint unreachable / key invalid.
      Design as a small CLI + Streamlit onboarding step.
- [x] **Cost analysis to confirm D1:** ✅ answered 2026-08-17 by competitive research —
      no vendor in the AI test-gen space hosts its own models (Mabl, testRigor, QA
      Wolf, Functionize, Qodo all BYO/cloud-API); GPU hosting vs $99–499/mo license
      revenue is a losing trade. Write the one-paragraph "why BYO" FAQ from
      RESEARCH_COMPETITIVE_LANDSCAPE.md §2.2/§5.2.

## §2. Deployment-per-company — what a customer actually installs

Research to write the deployment docs (and to confirm the v1 story is complete):

- [ ] **Docker image hardening:** the current image runs the Streamlit UI. For a team
      deployment: is one image with UI + headless driver + Action self-test enough?
      Who runs what (a server, or each developer's machine)?
- [ ] **Team deployment shape:** one shared Streamlit server (N employees, one
      workspace) vs each developer running locally with a shared vLLM endpoint.
      What breaks in each? (session state, concurrent runs, workspace file locking)
- [ ] **Licensing enforcement point:** where does the license key get checked —
      at startup (offline, signed token with expiry) or per-run? Offline validation
      means a signed key file (ed25519) that works with no internet. Decide + spec.
- [ ] **What phones home today?** Verify the "no data leaves your deployment" claim
      is literally true: audit all outbound HTTP in the codebase (LLM calls go to
      THEIR endpoint — confirm nothing else: no telemetry, no update checks, no
      PyPI/uv checks at runtime).
      ⚠️ **Escalated to priority (2026-08-17):** this audit is the #1 sales argument —
      it's the claim no cloud competitor can make. It gates both this doc and the
      positioning in RESEARCH_COMPETITIVE_LANDSCAPE.md (§3, §5.4 milestone 1).

## §3. Multi-tenant SaaS (tier 2 — research only, no build decision yet)

The three learned stores are **global per machine today** and are the leak vector if
strangers share a platform:

- [ ] `evidence/run_results.sqlite` — run history
- [ ] RAG vector store (Milvus Lite) — learns from self-healing patches, ingests docs
- [ ] Flow memory (JSON) — learns navigation patterns from passing runs
- [ ] Settings store (`settings.enc`) — includes API keys

Research:
- [ ] **Per-tenant isolation options:** per-tenant subdirectories (current AI-029, weak)
      vs per-tenant DB files + vector collections + flow stores (medium) vs
      per-tenant containers (strong, expensive). Cost of each.
- [ ] **Milvus Lite multi-tenancy:** does Milvus Lite even support multiple isolated
      collections/DBs per tenant, or do we need per-tenant files?
- [ ] **Process isolation:** can two tenants' pipeline runs safely run in one Python
      process (globals: `get_storage()` singleton, RAG store singletons, flow memory)?
      Probably not without a per-tenant context object — sketch the design.
- [ ] **SSRF guard:** (for any shared deployment) private-IP/localhost/metadata-endpoint
      blocklist on scraped URLs. Learn: OWASP SSRF, `169.254.169.254` cloud metadata.
      v1 per-company: document as a warning + cheap blocklist.

## §4. Credentials in CI/CD

D4 is settled. **Admin/role logins (confirmed 2026-08-17):** testing admin rights with
admin credentials is the normal path — journey steps already carry `credential_profile`
per step, and each test runs as its declared user. **Explicit rule (write into spec +
ToS): TanCat never selects credentials automatically, and the learning stores (flow
memory, RAG, self-healing) never learn which login unlocks which element** — they learn
navigation shape + locators only (no raw URLs, no credential text, no role-to-element
maps). A failing admin test is never re-run under a different user; self-healing repairs
locators, never switches accounts.

Research:
- [ ] **GitHub Actions secrets → env vars:** confirm the shipped Action reads
      credentials from `INPUT_*`/env and never writes them to disk (audit `ci/` +
      `scripts/ci_generate.py`). Document the "add secrets in repo settings" step.
- [ ] **GitLab CI/CD variables:** same audit for the GitLab template (masked/protected
      variables).
- [ ] **Credential leakage in evidence:** confirm screenshots/evidence never capture
      passwords (fields are filled with `fill()` — do screenshots mask inputs by
      default? Test it). If not, spec a redaction pass.
- [ ] **Customer responsibility clause:** ToS line — "you are responsible for any
      credentials you grant to the environments TanCat runs against."

## §5. Legal & commercial (owner: me — questions to answer, not code)

**Two-part SaaS plan (decision 2026-08-17):** Phase 6 is now Part 1 (per-company
deployment — customer's infra/LLM/data; team auth is on *their* instance; offline
license key; no-egress guarantee; SSRF blocklist) and Part 2 (true multi-tenant SaaS —
our platform, per-tenant isolation of sqlite/RAG/flow stores, S3, sandbox; **deferred
until Part 1 is selling**). Observability/uptime + concurrency/rate-limiting are
therefore NOT Part 1 work: customer ops watches their box, and the customer's own LLM
is the rate-limit boundary. They re-enter scope only with Part 2.

- [ ] **Entity & tax:** Cat Tan Operations Ltd as the selling vehicle? VAT
      registration threshold? How to invoice UK + international customers?
- [x] **Pricing model:** ✅ answered 2026-08-17 — **per-deployment, not per-seat**
      (testRigor $99/$450, Mabl ~$499/mo, QA Wolf per-test/ACV; "team shares one
      workspace" is the norm, matching D2). Suggested tiers: $99–149 self-serve,
      $299–499 pro, $1–3k/mo air-gap premium (Mabl "Private" ~$900 anchor).
      See RESEARCH_COMPETITIVE_LANDSCAPE.md §4.2.
- [x] **Free tier / sandbox size:** ✅ answered 2026-08-17 — comparable tools limit by
      **runs/credits, not generations** (Mabl 500 cloud runs/mo; testRigor time-boxed
      trial). Replace "3 generations" with **"N generations + evidence exports"** so
      the full value moment (story → generate → run → evidence → export) completes.
      See RESEARCH_COMPETITIVE_LANDSCAPE.md §4.2.
- [ ] **Terms of service:** "provided as-is" for generated tests (their release
      breaks — not my liability). Need it written down, not assumed.
- [ ] **Privacy policy scope:** if v1 stores nothing centrally, the policy is small —
      but the "no data leaves your deployment" claim must be verified first (§2).
- [ ] **GDPR:** does it apply to a UK company running it internally? Their personal
      data in their own test assertions is their responsibility — say so in ToS.
- [ ] **Professional indemnity insurance:** needed? Cost for a small software biz?
- [ ] **License key design details:** offline signed token format, expiry, grace
      period on validation failure, what the key authorises (deployment size?
      features? team seats?).

## §6. PyPI & the AI-039 rename (timing)

- [ ] **Learn:** how `pip install` works, how PyPI package names are claimed
      (names are permanent — a taken or badly-chosen name is stuck).
- [ ] **Decide the package name** (`tancat`? `tancat-testgen`?) **before first
      publish.** Publishing `ai-playwright-generator` (generic, descriptive) locks
      in a non-brand name or creates a confusing duplicate later.
- [ ] **AI-039 rename scope:** repo rename + PyPI name + Action owner reference
      (`<owner>/ai-test-generator@v1`) — one coordinated launch batch.
- [ ] **Semver from day one:** first publish should be a proper v1.0.0 with a tag,
      so the Action's `@v1` reference works.

## §7. Non-blocking items explicitly deferred (do NOT research yet)

| Item | Why deferred |
|------|--------------|
| Observability/uptime alerting | N/A for v1 per-deployment; customer ops watches their box |
| Concurrency/rate limiting | Customer's LLM is their rate-limit problem (D1) |
| Multi-tenant account linking | D3 — tier 2 |
| UD-01/02 user docs | Gated on tier split (Phase 6/8) — but note: deployment docs from §2 are needed for v1 sales, so split "internal docs" from "customer deployment docs" |

> **Cross-validation (2026-08-17):** competitive research confirms all four deferrals
> are correct — a solo vendor cannot out-SaaS funded incumbents (D3); customer-ops and
> customer-LLM rate-limit boundaries match how every rival actually sells. See
> RESEARCH_COMPETITIVE_LANDSCAPE.md §6–§7.

---

## §8. Commercial-readiness gaps — feature/architecture audit (2026-08-17)

Factual audit of the codebase against the commercial plan (answers: "do we need a
vector DB? is PDF ingestion up to scratch? chunking/indexing? what happens when the
embedding model changes? are the guard rails enough? what's the latency?").

### 8.1 Vector database
| Question | Current state | Gap for commercial | Severity |
|----------|---------------|--------------------|----------|
| Do we need a vector DB? | **Already have one** — Milvus Lite (embedded), `VectorStoreBackend` protocol (swap to ChromaDB/hosted Milvus = one-file change, flagged for Phase 6). | Milvus Lite is **single-writer** — safe for CLI/single-process Streamlit, but a per-company *team* deployment (D2: N employees, one workspace) risks concurrent writes from two Streamlit sessions or UI + CI Action. | **High** — blocks D2 team shape |
| Index type | IVF_FLAT, COSINE, nlist=128 | Fine at current scale (hundreds of chunks); revisit only if the corpus grows ~100x. | Low |

### 8.2 PDF ingestion (`src/pdf_ingest.py`)
| Question | Current state | Gap | Severity |
|----------|---------------|-----|----------|
| Is PDF ingestion up to scratch? | PyMuPDF: heading detection by font size, tables kept whole as markdown, chunking on heading boundaries (~2000 chars, 250 overlap). Optional `[pdf]` extra. | **No OCR** — image-only pages are *skipped*. Scanned insurance PDFs (common in the target domain) yield zero content. `src/ocr_backends.py` exists but is not wired into the ingest path. | **High** — core domain pain |
| Table handling | Tables kept whole, never split | A large table becomes one giant chunk → embedding/token limits, poor retrieval. | Medium |
| Chunking quality | Char-based heuristic (~500 tokens), naive overlap | Not tokenizer-aware; no semantic/recursive splitting. Adequate for advisory retrieval, weak for long domain docs. | Medium |
| Re-ingest safety | `--bundled` idempotent (version marker); learned patterns dedup by key | **Doc chunks have no dedup key** — re-ingesting a PDF/markdown dir duplicates chunks unless the store is manually cleared. | Medium |

### 8.3 Embedding model changes — REINDEXING REQUIRED (path currently broken)
| Question | Answer |
|----------|--------|
| What happens when the embedding model changes? | **Silent corruption or hard failure.** `SentenceTransformerEmbedder._DEFAULT_MODEL = "all-MiniLM-L6-v2"`; `dimension` returns literal `384`; the Milvus collection schema is fixed at dim=384 on first creation. Different dimension → inserts fail / collection must be dropped & recreated. Same dimension, different model → cosine similarity meaningless across embedding spaces → retrieval quietly degrades. |
| Is the model version recorded? | **No.** Store records no embedder identity; nothing detects a stale index. `rag_bundled` has a pack version marker but not an embedder stamp. |
| Is there a reindex command? | **No.** `rag_ingest.py` rebuilds golden/docs but has no "re-embed everything" migration; learned patterns wiped via `--prune-learned`. |
| Required fix (Phase 6 spec) | Store `embedder_name + dim` in collection metadata; on mismatch refuse retrieval and require re-seed; add `rag_ingest.py --reindex` re-embedding golden+docs and resetting learned. |

### 8.4 Guard rails
| Question | Current state | Gap | Severity |
|----------|---------------|-----|----------|
| Prompt injection | `src/agents/prompt_safety.py` wraps user input in `<user_input>` XML tags (PEP 750 t-strings) for agent prompts. | Coverage is per-prompt — audit every prompt path (skeleton gen, resolver, semantic ranker); AGENTS.md bans XML tags in skeleton prompts — resolve this tension. | Medium |
| SSRF | **Not implemented.** Only a `localhost:3000` config default for mock sites. | No private-IP blocklist, no `169.254.169.254` metadata guard, no URL-scheme restriction. §3 flags it; v1 per-company promised "warning + cheap blocklist" — neither exists. | **High** — the no-egress/security claim is a sales cornerstone |
| Credential redaction in evidence | Fernet-encrypted settings store; CI/CD reads env (D4). | **RESOLVED 2026-08-25** — `src/credential_redaction.py` (`masked_screenshot_page`) blanks credential fields during evidence screenshots; wired into `EvidenceTracker` (`evidence_tracker.py:346`) as AI-045 §8.4 #5. Verified shipped by the 2026-09-06 audit. | ~~High~~ Closed |
| Sandboxing | Generated tests run via real Playwright against real sites — by design. | No sandbox/dependency isolation; acceptable for v1 per-company (their infra), a hard requirement for multi-tenant (D3, deferred). | Low (v1) |

### 8.5 Latency
| Question | Current state | Gap | Severity |
|----------|---------------|-----|----------|
| What's our latency? | **No published number.** LLM timeouts: 5s probe, 30s list-models, 45s semantic ranking, 300s default, 600s max. `verify_production.py` times pipeline gen + execution; debug prints show per-phase elapsed. | No end-to-end latency benchmark, no SLO, no LLM-call cache. Per-run LLM calls: 1 skeleton + up to 3 corrections + semantic-rank batches (only when fast passes fail) + ASSERT-type selection. Embedding runs per-query at resolution time (MiniLM, CPU, fast). | **Medium** — demo/enterprise expectation is "story → test in minutes" |
| Free-tier implication | Cost ≈ £0 (BYO-LLM) so latency is the UX ceiling, not cost. | Target: < 2–3 min per 6-criteria story on consumer hardware with a mid-size local model; measure and publish a table per model tier. | Medium |

### 8.6 Accuracy evidence (for the sales claim)
- Current `scripts/eval/baseline.json`: **100% resolution accuracy on 67 resolutions** — but a **single site (saucedemo), 6 stories**. AGENTS.md cites 79.1% as the historical baseline; the file has since improved.
- **Gap:** "accurate on real sites" needs breadth — multi-site golden datasets (automationexercise, LV mock, saucedemo) re-validated on live sites, plus a published eval harness as the honesty signal (§5.4). Not enterprise-trustworthy on one site.

### 8.7 Priority order (feeds Phase 6 spec + BACKLOG)
1. **SSRF guard + egress audit** (8.4) — gates the no-egress sales claim (already escalated in §2).
2. **Embedding model stamp + reindex path** (8.3) — data-corruption risk if the model changes; cheap fix.
3. **Team-deployment concurrency** (8.1) — decides the D2 team shape; may be "one server, one process" + file locks instead of a DB swap.
4. **PDF OCR wiring** (8.2) — insurance scanned-doc pain; `ocr_backends.py` already exists.
5. **Screenshot redaction test** (8.4).
6. **Latency benchmark + LLM cache** (8.5).
7. **Multi-site eval dataset** (8.6).
