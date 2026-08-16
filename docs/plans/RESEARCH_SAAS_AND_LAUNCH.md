# Research Log — SaaS Deployment & Launch Viability

**Created:** 2026-08-17
**Status:** Open — research tasks, not implementation items
**Feeds:** Phase 6 (SaaS), Phase 8 (GTM), BACKLOG AI-039 (rename)
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

**Spec prerequisite (decision 2026-08-17):** the Phase 6 build starts from a spec —
`docs/specs/FEATURE_SPEC_phase6_saas.md` (NOT WRITTEN yet). It must cover: BYO-LLM
architecture (this section), the free-tier limit (§5 — the old "3 generations" sandbox
number is arbitrary), license key design (§5), credential policy (§4). The roadmap's
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
- [ ] **Cost analysis to confirm D1:** document why hosting LLMs is not profitable
      (GPU cost vs license revenue, token metering, abuse) — one paragraph for the
      pricing page's "why BYO" FAQ.

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
- [ ] **Pricing model:** subscription (per month, per what — deployment? seat?) vs
      perpetual + maintenance. What is a "seat" — everyone who can log in, or
      everyone who can generate? (v1 is per-deployment, so probably "per deployment")
- [ ] **Free tier / sandbox size:** roadmap says "3 generations" — arbitrary.
      Research comparable tools' trial limits (Mabl, testRigor, Cypress trial,
      Playwright MCP) + what's the minimum that completes the value moment
      (story → generate → run → evidence → export). Cost is ~0 since customer's
      LLM does the work, so the limit is about *perceived value*, not cost.
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
