# Feature & price comparison — TanCat vs the 2026 field

> **Purpose.** Evidence for the pricing decision (roadmap: *"Pre-launch: business plan + pricing
> validation research"*). It answers three questions: what we actually ship, what competitors ship
> that we do not, and where the market is going.
>
> **How to read it.** Every competitor price is tagged **first-party** (read off the vendor's own
> page on 2026-09-23) or **third-party** (analyst/reseller estimate — directional only). Our own
> features are tagged with the file that proves them, because a claim without a code path is a
> marketing bug.
>
> **Supersedes** `RESEARCH_COMPETITIVE_LANDSCAPE.md` §2.1 and §4.2 where they disagree. Two claims
> in that doc are now stale — see §7.

---

## 1. Method

| Source | Use | Captured |
|---|---|---|
| Vendor pricing pages, rendered headless (Playwright) | first-party prices + product claims | 2026-09-23 |
| Tavily web search, `advanced` depth | third-party price estimates, market direction | 2026-09-23 |
| This repo (`src/`, `README.md`, `pyproject.toml`) | our feature inventory | HEAD `3bf0dd9` |

Known limits: most incumbents do not publish prices, so their numbers are reverse-engineered by
analysts. Two vendors publish nothing at all (§2). Treat every third-party figure as an order of
magnitude, not a quote.

---

## 2. First-party price evidence (2026-09-23)

| Vendor | Pricing page says | Read from |
|---|---|---|
| **testRigor** | **No prices published.** The nav item "Pricing" links to `/sign-up/`, which shows no figures. Free tier for *public* projects only. | testrigor.com (nav → /sign-up/) |
| **mabl** | **No prices published.** "Request a Quote", 14-day free trial. Includes **unlimited local and CI test runs**, unlimited test-run concurrency, unlimited apps/environments/workspaces, **unlimited Participant licenses**. Only *cloud-run credits* are metered. | mabl.com/pricing |
| **Katalon** | Published. Free **$0** (web + mobile + API, local execution, no AI assistant). Professional **$84/seat/mo** for the first 3 seats, **$150/seat/mo** from the 4th, billed annually. **Runtime Engine $145/license/mo.** **$158/session/mo.** | katalon.com/pricing |
| **Autonoma** | Published. Free tier **$0** (100K credits), then **$100 per 150K credits**, no minimum. **SELF-HOSTED: "Free, forever. Run on your own infrastructure. No limits, no usage costs."** Open source (BSL 1.1), SOC 2 Type II, SSO, VPC peering. | getautonoma.com/#Pricing |

**The two structural facts to take from this table**

1. **Nobody meters local/CI execution.** mabl gives local and CI runs away and meters cloud credits;
   Katalon meters seats and CI *runtime nodes*; Autonoma meters credits on their cloud only. There
   is no metered surface in a fully self-hosted deployment — which is exactly why our
   per-deployment licence is the only model that fits.
2. **Per-seat is dying in this niche.** mabl advertises "unlimited Participant licenses"; Autonoma
   advertises "unlimited users". Our per-deployment model matches where the market is, and it is a
   genuine differentiator against Katalon's $84–150/seat/mo.

---

## 3. Third-party price bands (directional)

| Vendor | Model | Estimated price | Confidence |
|---|---|---|---|
| QA Wolf | managed service, per test | **$8k/mo entry (~200 tests)**; ~$40–44/test/mo; Vendr median ACV **$83.1k/yr** (58 purchases) | medium-high (Vendr deal data) |
| Functionize | enterprise only | **$30–80k/yr**, no self-hosting | medium |
| Testim (Tricentis) | SaaS | ~$1.5k/mo starter | low |
| ACCELQ | per user | ~$70–120/user/mo | low |
| Autify | SaaS | $199 Starter / $599 Pro | medium |
| QA.tech | SaaS | $499–1,999/mo | medium |
| Applitools | visual add-on | $300/mo starter | medium |
| Octomind | SaaS, URL → Playwright | from ~$146/mo | medium |
| Momentic | SaaS | Starter from $49/mo (quote-based above) | medium |
| BugBug | SaaS | free plan + from $99/mo | medium |
| Midscene.js | OSS (MIT), BYO model key | $0 (14.6k★) | high |
| Playwright MCP | OSS | $0 (27–36k★) | high |

**Price floor of the category is $0**, and it is not a token floor: Playwright MCP + a local LLM
(LM Studio) is a documented, free, fully private test agent as of Feb 2026. Anything we charge must
be for something that stack does not give away.

---

## 4. Our feature inventory — verified against the code

| Capability | Evidence in repo |
|---|---|
| Story → **pytest sync** tests (not async), skeleton-first two-phase generation | `src/test_generator.py`, `src/skeleton_parser.py`, `src/prompt_builder.py` |
| Semantic scraper: BS4 + CDP accessibility tree + ARIA snapshot; stateful multi-page journeys | `src/scraper.py`, `src/accessibility_enricher.py`, `src/aria_parser.py`, `src/stateful_scraper.py`, `src/journey_scraper.py` |
| Placeholder resolution: scorer, semantic matcher, candidate ranker, section scoping, role mapping, fallback | `src/placeholder_scorers.py`, `src/semantic_candidate_ranker.py`, `src/section_scoper.py`, `src/role_mapper.py`, `src/locator_fallback.py` |
| Self-healing that writes repairs back into the local store | `src/self_healing.py`, `src/locator_repair.py`, `src/rag_learn.py` |
| Local site-scoped RAG memory (learns from passing runs) | `src/rag_store.py`, `src/rag_retriever.py`, `src/flow_memory.py`, `src/rag_bundled.py` |
| **Honest verification** — unverified assertions emit `pytest.skip`, not a green assert | `src/evidence_tracker.py` (`assert_attribute`, `assert_no_forbidden`, `assert_attribute_all`), `src/code_postprocessor.py` (`attribute_predicate`) |
| Evidence: annotated screenshots, credential masking, per-step URL, new-tab verification | `src/evidence_tracker.py`, `src/credential_redaction.py` |
| Role-based views: heat map (product owner), Gantt (test manager) | `src/heatmap_utils.py`, `src/gantt_utils.py` |
| Exports: **CSV, NDJSON, JUnit XML, Jira, HTML, Markdown** | `src/evidence_export.py` (`export_csv`, `export_ndjson`, `export_junit_xml`), `src/report_formatters.py` (`generate_jira_report`) |
| Traceability test → source document; PDF/OCR ingest of reference docs | `src/citation_verifier.py`, `src/source_refs.py`, `src/pdf_ingest.py`, `src/ocr_backends.py` |
| POM mode; multi-site suites | `src/page_object_builder.py`, `src/pom_helpers.py` |
| CI: GitHub Action (generate / generate-and-run / run-existing, PR comment, cache, `/adapt` + `/ignore`) | `action.yml`, `action/`, `scripts/ci_generate.py`, `scripts/ci_slash_commands.py` |
| BYO-LLM: llama.cpp, Ollama, LM Studio, any OpenAI-compatible endpoint | `src/llm_providers/`, `src/provider_config.py`, `src/llm_health.py` |
| Offline licence key, per-deployment tiers, usage metering | `src/licensing/license.py`, `src/licensing/tiers.py`, `src/usage_meter.py` |
| Bounded-egress claim **checked in CI** (SSRF guard + call-site audit) | `scripts/audit_egress.py`, `src/url_guard.py`, `scripts/smoke.py` |
| Eval harness as an honesty signal (golden-key accuracy gate, 97.9% static) | `scripts/eval/eval_harness.py`, CI job `eval-accuracy` |
| Interfaces: Streamlit UI, interactive CLI | `streamlit_app.py`, `cli/main.py`, `src/ui/` |

**Not present (checked, not assumed):** MCP server, mobile/Appium, API testing, desktop, visual
regression, performance, accessibility scanning, cloud grid/cross-browser, SSO/SAML, RBAC,
SOC 2/ISO, dashboards, recorder.

---

## 5. Feature matrix

`Y` = ships · `P` = partial · `—` = does not ship · `?` = not established

| Capability | TanCat | testRigor | mabl | Katalon | QA Wolf | Autonoma | Midscene | Playwright MCP |
|---|---|---|---|---|---|---|---|---|
| Input | story, reference docs | plain English | recorder, story, Jira, Playwright import | recorder, code | managed (humans) | your codebase | NL + screenshots | agent + DOM |
| Output | **pytest files in your repo** | cloud test cases | cloud test cases | Katalon format | Playwright (you own) | cloud (no test code) | TS/YAML | TS/JS |
| Tests are plain source you own | **Y** | — | — | P | Y | — | Y | Y |
| Self-healing | Y (writes back to RAG) | Y | Y (healing insights) | Y | Y (managed) | Y (vision) | P | — |
| Locator basis | DOM + a11y tree | resilient refs | element models + vision | object repo | Playwright | vision | vision | a11y tree |
| **BYO / local LLM** | **Y** | — | — | — | — | P (self-host inference) | Y (key) | Y |
| **Self-hosted / on-prem** | **Y** | — | — ("Private" = hosted) | P (test lab) | — | **Y (free)** | Y (runner) | Y |
| **Air-gap capable** | **Y** | — | — | ? | — | Y | P (model must be local) | Y |
| Web | Y | Y | Y | Y | Y | Y | Y | Y |
| Mobile | — | Y | Y | Y | P | Y (Appium) | Y | — |
| API testing | — | Y | Y | Y | P | P | — | — |
| Desktop | — | Y | — | Y | — | — | — | — |
| Performance / accessibility | — | — | Y | ? | — | — | — | — |
| Cross-browser / device cloud | — | Y | Y | Y | Y | Y | Y | Y |
| Visual regression | — | P | Y | P | — | P | P | — |
| Evidence artefacts | **Y (broad)** | Y | Y (dashboards) | Y | Y | Y | Y (HTML replay) | P (traces) |
| JUnit / CSV / Jira / HTML export | **Y (all)** | ? | Y | Y | Y | P | P | P |
| Requirement → test traceability | **Y** | P | P | P | — | — | — | — |
| Test management / dashboards | — | Y | Y (best-in-class) | Y | Y | Y | — | — |
| CI integration | Y (GitHub Action, GitLab) | Y | Y | Y | Y | Y | Y | Y |
| **MCP server** | — | ? | Y | ? | ? | ? | — | **Y** |
| SSO / RBAC | — | Y (paid) | Y | Y | Y | Y | — | — |
| SOC 2 / ISO | — | ? | Y (SOC 2) | ? | ? | Y (SOC 2 II) | — | — |
| Pricing model | per deployment | plan tier | cloud credits | seat + runtime node | per test | cloud credits / self-host | free | free |

---

## 6. What they have that we do not

Ordered by how often the gap loses a deal:

1. **Mobile, API, desktop, performance, accessibility.** mabl and Katalon sell "one platform for
   everything". We do web only. A buyer replacing a suite wants one vendor.
2. **Cloud grid + cross-browser + devices.** We run where the customer installs us. That is the
   point — but it means no Safari, no real devices, no parallelism out of the box.
3. **Dashboards, run history, flake analytics.** Our run history is local SQLite; mabl's dashboards
   are described as best-in-class. Analytics is what a QA lead shows their boss.
4. **MCP server.** mabl ships one; Octomind, TestSprite and Shiplight do too. In 2026 the agent
   ecosystem expects it. Ours is a backlog idea (**B-075**), not a product.
5. **SSO / RBAC / SOC 2.** Every regulated buyer's procurement form asks. We have none, so we cannot
   answer a security questionnaire today.
6. **Test management.** Suites, plans, runs, assignments, reporting views. We produce test files and
   evidence; we do not manage a QA process.
7. **Recorder / low-code editor.** Non-technical testers are a real segment for Katalon and Autify.
8. **Social proof.** mabl names Mercedes-Benz, LendingClub Bank and JetBlue. We have no testimonials.

---

## 7. Where we differentiate — and what is no longer unique

**Still genuinely ours**

- **The output is durable, reviewable source code.** pytest files land in the customer's repo and
  run under their pytest. Autonoma's model is the opposite ("no test code required"); mabl and
  testRigor keep test cases in their cloud. If the vendor disappears, our user still has a test
  suite. That is a real procurement argument.
- **Evidence breadth, and honesty about it.** CSV + NDJSON + JUnit + Jira + HTML, per-step
  screenshots, per-step URL, role-based heat map/Gantt, requirement→test traceability. No competitor
  advertises an *honest verdict* — that unverified assertions are reported as skips, never as passes.
  This is the "must show its working" buyer's feature, and it is the one thing an LLM one-shot
  cannot produce.
- **Bounded egress as a checked claim.** The egress audit runs in CI and is published. Competitors
  make a privacy claim; we can show the check.
- **Reference-document ingestion + traceability.** Stories *and* PDFs/requirements, with citations
  back to the source. Nobody else in this table sells that.

**No longer unique — correct the older research**

- `RESEARCH_COMPETITIVE_LANDSCAPE.md` §2.2 says *"Zero incumbents sell a local-LLM, no-egress test
  generator."* **That is no longer true.** Autonoma is open source, self-hostable, and gives
  self-hosted away **free, forever, with no usage limits** (first-party, 2026-09-23). Shiplight runs
  on "your own CI with your own LLM key". Midscene.js is MIT with a bring-your-own model key.
  Playwright MCP + LM Studio is a free private agent.
- §2.1 and §4.2 quote **testRigor $99 Starter / $450 Pro**. testRigor **no longer publishes any
  price**; 2026 third-party estimates put Pro at ~$900–1,000/mo. The landing page still prints the
  old figures as "anchors".

**Consequence:** self-hosting is no longer a premium tier in this market. It is table stakes for the
regulated buyer. The air-gap *premium* has to be paid for something else (§8).

---

## 8. Where the market is going (2026)

1. **Agentic testing is the whole conversation.** mabl now calls itself "the agentic testing platform
   that gives you coverage that builds itself, runs itself, and recovers itself". Tricentis and
   ACCELQ publish the same framing. Gartner: 33% of enterprise applications include agentic AI by
   2028, from under 1% in 2024.
2. **MCP is the integration surface.** mabl, Octomind, TestSprite, Shiplight and Testomat all ship
   MCP servers; Playwright MCP has 27–36k stars. Not shipping one makes us invisible to the agent
   tooling buyers are already using.
3. **Vision and intent are replacing selectors.** Autonoma and Midscene drive from screenshots;
   testRigor sells "resilient element references". Our DOM+a11y resolution is more deterministic and
   cheaper to run, but it is not the trend line.
4. **Data residency moved from nice-to-have to procurement gate.** SOC 2 Type II, Schrems II, EU
   sovereignty, HIPAA and DORA are the stated drivers for self-hosting in 2026. This is our wedge,
   and it is expanding.
5. **Consolidation continues.** Testim → Tricentis; the agentic startups (TestSprite, QA.tech,
   Momentic, Octomind, Bugzy) are all funded and all priced in the $49–1,999/mo band.
6. **The floor is free and credible.** Free OSS plus a local model is a real answer for a small team.
   Our free tier competes with that, not with testRigor's trial.

---

## 9. What this means for our prices

1. **Per-deployment is right, and per-seat is confirmed dead** in this niche (mabl "unlimited
   Participant licenses", Autonoma "unlimited users", Katalon's seat model the outlier).
2. **Do not enter the $49–499/mo self-serve lane.** It is crowded (Octomind $146, Momentic $49,
   QA.tech $499, Autify $199, BugBug $99), the incumbents are funded, and our differentiator is not
   price. The older doc's "Self-serve $99–149" tier should be dropped or folded into Pro.
3. **Self-hosted is free elsewhere, so the Air-Gap tier cannot be sold as "the licence".** Autonoma
   gives the software away. Our Air-Gap value is: contractual egress limitation, a support/SLA
   commitment, audit-ready evidence, onboarding, and a named counterparty for procurement. That is
   the only defensible premium — and it is exactly the "must show its working" buyer from the
   viability check.
4. **The right anchor for Air-Gap is not mabl Private ($900/mo).** It is the compliance/managed
   class: QA Wolf at ~$40–44/test/mo with an $83.1k median ACV, and the audit platforms that
   regulated buyers already pay for. Against that, a five-figure annual per-deployment figure is not
   aggressive.
5. **Pro should be priced as "the tool plus updates", not as a service.** It competes with a free OSS
   stack, so it has to be cheap enough to skip a procurement conversation.

**Open decisions this analysis does not settle (yours):**

- The **period** for the published price. The page says "/ deployment" with no term; every anchor in
  this document is monthly.
- **Three public tiers or four.** `src/licensing/tiers.py` defines four (free, self-serve, pro,
  airgap); the page shows three. Self-serve (Jira export) has no public entry.
- Whether to keep printing competitor anchors on the page at all. They drift — this document already
  shows two of them are wrong — and they invite comparison shopping.

---

## 10. Next research steps (only if the price is still not decidable)

1. Get one real quote: request a Katalon Professional and an Autonoma cloud quote, and note what a
   mid-size regulated team is actually offered.
2. Ask five design partners the price question directly (the GTM plan already gives them free
   licences) — "what would you expect to pay per deployment per year for this?".
3. Re-run the first-party price capture every 3 months; the third-party estimates in §3 decay fast.
