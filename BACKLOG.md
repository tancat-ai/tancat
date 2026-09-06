# BACKLOG.md
## AI Playwright Test Generator

Last updated: 2026-09-06 (AI-064 verified COMPLETE — fix committed 288e2f8 on 2026-08-29, never closed; scorer+resolver tests 130/130 + eval static green this session; remaining AI-058 gate blockers now logged as B-054 (single-candidate pool gap) + B-055 (page-context mis-assignment). B-048 FIXED: production-store wipe guard + self-healing seed marker, 7 tests, suite 3104/0 — see CHANGELOG [Unreleased] Fixed. AUDIT FOLLOW-UPS: B-050/B-051/B-052/B-053 opened from the 2026-09-06 security+commercial audit; B-048 flagged 🚩 PRE-LAUNCH BLOCKER; screenshot credential redaction verified SHIPPED (`src/credential_redaction.py`, 2026-08-25) — `RESEARCH_SAAS_AND_LAUNCH.md` §8.4 row corrected; mypy `map_3d` override removed. AE scraper-timeout re-verified 2026-09-06: does NOT persist (plain 18.4s / stateful subprocess 15.4s vs the 120s cap) — B-049 NOT opened. `verify_production automationexercise` run 2026-09-06 (LM Studio up): FAIL 11/13 but NO timeout — the 2 failed gates are 2 unresolved ASSERT placeholders ('confirmation popup', 'added product details') → honest skips; execution 5 passed / 2 skipped / 93.5s live. Remaining AE gap = known ASSERT-resolution class (AI-058/AI-064), not a scraper bug. Prior: SHIPPED — Phase 6 Part 1 6a–6i code-complete: 6c/6d/6e/6h/6i built + gated in this session; roadmap Phase 6 owns the full status. Full-eval investigation closed: RAG-store wipe root-caused and repaired (see B-048), eval-harness graph mock-parity fixed, controlled fork-vs-mainline + graph-vs-linear comparisons recorded in eval_runs; B-048 opened — RAG store seeding gap: AI-059 lab rebuild wiped the production store 2026-08-31 while the seed marker survived → all evals since measured with golden RAG bonus = 0, explaining the 48.7%→42.5% drop; store re-seeded manually `rag_ingest.py --bundled --force`; 6c/6d/6e/6h/6i code-built + gated, handoff `docs/sessions/2026-09-04_phase6_6c_6d_6e_6h_6i_handoff.md`; AI-064 opened — container-element haystack dominance, the #1 AI-058-gate blocker; AI-058 Slice 2 re-tested live; AI-063 step-scoping + resolved-but-wrong trigger SHIPPED and verified live: 9 real negatives, exact retrieval, step-scoped scoring; hidden Locator.wait_for classifier gap fixed; **A/B harness bug fixed — driver conftest always wrote `passed`, so every prior A/B was blind; real statuses + real negatives now record**; full A/B re-runs (banking/trap) confirm all legs identical — metric gate blocked by THREE resolver-infrastructure issues (single-candidate failures, `main`-haystack dominance, page-context assignment), NOT the store; 2898 pytest + eval static 97.9%; AI-058 Slice 1 shipped — contrastive learned store; AI-059 harness + D1/D2 baseline complete 2026-08-27)

---

## 🆕 B-054 — Single-candidate unrecoverable resolution: page rendered as one text block → specific target never enters the candidate pool

**Status:** 🆕 new — opened 2026-09-06 from the AI-058 gate analysis (was prose inside the AI-058 entry; now a standalone item per the 2026-08-29 handoff §8 decision "logged as separate resolver items").
**Priority:** High — one of the two remaining blockers for closing the AI-058 `mean_pass_depth` metric gate (AI-064 removed the other; B-055 is the third).
**One-line:** on the banking mock (eval-007) the "Transfer Money"/"Pay Bills" page renders as ONE text block, so `main:has-text("Welcome to Mock Bank…")` is the **only** candidate in the pool — a learned negative (even the −40 container penalty) has nothing to flip to, and all three A/B legs generate byte-identical code. The specific link/button is never captured, so no scoring can recover it.
**Evidence:** `docs/sessions/2026-08-29_ai058_slice2_negatives_handoff.md` §8 blocker (1); A/B legs identical (`0.900` cold/warm/warm+NEG), `negatives_inserted: 3` banking but no lift.
**Key distinction from AI-064:** AI-064 fixed the case where the container AND the specific element washes were BOTH in the pool (container now loses). B-054 is the case where the specific element is absent from the pool entirely — a candidate **discovery/capture** gap, not a scoring gap.
**Candidate directions (investigate before committing to one):**
- [ ] Scraper capture: on single-text-block pages, split merged `main` text into interactive sub-elements (sibling links/buttons with fragment text) so real targets enter the pool.
- [ ] Resolution-time fallback: when the only candidate is a container/prose block for a CLICK action, widen capture (re-scrape with a different capture policy) or honestly skip.
- [ ] Mock-fidelity note: the banking mock page layout itself (one text block) is a data limitation — verify against a real site (automationexercise) that the same "only-container-in-pool" case actually occurs before over-investing in the mock-driven fix.
**Blocks:** AI-058 metric gate (measurement can't move while unresolvable single-candidate failures are the constant leg outcome).
**Estimated sessions:** 1–2 (investigation + capture fallback).

---

## 🆕 B-055 — Page-context/trail mis-assignment: steps resolved against the wrong page object's candidate pool

**Status:** 🆕 new — opened 2026-09-06 from the AI-058 gate analysis (was prose inside the AI-058 entry; now a standalone item per the 2026-08-29 handoff §8 decision).
**Priority:** High — one of the two remaining blockers for closing the AI-058 metric gate.
**One-line:** on the trap mock (eval-009/custom, "Pay Bills"), the step resolved to `#signin-button` (the INDEX page) because the step's `current_url`/page assignment put it on the wrong page object — the correct `a[href="/pay.html"]` exists on the dashboard but was never in that step's candidate pool. The resolver's pool is built from the WRONG page, so the right answer is structurally absent.
**Evidence:** `docs/sessions/2026-08-29_ai058_slice2_negatives_handoff.md` §8 blocker (3).
**Relationship to existing work:** this is the **resolution-time candidate-scoping layer** — AI-052 (observed transitions, evidence-only navigation) and AI-054 territory, and overlaps AI-063 **Layer 2** ("scope candidates at resolve time to the current section/vehicle using `data-vehicle` context, prior steps (`resolved_steps`), and/or the observed trail — unify the existing `section_scoper.scope_elements` into the actual candidate selection used by scoring"). Do NOT build a parallel mechanism: B-055 should consume the observed trail / `resolved_steps` to pick the candidate page before scoring.
**Candidate directions:**
- [ ] Gate candidate collection on the step's `current_url`/trail-derived page (only that page + maybe its navigation siblings enter the pool).
- [ ] Reuse `section_scoper.scope_elements` inside candidate selection (AI-063 Layer 2 scope).
- [ ] Regression test shape: a story whose steps span 2+ pages must never resolve a step against a candidate that exists only on a non-current page.
**Blocks:** AI-058 metric gate (trap-mock leg cannot demonstrate negative-driven lift while wrong-page candidates dominate).
**Estimated sessions:** 1–2 (trail-scoped candidate selection + regression test).

---
## 🆕 B-050 — License trust root overridable via env var (`AITEST_LICENSE_PUBKEY`) weakens tier enforcement

**Status:** 🆕 new — opened 2026-09-06 from the security/commercial audit (owner approved logging).
**Priority:** Medium — commercial integrity, not a classic vulnerability.
**One-line:** `src/licensing/license.py:71` ships the vendored ed25519 public key, but `AITEST_LICENSE_PUBKEY` lets any **stock** build swap the trust root via an env var — no code modification required — so self-signed licenses unlock full-tier features without the "fork" the open-core posture accepted.
**Decision needed (pick one):**
- [ ] Remove the override entirely;
- [ ] Move it to a config file (visible, deliberate, fork-like act) instead of a silent env var;
- [ ] Document it as a sanctioned self-host knob in the tier table + spec §5.4.
**Related:** `docs/security/license-key-ops.md` (B-053) documents the interplay.
**Estimated sessions:** 0.5

---

## 🆕 B-051 — Free-tier metering is trivially resettable (local sqlite + ledger)

**Status:** 🆕 new — opened 2026-09-06 from the security/commercial audit.
**Priority:** Low — accepted-for-v1; must be **documented honestly**, not silently left.
**One-line:** `src/usage_meter.py` keeps the 30-day runs/exports windows in local `run_results.sqlite` + a local export ledger — deleting the store resets the free-tier caps, so enforcement is honour-based on tampered deployments.
**Actions:**
- [ ] Add an honesty note to the tier/usage docs + GTM copy (never imply stronger enforcement than exists).
- [ ] (Later, gated on need) tamper-evident local ledger (e.g. HMAC-chained entries) if/when metering becomes revenue-critical.
**Estimated sessions:** 0.25 (docs)

---

## ❓ B-052 — Prompt-injection exposure of skeleton/resolver prompts — UNDERSTAND FIRST, no action yet

**Status:** ❓ needs-info — opened 2026-09-06 from the security audit. **Owner asked to understand the topic before anything is built — research/learning item only.**
**What the audit observed (unedited):** `src/agents/prompt_safety.py` wraps user input in `<user_input>` XML tags for agent prompts, but coverage is per-prompt; the skeleton-generation and resolver prompts consume **scraped DOM text** (attacker-influenced if a customer points the tool at a hostile page) and are not uniformly wrapped. There is also a documented tension: AGENTS.md §8 bans XML tags in skeleton prompts while the agent-side safety wrapper relies on them.
**What to learn before deciding anything (reading/research only, NO code):**
1. Blast radius in THIS pipeline: hostile page text steers the LLM toward a dangerous placeholder or generated-test action — what is actually reachable, given Phase 2 resolves against real DOM and generated tests execute for real?
2. Why does AGENTS.md §8 ban XML tags in skeleton prompts (historical: local models copy tags verbatim?) — does that ban still hold, and how does it compose with wrapper-based defence?
3. What do comparable tools (or the literature) do about scraped-content injection in code-generating agents?
**Deliverable of this item:** a short written note (`docs/security/prompt-injection-notes.md` or a session doc) answering 1–3 + a recommendation (wrap / sanitise / accept-and-document). Implementation is a separate, future item.
**Estimated sessions:** 0.5–1 (research)

---

## ✅ B-053 — License key-ops documentation (single-operator signing key: backup, rotation, revocation)

**Status:** ✅ **Complete 2026-09-06** — `docs/security/license-key-ops.md` created and committed. Covers generation, storage (private key never in repo), two-location backup + tested recovery, rotation-as-release (vendored pubkey ⇒ rotation ships with a product release), revocation-by-short-expiry (offline ⇒ no CRL), and the `AITEST_LICENSE_PUBKEY` interplay → B-050. Keep the doc current when the licensing surface changes.
**Priority:** Medium — must exist before the first paying customer.
**One-line:** the ed25519 signing key is held by one operation ("Cat Tan Operations") with no documented backup/rotation/revocation plan; **loss** = cannot issue licenses, **leak** = anyone can mint licenses forever; offline licenses cannot be revoked except by expiry.
**Estimated sessions:** done (0.25)

---


## ✅ B-048 — RAG store seeding gap: AI-059 lab rebuild wipes patterns, stale marker blocks re-seed

**Status:** ✅ **Fixed 2026-09-06** — both candidate guards built, tested, verified. (a) `restore_store_snapshot` refuses any target that is / contains / lies inside the production `rag_path()` or its `.embedder.json` companion, with `allow_production_store=True` as the explicit escape hatch (`src/learning_impact.py`, 5 guard tests). (b) `ensure_bundled_seeded` marker truth: the marker now means "seeded AND golden count > 0" — a surviving marker on a pattern-less store re-seeds and reports `"status": "reseeded"` (`src/rag_bundled.py`, 2 new tests + 1 latent-variant fix: no-marker docs-only store now seeds instead of marking). Verification: 62/62 targeted, full suite 3104/0, real store `{golden: 113, doc: 101}` intact + steady-state "skipped", eval static gate green. Prior manual repair (2026-09-05): `rag_ingest.py --bundled --force`.
**Priority:** High — data-integrity / measurement-silence class. **🚩 PRE-LAUNCH BLOCKER (flagged 2026-09-06, owner review):** measurement integrity is launch-gating — every shipped eval/learning claim is only as good as the store it measures against, and the static gate cannot see this failure. The store ran pattern-less for a week+ and every full eval measured with the golden RAG bonus = 0 (the Aug reference band 53.2–54.1% resolved WITH the golden patterns). The static gate (97.9%) never catches it — static mode doesn't use RAG.
**One-line:** `src/learning_impact.py:115` `shutil.rmtree(target)` (the AI-059 lab warm-store rebuild) wiped the PRODUCTION RAG store on 2026-08-31, but the idempotent seed marker (`evidence/.rag_bundled_seeded.json`, `seeded_at 2026-08-20`) survived → `ensure_bundled_seeded()` skips re-seeding forever → golden/learned patterns absent until a manual `rag_ingest.py --bundled --force`.
**Fix (two one-line candidates — do either or both, then verify with the eval):**
- [x] (a) **Sentinel-scope the lab wipe:** `rebuild_warm_store_from_evidence` must operate on the lab-store path (`AI059_LAB_SITE_HASH` companion), never the production `get_storage().rag_path()`, or refuse when the target is the production store unless an explicit override is passed. — DONE 2026-09-06: `restore_store_snapshot` guard + `allow_production_store=True`.
- [x] (b) **Marker truth:** `ensure_bundled_seeded()` re-seeds when the store is pattern-less (golden count == 0) even if the marker exists, then refreshes the marker — the marker should mean "seeded AND store non-empty", not "seeded once ever". — DONE 2026-09-06: golden-count check + `"reseeded"` status.
**Found (2026-09-05):** full-eval repeat runs 48.7% and 42.5% (per-dataset numbers deterministic across runs ⇒ systematic, not LLM variance); store query showed `{doc: 66}` — zero golden/learned; store dir mtime 2026-08-31 14:43 vs marker 2026-08-20. **Repaired:** `rag_ingest.py --bundled --force` → `{golden: 113, doc: 101}` verified, marker refreshed. **Controlled-verification done:** mainline build + restored store = **54.9%** (the reference band) — hypothesis confirmed; fork build + restored store = 48.7% (−6.2pp build cost, separate finding).
**Verification for the fix:** after a lab rebuild, store pattern counts remain ≥ 113 golden; a fresh full eval (`--mode full --regenerate`, settings per the session handoff) shows resolution accuracy recovering toward the 53–54% band.
**Session record:** `docs/sessions/2026-09-04_phase6_6c_6d_6e_6h_6i_handoff.md` (root-cause finding section).

---

## ✅ AI-055 — Ingestion Improvements (Local): tiered CPU-first OCR + format scope + quality summary + cause-differentiated warning

**Status:** ✅ **Core built 2026-08-25** — tier-1 CPU OCR backend, extended `get_ocr_backend()`, `[ocr]` extra, ingestion quality summary, format scope, **cause-differentiated skip warning** (with install fix), and the **CI regression test** are all built + tested. **Remaining (follow-up):** wire per-page OCR into the generation pipeline's direct-doc parse (protected file — needs sign-off); optional most-recent sidecar manifest for investigation. Roadmap ref: `docs/plans/ROADMAP_ROADTO_PRODUCTION.md` → Tier 5 → #16.
**Built (this session, 2026-08-25):**
- ✅ Tier-1 CPU OCR backend (`RapidOCRBackend` + `AutoOcrBackend` in `src/ocr_backends.py`); `get_ocr_backend()` extended (auto/cpu/high-accuracy/power); legacy names still map correctly.
- ✅ `[ocr]` optional extra in `pyproject.toml` (fixed a `oocr`→`ocr` typo that would have broken `uv sync --extra ocr`).
- ✅ Ingestion quality summary in `src/rag_bundled.py` + `scripts/rag_ingest.py`: per-doc outcome, page text/OCR/skip counts, dedup new-vs-present, actionable suggestion.
- ✅ **Cause-differentiated skip warning** (the trust signal): a skipped page surfaces as `[WARN] <doc>: N page(s) (cause) -> NOT digested` and **does not hide behind an overall green result**. Causes: `no_engine` (shows the exact install fix `uv sync --extra ocr` + docs link) / `ocr_no_text` (no install fix shown — wrong fix) / `ocr_failed`. Serves the use case: a scanned doc in a bigger pack that gets a positive result is still flagged as **not digested** + the one-line fix.
- ✅ **CI regression test** (`test_lv_docs_no_pages_skipped_regression`) — the durable form of the ingestion tracking; LV docs must ingest with 0 pages skipped, or CI goes red before the regression ships.
- ✅ **Dedup-key source-in-hash guarantee** tests (two different docs with identical text never dedup against each other) + stale-lingering-on-append behavior documented.
- ✅ Full gate green: 2960 tests pass, ruff check + format clean, mypy clean (src/ cli/ + staged), smoke 39/39, eval static ≥79%.
- ⚠️ **Known ceiling (documented, not a bug):** page-OCR handles *text* in images, **not** tables/graphs rendered as images. Traceability of an image-graph figure is not possible — see the traceability roadmap item (16b) + `docs/specs/SESSION_SPEC_test_to_doc_traceability.md`.

**Remaining (follow-up, needs sign-off for the protected-file one):**
- [ ] Wire per-page OCR into the generation pipeline's direct-doc parse (`pipeline_graph.py _parse_document` currently uses whole-doc `parse_pdf`, not per-page `parse_page`). Reuse the `ingest_pdf` loop. *(Touches a protected file.)*
- [ ] Optional: most-recent sidecar manifest in `evidence/` (resolved tier + `ocr_engine_installed` flag + per-doc skipped pages) for bug investigation.

**Priority:** Medium (commercial trust + domain accuracy) — pre-launch
**Folds in / continues:** AI-045 #4 (PDF OCR *wiring* + dedup — shipped 2026-08-24). This is the *product* layer on top of that wiring: make it work everywhere (CPU-first), promise a defined format scope, and tell the customer what happened.

**The one-line version:** ingestion is a **one-time onboarding step** (run once → durable RAG store → reuse; **not** a CI/CD concern — CI restores the pre-built store from cache, it never re-ingests/re-OCRs). It's the **trust differentiator** ("your generator learns *your* domain, on *your* hardware, no egress"). Ingestion quality *is* product quality — a garbage ingested PDF → garbage tests → customer blames the product.

**What to build (spec §7):**
1. **Tier-1 CPU OCR backend** (RapidOCR / PP-OCRv5-v6 via ONNX Runtime) — scanned pages on *any* machine, CPU-only, ~50–80 MB, no network. New optional `[ocr]` extra (default install stays light). Closes the "no dedicated GPU = no OCR" gap from AI-045 #4.
2. `get_ocr_backend()` selection: `auto` (default → tier 0, fall through to tier-1 CPU) / `cpu` / `high-accuracy` (tier-2 PaddleOCR-VL/Surya, opt-in) / `power` (tier-3 VLM, opt-in).
3. **Ingestion quality summary** in `rag_ingest.py`: per-doc outcome, page OCR-vs-skip counts, dedup new-vs-present, actionable re-run suggestion.
4. **Format scope**: pdf + md in; unknown formats rejected loudly.

**Tiers (research 2026-08-24):** 0 PyMuPDF (text) → **1 RapidOCR (CPU, new default OCR)** → 2 PaddleOCR-VL/Surya (small GPU / high-spec CPU) → 3 olmOCR/dots.ocr (dedicated GPU; re-pick from Unlimited-OCR). Leaning: ship tiers 0–1 + summary in v1, defer 2–3 (spec §9 Q3).

**Companion (later, separate product):** TanCat Cloud ingestion → see AI-056 below + `docs/specs/FEATURE_SPEC_tancat_cloud_ingestion.md`. Deliberately **not** part of this build.

**Open questions to grill (spec §9):** confirm RapidOCR as tier-1 (pkg name + CPU latency); build tier-2 in v1? (leaning no); keep Unlimited-OCR as tier-3 (leaning yes, re-pick later); add `.txt`?; CLI-only vs UI summary; offline-installability of `[ocr]`.

**Estimated sessions:** 2–4

---

## 🆕 AI-056 — TanCat Cloud (Ingestion Service) — separate product, post-launch

**Status:** 🆕 new — decision record written 2026-08-24: `docs/specs/FEATURE_SPEC_tancat_cloud_ingestion.md` (NOT a build — no code, no schedule yet)
**Priority:** Low (post-launch) — record now, spec properly after local product ships

**The one-line version:** make cloud ingestion a **separate product** so it can never blur the local product's air-gap / no-egress wedge (customer docs leaving their deployment = the one thing that undoes the #1 sales claim). Mirrors the LLM triad we already have (local / self-hosted / cloud-API-key): ingestion gets the **same axis**.

**The ingestion-backend triad:**
1. **Local** (the local product) — tiers 0–3, CPU-first, full air-gap (AI-055, pre-launch).
2. **Self-hosted service** — customer deploys it *in their VPC / on-prem*; we run it, their infra, **full air-gap + hardware-agnostic**. = the *self-hosted LLM* analogue. **The strategic center** — kills the hardware-heterogeneity problem *without* breaking the no-egress claim.
3. **Cloud API (convenience)** — docs go to a cloud OCR/embed provider; **egress — labeled** as such. = the *cloud-API-key LLM* analogue.

**Hard requirements (protect the wedge):** egress explicit + labeled on every path; any cloud-provider call goes through the egress audit (`scripts/audit_egress.py`); reuse the local ingestion code (tiered `OcrBackend` seam), don't fork; data-minimization + retention policy for the convenience tier (legal/ToS).

**Sequence when it becomes real:** option 2 (self-hosted) first, option 3 (cloud-API) after; the tier-3 VLM re-pick (dots.ocr/olmOCR vs Unlimited-OCR) lands here (cloud controls the GPU stack).

**Guardrail:** do NOT let TanCat Cloud scope leak into the local product's launch scope — local ingestion is tiers 0–1 + summary, nothing cloud-shaped.

---

## 🆕 AI-057 — `llm_providers` extensibility for easy provider/model addition (POSSIBILITY — needs investigation)

**Status:** 🆕 new — possibility logged 2026-08-25; **NOT a committed work item**. Needs further investigation before any scoping or build.
**Priority:** TBD (future — as provider/model/API churn demands)
**Context (from cleanup review 2026-08-25):** `src/llm_providers/__init__.py` (624 lines) mixes the `LLMProvider` ABC, the `get_provider()` factory, and the three concrete providers (OpenAI / LMStudio / Ollama) in one file. It is the single largest *protected* file (AGENTS.md §3: stable LLM client — changes require explicit instruction) and the one most likely to need frequent editing as new providers, models, and provider-API updates land.
**Why it matters:** provider/model/API updates will keep arriving; the current single-file shape makes each addition a manual edit to a protected, high-blast-radius module. Designing for extensibility now (e.g. provider-as-plugin registration, per-provider adapter modules, declared model-capability metadata) would make future additions mechanical rather than surgical.
**Open questions (investigate before scoping):**
- Plugin/registration pattern vs explicit factory switch — which keeps the protected-file change surface smallest?
- Per-provider adapter modules (`base.py` + `openai.py` / `lmstudio.py` / `ollama.py`) vs status quo — does this reduce risk or just relocate it?
- Model-capability metadata (context window, thinking support, quantization notes) — where should it live so resolver/prompt layers read it without importing providers?
- Relationship to the dormant Phase 1 per-agent model config (`src/agents/` NOT BUILT scope) — is this the seam that finally delivers it?
- Air-gap / no-egress interaction — providers must never phone home; how does an extensible registry preserve the wedge?
**Not in scope now:** no code, no schema, no build. Captured so it resurfaces when provider churn makes it urgent. Folds into the AI-054 testing-strategy review's "what do we maintain" question.

---

## 🆕 AI-058 — Contrastive learned store: record BOTH positives and negatives, cross-reference at scoring

**Status:** 🟡 ready-for-agent — **Ambiguous-mock measurement built + resolver-level flip proven DETERMINISTICALLY 2026-08-30** (see the measurement note below) + **Slice 1 shipped 2026-08-28** (`9aa8bbc`) + **Slice 2 wiring shipped 2026-08-28** (uncommitted working tree as of 2026-08-29) + **AI-063 (the gate's blocker) SHIPPED 2026-08-29**: negatives are now step-scoped AND the recording trigger covers the *resolved-but-wrong* shape (failed assertion with a resolved selector), with the hidden `Locator.wait_for` classifier gap fixed. **VERIFIED LIVE on real failure data**: 9 negatives learned (was 3), exact retrieval for "payment success message" → `#payment-error`, step-scoped scoring −4 on its step / 0 elsewhere, no cross-step leak. Gates: 2898 pytest, ruff + mypy clean, eval static 97.9% (no regression). **METRIC-FIRST gate**: `warm+negatives > warm` on `mean_pass_depth` now has a *real signal to act on* — next step is the A/B on a mock that reproduces a recoverable resolved-but-wrong failure (see the fresh-ecommerce A/B in §6 of the handoff; a controlled ambiguous mock is the cleanest way to show the literal lift). Do NOT proceed to Slice 3 or touch scoring. Full record: `docs/sessions/2026-08-29_ai058_slice2_negatives_handoff.md`.
**Priority:** Medium (product-differentiation experiment, not a launch blocker — sequence after AI-055 and Phase 6 6c/6d).

### Controlled ambiguous mock + DETERMINISTIC resolver-level proof (2026-08-30)
The available mocks never emit a *recoverable* wrong-element failure (clean mock resolves correctly → no signal; hard mock times out on a single candidate → a negative can't steer), so the `mean_pass_depth` gate had nothing to measure against. Built a purpose-built **ambiguous mock** (`mock_sites/ambiguous/`, dataset `eval-010`) whose confirmation page offers 2+ genuine candidates for the "order success message" step: the golden `#order-success-message` (112), the other correct `#order-success-title`, and a VISIBLE text-overlap **TRAP** `#order-note` (32, shares the "Your order ..." prefix). Two tools:
- `scripts/ai058_ambiguous_seeded_ab.py` — the generation-level seeded A/B (control vs a step-scoped negative on the trap). **Not runnable on this box**: the Qwen3.8-27B skeleton generator burns the token budget producing degenerate output (24 KB, zero placeholders, times out) for the local-mock story — an LLM/model-state issue, not a harness bug. Kept for when a clean model run is available.
- `scripts/ai058_ambiguous_resolver_ab.py` — the **deterministic resolver-level** A/B (frozen `scraped_pages/` pool, no LLM, no mock server). **ALL 6 CHECKS PASS**: (1) the trap is a real candidate in the control pool; (2) control ranks the correct winner; (3) **the step-scoped negative demotes the trap (32 → 12)**; (4) treatment keeps the correct winner; (5) the correct winner's score is unchanged (112 = 112); (6) a different step ('Back to Store') is byte-identical with/without the negative (no cross-step bleed). This is the same deterministic proof pattern that shipped under AI-064, now on a mock built specifically to expose the flip. **Verdict: the step-scoped negative demonstrably steers resolution at the resolver level — the AI-058 gate is demonstrable deterministically.** A generation-level `mean_pass_depth` lift additionally requires the LLM to actually pick the trap on a cold run (LLM-variance dominated; not forceable) — the resolver-level flip is the strongest available proof. 2906 pytest, ruff clean, mypy (scripts/ not gated; 2 non-gated errors match the sibling `ai058_seeded_ab.py`), eval static 97.9% (94/96, no regression).

**Folds into:** AI-054 (testing-strategy review) + the AI-045 RAG/evidence thread.

### Two separate concerns (2026-08-26 reframing)
Keep AI-058 (production) distinct from **AI-059** (isolation):
- **Production (AI-058):** does the user's suite get greener over time as the store warms, with no intervention? KPI is a **trend**, not a point. No golden snapshot exists in production — the only ground truth is whether the user accepted the test.
- **Isolation (AI-059):** can we *attribute* improvement to the store? Lab condition — store is the only variable, deterministic mocks, auto-learn disabled during measurement. Deliberately NOT how production behaves. Mixing the two is the trap that blinded the golden-res accuracy metric.

**The one-line version:** a human tester learns from mistakes — so should the generator. Add a **`learned_negative`** entry type alongside positives, record confirmed wrong locators, and cross-reference them at scoring time so the resolver down-weights elements that failed before (and up-weights what worked), mirroring how a person builds intuition per site.

### Objective reframing (the 2026-08-26 eval finding that motivates this)
- The current learned store is **positive-only and ingests ONLY passed steps** → it can only *reinforce* choices the pipeline already gets right. Structurally it **cannot** move resolution accuracy on a fixed golden benchmark, because the benchmark's error mass is exactly the data learning never observes. Worse, on this project's eval the learned descriptions have **0% overlap with golden descriptions** (LLM vocabulary vs hand-authored), and we measured **byte-identical** resolution accuracy with learned=0 vs learned=380 — confirming the point.
- **Therefore the objective of learned/RAG is NOT "match the hand-authored golden locator."** That is a code-health gate (caught by the static eval). The learning objective is **end-to-end test success / progress**: how far through each generated test a run gets, how many tests go green on first generation, and how few self-heal iterations it takes. **Resolution accuracy is the wrong north-star for measuring learning.**
- Consequence for this item: the measurement must track **per-test progress depth** and **pass/heal outcomes on novel stories**, not golden-key fidelity.

### Target envelope via manual pass (infer-then-prune)
A real tester validates *intent, not implementation*: "add item to cart" is satisfied by any working cart-add — we must NOT force "click the red dress". But we also must not let the model *game* the test (GOTO past a step, drop an assertion, pass trivially).
- **Method:** generate v1 → a single human pass reviews each test, confirms validity, fixes gaps → that reviewed state becomes the **target envelope** (an *acceptance set*, not one locator).
- **Infer-then-prune:** auto-infer the envelope from the first valid run, let the human prune — keep the manual pass light **until we understand whether learning is even working**; only then attempt an automated gate.
- **Two guards for the strictness dialectic:**
  - *Variety* ← positive learned store (description-keyed, already allows multiple valid locators/routes).
  - *Integrity* ← a **test-integrity check** (not yet built): did the test perform the required actions (navigate/click/fill counts match the plan) and are its assertions non-trivial? Catches the "circumvent issues that should be there" gaming mode.

### Metric (primary = A: `mean_pass_depth`)
- `mean_pass_depth` = avg(steps before first failure ÷ total steps) per test — the headline, golden-free, matches "how far through each test".
- Corroboration: `first_pass_green_rate` (reuse `test_pass_rate`), `false_positive_rate`, `self_heal_iterations_to_green` (new). Optional failure-class breakdown (existing `failure_classifier`) isolates locator-class depth loss from infra noise.
- **Production:** trend of the above climbing across the user's runs. **Isolation (AI-059):** delta when only the store changes.

### Open questions to grill before build
- Which KPI is the real signal — `mean_pass_depth`, `first_pass_green_rate`, or `self_heal_iterations`? (Propose tracking all three; judge by signal-to-noise. The user's instinct that "how far through each test" is the objective is the leading candidate.)
- **Recording gates for negatives (precision is everything):** locator-class failures only (`LocatorNotFoundError` / locator-timeout / hidden-element timeout, with a resolved selector present)? **Self-heal replacement pairs** (old selector = confirmed negative, new = reinforced positive — highest-precision signal, half already captured by `pattern_from_patch`)? How to **exclude infra flakes** (GPU contention, LLM timeout, navigation non-arrival) so they never become negatives?
- Store shape: `learned_negative` entry type in existing store (reuse embedder/retrieval) vs separate collection. Lean: same store, `entry_type` filter.
- Cross-reference: penalty mirroring `_learned_pattern_bonus` (−5/−10 × confidence×`hit_count`, capped below +80, keyed by description not globally). Review-time swap when top candidate has negative history and runner-up positive?
- Integrity check: how to detect trivially-true assertions / skipped steps without flooding false alarms.

### Estimated sessions
- Metric harness (AI-059, prereq, ships first): ~1–1.5
- Feature (store → gates → scorer penalty → tests): ~2–3

### Slice 2 — wiring shipped, live A/B pending (2026-08-28)
Code-complete; the live measurement A/B is the only outstanding acceptance step.
- **What shipped (Slice 2 wiring):**
  - `src/rag_learn.learn_from_evidence_sidecars` now sweeps **failed/partial** sidecars and calls `learn_negatives_from_evidence` on their steps, returning `negatives_inserted`/`negatives_exists`. The passed-only positive path is byte-for-byte unchanged (the per-step locator-class gate in `learn_negatives_from_evidence` still excludes assertion/navigation/unknown + selector-less steps, so infra flakes never reach the store). A `learn_negatives=False` switch restores the positives-only sweep.
  - `src/learning_impact.rebuild_warm_store_from_evidence` is now negative-aware: failed/partial steps that classify as `LOCATOR_TIMEOUT` are written as `learned_negative` tagged with the **same lab sentinel** (`hit_count`/`last_seen` intact), so the resolver (scoped via `AI059_LAB_SITE_HASH`) down-weights them. New `learn_negatives=False` builds the positives-only control store. `scripts/eval/learning_impact.py::rebuild-warm` gained `--no-negatives`. The `baseline` command already supports the `warm-positive` vs `warm-positive-negative` legs.
  - The contrastive *scoring* path (`PlaceholderScorer._learned_net_evidence` → `learned_negative` penalty, site-keyed) and `RAGStore.retrieve` (already returns `learned_negative` entries) were built in Slice 1 and are unchanged — so negatives loaded by the negative-aware rebuild flow straight into the penalty at resolve time.
- **Tests added (5):** `test_rag_learn` — `test_learns_negatives_from_failed_sidecar` (locator timeout → negative, assertion failure excluded) + `test_no_negatives_when_disabled`; `test_learning_impact` — `test_rebuild_warm_store_negative_aware_records_negatives`, `test_rebuild_warm_store_negative_aware_toggle`, `test_rebuild_ab_warm_vs_warm_negatives_differ` (proves the two A/B stores carry different signal from the same evidence).
- **Gates (this session):** 2891 passed (+5), smoke 39/39, ruff + mypy clean, eval static 97.9% (no regression).
- **Live mock A/B RUN (2026-08-28) — result: evidence starvation on BOTH mocks, NOT a win, NOT a reject.** Drove the real pipeline (`scripts/ai058_ab_mock_run.py`, parameterized by `AI058_DATASET`) against mocks served on :8781 (LLM = Qwen3.8-27B on :8080):
  - **ecommerce (eval-006):** 3 legs (cold / warm-positives / warm+negatives) each 8/8 passed, `mean_pass_depth = 1.000`. Rebuild of the cold evidence consumed **13 positives / 0 negatives**. Clean mock → no locator failures → `warm+negatives == warm` → delta 0.
  - **lv_insurance (eval-005):** 10/10 passed, `mean_pass_depth = 1.000`. Rebuild consumed **0 positives / 0 negatives** — the LV hard steps degrade to GOTO/navigation (resolver logs `Failed to find 'Create Account'/'Submit'/'Lookup'` but emits a GOTO fallback that passes), so they yield *no learnable locator of any kind*, not even positives. LV is doubly sterile for this feature.
  - Verified `generated_tests/conftest.py` records the *real* test status (`rep_call` → passed/skipped/failed), so a genuinely failed test WOULD be recorded as `failed` and the negative branch WOULD fire. The conftest is not the blocker — the absence of locator-timeout *failures* is.
  - **Root cause:** the available mocks never emit a hard locator-timeout failure (clean mock resolves; LV GOTOs instead). The negative store has zero signal to learn on either mock, so `warm+negatives == warm` by construction and `mean_pass_depth` is pinned at its ceiling. This is the "evidence starvation" branch (no failures at all — not wrong ones).
  - All legs: **8/8 tests passed, `mean_pass_depth = 1.000`** (clean mock — the pipeline already resolves perfectly).
   Rebuild of the cold-run evidence consumed **13 positives / 0 negatives** (the negative-aware rebuild path is verified against *real* sidecars; positives land, negatives correctly stay 0 because there were no locator failures).
  - Therefore `warm+negatives == warm` by construction → **delta = 0.000**. The contrastive store has nothing to learn negatively on a perfect mock.
- **A/B re-runs 2026-08-29 (harness FIXED — important):** the A/B driver's custom conftest was writing `tracker.write(status="passed")` **unconditionally** (bug), so EVERY earlier A/B was blind — sidecars never said `failed`, the negative sweep had nothing to scan, and `green_rate` was always 1.000. The production conftest computes real status from `rep_call` via `pytest_runtest_makereport`; the driver template had neither. **Fixed** (added the hook + real status to `scripts/ai058_ab_mock_run.py`). With the fix, banking cold shows REAL failures (`green_rate=0.250, tests=2 passed`, was fake `1.000/8`) and the warm+neg store records **3 real banking negatives** + **1 trap-mock negative**. But all legs are still identical (`0.900` / `0.920`) — **three resolver blockers, none in the store** (§8 of handoff): (1) single-candidate unrecoverable (`main:has-text` is the only candidate), (2) `main`-haystack dominance (aggregated page text always scores 100, masking specific candidates — verified: a page with BOTH `#payment-error` and `#success-title` resolves to `main`), (3) page-context/trail assignment (steps resolved on the wrong page object). **Verdict: A/B on available mocks cannot close the metric without resolver work (AI-052/AI-054)** — the negative mechanism is fully proven live; the blockers are resolution-infrastructure, not Slice-2/AI-063.
- **Metric-first verdict:** the acceptance gate (`warm+negatives > warm`) is **inconclusive — evidence starvation**, exactly the "no" branch the plan anticipated. Do NOT proceed to Slice 3 on this result, and do NOT touch scoring. The Slice-2 *code* is verified (5 new unit tests + real-evidence rebuild: 13 positives consumed correctly, negative path proven on synthetic evidence); the *feature* is neither proven nor disproven because no mock exercises it.
- **AI-063: CHARACTERIZED at code level (2026-08-29), not yet reproduced as a live mis-scope.** Failures DID occur (banking mock emitted 3 real locator-timeouts on "Transfer Money"/"Pay Bills"), so this is no longer the "zero failures" branch — but those failures are **unrecoverable** (the resolver's only candidate is `main:has-text("Welcome to Mock Bank…")`; no alternative exists, so a negative can't steer anywhere). Code-level finding: `PlaceholderScorer._learned_net_evidence` / `_learned_negative_penalty` match a negative by **selector + site_hash only** — the `step_label`/`action` stored on the pattern are **never used in matching**. So a negative penalizes a locator *everywhere it appears*, not just on the failing step: the AI-063 mis-scoping risk, confirmed. No genuine *recoverable* wrong-element failure (correct element among candidates) was reproduced on any available mock — ecommerce "mismatches" are golden-key tolerance gaps, not wrong-element picks.
- **What a real measurement needs (still outstanding):** a scenario with a *recoverable* wrong-element failure (correct alternative exists) so a step-scoped negative can flip the choice and move `mean_pass_depth`. Options: (a) bring up the **LV insurance mock** (`mock_sites/lv`, not present locally) for the multi-vehicle case; (b) construct a controlled ambiguous mock (a step with 2+ candidates where one is a known-bad locator + a correct alternative); (c) apply only AFTER negatives are made **step-scoped** (gate the matcher on `step_label`/`action` in the two scoring functions) — that is the AI-063 fix, do NOT implement it inside Slice 2. `scripts/ai058_ab_mock_run.py` is parameterizable for whichever scenario is chosen.

### The real pain (2026-08-29 reframe) — "high-scoring locator that keeps failing"
- **The user-facing problem is NOT "no element found."** It is: a locator **scores high → gets used → but the test fails repeatedly.** The user keeps hitting the same broken test. The generator should say: *"I know this scores highly, but it fails time after time — treat it as unreliable."* That is the negative's real job: a **reliability memory** for high-scoring traps.
- **Two failure shapes in the real evidence data (confirmed by sidecar scan 2026-08-29):**
  1. **Locator-timeout** — the element literally isn't there (`main:has-text` banking). Current code records a negative. ✅ (but unrecoverable: single candidate).
  2. **Resolved-but-wrong** — the interaction *passes* but the element is the wrong pick, so the test outcome is bad. **Current code records this as a POSITIVE** (reinforces the trap) — the exact opposite of the intent. ❌ **This is the missing shape.**
  - Real example of shape 2: `test_05_verify_cart_product_details` — `s4 click "Cart" a[href=/cart.html]` → **passed**, then `s5 assertion "Blue Top" #empty_cart` → **FAILED** (wrong state reached). `test_04_verify_item` (saucedemo) — `s5/s6 click add-to-cart` → passed, then `s8 assertion .login_logo` → FAILED.
- **Why the negative store is currently dead weight:** on every available mock the resolver either (a) picks a working element → test passes → recorded as positive (shape 2 never becomes a negative), or (b) picks the only candidate → times out → unrecoverable negative (shape 1). There is no mock where a *bad* element is picked, *fails at runtime*, and a *good* alternative exists — the one scenario the current trigger+matcher can act on. Hence `warm+negatives == warm` on all A/B runs.
- **The fix (this is AI-063 work — do NOT fold into Slice 2):**
  1. **Broaden the recording trigger** (`learn_negatives_from_evidence`): also record a negative on the *resolved-but-wrong* shape — a `click`/`fill` step where `result.status=passed` but the **test overall failed** and the failure is attributable to that element's choice (a subsequent assertion/state-check on that element's result failed). This turns shape 2 into a learnable negative instead of a false positive.
  2. **Step-scope the matcher (AI-063):** gate `_learned_net_evidence` / `_learned_negative_penalty` on `step_label`/`action` so a negative only suppresses the element *on the step where it failed* — the "exemption to the rule" (same element is fine on step 3, known-bad on step 4).
  3. **Prove it:** with the broadened trigger, the real resolved-but-wrong failures (Cart link, add-to-cart) now produce negatives and the A/B can show `warm+negatives > warm` on those steps.
- **No scoring rewrite.** Scores combine as-is; only the *recording trigger* and the *matcher scope* change.
- **Open (grill before build):** how to robustly *attribute* a failed test outcome to a specific earlier click's element (vs an unrelated later step) without flooding false negatives; how to exclude infra flakes (LLM timeout, GPU contention, nav non-arrival) from the broadened trigger; and whether a "resolved-but-wrong" negative needs a higher confidence/`hit_count` bar than a hard timeout (since "the element worked, it was just the wrong one" is a weaker signal than "the element doesn't exist").

### Slice 2 — live full-eval run + multi-point negative test (2026-08-29)
- **Full eval run (ability-to-test regression check):** `eval_harness run --mode full --regenerate` across all 8 datasets. Settings mirrored the 2026-08-26 reference exactly (mode=full, regenerated, linear pipeline, rag=1, pom=0, openai-local, Qwen3.8-27B). Overall resolution accuracy **53.2% (58/109)** vs reference **54.1% (59/109)** — the 1-placeholder delta (eval-002 8/8→7/8) is LLM run-to-run variance at temp=0.0, **not** a Slice-2 regression (Slice 2 only touches negative-learning paths, idle with an empty store). **Testing capability intact after the changes.**
- **Multi-point negative test on REAL eval failure data:** built a store from the 53 evidence sidecars of the run via `rebuild_warm_store_from_evidence(learn_negatives=True)` → `{'inserted': 80, 'exists': 219, 'negatives_inserted': 3, 'negatives_exists': 4}`. Then: (1) RECORDING proven (3 real `learned_negative` from banking `main:has-text` timeouts); (2) RETRIEVAL — `retrieve("Transfer Money", CLICK)` returns the `learned_negative`, site-scoped; (3) SCORING — `_learned_net_evidence` gives **−3** on the real wrong locator and **+4** on a clean locator. So the negative IS recorded, retrieved, and scored from real failures.
- **Banking mock A/B (2026-08-29):** cold/warm/warm+negatives all `mean_pass_depth = 0.900` (3 unrecoverable locator-timeouts). Generated code for the failing steps is **byte-identical** cold vs warm+negatives → negatives applied but no alternative candidate exists → no flip. This is NOT starvation (failures exist) and NOT a wiring bug (negatives work) — it is "negative applied, failure unrecoverable."
- **Metric-first verdict (updated):** the acceptance gate (`warm+negatives > warm`) is **still OPEN**, but the blocker is now precise: (a) no *recoverable* wrong-element failure exists on the available mocks (banking = unrecoverable; ecommerce = golden-key tolerance gaps), and (b) selector-scoping (AI-063) makes applying negatives as-built unsafe. The Slice-2 *code* is verified end-to-end on real failure data; the *feature's metric lift* is unproven because no recoverable failure exists to demonstrate it. Do NOT proceed to Slice 3, do NOT touch scoring, do NOT fix scoping inside Slice 2. Full record: `docs/sessions/2026-08-29_ai058_slice2_negatives_handoff.md`.

---

## ✅ AI-064 — Container-element haystack dominance: `main`/page-aggregate text outranks specific candidates (blocks AI-058 measurement)

**Status:** ✅ **COMPLETE 2026-09-06** — fix shipped 2026-08-29 (`288e2f8`) but never marked done; verified this session: `tests/test_placeholder_scorers.py` acceptance tests (container penalized / interactive spared / prose-vs-link / page-level-assert spared) + `test_resolver_ab_downweights_wrong_pick_on_own_step` → **130/130 pass**, ruff + mypy clean, **eval static green (no regression)**. **Remaining AI-058 metric-gate blockers now logged as standalone items: B-054** (single-candidate unrecoverable — the specific target never enters the pool; a discovery/capture gap, distinct from this scoring fix) **and B-055** (page-context/trail mis-assignment — steps scored against the wrong page's candidate pool). Historical record:
- **Fix (`288e2f8`):** `PlaceholderScorer._container_aggregate_penalty` — (a) a generic container (`main`/`body`/`div`/`section`/`nav`/`header`/`footer`/`article`/`form`) that matched only via MERGED descendant text gets −40 on the haystack fast path (skipped for page-level ASSERTs via `PAGE_LEVEL_ASSERT_TERMS`; only tag/role-verified containers); (b) for CLICK, a non-interactive **prose text-run** (`p`/`h1-6`/`li` with no link/button role/href) also gets −40 so a real interactive target always wins.
- **Seeded-store A/B (`b1fcef3`):** `scripts/ai058_seeded_ab.py` — hermetic driver (temp dirs, own `AITEST_STORAGE_ROOT`, auto-learn off) seeds ONE known negative (the recurring banking `#payment-error` for ASSERT 'payment success message') and verifies the round-trip: insert → `find_negative` row → step-scoped score −4 on `#payment-error` / 0 on `#payment-success-title`. Leak-audited. 2906 pytest (+1), ruff + mypy clean, eval static 97.9%.
- **Resolver-level A/B (`c54b83a`):** `scripts/ai058_resolver_ab.py` + unit test `test_resolver_ab_downweights_wrong_pick_on_own_step` — fully deterministic (frozen `scraped_pages/` pool, no LLM, no mock server). Leg 1 (payments-only): control ranks the wrong hidden `#payment-error` first (52), the seeded negative drops it to 32. Leg 2 (consolidated pool): the correct `#payment-success-message` (112) already wins post-AI-064 and the negative cannot hurt it. Leg 3 (step-scoping guard): a different step ('payee') is byte-identical with/without the seed.
**Priority:** High — it is the #1 blocker for demonstrating the AI-058 `mean_pass_depth` lift (mocks resolve to `main`, so a learned negative never gets a chance to flip a specific candidate), and it degrades real resolution quality too (any description that happens to appear in page text resolves to the container instead of the element).
**Folds into:** AI-054 pipeline consolidation; unblocks AI-058 metric gate. Distinct from AI-063 (negative scoping) — this is about the BASE scorer letting a container win.

**One-line:** `_build_haystack` for a `main`/`body`/`div`/`section` container includes ALL descendant text, so the container is textually the best match for any description that appears anywhere on the page — the fast path returns ~100 for it and the specific element (exact id/text match) loses.

### Fix sketch (scorer-only — no pipeline / pipeline-trace changes)
- **Chosen & implemented (option b):** `_container_aggregate_penalty` (−40) applied in the haystack fast path with the page-level-ASSERT carve-out, plus the CLICK prose penalty for non-interactive text-runs. Not (a) — excluding container text entirely would break the honest page-level fallback; not (c) — a container-only-`only-candidate` rule would still let a prose paragraph win a CLICK.
- In `_haystack_score` / the compute fast path, **container tags** (`main`, `body`, `div`, `section`, `nav`, `header`, `footer`, `article`) should not win on aggregate text alone.
- Must NOT break: page-state/URL assertions that legitimately target `main`/page level, and the existing eval static 97.9% baseline (guard via eval static + full suite).

### Acceptance
- [x] `debug.py score <page> --desc X` (page with 2+ specific candidates) → resolves to a SPECIFIC candidate, not `main`, when the description matches that candidate exactly. — PROVEN 2026-08-29/09-06 by `test_container_haystack_penalized_specific_element_wins` + resolver A/B leg 2 (correct `#payment-success-message` wins once both pages are scraped). 
- [x] The banking "Transfer Money" step resolves to a real transfer link (or honestly skips) instead of `main:has-text(...)`. — PROVEN: specific candidates beat the container post-AI-064 (resolver A/B leg 2); the remaining single-candidate banking case (page renders as ONE text block, no alternative exists) is tracked as **B-054**, not this item.
- [x] Eval static ≥ baseline, full suite green, no scoring regression on the 8 datasets. — VERIFIED 2026-09-06: eval static exit 0, scorer+resolver tests 130/130, full suite green.


## 🆕 AI-063 — Context-aware candidate scoping for ambiguous descriptions (back buttons, multi-vehicle add-driver)

**Status:** ✅ **AI-063 step-scoping SHIPPED 2026-08-29** (uncommitted): negatives (and positives) are now **step-scoped** — `PlaceholderScorer._learned_net_evidence` / `_learned_negative_penalty` gate the matcher on `(action, description)` via `_step_scope_matches` (strips the stored `ACTION: ` prefix, case-insensitive), so a negative only applies on the step it was recorded on. The recording trigger was also **broadened** to the *resolved-but-wrong* shape (AI-058 "high-scoring locator that keeps failing"): a failed `ASSERTION` step with a resolved selector is now a `learned_negative` at conf 0.6 (locator-timeouts stay 0.9), in both `src/rag_learn.py` and the `learning_impact.py` lab rebuild. **Hidden blocker found + fixed:** `Locator.wait_for: Timeout 5000ms exceeded` (EvidenceTracker sync API, no `TimeoutError:` prefix) was classifying as `other` — so the real resolved-but-wrong failures were invisible to BOTH gates; `src/failure_classifier.py` now recognizes it as `LOCATOR_TIMEOUT`. **Verified live on real failure data:** rebuild of today's failed sidecars → 9 negatives (was 3), including `#payment-error` (dist 1.000 for "payment success message"), `#empty_cart`, `.login_logo`, `.text`; scoring shows `#payment-error` −4 on ITS step and 0 on other steps; the `.add-to-cart` trap does not leak across steps. Gates: 2898 pytest (+14 net new), ruff + mypy clean, eval static 97.9% (no regression). Remaining for AI-063: **resolution-time candidate scoping** (Layer 2 — the LV multi-vehicle `data-vehicle`/`data-driver` context) is a separate follow-up; the negative-store layer (Layer 1) is done.
**Priority:** High (this is the change that turns AI-058 negatives from dead weight into a real "don't re-pick this failing locator" memory — the user-facing pain).
**Depends on:** AI-058 Slice 2 measurement (done — mechanism proven; gate OPEN). Folds into: AI-054 pipeline consolidation review.

**One-line (expanded 2026-08-29):** the same description legitimately maps to DIFFERENT elements by context — LV mock has per-`data-vehicle` / per-`data-driver` "Add Driver" buttons and 18 "Back" controls (step-back vs back-to-start); the RAG scoring path sees only `(action, description, element, site)` and no step/section context, so "add driver" in a 1-vehicle test and after adding vehicle 2 share one key. **AND** the negative-recording trigger must learn from *resolved-but-wrong* picks (high-scoring locator that keeps producing bad outcomes), not just from locator-timeouts — otherwise the generator keeps reinforcing the very traps the user is complaining about.

### Implementation (2026-08-29 scope, minimal — no scoring rewrite)
1. **Step-scope the matcher** ✅ SHIPPED — gate `_learned_net_evidence` / `_learned_negative_penalty` on `step_label`/`action` so a negative only applies on the step where it failed (the "exemption to the rule").
2. **Broaden the recording trigger** ✅ SHIPPED (`src/rag_learn.learn_negatives_from_evidence`) — a failed `ASSERTION` step with a resolved selector is now a `learned_negative` at conf 0.6, and `src/failure_classifier.py` recognizes `Locator.wait_for: Timeout` (sync API) as `LOCATOR_TIMEOUT` so the real assertion-step failures classify correctly. Same in `learning_impact.py` lab rebuild.
3. **Guard against false negatives** — infra flakes excluded (navigation/unknown/selector-less never become negatives); resolved-but-wrong uses lower confidence (0.6) so a single mis-attribution is weak and only `hit_count` accumulation (repeated failures) makes it bite.
4. **Prove it** ✅ VERIFIED LIVE 2026-08-29 — rebuild of real failed sidecars → 9 negatives, retrieval exact for the resolved-but-wrong cases, step-scoped scoring: `#payment-error` −4 on its step / 0 elsewhere; no cross-step leak of the `.add-to-cart` trap. 2898 pytest, ruff + mypy clean, eval static 97.9% (no regression).
- **NOT doing:** no change to how scores combine, no new scoring tiers, no bonus math. Only the *recording trigger* + *matcher scope* change.
- **Layer 2 (resolution-time candidate scoping, still OPEN):** scope candidates at resolve time to the current section/vehicle using `data-vehicle` context, prior steps (`resolved_steps`), and/or the observed trail — unify the existing `section_scoper.scope_elements` into the actual candidate selection used by scoring. This is the LV multi-vehicle mis-scope (the original AI-063 one-line) — separate from the negative-store layer.
- **Open (grill before build):** robustly *attributing* a failed test outcome to a specific earlier click's element (vs an unrelated later step) without flooding false negatives — the v1 resolved-but-wrong trigger uses confidence 0.6 + hit_count accumulation as the guard.

### Why the store alone can't fix it
- A negative on vehicle-2's add-driver only down-weights that exact `(desc, selector, site)` — vehicle-1's stays correct. Good (no cross-context bleed).
- But **systematic mis-scoping** (resolver always picks vehicle-1's button for "add driver" in a 2-vehicle test because DOM order wins) can only be corrected AFTER repeated failures — slow and noisy. The right fix is resolution-time candidate scoping, not a store-key change (context tokens in keys fragment evidence and starve cold-start).

### Fix sketch (two layers)
- **Layer 1 (this item — store/negative layer, minimal):** step-scope the negative matcher + broaden the recording trigger to *resolved-but-wrong* picks (see Implementation above). No scoring rewrite.
- **Layer 2 (resolution-time candidate scoping, separate / later):** scope candidates at resolve time to the current section/vehicle using `data-vehicle` context, prior steps (`resolved_steps`), and/or the observed trail — unify the existing `section_scoper.scope_elements` into the actual candidate selection used by scoring. Only build Layer 2 if Layer 1 + a real resolved-but-wrong measurement shows the LV-style flow still mis-scopes.

---

**Status:** 🆕 → **SUPERSEDED 2026-09-05 — merged into ROADMAP §12d** (Hybrid — LangGraph-orchestrated linear pipeline). One-line pointer only, per AGENTS.md §10. The full item (proposed shape, decision gate, open questions, today's updated data) lives there: `docs/plans/ROADMAP_ROADTO_PRODUCTION.md` §12d.

**The one-line version:** combine LangGraph's stateful routing, validation, retry, and human-checkpoint capabilities with LangChain-style Runnables inside nodes, while retaining the existing linear scraper/resolver as the stable execution seam.

### Proposed shape

```text
LangGraph: ingest → plan → existing linear scrape/resolve → integrity check → repair/retry → export
                                      └─ RAG retriever shared by both paths
```

- Keep the current linear pipeline as the production baseline.
- Use LangChain Runnable composition for focused prompt → model → parser / retrieval subchains inside graph nodes; do not duplicate locator-resolution logic.
- Add graph-level integrity validation and explicit retry/human-review routing, especially for skipped or weakened assertions.
- Compare the architecture independently from store warmth: `linear+cold`, `linear+warm`, `graph+cold`, `graph+warm` using identical stories, mock sites, model/settings, snapshots, and evidence metrics.
- Record whether any gain comes from orchestration, RAG warmth, or integrity checks; no negative-learning implementation is implied by this item.

**Decision gate:** only consider graph participation in the user-facing flow if it improves reviewed `mean_pass_depth` and integrity-adjusted outcomes without unacceptable latency/regression. Otherwise keep LangGraph experimental and linear as the product path.

**Open questions:** should the graph wrap the whole pipeline or only validation/repair; which state/checkpoint data is durable; how much extra model latency is acceptable; can graph and linear share one resolver without divergent behavior; how should graph-specific RAG retrieval be isolated in the A/B harness?

**Estimated sessions:** 1–2 (design + controlled comparison; no production replacement in this item).

---

## 🆕 AI-059 — Learning-impact isolation harness (METRIC FIRST, ships before AI-058)

**Status:** ✅ Complete (Deliverables 1–2 shipped 2026-08-27 — `f2f0b60` sentinel identity + controlled baseline; `c2af997` resolver usage trace). **Prerequisite spike for AI-058:** the isolation harness is in place and the cold-store baseline captured. **Deliverable 3** (opt-in production sentinel scoping, mirror of the lab sentinel) is tracked separately as a distinct 🆕 item (see the AI-059 lab hardening note below).
**Priority:** Medium (enables measurement of AI-058; without it, learning changes are unverifiable).
**Folds into:** AI-054 testing-strategy + AI-058.
**Plan of record:** `docs/plans/AI-059_learning_impact_plan.md`; Session 1 record: `docs/sessions/2026-08-27_ai059_session1_controlled_baseline.md`.

**One-line:** a lab that makes **store state the single variable** so we can attribute test-progress changes to the learned/RAG store — independent of production behavior.

### Design
- **Controlled A/B:** same story set + same site snapshot + same model/temp/thinking; the **store is the only independent variable**. Legs: golden-only → golden+positives → golden+pos+negatives.
- **Store hygiene during measurement (the key gotcha):** disable evidence auto-learn on the measured runs (a run would otherwise pollute the store), and **pre-seed each leg from a fixed store snapshot** (restore before each leg). Without this the legs contaminate each other.
- **Sites:** deterministic mocks for the baseline (no live-site noise); spot-check 1–2 live sites for realism. Stories may be real/varied — only the *pair's inputs* are held constant, so no curated fixed benchmark is needed.
- **Extraction:** compute `mean_pass_depth`, `first_pass_green_rate`, `false_positive_rate`, and (phase 2) `self_heal_iterations_to_green` from the run's `.evidence.json` sidecars — no golden keys.
- **Output:** persist per-leg metrics so cold/warm/warm+neg are directly comparable (new `eval_runs` columns or a sibling table).
- **Baseline gate:** capture the cold-store numbers FIRST; AI-058 ships only if `warm+neg > warm > cold` on `mean_pass_depth`.

### Scope guard
- This is NOT a production feature. It must not change generation behavior; it only instruments and measures. Keep it behind a `scripts/` harness + a `--metric` path, not in the user-facing flow.

### Estimated sessions
- ~1–1.5 (extraction + store-snapshot A/B loop + baseline capture). Phase 2 self-heal instrumentation adds ~0.5.

---

## 📋 AI-054 — Pipeline consolidation & testing-strategy review (UNDISCOVERED decisions + test triggers)

**Status:** 📋 review — consolidated 2026-08-23 from a session test-coverage audit (after the AI-051/052/053 ship). Six related facets of "what do we maintain, and when do we test it." No code changes implied yet — this is a decision + test-strategy record. We will add fixes/changes here as they are scoped.
**Priority:** Medium — mostly strategy/coverage; the one buildable piece is (5).

### 1. One pipeline? — LINEAR vs LANGGRAPH (⏸️ UNDECIDED — pending research)
**→ CONSOLIDATED 2026-09-05 into ROADMAP §12d (Hybrid — LangGraph-orchestrated linear pipeline).** The decision record + data (historic 88.1-vs-32.8 inflated by the fixed mock-ensure bug; clean −9.8pp; demoqa story-bleed root-caused) live there. This section stays as the research-summary history + the open research needs:
**Decision owner:** user — undecided until more data.
**What we know (recorded):** linear is the production default; the LangGraph multi-agent path (Planner→Generator→Validator, `src/agents/`) is built + unit-tested but **dormant — not wired into the user flow** and never made default because eval results were worse. The decisive comparison (`docs/sessions/2026-07-29_eval_baseline_restoration.md`): **linear 88.1% vs graph 32.8%**, BUT that session concluded the gap is **not the architecture** — graph generates more comprehensive skeletons (more steps; e.g. LV Insurance 90–102 steps) that the **journey scraper can't keep up with** (multi-step SPA forms, hidden sections). Recorded verdict: *"Once the scraper can click through form sections, the graph pipeline should match or beat linear."*
**Research the user needs before deciding:** (a) deep-dive the two pipelines' real benefits/limitations (per-site, not just the headline number — the 2026-07-29 table shows graph *won* on automationexercise +12pp); (b) **market direction** — how AI test-generation is evolving and what's best for our customers (multi-agent/agent-orchestration trends vs robust single-pass); (c) what a customer actually buys (breadth of coverage vs reliability/speed).
**Candidate outcomes (to grill later):** keep-dormant (linear is the product, graph stays experimental) / invest-in-scraper-then-reactivate-graph / delete-graph (cut the dormant ~`src/agents/` surface). **Do not decide on memory — re-pull the 2026-07-29 per-site numbers first.**

### 2. RAG — on/off is already settled in code; the gap is test coverage
RAG is **always-on by default** (B-036, 2026-08-04): `src/orchestrator.py::_build_rag_retriever()` treats a missing `RAG_ENABLED` as *enabled*; only `RAG_ENABLED=0` opts out; empty store ⇒ no bonus ⇒ identical behavior (graceful degradation). **When off:** hermetic tests + CI (CI forces `RAG_ENABLED=0` to skip the ~80 MB embedder download per runner — flow-memory-only in CI, see `docs/ci.md` §8b).
**The real gap:** our `verify_production` / `uat` / eval-static runs this session were **RAG-off**, so we have NOT seen RAG retrieval + golden-pattern bonus + the trail fix (AI-051/AI-052) *compose* live.
**Test trigger:** run **one RAG-ON verify** (`RAG_ENABLED=1 verify_production saucedemo`) to confirm composition; treat RAG-on as the product default in future UAT.

### 3. thinking=ON — model-gated re-test (pairs with flakiness, #6)
`enable_thinking` switch is ✅ shipped (AI-050). But a **valid thinking-ON verdict is blocked** by AI-046: the 3.8 GGUF on this box is Q2_K-heavy (3.3bpw) vs 3.6 (6.7bpw), so the earlier thinking-ON A/B (75.3 vs 62.4 excl.-timeout) is a **quantization confound, not a model/thinking verdict**. Records: `docs/sessions/2026-08-19_thinking_collapse_and_ab.md`, `2026-08-19_external_benchmark_and_thinking_on_ab.md`, `2026-08-20_model_ab_retest_handover.md`.
**Test trigger:** when a matched-precision 3.8 exists, re-run thinking-ON A/B + GSM8K per the handover plan — and measure **flakiness** in the same pass (byte-stability re-runs; the GPU-contention UAT timeout we saw is a candidate flake to investigate).

### 4. Flat (non-POM) mode — keep, test occasionally
Flat is a supported, distinct output shape (non-POM). No single "scenario" because it's **mode parity**, not a feature. **Test trigger:** after any *structural* pipeline change (resolver/scorer/skeleton shape), run **one flat UAT** (`uat.py --flat` or `verify_production --flat`) to confirm it still resolves. Low-frequency, high-value. (POM mode is what all this session's runs used.)

### 5. Export / code-postprocessor — bring to a quality bar, then GUARD it (the one buildable piece)
Two phases: **(a)** bring export quality up to a level we're happy with — evidence collection, POM/flat strip (`code_postprocessor`), JUnit/HTML/JSON export, artifact (heatmap/Gantt) accuracy; **(b)** add a **regression gate** so pipeline changes are checked against evidence export (extend the eval harness or a CI job: generate → export → validate evidence shape/sidecars). This is the only sub-item that requires *building* rather than just *testing*.

### 6. Flakiness — fold into the thinking re-test, don't chase constantly
We don't need dedicated flakiness runs constantly. **Test trigger:** measure flakiness (determinism / byte-stability / timeout behavior) **during the thinking-ON re-test (#3)** — that's where non-determinism would show. Known candidate: the `uat.py --all-sites` saucedemo leg timed out on LLM generation under GPU contention (2026-08-23) — infra flake, but worth understanding.

### Suggested test cadence (rollup)
| Trigger | What to run |
|---------|-------------|
| Structural pipeline change (resolver/scorer/skeleton) | eval static (gate) + **one flat UAT** (#4) + **one RAG-ON verify** (#2) |
| Thinking re-test / model change (#3) | thinking-ON A/B + GSM8K + **flakiness/determinism** (#6) |
| Export/touch code_postprocessor (#5) | export-quality pass + evidence-export regression gate |
| Before any ship | existing: smoke → pytest → verify_production both sites → eval static → ruff/mypy → CI |

**Session record:** `docs/sessions/2026-08-23_ai054_pipeline_testing_review.md` (to be created when work starts).

---

## 🆕 AI-050 — Thinking models burn the token budget on reasoning and return EMPTY content: the real cause of the `got=0` collapse and the resolution timeouts (✅ COMPLETE 2026-08-19)

**Status:** ✅ Complete 2026-08-19 — explicit `enable_thinking` switch shipped (provider `chat_template_kwargs` passthrough, `None`=never silently overridden, logged per call + `eval_runs.thinking`), skeleton + resolution call sites opt out deliberately. Gates green: full suite **2691 passed / 1 skipped**, smoke 39/39, mypy clean, eval static 97.9% (exit 0), ruff clean. Continues `docs/sessions/2026-08-18_llm_model_ab_investigation.md`; session record: `docs/sessions/2026-08-19_thinking_collapse_and_ab.md`. **OPEN FOLLOW-ON (→ AI-046):** the thinking-OFF A/B (76.1 vs 62.4) is NOT a valid model verdict — see AI-046; needs a thinking-ON re-run + external-benchmark validation.
**Priority:** Critical — this invalidated the "156k config collapses generation" hypothesis AND retroactively explains AI-049's timeouts: resolution calls spent 160–310s thinking, far past any timeout.
**Root cause (raw-response probe, 2026-08-19):** Qwen3.6 and Qwen3.8 are *thinking* models. With the server's jinja template they emit a `reasoning_content` phase BEFORE any content. Measured on both models with the exact skeleton prompt (temp=0.0): default calls burned the whole 4096-token `max_tokens` cap on thinking ("Thinking Process: 1. Analyze the Request...") → `finish_reason=length`, `content=''` (3.8: 2/3 calls; 3.6: 2/2). The provider reads only `message.content` → empty skeleton → `expected=N, got=0 → Retrying` loops, and on resolution calls the thinking phase alone (160–310s) blew the old 45s timeout. **Run C's "3.6 tolerates the 156k config" was retry luck — 3.6 collapses identically at the raw-call level.** The collapse was never a server-config flag.
**Fix (explicit, visible, never silent — per user direction):** (1) `LLMProvider.complete()` gains `enable_thinking: bool | None = None` — `None` sends NOTHING (model/server default governs, never silently overridden); `True`/`False` goes to OpenAI-compatible endpoints as `chat_template_kwargs={"enable_thinking": ...}` (proven effective: llama.cpp honors it per-request). Ollama accepts-and-ignores for contract parity. (2) `LLMClient.generate/generate_test/_complete_sync` thread it through and LOG it per call (`thinking=off|on|default` next to `temp=`). (3) The two proven-broken structured call sites opt out explicitly with documented rationale: `TestGenerator._generate_skeleton_single_call` (skeleton generation) and `SemanticCandidateRanker` (resolution ranking — constructor param, default False, overridable). LangGraph stages keep the model default until measured per-stage (future work). (4) `eval_runs` gains `thinking TEXT` (ALTER-migrated): linear runs record `"off"` (structured calls), graph runs `"model-default"` — a future session can never be misled about what a number was measured with. `/no_think` in-band was tested and REJECTED (model ignores it); raising max_tokens to 16384 works but is 17× slower.
**Measured effect:** skeleton call 160–310s → ~15–18s with content every time (both models); determinism check: empty-generation failure eliminated. **Side finding:** speculative decoding (draft-mtp) is the residual non-determinism source — spec ON at temp 0 gives token-level naming jitter (14.8s/gen), spec OFF is byte-identical (32.4s/gen). A/B decision (user): **spec OFF** for the definitive run.
**Tests:** 14 new (client delivery x3: default-sends-nothing/explicit-off/explicit-on; provider payload x6: default-omits-field/explicit-off/explicit-on for OpenAIProvider + LMStudioProvider, ollama contract parity; ranker x4: default-off/sends-off/overridable/batch; generator call site x1). Gates: full suite **2691 passed / 1 skipped**, smoke 39/39, eval static 97.9% (exit 0), ruff + mypy clean.
**Note:** touched three protected files with minimal additive changes (`src/llm_providers/__init__.py`, `src/llm_client.py`, `src/test_generator.py`) — flagged for review.

---

## 🆕 AI-049 — Resolution LLM timeout hard-coded at 45s + silent failure: flat-0% eval sites (✅ COMPLETE 2026-08-19)

**Status:** ✅ Complete 2026-08-19 — `DEFAULT_RESOLUTION_TIMEOUT=120.0` (keyword-only, plumbed ElementMatcher→PlaceholderOrchestrator→TestOrchestrator), `_is_timeout_error()` cause-chain walker, both call sites log WARNINGs (timeout / elapsed-vs-limit / affected placeholders) so `None`→0% is never silent. 8 tests. Cross-ref `docs/sessions/2026-08-18_llm_model_ab_investigation.md` §10 (the discovery), §12 (this was the named TO-DO).
**Priority:** High — this silently polluted every eval leg on a loaded server (run C: 27 timeouts, run E: 7), making the 3.6-vs-3.8 comparison invalid and producing flat-0% sites that looked like model/config behavior.
**Root cause:** `src/semantic_candidate_ranker.py` hard-coded `timeout=45` on both resolution LLM calls (single + batch) and wrapped them in `except Exception: return None` — a timeout yields `generated_locator=None`, the placeholder scores 0, and nothing is logged. On a loaded server (generation + resolution + the always-on RAG embedder/Milvus sharing the box) 45s is routinely exceeded. Per the session's key rule: **flat zeros = failure, not tuning.**
**Fix:** (1) `DEFAULT_RESOLUTION_TIMEOUT = 120.0` in `src/semantic_candidate_ranker.py`; ranker takes `timeout=` keyword-only; `_is_timeout_error()` walks the exception cause chain (`LLMClient.generate` wraps provider errors in `RuntimeError`, so the httpx timeout sits one level down). Both call sites now log a WARNING naming the timeout, elapsed vs limit, and the affected action/description(s) — `None`→0% is never silent again. (2) Plumbed keyword-only with defaults through `ElementMatcher` → `PlaceholderOrchestrator` → `TestOrchestrator` (no call-site break). (3) `scripts/eval/eval_runner.py` passes `resolution_timeout=DEFAULT_RESOLUTION_TIMEOUT` explicitly at both orchestrator constructions — the eval is the consumer that measures resolution, so its choice is visible in code. **Deliberately NOT an env var / CLI flag:** sane default everywhere, constant-in-code keeps A/B legs on identical conditions (runtime knobs were the confound class that burned the investigation).
**Tests:** 8 new in `tests/test_semantic_candidate_ranker.py` (default=120; timeout passed to generator; timeout → None + loud WARNING with description; non-timeout failure also logged; batch timeout names every affected placeholder; cause-chain detection direct/wrapped/negative; plumbing through matcher + orchestrator; default plumbing). Gates: full suite **2677 passed / 1 skipped**, smoke 39/39, eval static 97.9% (exit 0), ruff + mypy clean.
**Next steps (from session doc §12):** ~~isolate the 156k-config `got=0` generation-collapse flag~~ DONE 2026-08-19 — the collapse was thinking-budget exhaustion, not a config flag (see AI-050). Remaining: the genuine single-config manifest-logged 3.6-vs-3.8 A/B (spec OFF, thinking off recorded) that re-answers AI-046 — in progress.

---

## 🆕 AI-048 — Linear pipeline delivered NO temperature: sampling config silently governed generation (✅ FIXED 2026-08-18)

**Status:** ✅ Fixed (2026-08-18 session, committed 2026-08-19), cross-ref `docs/sessions/2026-08-18_llm_sampling_config_fix.md`
**Priority:** High — this was the *unrecorded confound* behind AI-046 (and a day+ of 3.6-vs-3.8 investigation)
**Root cause (read the code, 2026-08-18):** the **linear pipeline path** (default UI/CLI/eval/verify_production) called `LLMClient.generate()` with `temperature=None`, so providers omitted the field and the **server's own default** (1.0 on llama.cpp launches — max entropy) silently governed skeleton generation. The LangGraph agents always pass `temperature=0` (pinned 2026-07-31 for self-consistency, commit 69e5d9a: 55.6% → 100% byte-for-byte identical skeletons). So graph = deterministic, linear = server-default entropy — model A/Bs through the linear path compared two launches' sampling configs, not two models. The 3.6 launch's `/props` was never captured (same gap class as the empty `model` column). Also learned: **`/props` `speculative.types` is the per-request override default, NOT the serving config — the running slot (`/slots`) reports the truth** (slot 0: `speculative: True`, n_ctx 262144 on the current Qwen3.8 launch); models are session-level (`LLMClient._session_model`); per-agent/per-stage model+settings selection never existed — the multi-provider spec §13 Q4 stayed an open question, resolved centralized.
**Fix:** (1) `src/llm_client.py` — `llm_temperature_default()` reads `AITEST_LLM_TEMPERATURE` (default 0.0, clamped 0–2, invalid → warn + 0.0; matches the graph's proven determinism); `_complete_sync` substitutes it when a caller passes None (graph agents pass 0 explicitly — unchanged); `generate_test` gained a `temperature` pass-through. (2) `scripts/eval/eval_runner.py` — `eval_runs` gains `temperature_sent REAL` + `server_defaults TEXT` (ALTER-migrated; legacy rows stay NULL = honestly unknown); `_sampling_identity()` records the resolved delivered temperature (graph → 0.0, linear → env-or-0.0) + a best-effort `/props` snapshot (temperature/top_p/top_k/seed/repeat_penalty/n_ctx). `.env.example` documents the var.
**Tests:** 7 new (pin default / env override / explicit overrides env / invalid env → 0.0 / helper clamp; persist stores temperature_sent + server_defaults; legacy-schema migration preserves data + NULLs). Gates: full suite **2668 passed / 1 skipped**, smoke 39/39, ruff + mypy clean (eval_runner's 5 pre-existing mypy notes are in the hook-excluded scripts/ dir, unchanged).
**Next step (after this):** re-run the model A/B WITH the pin (identical `AITEST_LLM_TEMPERATURE` for both launches) — now it measures models, not launch config. Numbers will shift off the 31→55% line (those were at temp 1.0); re-baseline via the eval-accuracy gate (`--min-accuracy`). Keep AI-046's "use qwen3.6" workaround until the controlled rerun.

## 🆕 AI-046 — Qwen3.8-27B skeleton/resolution regression (vs 3.6)

**Status:** ❗ MODEL-FILE CONFIGOUNDED — NO valid verdict possible from current data. **2026-08-20 UPDATE: the A/B is invalidated at the GGUF level, NOT by model architecture.** Both files are named `UD-Q4_K_XL` but are wildly different precision (measured via `gguf.GGUFReader`): **3.6 = 6.71 bpw overall (attn_qkv Q3_K, 6.29 bpw) vs 3.8 = 3.30 bpw overall (attn_qkv Q2_K, 2.56 bpw, 325/866 tensors at Q2_K ≈ 38%)**. So the observed "3.6 ≈ or > 3.8" result is largely a quantization-quality artifact — a 6.7bpw model was compared to a 3.3bpw model. No Qwen3.8 at matched precision exists on this box (Q4_K_XL=3.3bpw, Q6_K_XL=4.0bpw — neither near 3.6's 6.7bpw). Repro: `scratch/gguf_quantization_confound.md`, `scratch/model_ab_all_conditions.md`.

**Earlier (2026-08-20, since revised):** thinking-ON A/B + external GSM8K appeared to show 3.6≥3.8 (thinking OFF 76.1 vs 62.4; thinking ON excl.-timeout 75.3 vs 62.4; GSM8K tie 0.82 vs 0.81). These numbers are REAL for the files tested but the two files are not a fair architecture comparison.

**What a valid re-test needs:** a Qwen3.8 GGUF at MATCHED precision to 3.6 (≈6.7bpw, e.g. true Q4_K/Q6_K recipe, not the aggressive Q2_K-heavy 3.8 here), then re-run the thinking-ON A/B + GSM8K. A matched-precision 3.8 download is in progress; when it arrives follow the full re-test plan in `docs/sessions/2026-08-20_model_ab_retest_handover.md` (corrected config: MTP ON for BOTH models, draft n-max 3 / p-min 0.0; bpw gate before running; same env knobs). Until then, AI-046 has NO defensible model verdict. The earlier 2026-08-17 "3.8 is worse" and this session's "3.6 wins" are both treated as confounded/unsupported.

**Session records:** `docs/sessions/2026-08-19_thinking_collapse_and_ab.md` + `docs/sessions/2026-08-19_external_benchmark_and_thinking_on_ab.md`; evidence moved to **`/c/Users/l_a_c/code/llm-benchmarks/evidence/model-ab-2026-08-20/`** (README, manifests, logs, gguf_quantization_confound.md, model_ab_all_conditions.md).
**Priority:** Medium — model-choice issue, not code
**Evidence (2026-08-17, same eval `--mode full --regenerate`, same code):** resolution 31.2% (3.8) vs 45.9% (3.6); saucedemo **35% vs 75%**; lv_insurance 42% vs 75%; identical saucedemo scrape both runs (model-independent); live DOM verified intact; zero SSRF/stamp interference. `verify_production`: saucedemo 5 failures with 3.8 (login asserts pre-login URL; duplicate add-to-cart clicks) → all pass with 3.6. eval_runs `model` column now records the model (was empty — this A/B was hampered by it).
**Cross-ref:** docs/sessions/2026-08-17_phase6_spec.md (session record), tests/test_eval_runner_mocks.py (eval fix).

## 🆕 AI-047 — Eval harness mock-server bug: mock stories 0% in regenerate mode (✅ FIXED 2026-08-18)

**Status:** ✅ Fixed — committed and CI green (see commit); fix verified by the mock-only confirm run (0% → 81%) and the full eval (31.2% → 55.0% on qwen3.8)
**Priority:** Medium — eval infrastructure; polluted the 3.8/3.6 A/B headline (3 mock stories dragged resolution to 31.2%)
**Root cause:** `EvalRunner._ensure_mock_server` served ONE directory for the whole run — the first localhost dataset's `mock_dir` (legacy eval-005 has none → repo root), so `mock_sites/ecommerce|banking` URLs 404'd (golden keys reference root-relative URLs like `/cart.html`; ecommerce and banking both use `/index.html` so one root cannot serve both).
**Fix (`scripts/eval/eval_runner.py`):** `_build_mock_dirs()` maps story_id → served dir (declared `mock_dir` resolved against the repo root; legacy → repo root; injectable root for tests); `_ensure_mock_serves()` (re)starts the :8781 server per story in BOTH the regeneration and execution phases (`on_story` hook into `run_full_validation`). Also: `_loaded_model_identity()` records provider/model into `eval_runs` (the empty-model gap that hampered the A/B). **Repo-root derivation bug found while fixing:** `dataset_dir.parent.parent` lands on `scripts/` not the repo root — now module-path-based.
**Tests:** `tests/test_eval_runner_mocks.py` (4: legacy→repo root, declared mock_dir resolution, live-sites ignored, per-dir server swap). Verified end-to-end: each mock family serves at root (ecommerce/banking/lv all 200).

## 🆕 AI-045 — Commercial-readiness gaps for Phase 6 (from competitive research + code audit)

**Status:** 🟡 ready-for-agent — priority list folded into the Phase 6 spec as the 6a–6i build order (`docs/specs/FEATURE_SPEC_phase6_saas.md`, WRITTEN 2026-08-17 — Draft, §9 open questions to grill before 6a/6e build). **Phase 6 status → ROADMAP §13: Part 1 (6a–6i) code-complete 2026-09-05** (one-line pointer per AGENTS.md §10; full status lives in the roadmap item + evaluator records).
**Priority:** High — commercial viability blockers, not nice-to-haves
**Cross-ref:** `docs/plans/RESEARCH_SAAS_AND_LAUNCH.md` §8 (full audit with per-item severity); `docs/plans/RESEARCH_COMPETITIVE_LANDSCAPE.md` (why air-gap/no-egress is the wedge)
**Source:** code audit 2026-08-17 (read `rag_store.py`, `pdf_ingest.py`, `rag_bundled.py`, `llm_client.py`, `prompt_safety.py`, `secure_config.py`, `verify_production.py`, eval baseline)

**Context:** competitive research concluded the differentiated revenue is the **air-gap/compliance tier** (BYO-LLM, no egress). These gaps are what must be true before that pitch is honest and before the Phase 6 spec is written. The `no data leaves your deployment` claim is the #1 sales argument — two of these gaps (SSRF, redaction) are security claims, not just features.

**Priority order (from the audit):**
1. **SSRF guard + egress audit** (§8.4) — **✅ SHIPPED 2026-08-17 (spec 6a)**: `src/url_guard.py` (resolve-and-classify: link-local/metadata always-blocked, private opt-in via `AITEST_ALLOW_PRIVATE_NETWORKS`, loopback default-ON for local/mock family, Playwright request-level redirect handler) wired into orchestrator intake + all scrapers + `ci_generate.py` (under the Phase 7 danger-zone check, new `--allow-private-networks`); `scripts/audit_egress.py` static gate (143 files / 13 sites / 0 flagged) in smoke Gate 0 + CI; `docs/security/egress-audit.md` published. 43 new tests; suite 2641 passed / 4 skipped, smoke 39/39, ruff + mypy clean, fake-LLM E2E green.
2. **Embedding model stamp + reindex path** (§8.3) — **✅ SHIPPED 2026-08-17 (spec 6b)**: `SentenceTransformerEmbedder.identity` (`model@dim`) + `MilvusLiteBackend` embedder stamp sidecar (`<db>.embedder.json`, written at creation; dimension mismatch ALWAYS refused, embedder mismatch refused, legacy no-sidecar stores accepted+migrated only for the default model); `RAGStore` cross-checks its actual embedder before every op; `rag_ingest.py --reindex` (rebuild from bundled pack, resets learned, rewrites stamp + marker); mismatch surfaced loudly (retriever ERROR + orchestrator seed catch, CLI clean error). 13 new tests; suite 2654 passed / 4 skipped, eval static 97.9% (no regression), smoke 39/39, ruff + mypy clean; legacy migration verified against the real store (145 entries, stamped).
3. **Team-deployment concurrency** (§8.1) — Milvus Lite is single-writer; D2 team shape (N employees, one workspace) risks concurrent writes (two Streamlit sessions / UI + CI Action). May resolve as "one server, one process" + file locks instead of a DB swap.
4. **PDF OCR wiring** (§8.2) — **✅ COMPLETE 2026-08-24 (commits `b87426e`…`063a701`, branch `overnight/ai045-4-pdf-ocr-dedup`)**: `ingest_pdf`/`ingest_pdf_directory` gained a page-scoped `ocr_fallback` hook; `OcrBackend.parse_page` added (UnlimitedOCR rasterises the single page at 300 DPI); `rag_ingest.py --pdfs` consults `get_ocr_backend()`; image-only pages log a WARNING (was silent) when no OCR backend is available. **Dedup key (§8.2 sub-item) also done**: `DocChunk.dedup_key` = `sha256(source \x00 heading_path \x00 normalised_text)`; `RAGStore.add_docs` returns `(inserted, skipped)` and is idempotent; new `--prune-dupes` CLI flag. 10 new tests (OCR wiring uses real PyMuPDF PDFs + a plain callable OCR hook, no GPU); gates (fitz installed for CI parity): 2793 passed / 0 failed, smoke 39/39, eval static 97.9% (no regression), ruff + mypy clean, coverage 70%. Session record: `docs/sessions/2026-08-24_ai045_4_pdf_ocr_dedup.md`. Note: `UnlimitedOCRBackend.parse_page` real GPU path is untested (mocked in tests; opt-in + GPU-gated by design).
5. **Screenshot credential redaction** (§8.4) — unverified whether screenshots mask filled password fields; needs a test + redaction pass if not.
   - **✅ SHIPPED 2026-08-25 (commit `311323c`):** `src/credential_redaction.py` — sensitive-field detection (locator + live attrs + label text, camelCase/snake_case-aware), sidecar value/label/URL redaction in `evidence_tracker.fill/navigate`, `masked_screenshot_page` blanks filled sensitive inputs for every evidence screenshot capture then restores. 51 unit tests + 1 real-browser integration test; verified live via verify_production saucedemo (sidecar shows `***REDACTED***`, zero secret hits across evidence JSONs, pixel-level dot check clean). Gates: suite 2844 passed / 0 failed, smoke 39/39, eval static 97.9%, ruff + mypy clean.
   - **KNOWN TRADE-OFF (accepted, low priority):** masking blanks ALL sensitive fields including native `type="password"` inputs, so evidence screenshots show an EMPTY field instead of the browser's dot rendering. A user story explicitly asserting "password displays as masked dots" still passes correctly (verdicts come from live Playwright assertions, unaffected by the ms-scale capture mask), but the reviewer loses visual dot evidence. Possible future refinement: skip blanking for true `type="password"` fields (dots already hide content; only length leaks). Accepted for now because fail-safe > fail-open for the no-egress security claim — and the dot-rendering behavior can be verified manually against any live site when needed.
6. **Latency benchmark + LLM cache** (§8.5) — no published E2E number, no SLO, no LLM-call cache. Target < 2–3 min per 6-criteria story on consumer hardware + a published per-model-tier table.
7. **Multi-site eval dataset** (§8.6) — current baseline 100% on 67 resolutions but single site (saucedemo); not an enterprise-trustworthy accuracy claim. Needs automationexercise + LV mock goldens re-validated on live sites.

**Dependencies:** the Phase 6 spec is written (2026-08-17, draft — grill §9 before 6e) with 6a + 6b shipped; remaining 6c–6i build from the spec's §6 table.

---

## ✅ AI-051 — B-021 post-action URL assertions emit the base/starting URL, not the landing page (login redirect unaccounted) — FIXED 2026-08-23

**Status:** ✅ Fixed 2026-08-23 — surfaced 2026-08-21 via `verify_production` FAIL. Concrete case: generated saucedemo `test_01_login` ends with `expect(page).to_have_url("https://www.saucedemo.com/")` after clicking Login, but saucedemo always redirects to `/inventory.html` post-login → `AssertionError: Page URL expected to be .../ actual .../inventory.html`.
**Priority:** Medium — pipeline-generation quality; makes generated tests fail-safe at runtime but produces false-red tests for redirecting flows.
**Root cause:** `placeholder_orchestrator.py` **B-021** (`if action == "ASSERT": # B-021: Page-state assertions become URL assertions`) converts a page-state ASSERT into a URL assertion but emits the **initial/base URL** (`current_url` at step start) instead of the **landing URL** the preceding action actually navigates to. The resolver tracks `current_url` through the journey (and `url_inference.infer_next_page_url` does compute transition targets for CLICK steps) — the ASSERT conversion does not consume that inferred "next" URL.
**Runtime safety net works as intended:** `evidence_tracker`/Playwright `to_have_url` correctly flags the mismatch; the failure is generated-upstream, not a runtime path defect.
**Regression status:** pre-existing — reproduced **identically** on clean HEAD (`git worktree`, no diff): `[saucedemo] 10/13 gates (3 failed)` / `TOTAL 22/26 (4 failed)` both with and without the thinking/timeout commit (`6fd2620`). Not introduced by that change.
**OPEN QUESTION — enable_thinking may affect it:** bug originates in skeleton generation + resolution ranking (the two call sites `enable_thinking` toggles). Current runs are `thinking=off`. A thinking-ON leg could change *which* URL the model emits / how the assert is framed — candidate to test when the matched-precision 3.8 re-test (AI-046) runs. Currently unverified which direction.
**Fix (2026-08-23):** the B-021 page-state ASSERT branch in `placeholder_orchestrator.py::_replace_placeholders_sequentially` now consults the **observed trail** (AI-052's `ObservedTrail`, the same evidence-only principle as AI-052): when the trail evidences the step's landing page differs from the keyword-inferred one (e.g. Login CLICK navigates `home → /inventory.html`, which keyword resolution can't reach because it was never scraped as a *description* match), the assertion emits the **observed `to_url`** (a browser fact) instead of the base/starting URL. Gated on `obs is not None and not diverged and pending_evidence is None` so it never fires in back-compat (no-trail) mode. 4 new tests in `tests/test_ai051_page_state_url.py` (login repro, no-trail back-compat, scraped-landing no-flip, keyword==observed agreement). **Verified in production on BOTH sites:** saucedemo (`verify_saucedemo_20260823_180614`) — `test_01_login` now asserts `/inventory.html`, execution **5 passed / 1 honest skip / 0 failed / 0 different-page** (was 4/1F/1S); automationexercise (`verify_automationexercise_20260823_193521`) — **7 passed / 0 failed / 13-13 gates** (was 6/1F). The automationexercise `test_07_proceed_to_checkout` failure was the **same bug** (not login-gated — that site has no login): the assert guessed `/checkout` from keywords, but the click stays on `/view_cart`; the fix now asserts the observed `/view_cart`. Eval static 97.9% (no regression); 2744 passed / 1 skipped; smoke 39/39; ruff + mypy clean. The `enable_thinking` open question is moot — the fix is trail-driven, independent of skeleton phrasing.

**S6 note (2026-08-23):** reproduced post-AI-052 ship as the sole remaining saucedemo execution failure (`verify_saucedemo_20260823_111019`, `uat_saucedemo_20260823_115751`); resolved by the fix above. The UAT `--all-sites --save` quirk found in S6 (only the last site persisted) is **fixed 2026-08-23** — `results.append` moved inside the loop, OVERALL now aggregated across all sites via `summarize_results()` (see AI-053 below). Session records: `docs/sessions/2026-08-23_ai052_session6_ship.md`, `docs/sessions/2026-08-23_ai051_page_state_url.md`.

---

## ✅ AI-053 — `uat.py --all-sites --save` persists only the last site (✅ COMPLETE 2026-08-23)

**Status:** ✅ Complete 2026-08-23 — found during AI-052 S6 ship: with `--all-sites`, `results.append(site_result)` sat OUTSIDE the site loop in `main()`, so the saved JSON (e.g. `docs/sessions/uat_ai052_final.json`) and the OVERALL line both reflected only the last site (saucedemo) even though both ran. **Fix:** `scripts/uat.py` — append moved inside the loop; OVERALL counts aggregated across all sites via new `summarize_results()` (testable helper; `--compare` already merged multi-site baselines by site_id). 5 new tests in `tests/test_uat.py` incl. an AST guard pinning `results.append` inside the loop (catches the exact regression shape). Gates: full suite 2740 passed / 1 skipped, smoke 39/39, ruff + mypy clean.

---

## ✅ AI-052 — Resolver page-scope enforcement: locator resolved for a page the test isn't on (wrong-page add-to-cart) — SHIPPED 2026-08-23

**Status:** ✅ Complete 2026-08-23 — surfaced 2026-08-21 via `verify_production` FAIL. Concrete case: generated saucedemo `test_02/03/04` sequence `click('#item_4_title_link')` (nav → product-detail `inventory-item.html?id=4`) then `click('#add-to-cart-sauce-labs-fleece-jacket')` which exists **only on the inventory page** → runtime `_LocatorNotFoundError: element exists on a different page than the one this step runs on`.
**Priority:** Medium — pipeline-generation quality; produces semantically-wrong journeys and page-scope violations.
**Root cause (two compounding generation bugs):**
1. **Skeleton/flow logic** — the LLM generated a wrong sequence ("view item A, then add item B" where B's button is on a different page).
2. **Resolver page-scope bounding** — `placeholder_orchestrator` tracks `current_url` per step (B-014 step-context exclusion at the resolver, `url_inference.infer_next_page_url` computes the transition after the title-link CLICK) but the **next** step's resolution was **not bounded to the actual current page**; the yellow-flag locator slipped through.
**Runtime safety net works as intended:** `src/evidence_tracker.py::click` fast-fails with `_LocatorNotFoundError` (count==0 on current page) instead of burning the ~150s fallback marathon — that guard is functioning correctly; the bug is that the wrong-page locator was generated at all.
**Regression status:** pre-existing — reproduced **identically** on clean HEAD. Not introduced by commit `6fd2620` (thinking/timeout).
**OPEN QUESTION — enable_thinking may affect it:** the wrong-page locator is produced by skeleton generation + resolution ranking (the call sites `enable_thinking` toggles, currently `off`). Whether thinking-ON changes the model's page-awareness/flow logic is unverified — candidate to test in the AI-046 re-test. Currently unverified which direction.
**Repro:** `generated_tests/verify_saucedemo_20260820_234225/test_saucedemo.py::test_02_add_item`. Session record: `docs/sessions/2026-08-21_peer_verification.md`.
**Fix in progress (2026-07-23):** plan of record `docs/plans/AI-052_observed_transitions_plan.md` — 6 sessions. **S1 ✅** (capture `ObservedTrail` in `JourneyScraper`) + **S2 ✅** (plumbed into resolver) + **S3 ✅** (core fix: trail-driven scoping, strict no-all-pages-fallback, divergence-aware replay of proven selectors, divergence latch) + **S4 ✅** (keyword-URL guessing deleted — evidence-only transitions; eval static 97.9% unchanged) + **S5 ✅** (ARIA role gate in fast passes, penalty-first; resolver-mode A/B 97.9% = 97.9% — zero golden regressions). Both verify sites show **zero different-page locator errors**. Records: `docs/sessions/2026-07-23_ai052_session3_core_fix.md`, `docs/sessions/2026-08-23_ai052_session4_no_guessing.md`, `docs/sessions/2026-08-23_ai052_session5_role_gate.md`. **S6 ✅ SHIPPED (2026-08-23)** — regression sweep clean: `verify_production` both sites post-S5 = zero different-page locator errors (saucedemo 4 passed/1 failed [AI-051 only]/1 skip; automationexercise 6/7 [login-gated checkout]); `uat.py --all-sites --run`: automationexercise 12/13 checks, saucedemo 10/13 (3 failures = designed honest skips for unevidenced cart/checkout/finish transitions + 1 AI-051 execution failure); eval static 97.9% unchanged; 2735 passed / 1 skipped, smoke 39/39, ruff + mypy clean, CI 9/9 green. Commits: `2819c0b` (S1–S3), `9d4c50c` (S4), `c4685f3` (S5). Records: session 6 `docs/sessions/2026-08-23_ai052_session6_ship.md` + UAT evidence `docs/sessions/uat_ai052_final.json`. **UAT quirk found:** `scripts/uat.py --all-sites --save` persists only the last site's `SiteResult` (append outside the loop) — see S6 record. Remaining saucedemo failure is AI-051 (out of scope); automationexercise checkout is login-gated (skeleton gap).

---

## ✅ Phase 7 CI/CD Integration — spec + 7a + 7b + 7c complete (2026-08-13/14/15)

**Status:** ✅ Complete — spec (no open questions) + **7a** (driver 2026-08-13, Docker action tail 2026-08-14) + **7b** (generate-and-run 2026-08-15) + **7c (GitLab parity 2026-08-15)**: `.gitlab-ci.template.yml` include template (three modes + build/compute-key jobs + manual slash job), `ci/platform/gitlab.py` (MR notes), protected-environment approvals, `docs/ci.md`. Roadmap Phase 7 → `[x]`.
**Priority:** Medium-High (Tier 5 — Commercialization)
**Spec:** `docs/specs/FEATURE_SPEC_phase7_ci_cd_integration.md`

**What shipped this session (7a core, all gates green — 2510 passed, smoke 38/38, eval static 97.9%):**
- `scripts/ci_generate.py` — **headless driver**: the product's first non-interactive generation entry point. Exit codes 0/1/2, `--json` output, AI-029 workspace isolation, danger-zone allow-list (`localhost`/`*.staging.*`/`*-dev`/`*.test.*` + `--danger-zone`/`--allowed-domains` overrides), credential profiles, ignore-file validation. Calls the SAME `ui_pipeline.run_pipeline()` the UI/CLI use.
- `scripts/fake_llm.py` — OpenAI-compatible fake LLM (conditions / per-condition skeleton fragments / semantic routing) so the FULL generation pipeline runs offline against the mock-site family — hermetic, never decays.
- `src/ci_ignore.py` — `.ai-test-ignore.yml` parser/validator/matcher (the "buttons moved but still works" mechanism). **Anti-rug rule: `reason` is required per rule** — an ignore without a recorded why fails at parse time.
- `tests/test_ci_ignore.py` (12) + `tests/test_ci_generate.py` (16: allow-list, config-error contract, JSON shape + 1 slow-lane E2E: fake LLM + ecommerce mock → package written, workspace isolated, 8 tests).
- **Product bug found + fixed: `src/pipeline_writer.py`** — `PipelineArtifactWriter` hardcoded `output_dir="generated_tests"`, silently bypassing AI-029 workspace isolation for the UI path (named workspaces still wrote to the repo root). Now storage-aware via `get_storage().generated_tests_dir()`; default-workspace behavior identical (verified: full suite green).

**Grilled decisions (all closed, folded into the spec):** referee-by-default CI (no self-healing — false-negative risk; learning opt-in `learn: true`), verified adaptation offered post-failure (`/adapt` command + tool link, never default; locator-only + assertion-verified), `.ai-test-ignore.yml`, danger-zone Option C, two-stage Action repo (in-repo now → thin public repo + PyPI at launch), trigger scope (`workflow_dispatch`+`push`; fork PRs unsupported), flaky from cached per-branch history, GitLab parity in 7c (same milestone, platform adapters).

**Also deferred this session:** AI-044 (Visual Grounding) — off-the-shelf GUI-grounding models (UGround/OS-Atlas/UI-TARS) cover the core task; AI-041 (training) failed; slim AI-044-B option documented. Cross-referenced in AI-039's launch batch.

**7a tail shipped 2026-08-14 (Docker action + self-test; verified locally 9/9 gates):**
- `action/` — Docker action: `action.yml` (inputs: mode/story/tests/url/workspace/pom/provider/model/llm-base-url/llm-api-key/credential-profile/ignore-file/danger-zone/allowed-domains/pytest-args + internal `self-test`), `Dockerfile` (uv-built 3.14 venv on python:3.14-slim — NOT the playwright/python image, whose python 3.10 can't run the repo's PEP-758 syntax; Chromium installed from the venv's own playwright so browser version matches uv.lock), `entrypoint.sh` (thin orchestrator: generate-only + run-existing; `generate-and-run` fails fast — 7b), `report.py` + `export_evidence_junit.py` (platform-neutral cores: JUnit → counts + repair-candidate marking [7a: marking only, no adaptation]; AI-028 evidence → enriched JUnit).
- `scripts/ci_generate.py` gained `--storage-root` (action passes $GITHUB_WORKSPACE so artifacts persist to the runner mount) + 2 unit tests.
- `.github/workflows/ci-cd-action.yml` — hermetic self-test (mock site + fake LLM inside the container): generate-only (exit code + driver JSON contract + package artifact) then run-existing (pytest junit + AI-028 evidence junit + report payload shape, asserted via stub steps; no real PR).
- `scripts/ci_action_selftest.py` — the same 9-gate self-test locally via Docker (`docker build -f Dockerfile.action .` + two container runs with GitHub's INPUT_*/GITHUB_WORKSPACE env surface). Verified on this machine: generate-only → 8 tests (137s), run-existing → 8 tests (6 passed/2 skipped), junit + evidence junit well-formed, report shape OK. 16 new unit tests (storage-root x2, report x11, evidence-junit x3); full suite 2526 passed / 1 skipped, smoke 38/38, ruff + mypy clean, eval static 97.9%.
- `.dockerignore` hardened (was shipping 7.3 GB of historical output to the build context → now ~20 MB) — also speeds up the product image build. Latent product-image issues recorded below.
- **Latent issue noted (product `Dockerfile`): ✅ FIXED 2026-08-15** — the product `Dockerfile` adopted the action image's three fixes (two-stage `uv sync` [empty-project-wheel flaw], `UV_INSTALL_DIR`/`UV_PYTHON_PREFERENCE` [cargo path + managed-CPython symlink], `python:3.14-slim` runtime + browsers from the venv's own playwright [3.10 vs PEP-758 mismatch]). Verified: clean build, in-image imports OK on 3.14.7, chromium present, Streamlit container boots. See CHANGELOG [Unreleased] Fixed.

**Remaining:** none — **`learn: true` shipped 2026-08-15 (7d tail)** — flow-memory learning in CI (see the 7d BACKLOG entry). **Real GitLab.com gate: ✅ passed 2026-08-15** — `scripts/ci_gitlab_real_project_test.py` against `cat-tan-operations/ai-testgen-selftest` (14/14 live checks: push pipeline + junit 8/8 + cache miss, MR §6 note posted + edited-not-duplicated, cache hit on re-run; account needed GitLab identity verification first).

**7d tail shipped 2026-08-15 (`learn: true` — flow-memory learning in CI; verified locally 50/50 gates):**
- **`learn: true` implemented** — replaces the 7b fail-fast with the settled design (no re-grill): on a green generate-and-run with `learn: true`, the action exports `RAG_ENABLED=0` (flow memory ONLY in CI — the RAG leg's ~80 MB embedder download per runner; documented in `docs/ci.md` §8b) + `AITEST_STORAGE_ROOT`/`AITEST_WORKSPACE` (the conftest's lazy storage singleton points at the runner-mount workspace, so the store lands where the caller's `actions/cache` persists it). The generated package's conftest teardown learns within-test flows (free — the action already runs it); the entrypoint reports the learned counts (`flow_store`/`flow_patterns`/`flow_sites` outputs + a `learning:` log line) on green runs. Saturation is expected and documented (first green run learns most patterns; later runs dedup + reinforce hit counts — value = consistency + first-run seeding for NEW stories on the same site). Suite chains (UI/CLI post-run hook) deliberately NOT learned.
- **`src/storage.py`** — `get_storage()`'s lazy default now honours `AITEST_STORAGE_ROOT`/`AITEST_WORKSPACE` env overrides (backwards compatible: unset = repo-root discovery + default workspace; the UI/CLI call `init_storage` explicitly and are unaffected). This is the seam that makes the conftest's `FlowMemoryStore()` write to the runner mount.
- **`generated_tests/conftest.py`** — the RAG-learning leg is now gated on `RAG_ENABLED != "0"` (so CI never pulls the embedder); the flow-memory leg stays always-on for passing steps (the leg `learn: true` persists). Bug found in this session: an early edit accidentally nested the flow leg inside the RAG gate (RAG_ENABLED=0 killed both) — caught by the selftest learn gates, fixed, re-verified.
- **`action/flow_memory_stats.py`** (new) — platform-neutral store-stats helper (missing/corrupt store = zeros + exit 0; the entrypoint's learned-count reporting). +7 unit tests.
- **Cache** — `.github/workflows/ci-cd-action.yml`: branch-scoped `actions/cache` key `ai-testgen-flowmem-${{ github.ref }}` (restore/save) + a `learn: true` self-test step (single `-k` test; stub asserts store file + outputs + no `rag_store.db`). `ci/gitlab-ci.template.yml`: `AITEST_LEARN` var + `INPUT_LEARN` mapping + `ai-test-workspace/evidence/flow_memory.json` in the branch-scoped cache `paths`.
- **`action.yml`** — the `learn` input description updated (was "NOT IMPLEMENTED").
- **Selftest 39 → 50 gates** — `scripts/ci_action_selftest.py` learn gates: **seed** (green run persists the store; `flow_patterns`/`flow_sites` ≥ 1; RAG leg off — no `rag_store.db` on the mount; comment still one idempotent edit) + **restore** (a pre-seeded marker pattern survives a re-run AND `flow_patterns` = 2 = marker + newly-learned — merge, not overwrite; the branch-cache contract).
- Gates: local selftest **50/50**, full suite **2597 passed / 1 skipped**, ruff + mypy clean, YAML parses (action.yml / ci-cd-action.yml / gitlab template).

**7b shipped 2026-08-15 (generate-and-run; verified locally 28/28 gates):**
- `generate-and-run` mode in `action/entrypoint.sh` — the full spec §5.4 pipeline: generate (or restore from cache) → pytest (referee exit) → AI-028 evidence JUnit → report + **flaky markers (AI-011 from the action's own cached per-branch run history)** → §6 PR comment payload (+ idempotent posting via the GitHub adapter when a token/PR context exists). `adapt: true` repo-level opt-in runs the verified adaptation engine and applies the referee-exit override (all failures adapted + re-run green → exit 0). `learn: true` fails fast with a clear message (never a silent no-op).
- **Cache (spec §7)** — `action/cache_key.py`: the single source of truth for key = `sha256(story + url + model + provider + PROMPT_FINGERPRINT)` (pure stdlib, shared by the workflow's `actions/cache` steps and the action's internal cache-dir check — they can't drift). The action emits `cache_key`/`cache_hit` outputs, seeds `<cache-dir>/packages/<key>/` on miss, reuses on hit (no regeneration); `cache: false` forces fresh generation. Workflow: run-specific package key (deterministic miss for the self-test) + branch-scoped run-history key.
- **PR comment (spec §6)** — `ci/platform/github.py`: the GitHub surface behind the §5.5 seam (find-by-marker → edit-not-duplicate create, reply posting; stdlib urllib; injectable base URL for hermetic tests). `action/report.py` gained the §6 context fields (**Site**/Model lines) + the flaky block; the entrypoint always writes `comment.md` and posts only when `repo`+`pr-number`+`github-token` inputs are present (local runs / stub steps assert the payload).
- **Verified adaptation engine (spec §8/7b + §9.6)** — `action/adapt.py`: parses LocatorNotFound-class failures (both Playwright `locator('…')` and evidence_tracker `Locator '…' not found` shapes) → locates the source step → re-resolves the step's semantic label with the product's OWN machinery (`PageScraper` + `PlaceholderResolver`, no LLM) → patches → re-runs ONLY that test → keeps only if the test's assertions still pass, reverts otherwise → `adaptation.json` (every attempt recorded; CI never mutates silently). Assertion failures never reach the engine.
- **Slash-command loop (spec §6)** — `scripts/ci_slash_commands.py` (platform-neutral parse + reply rendering: `/adapt <test>` reply from the adaptation report; `/ignore <test>` reply renders the exact `.ai-test-ignore.yml` entry with the required reason) + internal `slash-command` mode in the entrypoint + `.github/workflows/ci-slash-commands.yml` (`issue_comment` trigger, `pull-requests: write`, fork-PR guard, branch-cache restore via `restore-keys`).
- **Self-test extended** — `.github/workflows/ci-cd-action.yml`: cache-key step + `actions/cache` restore/save (package + run-history) + generate-and-run phase (stub asserts: cache miss + seeding + §6 comment shape + flaky key) + sabotage→`/adapt` phase (stub asserts kept≥1, reverted=0, source fixed) + `/ignore` phase (stub asserts the YAML reply). `scripts/ci_action_selftest.py`: 28 gates locally incl. a host-side **mock GitHub API** (container posts comments via `host.docker.internal` — real POST/PATCH traffic verified: 1 comment, edited not duplicated on cache hit, adapt reply, ignore reply = 3 total).
- **Tests:** +45 (cache-key 5, flaky-history 5, slash-commands 10, GitHub adapter 7, adaptation engine 13, report flaky/context 5). Full suite **2571 passed / 1 skipped**, smoke 38/38, ruff + mypy clean. The four 7a GitHub gotchas were not re-derived (action.yml at root, Dockerfile build context, hyphenated INPUT_* env vars, workspace dir name).

---

## ✅ Learning-loop E2E test (AI-042 learning loop, end-to-end)

**Status:** ✅ Complete 2026-08-13 — `tests/integration/test_learning_loop_e2e.py`, 4/4 tests green, full suite 2482 passed / 1 skipped, ruff + mypy clean
**Priority:** Medium — proves the feature loop the product is built on
**Actual sessions:** 1 (estimated 0.5-1)

**Shipped:** one integration test that runs a tiny generated pytest package (the REAL
`generated_tests/conftest.py`) against a local mock site and asserts the full
learning loop end-to-end:

1. **Mock site is brought up as part of the automation** — module-scoped
   `MockServer` (port 8784, `mock_sites/ecommerce`) with a fail-fast urllib probe;
   a dedicated test asserts all journey pages serve 200.
2. tests pass → conftest teardown learns within-test flows (verified: 4/4
   passed, one sidecar per test, all `passed`)
3. the package post-run hook (`PipelineRunService` / verify_production) chains
   suite flows (verified: 3 suite chains)
4. `evidence/flow_memory.json` gains the patterns (verified: exactly 7 designed
   patterns, site-scoped to `localhost:8784`, dedup + hit bumps on re-run —
   7 patterns / hit_count 2 after run 2)
5. a follow-up resolution (orchestrator GOTO/URL step 2.5) resolves using the
   learned flows (verified: "view cart" from products → cart URL)

Hermeticity: real `evidence/flow_memory.json` snapshotted/wiped/restored;
`generated_tests/evidence/` (past sidecars from other ports) parked/restored;
RAG-learning leg neutralised via a package-local conftest (sibling loop — avoids
real `rag_store.db` writes + ~80 MB embedder download on fresh CI). Marked
`slow` + `integration` + `subprocess` — excluded from the default suite.

**Open item: ✅ FIXED 2026-08-16** — `PipelineRunService.run_saved_test` now
resolves the suite-chain evidence dir explicitly (`saved if saved.is_dir() else
saved.parent`) instead of always using `Path(saved_path).parent`, so a
directory target points at the package's own `evidence/` (a test file still
resolves to its containing package). The learning-loop E2E's workaround is
removed — it no longer parks `generated_tests/evidence/` nor calls
`learn_suite_flows` manually (the fixed hook chains the right dir; the manual
call was doubling hit counts). +2 unit tests; E2E 4/4.

---

## ✅ Shipped 2026-08-06 — Run & Fix restructure, report fixes, self-heal fixes, evidence improvements

**Session highlights** — the app went from 2 pages to a 3-page workflow (Test Generator / Run & Fix / Evidence & Reports), and a cluster of run-results, report, and self-healing bugs were fixed. Full suite 2288 passed; ruff + mypy clean; eval static 95.2%.

**Page restructure:**
- **Run & Fix page** — results/repair/evidence/export moved out of Test Generator; empty-state with handoff; sidebar-loaded packages surface immediately (hydration).
- **Export panel** moved to Run & Fix; `build_report_bundle` now dir-aware (`saved_path` may be a package directory — reports were landing in `generated_tests/`).
- **Last-package auto-restore** (`SETTING_LAST_PACKAGE`) — the loaded suite survives page reloads / session resets instead of blanking to "No current suite loaded".
- **Package dropdown labels** — readable date/site/story instead of raw `test_YYYYMMDD_<slug>` names.

**Run results / reports:**
- **B-044 (reload-safe RunResult)** — Streamlit's module watcher reloads `src` modules mid-session, creating a new `RunResult` class; stored instances then failed `isinstance` and the results/evidence silently vanished ("results disappeared" bugs). New `is_run_result()` duck-type check (`TypeGuard`) replaces all 12 `isinstance` gates.
- **Real per-test durations in reports** — sidecars now write `duration_s` (was hardcoded 0.00).
- **Report titles** — "6. 6. [T06]" double-index removed (criterion enumeration stripped; report formats add their own index).
- **HTML report embeds failed-step screenshots** (base64) — passing galleries stay on the Evidence page (full-page PNGs ~3.4MB each would bloat the report).
- **Re-run Failed merge** — `merge_rerun_results()` keeps passing tests in the table; a failed-only rerun no longer drops them.

**Evidence:**
- **Click-success screenshots** — every passing click step now captures evidence (was failures-only); verified T07 evidence 4/9 → 9/9 steps.
- **Evidence UI** — screenshots render inline per step (📸 marker + image), not an unlabeled strip.
- **Image-wait before screenshots** — product grids no longer captured mid-load (blank images read as spurious defects); verified stddev 10.9 → 31.0 on the dress-category shot.
- **This-run evidence gating** — stale sidecars from previous sessions no longer show as "this run" (gated on a real session run).

**Self-healing:**
- **Timeout 300s → 600s** (`PIPELINE_TEST_TIMEOUT`) — suites longer than 300s silently timed out and reported "0 failures / nothing to heal" while real failures sat in the table.
- **Package-directory resolution** — `heal()` crashed (`PermissionError`) when `saved_path` is a package directory; resolves to the test file.
- **Empty-results ≠ all-pass** — a no-results run surfaces `run_error` instead of "✅ All tests pass".
- **LLM-unavailability surfaced** — if the LLM reviewer fails (provider not configured), the report names the tests instead of silently marking unfixable.

**Pipeline / generation:**
- **POM dedup** — `deduplicate_pom_lines()` in `pom_helpers.py` (wired into the orchestrator) removes the LLM skeleton's duplicated POM imports/instantiations (was `home_page` ×3 per test).
- **Living Test Plan UX** — `Reviewed` moved far from the headerless delete checkboxes, delete-row caption added, flagged-condition warning + tooltip.
- **`SETTING_MODEL_NAME`** wired into `streamlit_app.py` (persistence existed via literal key; constant now used).

**Open bugs added:** B-042 (locator-repair patch dedents to module scope — collection crash) and B-043 (dropdown run counts report 0 despite real history) — both still open.

---

## ✅ Shipped 2026-08-03 — Export gate: exports are now runnable + validated (B-031, B-032)

**Session doc:** `docs/sessions/2026-08-03_export_gate_and_broken_exports.md`

**What shipped** — exports went from 34/35 stubs + 1 non-importable to a gated, verified artifact:
- **B-031 fixed**: POM glob `po_*.py` → `*.py` (generated pages are `home_page.py`/`cart_page.py`); true POM-mode export (`preserve_pom_calls=True`); `@pytest.mark.evidence(...)` decorators stripped in all forms; B-020 assert family (`assert_hidden` etc.) converted in tests + POMs; stub guard raises on all-stub/all-skip/no-test sources; same-second export collision guard.
- **B-032 fixed**: export copies `run_results.sqlite` (was the never-created `playwright_tests.db`), legacy fallback; `_count_run_results` fixed too.
- **`scripts/export_gate.py`**: 9-gate end-to-end export validation against a deterministic golden localhost fixture (`fixtures/golden_package/` + `fixtures/golden_site/`): stub guard → export flat+POM → flat/POM artifact checks → run-history DB copy → collect → both suites execute and pass. Golden 9/9 PASS; real 20260803 package 8/8 PASS (26 tests collect clean).

**Verification:** full suite 2122 passed / 1 skipped (+20 tests); ruff + format + mypy clean; smoke 35/35; export gate 9/9 (golden) + 8/8 (real package).

---

## ✅ Shipped 2026-08-03 — Saucedemo checkout cluster (13/13 gates PASS)

**Session doc:** `docs/sessions/2026-08-03_saucedemo_checkout_cluster.md`

**What shipped** — saucedemo `verify_production` went 10/13 → **13/13 gates, 6/6 tests, stable**; automationexercise 3/7 (HEAD) → 4–5/7:
- **Soft-404 SPA recovery** (`src/scraper.py`): saucedemo (SPA-on-GitHub-Pages) serves every `.html` path as HTTP 404 + app shell; the stateless scraper bailed on `status >= 400`. Now renders first and judges content via a URL-rewrite signal (`_is_soft_404`).
- **Credentials reach the pipeline** (`scripts/verify_production.py`): saucedemo demo credentials (env-overridable, mirroring eval) passed to `TestOrchestrator` — without a session the stateful scrape captured the login wall, so the cart had no items and checkout wasn't an option.
- **Site-agnostic stateful routing** (`src/url_utils.py`): `is_stateful_cart_checkout_path()` replaces the automationexercise-hardcoded `{/view_cart, /checkout}` set; covers `/cart.html`, `/checkout-step-one.html`…
- **URL candidates re-enabled** (`build_common_path_candidates`): concept-driven, same-domain candidates from the shared route vocabulary — SPA sites have no hrefs for journey discovery, so cart/checkout URLs never existed.
- **Journey subprocess credential round-trip** (`src/journey_subprocess.py`): the payload serialized `credential_profile` but the child never read it back; plus `JourneyScraper` logs in at the starting URL when a profile is present.
- **B-015 ghost exorcised (3 places)**: `_dismiss_modals` / `_dismiss_confirmation_modals` / setup script clicked `button:has-text("Continue Shopping")` globally — saucedemo's cart-page button navigated journeys *and tests* back to inventory. Dismissal is now scoped to modal containers; the tracker no-ops modal-close clicks when the modal is already gone.
- **Dead/redirected page filters**: `_drop_dead_pages` (<3-element SPA shells) + `_drop_redirect_duplicates` (200-redirect-to-home keys, e.g. automationexercise `/inventory.html`) — these polluted keyword/ASSERT resolution.
- **B-024 class fields**: `normalise_element_text` includes placeholder (saucedemo checkout `#last-name` etc.); B-024g separator-normalized word-subset matching ("zip code" → "Zip/Postal Code").
- **Navigation-intent fallback**: SPA cart/basket icons have no accessible name — failing cart-navigation descriptions resolve as GOTO to the verified page URL, keeping page context advancing through cart → checkout.
- **Post-login ASSERT mapping**: "logged in" resolves to inventory/products, not the login page.

**Verification:** full suite 2095 passed / 1 skipped; ruff + mypy clean; smoke 35/35; eval static 100%; `verify_production saucedemo` 13/13 (4 consecutive runs), automationexercise 12/13 (improved from HEAD 12/13 with 3/7 execution).

**Open items (documented in session doc):** automationexercise guest-checkout login gate (story lacks login; the site requires auth to checkout); automationexercise cart-link/assert timing races; `scripts/3d/map` + pre-existing archived debug scripts lack markdown_docs; Windows backslash bug in `ui_run_results` setup-script print line (pre-existing).

---

## ✅ Shipped 2026-08-02 — CLI walkthrough driver + zero-pass pipeline fixes

**Session doc:** `docs/sessions/2026-08-02_cli_walkthrough_and_zero_pass_pipeline_fixes.md`

**What shipped:**
- **CLI walkthrough driver** (`scripts/cli_walkthrough.py`, new) — marker-driven subprocess driver; NAV pass 41/41, FULL pass 59/59 (real LLM + live automationexercise.com). Documents Windows pipe gotchas (read1 vs read, one-write-per-input, no-blank-lines paste).
- **CLI crash fixed — "Load Existing Generated Tests"** (`PermissionError`): `load_package_manifest()` called with a package dir instead of the manifest file; now directory-aware + both CLI callers pass `reconstruct=True`. 4 regression tests.
- **CLI POM/Consent invisible feedback**: State block shows `Consent`/`POM Mode`; toggle handlers pause with confirmation (also fixes stray-Enter msvcrt re-select bug).
- **POM mode discarded resolved selectors** → tests skipped at runtime (`home_page.click('product name link')` instead of the resolved `a[href="/product_details/1"]`). Now emits `click(label, selector=...)`; generated POMs use it directly; generic `fill()` added. `src/pom_helpers.py`, `src/page_object_builder.py`.
- **Consent-overlay pollution**: 1,448/2,328 scraped elements were OneTrust `.fc-*` markup (hidden in DOM); consent removal only matched ID-based selectors. Added class-based selectors to `src/scraper.py` — POMs 1806 → ~520 lines.
- **URL trailing-slash mismatch** in assertions/navigation (`normalize_url()` in `src/url_resolver.py`, applied at all emission points in `src/placeholder_orchestrator.py`).
- **FILL resolved to container div** (saucedemo `[data-test="login-container"]` accessible_name collision) — fillability gate added to `pass1_text_match`.
- **Evidence-tracker hang**: `_record_step` re-captured metadata for a locator that no longer exists after a click navigated — each un-timed Playwright call waited 30s (×4 ≈ 120s/test). `_record_step` now accepts pre-captured `element_metadata=`; suites complete in ~140-175s (were 600s timeouts).
- **verify_production timeout message bug**: printed literal `{max(60, min(180, len(test_funcs) * 25))}s`; now real value + salvages partial pytest output/evidence count on timeout. Suite cap raised to `min(300, tests*30)`.

**Verification:** full suite 2042 passed / 1 skipped; ruff + mypy clean; eval static 100%; `verify_production` 20/26 → 22/26 gates. Verdict still FAIL — remaining failures are the **semantic layer** (see session doc §Open work: dialog-role scoping, assertion-state polarity, heading-role asserts, upstream skeleton phrasing, LLM re-ranking with T-strings + bounded retries; **do not add site-specific lists** — match playwright.dev's ARIA-role vocabulary).

---

## ✅ Shipped 2026-08-02 (continued) — Semantic layer (page-load, dialog scoping, polarity) + CLI quality + eval harness gap

**Session doc:** `docs/sessions/2026-08-02_semantic_layer_and_cli_quality.md`

**What shipped:**
- **Page-load assertions resolve correctly**: "title" no longer vetoes page-state routing (`<page> page title` → `to_have_url`, matching the golden encoding); `resolve_url` root-path substring bug fixed (multi-word descriptions no longer resolve to the home URL); golden validator compares `to_have_url` trailing-slash-insensitively; skeleton prompts steer load-style conditions to `{{ASSERT:<page> loaded}}`. Production: `test_01_home_page_loads` → `to_have_url("https://automationexercise.com/")`.
- **Dialog-action scoping (Pass D)**: `{{CLICK:OK}}` no longer resolves to a hidden CSRF input ("ok" substring inside "csrfmiddleware**TOKen**" short-circuited the fast path at a flat 100). CLICK fast-path + pass-2 hygiene (hidden penalties, ≥3-char substring), plus a structural Pass D: dialog-intent descriptions resolve against in-modal interactive elements, preferring close-modal controls. Production: `click('OK button', selector='button.btn.close-modal')`; automationexercise execution 2/7 → 5/7.
- **Assertion-state polarity**: "popup closed"/"item removed" now emit `assert_hidden(...)` (`wait_for(state="hidden")`) instead of `assert_visible`. `polarity_assertion_type()` hooked at both resolution paths. Production: `assert_visible(...confirmation popup)` → `click('OK', selector='button.btn.close-modal')` → `assert_hidden('p.text-center', label='popup closed')`.
- **CLI fixes (found by running the real CLI — `scripts/cli_walkthrough.py --pass full` — not by unit tests)**: table truncation (Living Test Plan / Test Table wrap to terminal width), `[llm_client]`/`[pipeline]` debug moved to stderr (was interleaving with menus under `PIPELINE_DEBUG=1`), export `story_slug` AttributeError (Session property), export "Tests: 0" (file→dir path normalization), flat export POM→Playwright conversion + idempotent `expect` import (exported tests now runnable).
- **CLI walkthrough hardened**: new `reject:` capability (export step now FAILS if "Export failed" appears — previously passed while erroring because it only checked the "Press Enter" marker); heal-flow markers updated for the "2 test(s) still failing. → Choice:" outcome.
- **Eval harness gap closed**: `--mode full --regenerate` persisted no test files, so "Tests executed: 0" was reported every run. `EvalRunner._persist_regenerated_tests()` writes `generated_tests/test_<site>.py`; full run now executes **33 tests, 17 passed (51.5%)**.

**Verification:** 2081 passed / 1 skipped; ruff check + format clean; mypy `src/ cli/` clean; smoke 35/35; eval static 100% all sites; full-regenerate resolution 65.7-67.2% (best in DB history); CLI walkthrough NAV 41/41 + FULL 60/60; verify_production 22/26 (semantic ceiling unchanged).

**Note:** `src/llm_client.py` is a protected file — changed only for a 3-line stderr-routing fix (CLI log interleaving), flagged per AGENTS.md.

---

## ✅ AI-032 — Semantic Scraper Transition (COMPLETE)

**Status:** ✅ Complete  
**Branch:** `feat/semantic-scraper` (merged)  
**Spec:** `docs/specs/FEATURE_SPEC_semantic_scraper.md`

**What:** Three-layer hybrid extraction — BS4 (structure) + CDP AX tree (accessible_name) + `page.aria_snapshot(boxes=True)` (placeholder, value, bbox, groups). Enabled by default; `SCRAPER_BACKEND=bs4` for old behavior.

**Delivered:**
- ✅ **Phase 1** — `src/aria_parser.py` (328 lines, 33 tests)
- ✅ **Phase 2** — Hybrid extraction wired into `PageScraper._scrape_url_sync_result()`
- ✅ **Phase 3** — Resolver alignment (B-024/B-025/B-026 scorers, eval = 52.2%, no regression)
- ⚠️ **Phase 4 cleanup DEFERRED** — Hybrid architecture kept intentionally (each layer provides unique data: ARIA misses hidden elements, BS4 lacks semantic names)

**Results:**
- ✅ Resolver accuracy: **46.3% → 55.2%** (+8.9pp, RAG off)
- ✅ Resolver accuracy: **53.7% → 64.2%** (+10.5pp, RAG on)
- ✅ lv_insurance eval-005: **54.2% → 79.2%** (+25.0pp)
- ✅ Static eval harness: **79.1% → 88.1%** (+9.0pp vs baseline)
- ✅ Ruff clean, mypy clean, 125+ tests pass

**Actual sessions:** 3 (estimated 2-3)

---

## ✅ B-024 — `<select>` elements use placeholder text instead of label for accessible_name (✅ FIXED 2026-07-23)
**Related:** B-016 (synonym-aware matching), eval harness resolver accuracy
**Impact:** 3/67 placeholders fail (4.5pp) — `scheme`, `occupation`, `overnightLocation` on LV Insurance
**Eval context:** `eval-005_lv_insurance_quote.json` resolver mode

**Symptom:** `<select>` elements are scraped with `accessible_name: "Select..."` (the default
`<option value="">Select...</option>` placeholder) instead of the actual label text
(e.g., "Scheme", "Occupation", "Parking Location"). The resolver's Pass 1 text match
cannot find "scheme" or "occupation" in any element text, so these placeholders return
`None` and the generated test emits `pytest.skip()`.

**Root cause:** The scraper's `_extract_elements_from_html()` or CDP AX tree enrichment
reads the `<select>`'s accessible name from the first `<option>` (default placeholder)
rather than from the associated `<label for="...">` or the `<select>`'s `aria-label`
attribute. This is a standard ARIA pattern — the label wraps or references the select,
but the placeholder option is the visible text.

**Proposed fix:**
1. In `src/scraper.py` or `src/accessibility_enricher.py`: when extracting `<select>`
   elements, prefer the `<label for="...">` text or `aria-label` over the first
   `<option>` text for `accessible_name`.
2. Fallback: if no label exists, use the `<select>`'s `id` as the accessible name
   (e.g., `scheme` → "scheme").
3. Update eval harness golden keys to verify the fix.

**Expected improvement:** +4.5pp resolver accuracy on LV Insurance (from 54.2% → 58.7%)

**Estimated sessions:** 0.5

---

## ✅ B-025 — Parent div click targets lose to child heading elements in scoring (FIXED)

**Status:** ✅ Fixed (shipped as part of AI-032 Phases 2-3)
**Related:** B-014 (ASSERT scoring), B-016 (role filtering), AI-024 (a11y enrichment)
**Impact:** 9/67 placeholders fail across LV Insurance and saucedemo (13.4pp)
**Eval context:** `eval-005` (6 failures), `eval-001` (2 failures)

**Symptom:** When a clickable `<div>` (e.g., `#productCar`, `#paymentFull`, `#quoteSuccess`)
contains a child heading (`<h4>`, `<h2>`, `<h1>`) with the same text, the child heading
wins the resolver's Pass 3 scoring because it has exact text match in `accessible_name`.
The parent div (the actual click target) loses because it has no text of its own — the
text lives in the child.

**Fix shipped:**
1. **Heading penalty in `_click_role_bonus()`** — `src/placeholder_scorers.py`:
   - Heading without ID: -20 penalty (likely child of clickable parent)
   - Heading with ID: -8 penalty (unusual, but still penalised)
   - Container roles (generic, group, region, article) with ID: +10 bonus
2. **Pass1 heading skip in `element_matcher.py`** — Headings are skipped for CLICK
actions (headings are display elements, not click targets)

**Verification:**
- ✅ Code shipped: `_click_role_bonus()` lines 355-381
- ✅ CHANGELOG updated as part of AI-032
- ✅ Part of eval accuracy improvement from 46.3% → 55.2% (RAG off)
- ✅ No regressions checked via eval harness

**Actual sessions:** 0 (shipped as part of AI-032)

---

## ✅ B-026 — Resolver locator format mismatch — correct element, wrong selector syntax (FIXED)

**Status:** ✅ Fixed (shipped as part of AI-032 Phase 3)
**Impact:** 2/67 placeholders fail (3.0pp) — golden key comparison is too strict
**Eval context:** `eval-001` (saucedemo), `eval-002` (automationexercise)

**Symptom:** The resolver finds the correct DOM element but the locator string format
differs from the golden key's expected format, causing a comparison failure.

**Fix shipped:** Locator normalization in `scripts/eval/golden_validator.py`:
- `#foo` matches `[id="foo"]`
- `[data-test="bar"]` matches `.class[data-test="bar"]` (subset match)
- `input[name="x"]` matches `[name="x"]` (attribute-only vs tag+attribute)

**Estimated sessions:** 0 (shipped as part of AI-032)

---

## ✅ AI-031 — Eval Harness: Resolver Accuracy Improvement Sprint (PARTIALLY COMPLETE 2026-07-26)

**Status:** ✅ Resolver accuracy improved from 53.7% → 58.2% (+4.5pp, RAG off). LV Insurance 83.3% → 95.8% (+12.5pp).
**Related:** B-024, B-025, B-026 (all shipped as part of AI-032)

**Fixes shipped 2026-07-26:**
- `_build_haystack`: added `id`, `accessible_name` + camelCase splitting so element IDs contribute to matching
- `_structural_bonus`: fixed camelCase ordering, added single-word ID match bonus (+15), `ref`→`reference` expansion
- `_split_camel_case()`: splits `quoteRef`→"quote Ref", `usageType`→"usage Type"

**Actual sessions:** 0.5

---

## ✅ AI-030 — LV Insurance Mock Site & Ingestion Agent Foundation (COMPLETE 2026-07-26)

**Status:** ✅ Complete  
**Commit:** (pending ship-it)

**What:** Built a 7-step LV car insurance quote flow mock site (60KB HTML) and assembled real LV product documents for the Phase 1 Ingestion Agent. PDF parsing wired into `rag_ingest.py` via `src/pdf_ingest.py` (PyMuPDF-based: heading detection, table extraction, chunking).

**Delivered:**
- ✅ `generated_tests/mock_insurance_site.html` — full quote flow with reg lookup, driver management, premium calc, decline path
- ✅ `docs/rag_corpus/lv_docs/` — 7 docs (3 real LV PDFs + 3 redacted personal + 1 synthetic underwriting guide)
- ✅ `scripts/eval/dataset/eval-005_lv_insurance_quote.json` — 10 criteria, 33 golden placeholders
- ✅ `src/pdf_ingest.py` — PyMuPDF extraction pipeline (headings, tables, chunking)
- ✅ `rag_ingest.py --pdfs` — CLI flag ingests PDFs into vector store
- ✅ RAG store: 160 entries (67 golden + 27 Playwright docs + 66 PDF chunks from 3 LV policy PDFs)
- ✅ RAG accuracy: **53.7% → 64.2%** (+10.5pp), LV Insurance: **83.3% → 91.7%** (+8.4pp)

---

### ✅ CI-001 — Consolidate CI/CD Pipeline (2026-06-21)
**What:** Merged `ci.yml` and `project-health.yml` into a single gated pipeline.
**Changes:**
- Gate chain: sanitizer → ruff → mypy → pytest (fail fast, no wasted minutes)
- Added `concurrency` block to auto-cancel stale runs on same branch
- Added `setup-uv` caching (`enable-cache: true`) — caches `.venv` between runs
- Added Playwright browser cache via `actions/cache` keyed on `uv.lock` hash
- Added `--frozen` to all `uv sync` calls — fails if lockfile is stale
- Added failure artifact upload (`test-results/`, `screenshots/`) with 7-day retention
- Deleted `project-health.yml`

### ✅ CI-002 — Fix project_sanitizer bugs (2026-06-21)
- Fixed `PROJECT_ROOT` resolution (`.parent.parent` → `.parent.parent.parent`)
- Added `exported_tests/` to `SKIP_DIRS`
- Orphan `.md` files are warning-only (exit 0), not CI-breaking
- Deleted junk `scripts/debug/cli_test_capture.log`

---

## ✅ Shipped (doc audit 2026-05-17)

| ID | Status | Notes |
|----|--------|-------|
| AI-016–AI-022 | **Complete** | Evidence chain: tracker, spec analysis, test plan UI, annotated screenshots, Gantt, coverage + suite heatmaps |
| AI-024 | **Complete** | `AccessibilityEnricher` + CDP `getFullAXTree` in PageScraper (not `page.accessibility.snapshot()`) |
| B-0XX | **Complete** | Journey + stateful scrapers use same visibility + a11y enrichment as PageScraper |
| Prerequisite injection (Stage A) | **Complete** | `PrerequisiteInjector` in orchestrator |
| Keyword URL resolution | **Complete** | `UrlResolver` for GOTO; Phase 3 page scoping wired 2026-05-17 |
| Resolver restructure Phase 0–1 | **Complete** | Dead methods removed from `placeholder_resolver.py` |
| Resolver restructure Phase 2 | **Partial** | Pass 1 (CLICK/FILL + ASSERT text), Pass 2 structural, Pass 3 scoring+LLM; pass logging added |
| AI-019 | **Superseded** | Skeleton uses placeholders; `code_postprocessor` injects `evidence_tracker` — no LLM evidence rules needed |
| Phase 4 Export (core) | **Complete** | `ExportMode` enum, `ExportService.export()`, `strip_evidence_from_test_code()`, `strip_evidence_from_pom()`. 28 tests. Streamlit panel + CLI menu shipped (2026-08-03 export gate session — B-031/B-032, `scripts/export_gate.py` 9/9 gates). |

**Still open (high level):** (none at this time)

---

## ✅ AI-027 — Visual Element Enrichment (COMPLETE — All 4 Sessions Done)

**What:** Vision-based element enrichment for improved placeholder resolution on multi-product sites.
**Session 1 complete:** `VisionEnricher` + vision capability detection.
**Session 2 complete:** Screenshot capture during scraping, with interactive element bounding boxes stored in memory.
**Session 3 complete:** Vision enrichment service with element crop, mocked LLM call path, response parsing, and scraper enrichment bridge.
**Session 4 complete:** Vision enrichment wired into orchestrator pipeline + `_vision_enriched_bonus()` in PlaceholderScorer using `product_name`, `price`, `visual_label`, `enrichment_note`, `description` fields.
**Spec:** `docs/specs/FEATURE_SPEC_visual_element_enrichment.md`
**Priority:** High — placeholder resolution quality on multi-product sites

---

## ✅ Closed Bugs

### B-001 — LLM generates async standalone tests instead of pytest sync
**Fixed:** System prompt updated in `src/llm_client.py`.

### B-002 — LLM output occasionally has all imports on one line
**Fixed:** `normalise_code_newlines()` added to `src/file_utils.py`.

### B-003 — Generated tests not saved to `generated_tests/` automatically
**Fixed:** Phase A auto-save implemented.

### B-005 — `launch_ui.sh` starts mock server (not appropriate for general use)
**Fixed:** Mock server startup moved to `launch_dev.sh`.

### B-006 — Parser banner wrong when mix of pass/fail
**Fixed (Session 10):** Current parser implementation correctly uses last summary-line match.
Regression tests added: `test_b006_mixed_pass_fail_banner_correct`, `test_b006_all_fail_banner`.

### B-007 — Error panels duplicated in results view
**Fixed (Session 10):** Removed duplicate error rendering loop from `display_coverage()`. Errors
now render only in `display_run_button()`.

### B-009 — No ast.parse() validation before saving generated test files
**Fixed (Session 11):** `src/code_validator.py` created with `validate_python_syntax()`.
Integrated into `src/file_utils.py` `save_generated_test()` — raises `ValueError` before
writing if code fails syntax check.

### BREAK-1 — `src/pytest_output_parser.py` missing (CI BLOCKER)
**Fixed (Session 9):** `src/pytest_output_parser.py` committed.

### BREAK-2 — Session state wipe blanks run results panel
**Fixed (Session 9):** Reset lines removed from `display_run_button()`.

### B-008 — Run Status column shows ⏳ for all rows (never updates)
**Fixed (Session 13):** Coverage x Run Results now maps run outcomes through shared coverage utilities.

### B-010 — POM AttributeError: 'navigate' vs 'goto'
**Fixed (Session 16):** Standardized all POM-based navigation to `navigate()` in `PageObjectBuilder`. Added `__getattr__` safety net to generated POMs to `pytest.skip` missing methods instead of crashing.

### B-011 — LLM Placeholder Syntax Error
**Fixed (Session 15):** Improved `SkeletonValidator` to reject Python variable syntax in placeholders. Added `_replace_remaining_placeholders()` safety net to ensure final code is syntactically valid by skipping unresolved tokens.

---

## 🎯 Test Pack Restructure + Mock-Site Strategy (2026-08-03 CLI review)

**Status:** ✅ COMPLETE 2026-08-07 — all 5 work items shipped (mock catalog, test-pack split, gate_full, enshrined-bug rewrites)

**Work item 2 (test-pack split, 2026-08-07):** new `tests/contract/` (6 tests — mock artifact/schema/import/route/behaviour contracts against the banking+ecommerce mocks), `tests/adversarial/` (7 tests — 404-page pollution B-045, overlay injection B-029, broken-locator B-033, modal scoping B-015), `tests/resilience/` (6 tests — corrupt DB B-034, reload-safe RunResult B-044, sidecar-without-teardown B-035, concurrent opens, corrupt settings). Default pytest already routes to the offline layer via `-m "not slow and not integration"`; the new layers run in CI (Gate 3 `test` job). Also fixed the long-noted B-039 `MockServer._start()` `os.chdir` bug — the server now serves via the handler's `directory` kwarg and never mutates the caller's cwd (relative-path callers / second server starts no longer break).

**Work item 3 (gate_full.py, 2026-08-07):** `scripts/gate_full.py` — one-command chain smoke → unit pytest → eval-static → verify_production → export_gate, exit non-zero on first failure; `--offline` (gates 1-3, CI-able), `--skip N`, `--pytest-args`. Verified: offline mode 3/3 gates pass.

**Work item 5 (enshrined-bug rewrites, 2026-08-07):** audit confirmed both named examples were already rewritten as their fixes landed — B-033 (`screenshot is None` → asserts `is not None` + `failure_note`) and B-029 (asserts post-click navigation verification + failure amendment, `test_b029_*` ×3); grep for `screenshot is None` across `tests/` is empty. No further rewrites needed.

**Why:** 2,095 green unit tests coexisted with 7 real bugs (B-029→B-035). The suite asserts internal invariants against MagicMocks; the product fails on external contracts (navigation happened?, evidence exists?, export runs?, DB survives?, overlays handled?). The layers that catch real bugs (eval harness, verify_production) are manual-only.

**Structural problems found:**
1. Unit pyramid on a mock foundation — 101 module files test "what the function returns", not "does the product work".
2. Bugs enshrined as contracts — `test_click_fast_fails_when_locator_missing_on_page` *asserts* `screenshot is None` (B-033 is tested behaviour).
3. ~~Network tests mislabeled~~ **REVISED 2026-08-03 (export gate session): the audit claim was verified FALSE.** `tests/integration/test_pom_mode_end_to_end.py` is pure offline string/JSON-schema checks (the automationexercise.com URLs live in a module-level sample constant, never executed); the genuinely network-touching tests (LLM pipeline runs in `test_pipeline_end_to_end.py`, real embedding-model downloads in `test_rag_store.py`) already carry `slow`+`integration` markers, and CI applies `-m "not slow and not integration"` via pytest.ini addopts. Corrective action shipped: `tests/test_no_live_network_in_default_suite.py` — a static guard that FAILS if any unmarked test executes a navigation call (goto/navigate/scrape_url/run_pipeline/attempt_login) with a live-site URL literal, so the "default suite is offline" property is durable.
4. ~~Real gates outside CI~~ **eval static wired into CI (2026-08-03, export gate session)**: new `eval-static` job runs `eval_harness.py run --mode static --min-accuracy 79` (offline, ~0.5s, exit 2 below floor) in parallel with lint/type-check. `verify_production` + `export_gate` remain manual gates (browser+network; the golden export gate is CI-ready once the mock layer exists).
5. No adversarial/resilience/contract layers.

**Mock-site strategy (investigated 2026-08-03):**
- ✅ Strong case to make the mock site the primary test target: deterministic, local, no Google consent/ad stack — closer to a real user's own site (nobody tests their own site against prod ad networks). The overlay race (B-029) can ONLY be tested deterministically with a mock that can inject an overlay on command.
- ⚠️ Current mock (`generated_tests/mock_insurance_site.html`) is too thin: single-page JS-step form, **0 modals, 0 nav links, 0 multi-page journeys**. Covers form-fill only; none of the navigation/modal/overlay classes that produced B-029/B-030.
- 🎯 Extend it: multi-page e-commerce mock (home → category → product → cart → checkout) + add-to-cart modal + **optional injectable consent/ad overlay** (query param / server toggle) so tests exercise clean path AND overlay race deterministically.
- Golden keys against the mock never decay (real-site keys decay — AGENTS.md warns). Mock + static eval could run in CI (localhost, no external network).

**Mock-site catalog — product-range research (2026-08-03, tavily + GitHub verified):**

| Product type | Reference repo(s) | Stack / setup | Exercises | Priority to build |
|---|---|---|---|---|
| E-commerce (multi-page) | automationexercise (live, already used); Potion Shop; Practice Software Testing | static / low | nav, add-to-cart modal, cart, checkout — **the B-029/B-030 class** | **1 — build first** |
| Banking / fintech | `cypress-io/cypress-realworld-app` (5.9k★, TS, active) | React+Express+SQLite / med | auth, transfers, payments, multi-user | 2 |
| Insurance (multi-step form) | ✅ **already have** (`mock_insurance_site.html`) | static / done | multi-step form, validation | done |
| Booking / travel | Restful-Booker (React+API); Sunny Meadows B&B | React+API / med | search, date pickers, booking lifecycle | 3 |
| Healthcare | Spring PetClinic (Java, heavy); lighter patient/appointment form | Java / high → prefer own static | forms, CRUD, appointments | 4 |
| Enterprise / HR | OrangeHRM (open-source demo) | PHP+MySQL / high → prefer own | org hierarchy, multi-role, admin | 5 |
| Element / widgets | The Internet (saucelabs/the-internet, static, GH-Pages); LetCode; DemoQA (have) | static / low | auth, alerts, frames, drag-drop, shadow DOM | 6 |
| Robustness / security | OWASP Juice Shop | Node+docker / med | auth, admin, search, tricky forms | 7 |

**Build rule:** for each row, make OUR OWN minimal self-contained version in a `mock_sites/` catalog (single-file HTML/JS or tiny server, same pattern as the insurance mock) — deterministic, localhost, versioned in-repo (never decays), each covering one distinct product shape. Each mock ships with a user story + golden-key eval dataset so the harness runs across ALL product types. Do NOT depend on third-party demo sites (they decay, go down, or are covered in ads).

**Proposed work items:**
1. Fix mislabels first: mark all network-touching tests `slow+integration` (default run becomes deterministic).
2. Split by intent: default `pytest` = mock layer; `-m integration` = network; add `tests/contract/`, `tests/adversarial/`, `tests/resilience/`.
3. `gate_full.py`: smoke → unit → eval-static (offline, CI-able) → verify_production → export gate. Wire `eval --mode static` into CI Gate 3 today (free offline regression protection).
4. Expand the mock site per above; move eval golden keys onto it.
5. Rewrite enshrined-bug tests (B-033/B-029 contract) as fixes land.

---

## 🔴 Open Bugs

### B-045 — Banking mock surfaces: 404-page pollution, ecommerce-only login/success transitions, role-worded nav fast-matches, fill-on-select
**Status:** ✅ Fixed (2026-08-07, banking mock session)
**Priority:** High — 5 site-agnostic pipeline gaps the banking mock made deterministic

The banking mock (priority 2 in the mock catalog, eval-007) surfaced a cluster of pipeline gaps that live sites only show as flaky noise:
1. **HTTP-404 pages survived `_drop_dead_pages`** — the stdlib server's 404 body scrapes to ~5 elements (above the 3-element threshold), so concept-candidate URLs (`/products`, `/cart.html`, `/checkout` — ecommerce vocabulary generated for any story mentioning payment/order) stayed in the scrape and their "Error code: 404" text won keyword/ASSERT matching. Fixed: `_is_error_page()` content-based drop (2+ markers) in `src/placeholder_orchestrator.py`.
2. **Login-transition vocabulary was ecommerce-only** — `_infer_click_transition_url` mapped a login click to `inventory`/`products`, so a banking journey never advanced past the sign-in page and every downstream placeholder stayed scoped to it. Fixed: site-agnostic landing vocabulary (`inventory/products/dashboard/accounts/home/overview`) in `src/url_inference.py`.
3. **No submit-success page transitions** — transfer/payment forms submit without hrefs, so the resolver stayed on the form page and success-message asserts resolved against the form's own elements (submit button / error paragraph). Fixed: `transfer`→`transfer_success`, `pay/payment/submit`→`payment_success` transitions. Also fixed a branch-order bug where "submit payment" hit the transfer branch first.
4. **Role-worded descriptions fast-matched nav links** — "pay bill button" matched the header nav link "Pay Bills" (earlier in DOM) in Pass 1/2 text matching before scoring could prefer the real `#pay-bill` submit button. Fixed: `_named_role_in_description()` gates Pass 1/2 to the named role; exact-text pre-sweep so "Pay Bills" (nav) vs "Pay Bill" (button) disambiguate by exact equality; submit-intent verb bonus + fillable-element CLICK penalty in `src/placeholder_scorers.py`.
5. **`fill()` on native `<select>` crashed at runtime** — Playwright rejects `.fill()` on `<select>` ("Element is not an <input>, <textarea> or [contenteditable]"); the LLM's fill value ("Electric Company") also rarely equals the option `value` ("electric"). Fixed: `EvidenceTracker.fill()` probes the tag and routes to `select_option()`, with exact-value → exact-label → substring-of-option-label fallbacks.

**Also fixed (golden validator):** `_normalize_locator()` now strips a leading tag from class selectors (`p.account_balance` ≡ `.account_balance`) — lifted eval-006 from 12/16 to 14/16 and eval-007 to 13/13 (100%).

**Verified:** eval static overall 95.2% → **97.9%**; eval-007 13/13 static + **8/8 execution** against the mock (login → dashboard → transfer → success → pay bill → payment success, session gate verified); full suite 2309 passed (1 environmental flake in test_llm_client under parallel workers — passes in isolation); ruff + mypy clean.

---

### B-042 — Locator-repair patch dedents the replacement line to module scope (collection crash)
**Status:** ✅ Fixed (2026-08-07, `0951ec0`, CI pending)
**Priority:** High — every "🔧 Fix Locator" patch can silently break the whole suite at COLLECTION time

`apply_patch` in `src/locator_repair.py` rebuilds the patched line from regex groups (`before_quote` + locator + `after_quote`) that **exclude the line's leading indentation**, then writes it back at column 0. When the patched line is inside a test function, the replacement lands at module scope → `NameError: name 'evidence_tracker' is not defined` → the module fails to import → 1 error, 0 tests. Reproduction (live, 2026-08-06): a Fix-Locator repair of T11 in `test_20260805_181339...` wrote `evidence_tracker.assert_visible(...)` dedented to column 0; pytest then collected 0/14 tests.

**Fix shipped:** the reconstruction now explicitly re-applies the original line's leading whitespace (`indent` + `before_quote.lstrip()`) in the regex path, so a patched line inside a function body can never land at module scope. Also hardened: an **empty `original_locator`** (previously matched *every* line in the search window, then `.replace("", …)` mangled the whole file) now raises `LocatorRepairError`. Regression tests: patch inside a function body (regex path + evidence-tracker fallback path) still compiles via `ast.parse`; empty-original raises.

---

### B-043 — Sidebar package dropdown reports 0 runs when real run history exists
**Status:** ✅ Fixed (2026-08-07, `0951ec0`, CI pending)
**Priority:** Medium — the dropdown's run count actively misleads

`find_existing_packages` refreshes `run_results_count`/`last_run_at` from `package_manifest.json`, but those fields count a different artifact than actual test runs: the dropdown showed `(1 test, 0 runs)` for a package whose real history (`run_result_persistence`) held **13 runs / 85 passed / 28 failed** (verified via the loaded-package sidebar summary). Manifest fields are only updated when a run persists results in the way the manifest expects; evidence-bearing runs (sidecars + screenshots) don't bump them.

**Fix shipped (option a):** `find_existing_packages`/`_reconstruct_manifest` now reconcile run fields through `_refresh_run_stats()`: workspace SQLite run-history DB first (`run_stats_by_package()` — one `GROUP BY test_package` pass, exposed via `run_result_persistence`; matches the package dir and any path beneath it, Windows-case-normalised) → legacy per-package JSON/SQLite counting → the manifest's own values (CLI bumps via `update_last_run_at`). Regression tests: DB-persisted runs appear in the dropdown count + last-run; test-file-path recording matches the package; manifest-only counts survive when the DB has no rows.

---

### B-039 — Self-healing blind to its own most common failure mode
**Status:** ✅ Fixed (2026-08-04, AI-035 write-back Tier-1 verification, CI green)
**Priority:** High — discovered while live-testing the AI-035 self-healing loop against the e-commerce mock; without this fix the loop can never fix anything.

Two compounding parser/classifier gaps made the self-healing loop pre-screen **every** real generated-test failure as unfixable (it only ever worked against synthetic error strings):

1. **`pytest_output_parser._FAILURE_NAME_RE` rejected `[chromium]`-suffixed failures-block headers** (`^_+ (\w+) _+` stops at `[`) — ALL generated tests run parameterized, so `error_message` was **always empty** → `classify_failure("")` → OTHER → pre-screen skip. Fixed: `^_+ (\S+?) _+` + strip the param suffix before the `results_by_name` lookup (matching `_ERROR_RE`'s existing `split("[")[0]`).
2. **`failure_classifier` didn't recognize the evidence-tracker fast-fail** — `_LocatorNotFoundError: Locator '...' not found on current page (...)` matched no regex (only Playwright-native "TimeoutError waiting for" did) → classified OTHER → pre-screen skip. Fixed: new `LOCATOR_NOT_FOUND` regexes → `LOCATOR_TIMEOUT` (LLM-reviewable) with locator extraction.

**Verified live:** broken locator → heal → `fixed: 1, learned: 1, remaining: 0`; store gained `CLICK 'Cart link' → a[href="/cart.html"]` with `source=self_healing, confidence=1.0`; re-heal dedups (hit_count 2, one row). +7 tests (2263 total); eval static 95.2%.

**Also noted (not fixed):** `MockServer._start()` does `os.chdir(directory)` on the whole process — any relative path in the calling process breaks after auto-start (eval harness works because its dataset/captures defaults are absolute; `--dataset <relative>` silently yields 0 stories). Fixing = save/restore cwd around the server thread, or resolve paths before chdir.

---

### B-037 — E-commerce mock surfaces: empty-cart element resolution + the cvc/skip family
**Status:** ✅ Fixed (2026-08-03, B-037 session, CI green)
**Priority:** Medium — the mock made both failures deterministic; fixes lift eval-006 execution to 8/8

**Context:** first measured baseline on `mock_sites/ecommerce/` (eval-006, capture `ecommerce_mock_code.py`): static resolution 12/16 (75%), execution **6 passed / 1 failed / 1 skipped**. The mock reproduced deterministically what the live site only showed as flaky noise.

**Fixes shipped (3 code + 4 mock):**
1. **Empty-state gate** (`src/placeholder_scorers.py`, `_assert_empty_state_rejects`): elements whose text signals emptiness ("Cart is empty!", "no items") are EXCLUDED from content-presence ASSERTs — the B-016 negation gate only ran in pass-1 text matching; the scoring path let `#empty_cart` win "product name and price" by default.
2. **Payment-card synonyms** (`src/semantic_matcher.py`): `cvc ↔ cvv ↔ cvv2` — the LLM skeleton's "cvc" FILL was unresolvable against the "CVV" field, skipping the entire checkout+payment test (the skip family eval-002 never saw).
3. **CSS classes in structural matching** (`_structural_bonus`): `p.cart_total_price` now matches "price" in "product name and price" (+15) — table cells carry the words text alone lacks.
4. **Mock fixes** (`mock_sites/ecommerce/`): classed cells in `cart.js` (`h4.cart_description`, `p.cart_price`, `p.cart_total_price`) because the scraper's tag lists exclude `table`/`td`; `name="cardholder_name"` on the Cardholder Name input (was `card_name` — shared word "card" won the pass-1 tie over `#card-number`); **route aliases** (`mock_routes.json` + `scripts/mock_server.py` 302-redirects): `/view_cart`, `/products`, `/checkout`, `/basket`… map to canonical files so journey discovery and cart-seeding reach cart/checkout with items, and page URLs stay canonical for `to_have_url`.

**Measured after:** eval-006 execution **8/8 passed** (full checkout + payment leg executes: `#cvv` filled, order placed, success asserted). Static 12/16 — the 4 remaining misses are LLM skeleton/ranking nondeterminism (ASSERTs skeletonized as URL checks; one LLM-picked card field), the AI-037 class now isolated from site variance. +9 regression tests (empty-state gate ×3, class structural ×3, card synonyms ×2, card-number≠cardholder-name ×1).

---
### B-036 — Consumer config architecture: env-var feature gates don't fit the product
**Status:** ✅ Shipped (2026-08-03, Phases 1–4, CI green)
**Priority:** Medium — blocks RAG-resolution fix (B-030 family) from reaching consumers
**Spec:** `docs/specs/FEATURE_SPEC_B036_consumer_config.md` (2026-08-03) — 4 changes: always-on RAG, bundled golden pack auto-seed, evidence auto-learn (builds on AI-035), settings store + export-time fields. ~3 sessions.

**Principle:** this is a consumer product (Streamlit/CLI). Feature toggles must not require `.env` edits. The product already has the right pattern for API keys (`secure_config.py` — Fernet-encrypted, persisted); the env vars are dev-era leftovers.

**Shipped (Phases 1–4):**
1. ✅ Always-on RAG with graceful degradation — `_build_rag_retriever()` builds by default; `RAG_ENABLED=0` transitional opt-out; empty store ⇒ no bonus ⇒ identical behavior; store/embedder failure degrades to no-RAG (never blocks generation). `RAGRetriever.retrieve()` hardened with once-only warning.
2. ✅ Bundled golden pack + auto-seed — `src/rag_bundled.py` ships eval-001..006 golden keys (83 patterns) + curated Playwright docs (27 chunks); first generation run auto-seeds with idempotent marker `evidence/.rag_bundled_seeded.json`; `rag_ingest.py --bundled/--force/--stats/--prune-learned`.
3. ✅ Evidence auto-learn (AI-035 core + B-036 Phase 3) — `src/rag_learn.py` (`site_hash`, `domain_from_url`, `learn_from_evidence`); `RAGStore.upsert_pattern()` dedup on `(action_type, description, site_hash)` with `hit_count` bump; teardown hook in `generated_tests/conftest.py` learns from passing runs (guarded, batched); site-scoped scoring `SAME_SITE_LEARNED_BONUS=5` (same-site only, cross-site 0) threaded orchestrator → matcher → resolver → scorer. Plan: `docs/plans/AI-035_B036_P3_plan.md`. Live-verified against the e-commerce mock (3 learned patterns, dedup'd); eval static 95.2% unchanged.

4. ✅ Settings store + field migration — `src/settings_store.py` (`SettingsStore`, Fernet-encrypted `~/.ai-test-gen/settings.enc` on the secure_config pattern; corruption-tolerant; `load_setting/save_setting/save_settings/get_all_settings/reset_settings`). Migrated sidebar state consumers actually set: `pom_mode`, `consent_mode`, `provider`/`model_name`, `workspace` (Streamlit sidebar + CLI `Session` seeding — settings win, env is fallback). `JIRA_PROJECT_KEY` env read removed from `src/config.py` (constant default `TEST`); export-time UI field in the Streamlit export panel + CLI menu (`Session.jira_project_key`), feeds `JiraReportGenerator` test-case IDs and a `Project:` header line in the Jira report (`PipelineReportService.build_reports(jira_project_key=...)`). `OCR_BACKEND` → persisted setting (default `pymupdf`); env read is now a fallback only. `LANGGRAPH_ENABLED` removed outright (dead flag — `--use-graph` is the supported path; `generate_skeleton(use_graph=...)` parameter replaces the env read). Streamlit "Learned Patterns" section folded in (`SidebarConfig.render_settings()` — RAG store stats via `store_stats()` + prune button). +30 tests (2229 total); eval static 95.2% unchanged.

**Remaining deferrals:** none — AI-035's self-healing patch write-back (``_learn_from_patch``, ``source="self_healing"``, ``confidence=1.0``) shipped 2026-08-04 in ``src/rag_learn.py`` (``pattern_from_patch``/``learn_from_patch``) + ``SelfHealingRunner`` (guarded hook after each successful ``replace_locator`` patch; description recovered from the evidence sidecar's placeholder label; ``HealingReport.learned`` surfaces the count in CLI + UI). The self-healing lever and the learning loop are now fully wired.

**Also noted:** sidebar config now persists via the SettingsStore (B-036 Phase 4) — the `st.session_state`-only gap is closed. Tier-2 walkthrough (2026-08-04) closed the last gap: the Streamlit UI now also persists `provider_base_url` + `model_name` (save-on-change + seed-on-load) — verified live across app restarts (provider/POM/consent/OCR/workspace/model all round-trip via `~/.ai-test-gen/settings.enc`).

---

### B-035 — Evidence sidecar written only at test END; killed/timed-out tests leave orphaned screenshots with no record
**Status:** ✅ Fixed (2026-08-03, `e1b322d`, CI green)
**Priority:** Medium — evidence silently vanishes for the exact runs that need it (failures)

`tracker.write()` runs once in `generated_tests/conftest.py` teardown; `_record_step` never persists incrementally. If a test process dies mid-run (pytest `--timeout` kill — already the standard in UI/UAT/verify runs — crash, playwright failure), **no `.evidence.json` is written** while intermediate screenshots survive as orphans. The evidence index (`build_or_refresh`) only sees sidecars, so the run is invisible.

**Also in the same layer:**
- 10 silent `except Exception: pass` blocks in `evidence_tracker.py` — screenshot, diagnosis, and dismissal failures are invisible (no warning recorded anywhere).
- `report.html` (PipelineReportService) embeds **zero screenshots** (verified: 0 png refs in an Aug 1 report) — evidence exists but reports can't show it.
- Evidence files accumulate across reruns (old screenshots from prior runs stay in the dir, unreferenced by the current sidecar).

**Proposed fix:** persist sidecar incrementally per step (or at minimum on step failure); warn (not swallow) when screenshots fail; embed screenshots in reports; clean stale evidence on rerun.

---

### B-034 — `evidence/run_results.sqlite` is corrupted — UI evidence page will crash
**Status:** ✅ Fixed (2026-08-03, `e1b322d`, CI green)
**Priority:** High — live in the working environment right now

`PRAGMA integrity_check` → **"database disk image is malformed" (Tree 10 page 26)**. WAL mode with a 0-byte WAL + 32KB shm; some queries return rows, others throw. DB mtime Aug 3 03:26 (during the overnight verify runs). Likely concurrent writers (Streamlit UI `build_or_refresh(force=True)` + run-result saves) or a killed process mid-write; the corrupted DB has no self-healing — `_upsert_sidecar` has no try/except, so the UI evidence search/refresh raises `DatabaseError` instead of rebuilding.

**Also found:** `except OSError, json.JSONDecodeError:` (×2 in `evidence_index.py`) — Python-2 syntax that Python 3 parses as a tuple-except, so it *works by accident*; lint-level 2to3 leftover.

**Proposed fix:** on `DatabaseError` during build/search, rebuild the DB (drop + recreate + re-index) instead of propagating; add a preflight `integrity_check` with a recovery path; ensure single-writer discipline (WAL checkpointing) or lock around writes.

---

### B-033 — Evidence gaps: failures leave no diagnostic artifacts; clicks never screenshot
**Status:** ✅ Fixed (2026-08-03, `e1b322d`, CI green)
**Priority:** Medium — evidence is the product's audit trail; a failed step currently records *nothing* visible

**Confirmed from `test_20260803_101815_...` evidence sidecars:**
- **Failed fast-fail steps have NO screenshot, NO failure_note, NO diagnosis** (`_record_step` skips all three when `fast_fail=True` — contradicts the click() comment "Always screenshot on click failure"). t10 step 6: `screenshot=None, failure_note=None, diagnosis=None`.
- **Click steps NEVER screenshot** (only navigate + assert do) — the exact step that fails (or burns 30s in the fallback marathon) leaves zero visual trace. 23 PNGs for 13 tests, all navs+asserts.
- **No per-step URL** — steps don't record `page.url`; only the final URL at `write()`. Reconstructing where a flow diverged requires the error strings.
- **Storage bloat:** full-page screenshots average **2.4MB each** (54MB evidence dir for one 13-test package).
- **Misleading fast-fail message**: "The element exists on a different page than the one this step runs on" blames the locator when the real cause is an earlier step's silent non-navigation (t10 step 5 → step 6). No cross-step state check.

**Proposed fix:** screenshot + diagnosis on failed steps (fast-fail included); capture per-step URL; flag clicks whose elapsed >10s or that follow a link without a URL change; consider viewport-size (not full-page) screenshots.

---

### B-032 — Export run-history DB copy orphaned since AI-012 (`playwright_tests.db` never created)
**Status:** ✅ Fixed (2026-08-03, export gate session, CI green)
**Priority:** Low — silent no-op, no crash

`src/export_service.py` copies `evidence/playwright_tests.db` — **nothing in the repo creates that file**. The SQLite layer writes `evidence/run_results.sqlite` (`sqlite_persistence.py`, `storage.py`). Same orphan name in `src/pipeline_artifact_manager.py:270`. Dead since AI-012 (2026-06-15) swapped JSON-dir export for the SQLite copy but globbed the wrong filename.

**Fix shipped:** copy `run_results.sqlite` (primary) with legacy `playwright_tests.db` fallback; WAL/SHM files follow the found DB name; README note + `has_sqlite` check updated; `pipeline_artifact_manager._count_run_results` checks `run_results.sqlite` first (and its Python-2 `except A, B:` fixed). Verified by `test_export_copies_run_results_sqlite` + `test_export_legacy_db_fallback` + export gate gate 6.

---

### B-031 — Export feature produces non-runnable/broken suites; never validated end-to-end
**Status:** ✅ Fixed (2026-08-03, export gate session, CI green)
**Priority:** High — claimed shipped (UI button + CLI step), but no export has ever been verified by running the exported suite

**Confirmed:**
- **34 of 35 exports in `exported_tests/` are stubs** (`def test_x(page): pass`) — export ran against empty/stub source packages, no guard.
- **The one real export (`20260802_181655_...`) is non-importable**: `from pages.home_page import HomePage` with **no `pages/` dir shipped** (POM export globs `pages/po_*.py` but generated pages are `home_page.py`/`cart_page.py` — **glob matches nothing**), plus `HomePage(page, evidence_tracker)` NameError and dead `@pytest.mark.evidence(...)` decorators.
- Current strip (`eda9809`) fixes the POM→flat conversion (verified on a live package), but `@pytest.mark.evidence(...)` decorators still survive (regex only matches the bare form) → `PytestUnknownMarkWarning`.
- No end-to-end gate: unlike `verify_production.py` for the main pipeline, nothing exports → runs the exported suite → asserts pass.

**Fix shipped:**
- **POM glob**: `pages/*.py` minus `__init__.py` — matches generated `home_page.py`/`cart_page.py` (exported real package now ships all 5 pages).
- **True POM-mode export**: `strip_evidence_from_test_code(..., preserve_pom_calls=True)` keeps POM imports/instantiations/method calls (only the `evidence_tracker` arg drops from instantiations) — previously POM-mode silently emitted flat output with a dead `pages/` dir.
- **Evidence decorators stripped in all forms** (`_strip_evidence_decorators`): bare, arg-carrying, multi-line, whitespace variants.
- **B-020 assert family converted** (`_strip_tracker_asserts`, tests + POMs): `assert_hidden` → `to_be_hidden()` (the live gap — it survived exports and NameError'd at runtime), plus disabled/enabled/checked/empty/text/text_contains/value/count.
- **Stub guard**: exporting an all-stub / all-skip / no-test source raises `ValueError` with a clear message.
- **Export collision guard**: same-second same-slug exports get `_1`, `_2`… suffixes instead of silent overwrite.
- **Export gate** (`scripts/export_gate.py`): 9 gates — stub guard, flat+POM export, flat/POM artifact validation, run-history DB copy (B-032), collect (importability), and execution of both suites against a deterministic golden localhost fixture (`fixtures/golden_package/` + `fixtures/golden_site/`, port 8123). `--source <pkg>` for real packages (offline), `--run-remote` for live execution.

**Verification:** golden gate 9/9 PASS (flat + POM suites execute and pass), real package 8/8 PASS (26 tests collect clean); exported flat suite of the 20260803 package converts all evidence calls + decorators correctly.

---

### B-030 — "Check Out" resolves to wrapper div `#do_action` instead of the real button `.btn.btn-default.check_out`
**Status:** ✅ Fixed (2026-08-03, `e1b322d`, CI green)
**Priority:** Medium

`{{CLICK:Check Out}}` emitted `#do_action` (a wrapper `<div>`, no href) even though the scraper captured `('proceed to checkout', '.btn.btn-default.check_out')` and `PlaceholderScorer` rates the button **5 vs 0** for "Check Out" (verified directly). Survives into exports. Root cause is in the resolution path feeding element data to the scorer (tag/role/href likely stripped) — investigate why the anchor lost before the wrapper.

---

### B-029 — Tracker records "passed" for clicks that never navigated (ad-overlay swallow) — no post-click URL verification
**Status:** ✅ Fixed (2026-08-03, `e1b322d`, CI green)
**Priority:** High — caused all 4 checkout-cluster failures (t10-t13) in `test_20260803_101815_...`

**Symptom:** cart header-link click records `passed` after a **30.5s fallback marathon** with **no navigation**; the next step fast-fails with the misleading "element exists on a different page" error. All 4 failures share the identical signature (step 5 elapsed=30,516ms, status=passed, page still on `category_products/1`).

**Root cause chain (reproduced live, 3×):**
1. FreeCmp consent dialog (`.fc-consent-root`) + Google `#google_vignette` ad overlay intermittently cover the header and intercept link clicks.
2. The primary click (5s timeout) always fails → full fallback marathon (~30s: hover → mouseenter → ancestors → force-show JS `el.click()`).
3. `el.click()` "succeeds" even when Google's click-interceptor swallows the navigation → recorded `passed`, zero URL verification.
4. Contributing factor: the "Continue Shopping" step no-ops (2-6ms, "modal already dismissed") because the add-to-cart modal is mid-fade — the no-op path returns **before** the dismissal calls, leaving the modal to be handled by the next step's dismissal.

**Also latent:** `_dismiss_confirmation_modals` selector `button.btn-success.close-modal` is the **only unscoped** dismiss selector (B-015 scoped the rest) — hazard on pages with a visible close-modal button that is a real action.

**Proposed fix:** post-click navigation verification in `EvidenceTracker.click` — if the target is an `<a>` with a different-path `href` and the URL hasn't changed ~2s after a "successful" click, re-dismiss overlays and retry once (or `page.goto(href)`); scope `button.btn-success.close-modal` to modal containers.

---

### B-028 — Journey discovery selects cart nav link for product / add-to-cart actions
**Status:** ✅ Fixed (2026-08-01, ship-it) — full fix + follow-ups landed
**Priority:** High — cascades: wrong click → missing pages → unresolved placeholders → skips/fails

**Fixed (2026-08-01):**
- **Root cause #1 — action case mismatch:** `_discover_selector()` passed lowercase
  `"click"/"fill"` to `PlaceholderScorer.compute_element_score()` which branches on
  uppercase — every action bonus/gate was silently disabled, so discovery scores
  collapsed to raw word overlap ("View Cart" beat real product buttons at score=1).
  Fixed by normalising the action to uppercase + skipping invisible elements for
  CLICK/FILL + modal penalty only when a modal is actually visible.
- **Root cause #2 — context hints:** product-intent descriptions now prefer
  product-card selectors over nav chrome; category descriptions ("Product Category")
  prefer listing pages over detail pages; modal-dismiss descriptions only click real
  dismiss controls.
- **Root cause #3 — hallucinated locators:** generated POMs now embed a DOM-existence
  index (`_ELEMENTS`) — the click() fallback only targets scraped selectors or
  pytest.skip (never `text=<description>`). Hidden elements (CSRF inputs) excluded
  from POM method generation entirely.
- **Root cause #4 — fillability:** `PlaceholderScorer._is_fillable` aligned with
  `IntentMatcher` (role=number/email/password/...) so quantity inputs resolve;
  FILL-quantity falls back to +/- stepper clicks when no input exists.
- **Root cause #5 — `tag` field missing** from `_build_element_dict` (killed ASSERT
  display scoring in discovery).

**Follow-ups landed with the fix:**
- Batch placeholder fallback now searches ALL scraped pages (was scoped to the seed
  URL — left `Proceed To Checkout` unresolved despite scraped data).
- EvidenceTracker click fast-fails on missing/hidden locators (148s fallback marathon
  → 0.0s) and proactively dismisses consent/ad/modals (~2s vs 30s per blocked click).
- Per-test pytest `--timeout=120` in UI/UAT/verify runs — a stuck test can't hang the suite.
- LLM generation capped at 4096 tokens (`LLM_MAX_TOKENS`) — a runaway no longer burns
  the full 600s request timeout.
- Structural assembler (`src/test_structure_assembler.py`) rebuilds the generated file
  from the parsed journey model — module-level LLM statement leaks are structurally
  impossible (previously crashed pytest at COLLECTION time).

**Verified:** journey home → product page → fill quantity → add to cart → view cart
(with items). verify_production automationexercise: 12/13 gates, execution completes
in ~65-75s (was 600s timeout). Full eval (live regenerate): 53.7% → 65.7% resolution
accuracy vs prior run; static mode unchanged at 100%.

**Symptom:** During journey discovery, generic descriptions resolve to the cart nav link
instead of product cards / add-to-cart buttons:
```
'click on a product to view it'  → a[href="/view_cart"]  (score=1)   ❌
'add product to cart'           → a[href="/view_cart"]  (score=11)  ❌
'dismiss confirmation modal'    → a[href="/view_cart"]  (score=1)   ❌
```
The journey navigates products → view_cart instead of a product page, so checkout pages
are never scraped and cart-dependent placeholders never resolve.

**Live evidence (2026-08-01, automationexercise.com, generated package
test_20260801_120204_...):** T02 add-to-cart FAILED — resolver emitted a hallucinated
locator `text=First product link` (not in DOM; failure reporter suggested `#Men`,
`#gda`, `#Kids`) → `Locator.click: Timeout 5000ms` at ~249s per test. T06 (max cart
items) same root cause. T03/T04/T05 (cart/checkout/purchase) and T08/T09 (quantity)
skip — checkout pages never scraped + site uses +/- quantity buttons (no fillable input).

**Root cause:** `_discover_selector()` in `src/journey_scraper.py` scores generic
descriptions poorly and falls back to weak matches (B-012/B-015 family — those fixes
covered the resolver Pass 1, not journey discovery's element selection). Also: resolver
emits non-existent locators ("First product link") instead of skipping — needs a
DOM-existence guard.

**Proposed fix (next session):**
1. Structural hint in journey discovery: "product" descriptions should prefer
   product-card selectors (img/a/div inside `.product` containers) over nav links.
2. DOM-existence guard: resolver candidates must exist in scraped data before
   emitting a locator (prevents `text=First product link`).
3. Quantity: add a fallback mapping FILL-quantity → +/- button clicks when no
   fillable input exists.

**Mitigations available now:** explicit journey steps ("click on product name 'Blue Top'"),
credential profile for checkout, cart-seeding for state-dependent pages.


### B-004 — Ambiguous locators when same label exists on multiple forms (✅ FIXED by architecture evolution)
**Status:** ✅ Fixed — skeleton-first resolver pipeline emits ID/data-test/href selectors via `build_robust_locator()`, not `get_by_label()`. Multi-page scraping (AI-009) also shipped. No code change needed.

### B-012 — Pass 1 false positive: "add to cart" matches cart nav link
**Status:** ✅ FIXED (2026-05-17)
**Symptom:** CLICK:'Add to cart' button resolves to a[href="/view_cart"] (text="Cart")
because "cart" appears in both the description and the nav link text.
**Root cause:** Pass 1 minimum length guard (3 chars) allows short common words
to match across unrelated elements.
**Fix implemented:** Action verb awareness in `_pass1_text_match()` — when the
description contains action verbs (add, remove, place, buy, etc.), the element
text must also contain at least one of those action words. Prevents "View Cart"
from matching "Add to cart button" because "View Cart" lacks the word "add".
**Files changed:** `src/placeholder_orchestrator.py` — `_pass1_text_match()`
**Verification:** UAT automationexercise.com 6/6 tests pass (was 4/6).

### B-015 — Journey discovery selects wrong element for action descriptions
**Status:** ✅ FIXED (2026-06-23) — `dismiss_consent_overlays` rewrite
**Symptom:** Journey discovery clicks wrong elements, causing it to visit wrong pages:
- `"checkout button"` → `#react-burger-menu-btn` (burger menu, score=1) — opens side menu instead of checkout
- `"continue button"` → `#react-burger-menu-btn` (score=1) — same wrong element
- `"finish button"` → `#react-burger-menu-btn` (score=1) — same wrong element
- `"first name:John"` → `.product_sort_container[data-test="product-sort-container"]` (score=1) — `<select>` element, not a fillable input
- `"zip/postal code:12345"` → `.shopping_cart_link[data-test="shopping-cart-link"]` (score=10) — an `<a>` link, not an input

On automationexercise.com: `"Add to cart button"` → `a[href="/view_cart"]` (Cart link).

**Root cause:** `dismiss_consent_overlays()` in `src/browser_utils.py` used aggressive
global text matching (`button:has-text('Continue')`) that matched the `#continue-shopping`
button on saucedemo's cart page. This function is called before every click step in the
journey scraper — so the cart page navigated back to inventory.html before the next
scrape ran. The journey scraper then scraped `inventory.html` (29 elements) instead of
`cart.html` (14 elements), and selected `#react-burger-menu-btn` for "checkout button".

**Impact:** Journey discovery clicks the burger menu instead of checkout, navigating
to inventory.html instead of checkout-step-one.html. This means:
1. Checkout pages (`checkout-step-one.html`, `checkout-step-two.html`) are **never scraped**
2. The placeholder resolver has **zero data** for checkout form fields
3. `test_06_complete_checkout` gets `pytest.skip()` for all checkout FILL fields
4. The downstream placeholder resolver cannot compensate because the data simply doesn't exist

**Confirmed via UAT:** `scripts/uat/uat_automationexercise.py --site saucedemo` (2026-06-22):
- Journey clicks `#react-burger-menu-btn` for "checkout button" on cart page
- Click navigates `cart.html` → `inventory.html` (wrong)
- Pages scraped: only 3 URLs (home, inventory, cart) — checkout pages missing
- Resolver fails on: 'first name', 'last name', 'zip/postal code', 'finish button', 'thank you message'
- Final code: `test_06` has `pytest.skip()` for unresolved placeholders

**Fix:** Rewrote `dismiss_consent_overlays()` in `src/browser_utils.py` with a 3-stage approach:
1. **Google Consent TVM** — specific `.fc-consent-root` selectors (unchanged, safe)
2. **Structural containers** — known consent provider classes (`oneTrust`, `cookie-banner`,
   `Cookiebot`, `[role='dialog']`, etc.) — only click buttons **inside** these containers
3. **Position-based detection** — JS finds fixed/sticky elements near bottom of viewport,
   then looks for dismiss buttons inside them
4. **Ad overlay removal** — specific selectors only (Google Vignette, ASWIFT)

**Removed:** Generic text matching (`button:has-text('Continue')`, `button:has-text('OK')`)
on global page, dangerous `zIndex > 10000` DOM removal, `allElements` iteration over entire DOM.

**Verification (2026-06-23 saucedemo UAT after fix):**
- `#checkout` selected with score=12 for "checkout button" on `cart.html` ✅
- `#first-name` (score=90), `#last-name` (score=90), `#continue`, `#finish` all resolved ✅
- All 5 checkout pages scraped: `cart.html`, `checkout-step-one.html`, `checkout-step-two.html`,
  `checkout-complete.html` ✅
- `test_06_complete_checkout` has only 1 skip (ASSERT "Thank You page header" — B-014)
  instead of 8+ skips before ✅

**Files changed:**
- `src/browser_utils.py` — complete rewrite of `dismiss_consent_overlays()`
- `tests/test_browser_utils.py` — NEW — 10 tests covering safety (no false clicks),
  structural containers, Google Consent TVM, and zIndex removal regression

**Priority:** High — causes cascading failure (wrong click → wrong page → missing scrape → zero resolution)

### B-013 — Journey discovery stops one page short for checkout-step-two
**Status:** ✅ RESOLVED (2026-06-23) — root cause was B-015, now fixed
**Original claim:** "Journey discovery doesn't scrape the page after the final click"
**Actual finding (saucedemo UAT, 2026-06-22):** Journey discovery never reaches
checkout pages at all — it clicks `#react-burger-menu-btn` (burger menu) for
"checkout button", navigating to inventory.html instead of checkout-step-one.html.

**Impact:** Both `checkout-step-one.html` and `checkout-step-two.html` are missing
from scraped data. This is a B-015 consequence.

**Fix:** B-015 fix (rewrite of `dismiss_consent_overlays`) allows journey to reach
checkout pages. Verified: all 5 checkout pages now scraped correctly.
**Priority:** Medium — superseded by B-015, resolved via same fix

### B-016 — text_matches_description() fails on synonyms
**Status:** 🟡 PARTIALLY FIXED — negation detection + synonym expansion (2026-06-29)
**Symptom:** `PlaceholderResolver.text_matches_description()` produces false negatives
on semantically equivalent text and false positives on semantically contradictory text.

**Test results (from debug_compare.py, 2026-06-22):**
- ❌ `"Login"` vs `"Sign in button"` → False (expected True) — synonym not recognised
- ❌ `"Dress"` vs `"product category link"` → False (expected True) — proper noun vs generic descriptor
- ❌ `"Blue Top"` vs `"a product name"` → False (expected True) — same pattern
- ❌ `"Your cart is empty!"` vs `"cart content with items"` → True (expected False) — "cart" keyword overlap matches despite semantic contradiction (empty ≠ with items)
- ❌ `"Cart is empty"` vs `"cart page with selected items"` → True (expected False) — same false positive

**Root cause:** Text matching uses keyword/token overlap without semantic understanding.
No synonym dictionary or negation detection. "cart" + "content" in description matches
"cart is empty" because both contain "cart". Negation words ("empty", "no", "not") are
not treated as exclusion signals.

**Impact:** Placeholder resolution passes/fails incorrectly for login-related elements,
product names, and cart state assertions. This is a 33% failure rate on text validation
(5/15 checks fail consistently across both automationexercise and saucedemo).

**Priority:** High — foundational matching logic affects all resolution paths

**Fix implemented (2026-06-29):**
1. **Negation gate** — `_is_negated()` rejects matches when element text contains
   negation words ("empty", "none", "no items", "out of stock", etc.) but the
   description signals positive content ("with items", "selected", "visible",
   "loaded", etc.). Domain-agnostic — works on any site.
2. **Synonym-aware Jaccard** — After the original matching logic (containment,
   word-overlap, action-verbs), a fallback computes Jaccard similarity on
   *expanded* token sets from `SemanticMatcher.get_words(expand_aliases=True)`.
   The TOKEN_EXPANSIONS map is the single source of synonym truth — no duplicate
   dictionaries. Threshold 0.30 requires meaningful overlap.
3. **TOKEN_EXPANSIONS additions** — Added authentication/identity group:
   `login ↔ sign ↔ signin ↔ authenticate`, `logout ↔ sign-out ↔ signout`,
   `signup ↔ register ↔ sign-up`, `sign-out ↔ logout`.

**UAT results (2026-06-29):**
| Element text | Description | Before | After | Method |
|-------------|-------------|--------|-------|--------|
| "Login" | "Sign in button" | False ❌ | True ✅ | synonym Jaccard |
| "Your cart is empty!" | "cart content with items" | True ❌ | False ✅ | negation gate |
| "Cart is empty" | "cart page with selected items" | True ❌ | False ✅ | negation gate |
| "Items in your cart" | "cart content with items" | True ✅ | True ✅ | unchanged |
| "Dress" | "product category link" | False ❌ | False ❌ | needs LLM (B-020) |
| "Blue Top" | "a product name" | False ❌ | False ❌ | needs LLM (B-020) |

**Remaining cases (2/6):** "Dress"/"product category link" and "Blue Top"/"a product name"
are proper nouns vs. generic descriptors — zero token overlap with no synonym bridge.
These require LLM-assisted semantic matching (B-020) and are out of scope for keyword-based
resolution. This is by design: keyword matching handles the common cases; LLM handles
the semantically ambiguous ones.

**Files changed:**
- `src/placeholder_resolver.py` — `_NEGATION_WORDS`, `_POSITIVE_INDICATORS`,
  `_is_negated()`, updated `text_matches_description()` with negation gate + Jaccard
- `src/semantic_matcher.py` — added authentication/identity TOKEN_EXPANSIONS

**Tests:** `tests/test_placeholder_resolver_text_validation.py` — new B-016 test class

**Follow-up:** B-020 LLM wiring will handle the remaining 2/6 cases when complete.

---

### B-017 — FILL placeholders on unreachable pages fail to resolve
**Status:** ✅ CORRECTED — B-015 fix resolves checkout FILL failures (2026-06-23)
**Original claim:** "All FILL-type placeholders return zero ranked candidates" — 100% FILL failure.
**Actual finding:** FILL on **login pages** resolves correctly. FILL on **unreachable pages** fails.

**Evidence (saucedemo UAT, 2026-06-22):**
- Login FILL placeholders (`'username'`, `'password'`) → resolved to `#user-name`, `#password` ✅
  - Note: resolver logs say `Failed to find 'username'` but final code has correct selectors
  - This is because **prerequisite injection** reuses the resolved selectors from test_01
  - The resolver itself may still be failing — it's masked by prerequisite injection
- Checkout FILL placeholders (`'first name'`, `'last name'`, `'zip/postal code'`) → `pytest.skip()` ❌
  - Root cause: journey discovery clicked wrong element (`#react-burger-menu-btn` instead of `#checkout`)
  - Checkout pages were never scraped — resolver has zero data for those elements
  - This is a **B-015 consequence**, not a standalone resolver bug

**Impact:** FILL failures on checkout are caused by B-015 (journey discovery clicking wrong elements).
Fixing journey discovery's element selection should allow checkout pages to be scraped,
which would give the resolver data for checkout FILL fields.

**Open question:** Does the resolver itself fail on login FILL fields even when data is available?
The `Failed to find 'username'` debug messages suggest yes, but prerequisite injection masks it.
Needs isolated test: resolve `'username'` placeholder against saucedemo.com login page data WITHOUT prerequisite injection.

**Priority:** Medium — partially masked by prerequisite injection, partially caused by B-015

**Fix:**
1. ✅ B-015 fixed (2026-06-23) — checkout FILL placeholders now resolve: `#first-name`,
   `#last-name`, `#postal-code` all resolved correctly
2. Open: Isolate whether resolver itself fails on login FILL fields without prerequisite injection

---

### B-018 — Resolver gap: login elements fail in resolver but succeed in journey
**Status:** ✅ CORRECTED via saucedemo UAT (2026-06-22)
**Original claim:** "Journey discovery and resolver use different matching logic"
**Actual finding:** The gap is real but the primary impact is different than originally diagnosed.

**Evidence (saucedemo UAT, 2026-06-22):**
- Journey discovery: `#user-name` score=95, `#password` score=3, `#login-button` score=2 ✅
- Placeholder resolver logs: `Failed to find 'username'`, `Failed to find 'password'`, `Failed to find 'login button'` ❌
- Final code: `#user-name`, `#password`, `#login-button` ✅ (via prerequisite injection masking)

The resolver says it failed, but the final code is correct because prerequisite
injection reuses previously-resolved selectors. This masks the resolver bug.

**What ISN'T a gap:** Post-login page elements (inventory, cart) resolve fine
because those pages are scraped and the resolver finds matches.

**What IS a gap:** Login page elements — the resolver cannot match `'username'`
against `#user-name` even though journey discovery scores it 95/100. The resolver
is returning zero candidates for elements that exist in the scraped data.

**Root cause:** The resolver's matching pipeline (Pass 1 text, Pass 2 structural,
Pass 3 scoring+LLM) is not finding matches for input elements with no visible text.
Journey discovery uses a different scorer that considers `id`, `name`, `placeholder`
attributes directly.

**Priority:** Medium — masked by prerequisite injection in most cases, but real bug exists
**Fix:** See B-017. Needs isolated test without prerequisite injection to confirm.

---

### B-014 — ASSERT tokens resolve to wrong elements silently
**Status:** 🟡 PARTIALLY FIXED — step-context exclusion implemented (2026-06-25)
**Symptom:** ASSERT placeholders resolve to completely wrong elements:

**Evidence (saucedemo UAT, 2026-06-22 — BEFORE fix):**
- `"product inventory page"` → `#login-button` ❌
- `"cart badge shows 1"` → `.shopping_cart_link` ❌
- `"shopping cart page title"` → `.shopping_cart_link` ❌
- `"sauce labs backpack in cart"` → `#remove-sauce-labs-backpack` ❌
- `"checkout information page"` → `#checkout` ❌
- `"thank you message"` → `#user-name` ❌

**Root cause:** ASSERT resolution has no awareness of the preceding interactive step.
When a CLICK or FILL resolved to element X, the subsequent ASSERT could also resolve
to X because the scorer finds structural overlap. Additionally, the scorer doesn't
filter by element type for ASSERT actions.

**Fix implemented (2026-06-25):** Step-context exclusion in `src/placeholder_orchestrator.py`:
- CLICK/FILL steps track `last_selector` / `last_description` through the journey loop
- ASSERT resolution excludes the previous selector unless descriptions reference the
  same element (strict containment: `norm_a in norm_b or norm_b in norm_a`)
- Exclusion applied across all resolution passes (text, ASSERT-text, structural, scoring)
- Same-element assertions allowed (e.g. "login button" → "login button is disabled")
- Spec: `docs/specs/FEATURE_SPEC_B014_step_context_resolution.md`
- Tests: `tests/test_b014_assert_resolution.py` (53 tests, 100% pass)

**UAT results (2026-06-25 — AFTER fix):**
| ASSERT | Before | After | Improvement |
|--------|--------|-------|-------------|
| `"inventory page title"` | `#login-button` (PASSED — false green) | `#login-button` (FAILED — correct) | ✅ False green → real failure |
| `"cart badge with count 1"` | `.shopping_cart_link` | `.shopping_cart_link` | ❌ Unchanged — see B-016 |
| `"Sauce Labs Backpack item in cart"` | `#remove-sauce-labs-backpack` | `#remove-sauce-labs-backpack` | ❌ Unchanged — see B-016 |
| `"checkout information form"` | `#checkout` (PASSED — false green) | **SKIP** (unresolved) | ✅ False green → skip |
| `"Thank You page message"` | `#user-name` (SKIP) | **SKIP** | Same — see B-016 |

**Impact of fix:** 2 assertions went from false-green PASS to either real failure
or skip. Tests no longer silently pass for the wrong reason in the cross-step
preceding-interactive case.

**Limitations (tracked separately as B-016):**
1. ASSERTs whose wrong element is NOT the preceding interactive step — resolver
   quality issue, not step-context (see B-016)
2. Within-step ASSERTs on the same skeleton line as CLICK
3. Prerequisite-injected steps bypass step-context tracking

**Priority:** High — silent wrong assertions are worse than skips
**Tests:** `tests/test_b014_assert_resolution.py` (19 tests) — see B-016 for remaining cases.
---

### B-016 — ASSERT resolution quality for non-step-context cases
**Status:** ✅ VALIDATED (2026-06-30) — implementation complete, UAT confirms role filtering + fallback working
**Related:** B-014 (step-context exclusion handles the preceding-interactive case)
**Symptom:** ASSERT placeholders resolve to wrong interactive elements (buttons,
links) instead of display elements.

**Evidence (saucedemo UAT, 2026-06-25, post B-014 fix):**
- `"cart badge with count 1"` → `.shopping_cart_link[data-test="shopping-cart-link"]`
  — the cart navigation link, not a badge. Resolver picks the link because its
  `data-test` attribute contains "cart".
- `"Sauce Labs Backpack item in cart"` → `#remove-sauce-labs-backpack`
  — the REMOVE button. Wins because its `id` contains "backpack".

**Root cause:** The scoring pipeline scores elements by keyword overlap in
`id`, `data-test`, and structural attributes. Any element containing those
keywords wins — even if it's a button, link, or delete control rather than
the intended display element.

**Design decisions (grilling session, 2026-06-25):**
- Role filtering uses `computed_role` from CDP AX tree (AI-024), falling back to
  raw `role` field. The enricher already writes `computed_role` but the resolver
  currently ignores it.
- Display roles defined as a positive constant (`DISPLAY_ROLES`) in the orchestrator.
  No import from `AccessibilityEnricher` needed — resolver stays self-contained.
- `link` and `textbox` excluded from display roles (even though they are leaf
  ARIA roles) — ASSERT descriptions like "cart badge" should not match cart links.
- Soft filtering: prefer display elements first; fall back to all elements if no
  display candidates score above threshold (logged as low-confidence, never skip
  solely due to filtering).
- No description scope awareness — the skeleton doesn't encode element-level vs
  page-level intent. Role filtering + existing scoring pipeline covers the problem.
- Scraper gap (`"Thank You page message"` → SKIP) spun off as B-019.

**Approach:**
1. **ASSERT role filtering (soft)** — for ASSERT actions, score display-role elements
   first using ARIA roles (`heading`, `paragraph`, `text`, `status`, `region`,
   `listitem`, `cell`, `generic`). If no display elements score above threshold,
   fall back to all elements (logged as low-confidence).
2. Implementation lives in `src/placeholder_orchestrator.py`, alongside step-context
   exclusion (B-014). Runs as a pre-filter before scoring passes.

**UAT results (2026-06-25, saucedemo, openai-local/Qwen3.6-27B):**
| ASSERT | Before B-016 | After B-016 | Status |
|--------|-------------|-------------|--------|
| `"cart badge with count 1"` | `.shopping_cart_link` (wrong link) | **SKIP** | ✅ Fixed |
| `"Sauce Labs Backpack item in cart"` | `#remove-sauce-labs-backpack` (wrong button) | **SKIP** | ✅ Fixed |
| `"inventory page visible"` | `#login-button` | `#user-name` | ❌ Still wrong — page-scoping issue, not role |

**Priority:** Medium — role filtering working, low-confidence fallback paths logged correctly

**UAT validation (2026-06-30, saucedemo):**
- `"cart badge with count 1"` → B-016 fallback: best display score=5 is 85 below global top=90 — correctly falls back to non-display element
- `"Sauce Labs Backpack item details in cart"` → B-016 fallback: best display score=90 is 5 below global top=95 — correctly falls back
- Both cases logged with `[RESOLVE]` prefix for diagnostics — filtering is working as designed

---

### B-019 — Scraper misses heading text on JS-rendered pages (✅ FIXED by AI-032 Semantic Scraper)
**Status:** ✅ Fixed — three-layer hybrid extraction (BS4 + CDP AX tree + aria_snapshot) resolves aria-labelledby cross-references and dynamically composed accessible names that BS4 alone couldn't.
**Related:** B-016 (ASSERT role filtering)
**Symptom:** BeautifulSoup-based scraper doesn't capture heading text from
pages where content is rendered inside SVG elements or via complex ARIA
relationships (e.g., `aria-labelledby` references).

**Evidence (saucedemo UAT, 2026-06-25):**
- `"Thank You page message"` → **SKIP** (unresolved)
  — `checkout-complete.html` has a checkmark SVG and heading, but the scraper
  captures no meaningful text in `text`, `aria_label`, or `accessible_name`.

**Root cause:** Scraper uses BeautifulSoup on post-`networkidle` HTML. SVG
internal text, `aria-labelledby` cross-references, and dynamically composed
accessible names are not resolved by static HTML parsing. CDP `getFullAXTree`
(AI-024) could resolve these but is not yet wired into the main scraper's
element extraction.

**Approach:** Evaluate whether to enhance the existing scraper with CDP AX tree
resolution, or consider replacing BeautifulSoup with a Playwright-native DOM
walk that captures computed accessible names.

**Priority:** Low — affects completion pages and similar edge cases
**Note:** Separate from B-016 — B-016 is about wrong matches, this is about
missing data.
---

### B-020 — LLM-Assisted ASSERT Resolution
**Status:** ✅ COMPLETE + VALIDATED (2026-06-30)
**Related:** B-014 (step-context exclusion), B-016 (ASSERT role filtering)
**Symptom:** ASSERT placeholders always resolve via mechanical fallback to `assert_visible`. The LLM semantic pass (designed to select appropriate `assertion_type` like `toHaveText`, `toContainText`, `toHaveCount`, etc.) never fires because `SemanticCandidateRanker.generator` is `None`.

**Implementation done (2026-06-28):**
- `src/evidence_tracker.py` — added `assert_text`, `assert_text_contains`, `assert_disabled`, `assert_enabled`, `assert_checked`, `assert_count`, `assert_value`, `assert_empty`
- `src/semantic_candidate_ranker.py` — rewritten to accept step context and return `assertion_type`/`expected_value`
- `src/placeholder_orchestrator.py` — `_resolve_assert_semantically()` method; ASSERT routing through semantic path; `line_resolutions` extended to 7-tuple
- `src/code_postprocessor.py` — `_ASSERTION_TO_ET_METHOD` mapping; routes to correct evidence_tracker method
- `src/orchestrator.py` — `_resolve_placeholder_for_page()` returns 3-tuple `(resolved_value, next_url, assertion_type)`
- Tests updated: `test_semantic_candidate_ranker.py`, `test_orchestrator.py`, `test_orchestrator_dynamic_scrape.py`

**Session 2 (2026-06-30) — LLM wiring complete:**
- **Root cause:** `PlaceholderOrchestrator.__init__` hardcoded `SemanticCandidateRanker(None)` at line 91. The `AsyncGeneratorLike` protocol was never instantiated with a real LLM client.
- **Fix:**
  1. Added `generator: AsyncGeneratorLike | None` parameter to `PlaceholderOrchestrator.__init__`
  2. Changed `SemanticCandidateRanker(None)` → `SemanticCandidateRanker(generator)`
  3. `TestOrchestrator.__init__` now passes `generator=test_generator.client` to `PlaceholderOrchestrator()`
- **Files changed:** `src/placeholder_orchestrator.py` (import + `__init__`), `src/orchestrator.py` (1 line in `PlaceholderOrchestrator()` call)
- **Verification:** `ruff`/`mypy` clean, `1342/1343` tests pass, wiring confirmed via Python check
- **Remaining (optional):** `src/prompt_utils.py` — add `ASSERT:"exact text"` examples for skeleton generation

**UAT results (2026-06-28, openai-local/Qwen3.6-27B, debug_compare.py) — pre-fix baseline:**
| Site | Tests | SKIPs | ASSERT quality | Notes |
|------|-------|-------|---------------|-------|
| AutomationExercise | 6/6 | 1 (home banner) | All `assert_visible` (fallback) | Full pipeline 11-12/12 |
| SauceDemo | 3 tests | 2 unresolved (username/password input) | All `assert_visible` (fallback) | Full pipeline 11/12 |

**Key finding (pre-fix):** Results identical to pre-B-020 baseline because LLM semantic pass always falls back. Mechanical fallback produces the same locators as before.

**Post-fix expected improvement:** The LLM semantic pass now fires, selecting appropriate assertion types (`toHaveText`, `toContainText`, `toHaveCount`, etc.) rather than defaulting to `toBeVisible`.

**UAT validation (2026-06-30, openai-local/Qwen3.6-27B):**
| Site | Tests | SKIPs | Assertion diversity |
|------|-------|-------|--------------------|
| SauceDemo | 12/12 | 0 | `assert_visible`×4, `assert_text`×1, `assert_text_contains`×1 |
| AutomationExercise | 12/12 | 0 | LLM semantic pass active |

**Result:** Pre-fix all ASSERTs defaulted to `assert_visible` (fallback). Post-fix the LLM selects `toHaveText` and `toContainText` where appropriate — 3 unique assertion types vs 1 before.

**Priority:** Medium — unlocked assertion-type diversity (Text, Count, State, Value) for commercial viability
---

### B-021 — Page-state assertions fail to resolve (e.g., "home page visible")
**Status:** ✅ FIXED (2026-07-20)
**Spec:** `docs/specs/FEATURE_SPEC_URL_ASSERT.md`
**Roadmap ref:** Tier 2 — URL-Based Assertions for Page-State Verification
**Symptom:** Page-level ASSERT placeholders like "home page visible" and "dress products page visible"
can never resolve to any DOM element, producing `pytest.skip()` with:
```
Skipping: unresolved placeholders for: 'home page visible'; 'dress products page'
```

**Root cause:** `PageStateAssertStrategy` in `src/intent_matcher.py` correctly detects these as
page-state descriptions but returns `False` for all elements. The resolver has no URL-based
assertion path — `ASSERT` always maps to DOM elements. A heading like "AutomationExercise"
appears on multiple pages, so DOM-element assertions are not reliable page-identity checks.

**Proposed fix:** Extend the resolver to detect page-state ASSERT descriptions and resolve them
to URL assertions (`expect(page).to_have_url(...)`) via the existing `resolve_url()` method.
No new placeholder action needed — the description already carries sufficient signal.

**Why not a DOM element:** On automationexercise.com, the heading "AutomationExercise" appears
on both `/` and `/products`. The only reliable page-identity check is the URL itself.

**Priority:** Medium — skipped tests degrade user trust; URL assertions are more precise than
element-level proxies for page identity.
---

### B-023 — Cart modal intercepts clicks during journey discovery
**Status:** ✅ FIXED (2026-07-20)
**Symptom:** After adding a product to cart on automationexercise.com, the "Added to cart"
confirmation modal (`#cartModal`) blocks pointer events on the "Cart" header link.
The journey scraper retries clicking `a[href="/view_cart"]` but the modal intercepts:
```
<div id="cartModal" class="modal show">…</div> from <section>…</section> subtree intercepts pointer events
```
The journey eventually scrapes the cart page anyway (it navigates directly after retries),
but the retry loop adds noise and delay (~10s per affected test).

**Root cause:** The journey scraper's click step doesn't dismiss overlays before clicking
target elements. `dismiss_consent_overlays()` handles cookie banners but not confirmation
modals that appear after interactions.

**Proposed fix:** Before each click step in journey discovery, check for and dismiss any
visible confirmation/modals/popups. The `CartSeedingScraper` already has a "Continue Shopping"
dismiss step — this same logic should run before clicking cart/checkout navigation links.

**Priority:** Low — tests pass despite the retry noise. Fixing reduces UAT runtime by ~20s.
---

### B-022 — Scraper visits state-dependent pages with no prior session state
**Status:** ✅ FIXED (2026-07-20)
**Spec:** `docs/specs/FEATURE_SPEC_URL_ASSERT.md` (B-021 — related, same user story)
**Symptom:** Tests that navigate to state-dependent pages (e.g., `/view_cart`) resolve
placeholders to elements from an empty-state page. "Proceed to checkout" can't resolve
because the scraper visited `/view_cart` in a fresh browser context with no items added.
Even tests WITH prerequisite add-to-cart steps (TC01.05) resolve cart assertions to
`#empty_cart` — the scraper's data is from an empty cart.

**Concrete failure (automationexercise.com, 2026-07-20):**
```python
def test_tc01_07(page: Page, evidence_tracker):
    evidence_tracker.navigate("https://automationexercise.com/view_cart")
    pytest.skip("Skipping: unresolved placeholders for: 'Proceed to checkout'")
    evidence_tracker.assert_visible("#empty_cart", label="order summary")
```
The test jumps straight to `/view_cart`. The scraper visited that URL in a fresh session,
found an empty cart, and only `#empty_cart` elements were captured. "Proceed to checkout"
never existed in the scraped DOM → placeholder can't resolve → test skipped.

**Secondary symptom — POM duplication:** Every test in the generated file has duplicate
POM instantiations:
```python
home_page = HomePage(page, evidence_tracker)
home_page = HomePage(page, evidence_tracker)  # duplicate!
generated_page = GeneratedPage(page, evidence_tracker)
generated_page = GeneratedPage(page, evidence_tracker)  # duplicate!
```

**Root cause:** `PageScraper` opens a fresh browser context per URL. State-dependent pages
(view_cart, checkout, order confirmation) show different DOM depending on session state.
Elements only present with items in cart ("Proceed to checkout", cart table rows, quantity
columns) are absent from the scraped data.

**Proposed fix:**
1. When the pipeline detects placeholder descriptions referencing state-dependent pages
   ("Proceed to checkout", "cart table", "order summary"), trigger a **stateful journey scrape**
   that replays prerequisite steps (add to cart → view cart) before scraping
2. Or: the orchestrator should detect that TC01.07's first step is a direct navigation to
   `/view_cart` and inject add-to-cart prerequisites from TC01.03/TC01.04 before scraping
3. Fix POM duplication: investigate `src/page_object_builder.py` instantiation logic

**Priority:** High — this silently corrupts all cart/checkout/order assertions. Tests either
skip (worst case) or resolve to empty-cart selectors (false green).
---

### REF-001 — Rename `src/ui_pipeline.py` / rethink `src/ui/` naming
**What:** `src/ui_pipeline.py` is shared pipeline orchestration used by both
`streamlit_app.py` (Streamlit UI) and `src/cli/pipeline_runner.py` (CLI UI).
The `ui_` prefix implies it's Streamlit-only, but it's infrastructure.
Similarly, `src/ui/` holds Streamlit components while the CLI lives in `src/cli/` —
both are user interfaces, so the naming is inconsistent.

**Proposed rename:**
- `src/ui_pipeline.py` → `src/pipeline.py` (or `src/pipeline_orchestration.py`)
- `src/ui/` → keep as-is for now (Streamlit-specific rendering) or rename to `src/streamlit/`
- Consider whether `src/cli/` and `src/ui/` should share a parent like `src/interface/`

**Impact:** Medium — affects imports in ~10 files. No logic changes.
**Priority:** Low — cosmetic, but prevents future confusion.

---

## 🆕 AI-037 — LV Insurance Resolution Gap Optimization

**Status:** 🟢 PHASE 3 COMPLETE 2026-07-31 — LV regeneration 62.5% → 79.2% (19/24), static eval 100%, 1928 tests pass
**Priority:** Medium (Tier 2 — Resolver Accuracy)
**Spec:** `docs/specs/FEATURE_SPEC_AI037_lv_insurance_resolution_gap.md`
**Handover:** `docs/sessions/2026-07-31_ai037_resolver_fixes.md` + `docs/sessions/2026-07-31_ai037_phase3_journey_guidance.md`
**Impact:** LV Insurance resolution 54% → 62.5% → 79.2% regeneration (resolver 100%)
**Estimated sessions:** 1-2 (2 done)

**📊 Diagnostic update 2026-07-31 (Phase 3):** Resolver-only eval shows LV Insurance at
**24/24 (100%)** — not 54%. The regeneration metric is dominated by LLM
skeleton-generation nondeterminism.

**Phase 3 findings (2026-07-31):**
1. **Ideal-skeleton experiment**: feeding the golden keys as a perfectly-structured
   skeleton through the LIVE pipeline hit 21/24 BEFORE the fix — proving the
   remaining gap was NOT the resolver's vocabulary but the LLM's step placement +
   a scraper visibility bug.
2. **Scraper visibility bug (fixed)**: `JourneyScraper._scrape_current_page` never
   revealed SPA hidden sections before capturing, so every element on a non-active
   SPA section was marked `is_visible=False` and Pass 3 hard-skipped hidden
   CLICK/FILL targets. The frozen eval data (`refresh_lv_capture.py`) applied
   `_reveal_hidden_sections` — the live journey capture didn't. Fix: mirror the
   frozen methodology inside `_scrape_current_page`.
3. **Golden validator has-text gap (fixed)**: the resolver correctly returned
   `h2:has-text("✅ Quote Generated Successfully!")` (the real heading inside
   `#quoteSuccess`) but the golden tolerance `h2:has-text('Quote Generated')`
   didn't match — Playwright `has-text` is substring semantics, the validator was
   doing exact string compare. Fix: substring equivalence in `_locators_match`.

**Phase 3 shipped (2026-07-31):**
- ✅ **Skeleton prompt journey-structure guidance** (`src/prompt_builder.py` +
  `src/prompt_utils.py`, kept byte-identical): "fill ALL fields on the current
  page BEFORE navigating (Next) to the next page; never place a step after the
  navigation that leaves its page; do NOT emit pytest.skip; use the exact labels
  from the story" — in both `build_skeleton_prompt` and
  `build_single_condition_prompt`
- ✅ **SPA reveal on capture** (`src/journey_scraper.py` `_scrape_current_page`)
  — live captures now match the frozen-capture methodology (24/24 resolver
  parity on the ideal skeleton)
- ✅ **has-text substring equivalence** (`scripts/eval/golden_validator.py`)
  + 2 regression tests (`scripts/eval/golden_validator_test.py`)

**Results (2026-07-31 Phase 3):**
- Ideal-skeleton live pipeline: 21/24 → **24/24**
- A/B UAT (`uat_tstring_prototype.py`): LEGACY **20/24**, TSTRING 16/24
  (LLM nondeterminism dominates — both prompts byte-identical)
- Official regeneration (`eval_harness.py run --regenerate`): LV **19/24 (79.2%)**
  (was 15/24 = 62.5%), theinternet 7/7, overall 56.7% → 59.7%
- Static eval: 100% all sites · 1928 tests · ruff/mypy clean
- Remaining LV misses (5/24): CLICKs resolved to `#quoteSubmit` when the LLM
  emits generic descriptions ("Submit", "Next") instead of page-specific ones
  — pure skeleton sampling noise, resolver handles identical descriptions 24/24

**Anti-goal (confirmed):** do NOT add an insurance vocabulary list to
`TOKEN_EXPANSIONS` — it duplicates the DOM's own label text and doesn't scale
across domains. Phase 3 verified the pipeline itself resolves 24/24 when the
skeleton is correctly structured.

**Follow-up options (future):**
- If regeneration stability matters for CI: run skeleton generation with
  `temperature=0` (Phase 1d already does this) or add a deterministic
  skeleton→golden-alignment post-pass
- saucedemo/automationexercise regeneration scores fluctuate with LLM sampling
  — static gate stays 100%

### ✅ Shipped 2026-07-31 (Phase 1-2) — all structural, NO vocabulary list

- **Radio/checkbox label capture** (`src/scraper.py`) — radios wrapped in `<label>`
  get accessible_name ("Social, Domestic & Pleasure" was previously lost)
- **Clickable div capture** (`src/scraper.py`) — divs with explicit id kept even
  without direct text (`#productCar`, `#paymentFull`) — B-025 click-target premise
- **`<strong>` in display_tags** (`src/scraper.py`) — `#quoteRef` was never captured
- **Synthetic ARIA marker** (`src/scraper.py`) — Pass-2 containers flagged `synthetic_id`
- **Radio locator format** (`src/locator_builder.py`, `scripts/eval/eval_resolver.py`)
  — `input[name][value]` disambiguates radio groups
- **Quote-agnostic locator normalization** (`scripts/eval/golden_validator.py`)
- **camelCase in `get_words()`** (`src/semantic_matcher.py`) — `#vehicleReg` → "vehicle Reg"
- **Pass 1 synthetic skip** (`src/element_matcher.py`) — synthetic groups no longer
  win fast-text over real radios
- **Radio CLICK bonus + synthetic exclusion** (`src/placeholder_scorers.py`)
- **Proportional text bonus + punctuation normalisation** (`src/placeholder_scorers.py`)
- **`scripts/eval/refresh_lv_capture.py`** (new) — journey-state capture for frozen eval data
- 15 new tests (`tests/test_scraper_ai037.py`, `tests/test_ai037_resolver_fixes.py`)

**Results (2026-07-31):**
- Resolver eval (frozen data): LV **24/24 (100%)**, overall **59.7%** (was 58.2%), no regression elsewhere
- Full regeneration UAT: LV **15/24 (62.5%)** (spec baseline 54%), overall 56.7%
- Static eval 100% · 1928 tests · ruff/mypy clean

### ✅ Phase 3 (COMPLETE 2026-07-31): skeleton journey-structure guidance

Shipped: prompt journey guidance (both skeleton + single-condition prompts) +
SPA reveal-on-capture fix in `JourneyScraper._scrape_current_page` + has-text
substring equivalence in `golden_validator.py`. Result: LV regeneration
15/24 → 19/24 (79.2%), ideal-skeleton pipeline 21/24 → 24/24.
See `docs/sessions/2026-07-31_ai037_phase3_journey_guidance.md` for full detail.

**Original problem statement:** The remaining LV gap is NOT the resolver (100% on
identical descriptions). The LLM skeleton places steps on the wrong page →
wrong-page resolution. Evidence (9 misses):
`first name`/`postcode` → `#paymentFull`, `usage type`/`Add Vehicle` → `#quoteSubmit`.

**Levers:** skeleton prompt guidance in `src/prompt_builder.py` (now t-string structured):
"fill all fields on the current page before navigating; never place a field after
reaching a later page". Verify via `uat_tstring_prototype.py` / `eval_harness.py run --regenerate`.

**Anti-goal (confirmed):** do NOT add an insurance vocabulary list to `TOKEN_EXPANSIONS` —
it duplicates the DOM's own label text and doesn't scale across domains.

**What:** After the SPA scraper fix, LV Insurance resolution jumped 0% → 54%. The remaining
46% (11/24 placeholders) fail due to description-to-element mismatches — the skeleton says
"vehicle registration number" but the DOM has `#vehicleReg` labelled "Registration Number".
The resolver's token-matching pipeline lacks insurance-specific vocabulary.

**Phases:**
1. **Diagnostic** — Classify each failing placeholder into: synonym gap, description
   mismatch, scraper blind spot, scoring underflow, or page-not-found. Produce a structured
   report.
2. **Token Expansion** — Add insurance terms to `TOKEN_EXPANSIONS` in `semantic_matcher.py`
   (registration, license, occupation, scheme, premium, excess, overnight, NCD, usage).
   Wire `_split_camel_case` into `get_words()` so `#vehicleReg` → "vehicle Reg" → "vehicle
   registration".
3. **Description Cleanup** — Optional: tune skeleton prompt or post-process descriptions to
   match observed DOM labels.
4. **Scoring Tuning** — Optional: adjust thresholds/bonuses if underflow or false positives
   are detected.

**Success criteria:**
- LV Insurance linear resolution: 54% → ≥80% (19/24)
- LV Insurance graph resolution: 50% → ≥75% (18/24)
- Static eval (all 5 sites): 100% (no regression)
- Overall linear regeneration: 56.7% → ≥65%

**Related:** B-016 (synonym matching), AI-031 (resolver accuracy), AI-030 (mock site)

---

## 🆕 AI-038 — Unlimited OCR ROCm/AMD Compatibility Test

**Status:** 👤 DEFERRED 2026-08-07 — blocked by ROCm-on-Windows Python ABI ceiling; revisit when AMD ships ROCm torch for py≥3.13 or the project drops to 3.12
**Priority:** Low — future enhancement  
**Spec:** `src/ocr_backends.py` (Phase 1i)  
**Estimated sessions:** 0.5

**What:** Test Baidu's Unlimited-OCR 3B vision model on the Strix Halo AMD APU
(64GB unified memory) with a ROCm-compatible PyTorch build. The adapter is already
built (`OCR_BACKEND=unlimited-ocr`), but the model uses `trust_remote_code=True`
which may contain CUDA-specific kernels that fail on ROCm/HIP.

**Investigation 2026-08-07 — root cause found, feature deferred:**
1. **AMD installer silently skips the GPU stack on this laptop.** Its own log
   (`AMDInstallManager/Logs/CommonLibrary_Install.log_2026-8-7_8_26_42.log`) shows
   `DEBUG_ISHALOBOX registry key not found. Assuming not a HaloBox` — the
   Ryzen AI MAX+ 395 / Radeon 8060S is Strix Halo, but the installer's
   HaloBox detection failed, so it downloaded the ROCm/torch wheels
   (7.2.0.dev0, May 2026) and then **installed nothing**.
2. **No ROCm torch exists for Python 3.14 on Windows — this is the hard wall.**
   Verified across every source: the AMD Windows wheel repo
   (`repo.radeon.com/rocm/windows/rocm-rel-7.2.1`, Feb 2026 — fresher than the
   installer's 7.2.0) ships only `torch-2.9.1+rocm7.2.1-cp312-cp312-win_amd64.whl`;
   pytorch.org's ROCm index resolves no torch for 3.14; and the project venv is
   Python 3.14.5. PyTorch proper supports 3.14 (CPU + CUDA cp314 wheels exist),
   but **AMD's Windows ROCm wheels cap at cp312**. The OCR backend runs
   in-process (`get_ocr_backend()` in `src/agents/pipeline_graph.py`), so even a
   3.12 side-env install would need a subprocess bridge to be usable.
3. **Verdict per the item's own step 4** ("document limitation, keep PyMuPDF as
   default"): documented. PyMuPDF remains the OCR default; `unlimited-ocr` stays
   opt-in. Revisit when (a) AMD ships ROCm Windows wheels for py≥3.13, or (b) a
   3.12 side-env + subprocess OCR bridge is wanted, or (c) the Qwen-3.8-27B
   training work (below) already builds a 3.12/ROCm side-env worth reusing.

**Unblocking note (2026-08-07):** the fresh ROCm 7.2.1 wheels are available at
`repo.radeon.com/rocm/windows/rocm-rel-7.2.1/` for a Python 3.12 env. If the
Qwen training effort creates a dedicated 3.12 + ROCm environment, the same env
can run Unlimited-OCR via a subprocess bridge — the two deferrals share one
unblock.

**Steps (when unblocked):**
1. Install ROCm PyTorch 7.2.1 into a Python 3.12 env (replace `torch 2.13.0+cpu`)
2. Run `OCR_BACKEND=unlimited-ocr` against sample PDFs
3. If the model loads and infers successfully → enable as default for document
   mode when GPU is available
4. If custom CUDA kernels fail → document limitation, keep PyMuPDF as default

**Blocked by:** ROCm torch for Windows requires Python ≤3.12; project venv is 3.14

---

## ✅ AI-040 — Fine-Tuning Dataset Generation Tooling (TOOLING COMPLETE 2026-08-09 — training is AI-041)

**Status:** ✅ Complete (tooling + corpus + baseline shipped 2026-08-07/09); the actual training run is tracked as **AI-041**
**Priority:** Medium — enables the Qwen training effort referenced by AI-038
**Spec:** `scripts/build_finetune_dataset.py`, `scripts/synthesize_stories.py`, `training_data/`

**What:** Two scripts + a seed corpus that convert the pipeline's own artifacts into
instruction-tuning datasets for Unsloth Studio (or any SFT trainer):

- `build_finetune_dataset.py` — extracts (story → skeleton) Alpaca rows from
  `generated_tests/*/scrape_manifest.json` + the eval datasets, and (placeholder →
  locator) rows from eval golden keys. Emits `playwright_skeleton_alpaca.jsonl`
  and `playwright_resolution_alpaca.jsonl`.
- `synthesize_stories.py` — LLM-synthesizes new stories per eval site (anchored to a
  real element inventory so no hallucinations), runs the offline Phase-1 skeleton
  generator, validates through the same gates production uses
  (`normalise_placeholder_actions` → `validate_skeleton` → criteria-count check),
  and merges passing rows. `--mode linear|graph|both` (graph is deterministic,
  temp=0 — run once; linear is stochastic — rerun for diversity).

**Dataset state (2026-08-08):** 172 skeleton rows (22 generated + 7 eval + 143
synthetic), 90 resolution rows, **112 resolved-code rows** (story → resolved
test code, all 7 sites, 3464 evidence calls — from the `--resolve-and-learn`
full combo run: mocks × RAG on+off 56 passed / 6 failed, live × RAG on
20 passed / 23 failed). Verified: ruff ✓, mypy ✓, pytest ✓.

**Why it matters:** the 90 resolution pairs target AGENTS.md §13's open issue
(ASSERT placeholder resolution, 79.1% eval baseline) — a small LoRA on that set is
the fastest measurable pipeline win. The skeleton set is seed capital for a
story→code model. Both are input to the Qwen training effort AI-038 references.

**Blocker found while building (2026-08-07):** llama-server was launched with
`--ctx-size 156072` (156K context) — KV cache alone ~25 GB pinned against the
48 GB Strix Halo UMA, causing `vk::Queue::submit: ErrorOutOfDeviceMemory` on long
decodes. Relaunched at `--ctx-size 9072`; server healthy, suite green.

**B-047 found 2026-08-08 (multi-mock site_hash collision — pre-existing, protected code) — ✅ FIXED 2026-08-08:**
`domain_from_url()` in `src/rag_learn.py` stripped the port, so all localhost mock
sites (banking:8782, ecommerce:8783, lv_insurance:8781) shared one `site_hash`.
**Fix:** `domain_from_url()` now returns the full `netloc` (`host[:port]`,
lowercase, userinfo stripped) — both learn and resolve paths route through it,
so per-origin scoping is automatic; real sites (no port) are unchanged.
Regression coverage: `test_concurrent_mocks_scope_independently`,
`test_mock_ports_hash_distinctly`.

**Second root cause found while fixing B-047 — MockServer class-attribute leak
(`scripts/mock_server.py`, FIXED):** `SERVE_DIRECTORY`/`ROUTES` were base-class
attributes, so when `resolve_and_learn` started 3 mock servers in one process,
every port served the LAST-started directory (ecommerce HTML on the banking
port). This — not the site_hash alone — was the dominant contamination vector:
banking stories resolved ecommerce selectors (`#name`, `a[href="/products.html"]`,
`p:has-text("Stylish Dress")`) even in RAG-off runs. Fix: per-server handler
classes with their own `SERVE_DIRECTORY`/`ROUTES`. Regression test:
`test_multi_mock_servers_serve_own_directories`.

**Data cleanup (training quality):** 42 contaminated resolved rows
(banking_mock 25 + lv_insurance 17) purged from
`training_data/playwright_resolved_alpaca.jsonl`; re-ran
`resolve_and_learn --rag-both` for the 3 mocks → 52 clean site-correct rows
appended (122 total, 0 cross-site leaks, verified by selector-marker scan).
Purged 26 inert `site_hash=sha256("localhost")` learned patterns from the RAG
store (they could never match post-fix; store now 83 golden + 27 doc + 5
learned, all correct). **Known follow-up (evidence-backed 2026-08-09):
`learn_from_evidence` inside the pytest subprocess cannot open the Milvus
store while the resolve-and-learn parent holds it.** Controlled A/B proved:
(1) fresh process → subprocess learning works (inserted=1); (2) parent opens
store, `del` + `gc.collect()`, then subprocess → `DataDirLockedError: another
process holds the lock on evidence/rag_store.db` — the Milvus-lite lock is
held for the parent's ENTIRE lifetime, so EVERY subprocess hook in a
resolve-and-learn run fails silently (the conftest try/except swallows it).
The orchestrator opens the store on the first RAG-on pass (retriever
retrieve), so RAG-off passes are also blocked for the rest of the process.
Observed: learned count 27 → 27 across the 2026-08-08 3-mock re-run despite
27 passing tests; an instrumented single-file run (no holder) learned OK and
hit-bumped an existing pattern (hits 1→2). The historical 17→27 growth
provenance (resolved 2026-08-09): the 17-pattern baseline pre-dated the
2026-08-07/08 resolve-and-learn sessions — it came from prior uncontended mock
executions (2026-08-04 session's self-healing demo artifact `CLICK 'Cart link'
→ a[href="/cart.html"]` documented in
`docs/sessions/2026-08-04_consumer_config_and_self_learning_rag.md`, plus
eval-006's "8/8 execution passed" and earlier eval/UAT mock runs — the same
UAT / eval `--run` / verify_production phases cited below). The +10 (17→27)
was learned IN the 2026-08-07/08 session by the one uncontended standalone
ecommerce test (mock server up, no parent store-holder); the batch and
full-combo resolve-and-learn runs contributed 0 (lock-blocked). All 26 purged
patterns share `sha256("localhost")` because B-047's port-stripping was live
throughout — regardless of which session produced them, they were inert
post-fix, so the purge was correct.

**Fix — ✅ SHIPPED 2026-08-11 (`e03ee0e`, "RAG learning lock"): parent-side
sweep of `evidence/*.evidence.json` sidecars after each site's executions.
`learn_from_evidence_sidecars()` (`src/rag_learn.py`) runs IN the parent
process (no lock contention), same dedup + site scoping as the conftest
hook; the AI-042 flow-memory legs (`learn_from_sidecars` + F3
`learn_suite_flows`) ride the same per-site sweep (plain JSON store). Wired
in per-site in `scripts/synthesize_stories.py` `resolve_and_learn`; the
conftest subprocess hook stays for non-batch runs (UI/CLI/CI single runs
where no parent holds the store). Wired-in guards: `tests/test_script_hooks.py`
(presence + evidence-dir target + per-site loop placement). Live-verified
2026-08-15: parent holds the store → subprocess open blocked (as diagnosed)
→ parent-side sweep of 5 passed sidecars learned 9 new + 1 repeat in-process
(store 13 → 22 learned); 48/48 `tests/test_rag_learn.py` + full suite green.

**Completed follow-ups (2026-08-09):** dataset cleaned (--clean filter, 55
hallucinated-login rows dropped), skeleton prompt fixed (DO-NOT-INVENT-AUTH),
login URL resolution fixed, ecommerce skeletons regenerated, model-level
baseline captured with full reproducibility envelope. Full runbook in
`docs/sessions/2026-08-09_unsloth_training_runbook.md`.

**Next steps (now tracked as AI-041):**
1. Run the Unsloth Studio QLoRA training (see runbook §4)
2. Re-run `eval_model_baseline.py` against the fine-tuned model; compare
3. Decide where the fine-tuned model plugs into the pipeline (skeleton vs resolver)
4. ✅ (B-047) port-aware site_hash + MockServer multi-server fix (2026-08-08)

---

## 🆕 AI-041 — Unsloth Studio QLoRA Training Run (❌ FAILED / CLOSED 2026-08-11; DEFERRED indefinitely 2026-08-15)

**Status:** ❌ failed — training worked (Qwen3.6-27B 4-bit QLoRA, loss 0.94→0.081) but the GGUF export never completed; no usable model produced; all artifacts deleted (2026-08-11). **Deferred 2026-08-15:** no retry planned until Unsloth/Windows fixes unified-memory detection — the 55.6 GB fp16 model cannot fit the 53.9 GB usable ceiling (LoRA OOM'd at full precision; QLoRA's 4-bit in-memory quantize peaked at 50.94 GB and crashed the HIP driver). The 52 GB HF-cache download was deleted 2026-08-15 to reclaim space.
**Priority:** High — the payoff for AI-040's corpus + baseline
**Spec:** Unsloth Studio (localhost:8888), `training_data/`, `scripts/eval/eval_model_baseline.py`

**Why it failed:** the GGUF export needs a 16-bit merge (~55 GB) that a 64 GB Windows box can't produce — unsloth's `merged_16bit` save doesn't merge, `merge_and_unload` doesn't exist on the Qwen3.5 architecture, memory caps at ~46 GB, disk peak needs ~110 GB. Studio's Train UI additionally flips 4-bit→16-bit for Qwen3.6 (fused-CE crash), which a direct script worked around.

**Field guide (full write-up incl. what worked + dead ends):** `docs/sessions/2026-08-10_strix_halo_27b_qlora_field_guide.md`

**Recommendation for a future attempt:** train a **14B bnb-4bit** model on this hardware (export fits: ~28 GB merge + ~9 GB GGUF) — or retry the 27B on a machine with ≥110 GB free disk AND ≥55 GB addressable memory (e.g. Linux/128 GB Strix Halo).

**What:** Fine-tune a QLoRA on the clean training corpus (158 skeleton + 96
resolved + 90 resolution rows), export to GGUF, swap into the pipeline, and
measure the before/after delta with the captured baseline.

**Runbook:** `docs/sessions/2026-08-09_unsloth_training_runbook.md` — model
choice (safetensors, NOT NVFP4/GGUF), Studio settings table, export + model
swap (no .env edit — auto-detect via /v1/models), baseline comparison.

**Hardware:** AMD Strix Halo (gfx1151) — Unsloth AMD support is FULL; training
is bitsandbytes-based QLoRA (4-bit).

**Current model baseline (before):**
`training_data/model_baseline_qwen36_27b_ud_q4_k_xl.json` — valid skeleton
100%, criteria cover 100%, hallucinated login 0%, eval static 97.9%.

**Steps:**
1. Studio: QLoRA, `Qwen/Qwen3.6-27B`, upload skeleton dataset, Train on
   Completions ON (runbook §4)
2. Export GGUF q4_k_m → `~/.lmstudio/models/unsloth/`
3. Load fine-tuned model on :8080 (pipeline auto-detects)
4. `eval_model_baseline.py` + `eval_harness.py run --mode static` → compare

---

## 👤 AI-044 — Visual Grounding: vision-based element location (DEFERRED)

**Status:** 👤 Deferred 2026-08-13 — decision: use an off-the-shelf GUI-grounding model instead of training one; fine-tune only if eval shows a domain gap
**Priority:** Low-Medium (portfolio + long-term differentiator) — "sees the page like a tester does"
**Roadmap ref:** `docs/plans/ROADMAP_ROADTO_PRODUCTION.md` Tier 4 §18
**Original estimate:** 5-8 sessions

**Why deferred:** (1) AI-041 — the training-pipeline dependency — was closed FAILED 2026-08-11 (GGUF export physically impossible on 64GB Windows); (2) verified via tavily (2026-08-13) that open-source GUI-grounding models already do the core task: **UGround** (10M elements / 1.3M screenshots, ~95% web, LLaVA-based, SOTA on ScreenSpot), **OS-Atlas** (2.23M cross-platform), **UI-TARS**, **GUI-Actor** (attention-map grounding, no numeric coords). The product value (use screenshots for location; heatmap boxes from detection) is fully achievable off-the-shelf; training-own only pays off as a fine-tune-on-own-sidecars LoRA *after* measuring a gap.

**If resurrected, slim scope (AI-044-B, ~1-2 sessions):** pick UGround/ShowUI → wire vision score into `compute_element_score` as tie-break/pre-filter → eval bbox-IoU metric via AI-043's alignment layer → latency budget (CPU-only on this box; AI-038's ROCm wall applies) + DOM fallback. Fine-tune later only if eval shows a gap.

---

## 👤 AI-039 — Repo Rename: TanCat (DEFERRED)

**Status:** 👤 ready-for-human — deferred by decision 2026-08-01; revisit at launch readiness
**Priority:** Medium — GTM (Phase 8)
**Estimated sessions:** 0.5

> **Why deferred:** Renaming the repo + PyPI package is disruptive once the package is
> published (users, CI, docs links depend on the name) and carries zero functional value
> pre-launch. Parked until the product is ready for launch; branding decisions (TanCat
> product name, Cat Tan Operations Ltd, domains) stay as decided.

**What:** Rename GitHub repo from `AI-Playwright-Test-Generator` to `tancat`.
Update all internal references: `pyproject.toml` (PyPI package name), README,
docs headers, script docstrings, CI badge URL. Regenerate graphify output.

**Product name:** TanCat (`pip install tancat` / `uv add tancat`)
**Holding company:** Cat Tan Operations Ltd (cattanooperations.co.uk)
**Domains acquired:** tancat.dev, cattanooperations.co.uk, cattanooperations.com

**Launch-batch dependencies (grilled 2026-08-13, Phase 7 CI/CD):** the rename is the same
launch-readiness gate that governs the Phase 7 GitHub Action extraction — at launch,
extract a **thin public Action repo** (`action.yml` + `entrypoint.sh` + `Dockerfile`) whose
image installs the product from PyPI (the product repo stays private). The rename
determines the Action's owner reference (`tancat/ai-test-generator@v1`) and the PyPI
package name — both are post-rename constants. Spec: `docs/specs/FEATURE_SPEC_phase7_ci_cd_integration.md`
§Q4; keep `ci_generate.py` imports package-relative (`playwright_test_generator.…`) so the
extraction is copy-paste, not refactor. GitHub Marketplace requires a **public** repo +
semver release tags (same-repo listing is allowed but the thin-repo split is cleaner);
AWS/Azure marketplaces consume the Docker image/AMI, not the repo layout.

---

## ✅ AI-033 — Python T-String (PEP 750) Upgrade — ANALYSIS COMPLETE + PROMPT LAYER MIGRATED

**Status:** ✅ Complete 2026-07-31 (analysis + prompt-layer migration shipped)
**Priority:** Medium — technical debt / future-proofing
**Impact:** Prompt assembly now structured + auditable; Jinja2 blocker resolved

**What:** Evaluate and plan migration to Python t-strings (PEP 750, Python 3.14) for
internal template strings in the codebase.

**Original question:** Whether t-strings can separate LLM calls from other things
(structured rendering, audit trails, injection-aware transforms).

### ✅ Resolution — the Jinja2 blocker is NOT a blocker for the prompt path

**Critical finding disproved by implementation:** the original spec assumed
``{{CLICK:description}}`` double-brace skeleton placeholders would conflict with
t-string ``{expression}`` interpolation. In practice t-strings escape ``{{`` the
same way f-strings do — so ``t"...{{CLICK:x}}... {user_story}"`` renders literal
``{CLICK:x}`` *and* interpolates ``{user_story}`` side by side. Byte-identical to
the legacy ``.format()`` output (verified by UAT, 2886 chars, both count variants).

### ✅ Delivered 2026-07-31

- **`src/prompt_builder.py`** (new, PEP 750) — `PromptBuilder` + `RenderedPrompt`:
  renders a `Template` with per-field transforms keyed by `Interpolation.expression`,
  records structured metadata (fields, truncated, static-vs-dynamic parts),
  exposes `to_log_entry()` for structured audit logging. LangChain-parallel:
  declare template in code, bind variables, render — no runtime template parsing.
- **`build_skeleton_prompt()`** — t-string skeleton prompt, byte-identical to legacy.
- **`build_single_condition_prompt()`** — t-string single-condition prompt. Fixes a
  latent inconsistency: the legacy function sent literal `{{CLICK:...}}` (double
  braces) to the LLM while the main skeleton prompt sent `{CLICK:...}`. Now both
  render single braces (parser accepts both).
- **Wired into `src/test_generator.py`** `_generate_skeleton_single_call` and
  **`src/orchestrator.py`** `_generate_single_condition_fragment` — both now log
  `llm_call=... fields={...}` structured audit entries (prompt text to the LLM,
  metadata to the audit trail — the "separate LLM calls from other things" pattern).
- **`tests/test_prompt_builder.py`** (13 tests) — byte-identity, brace survival,
  per-field truncation, audit metadata. Full suite: 1913 passed.
- **UAT** (`scripts/eval/uat_tstring_prototype.py` + `scripts/eval/generated_tests/`)
  — prompts byte-identical; post-wiring regeneration variance (LEGACY 54.2→50%,
  TSTRING 50→37.5%) confirmed to be LLM skeleton sampling, not prompt-path change.

**Not migrated (deferred, separate work):** Streamlit HTML blocks, evidence/report
generation templates — no prompt-assembly benefit; double-brace skeleton
placeholders were the only compatibility question and it is resolved.

**Files:**
- `src/prompt_builder.py` (new)
- `src/test_generator.py` (wired)
- `src/orchestrator.py` (wired)
- `tests/test_prompt_builder.py` (new)
- `scripts/eval/uat_tstring_prototype.py` (new)

**Estimated sessions:** 1 (analysis) + 1 (migration)

**Background:** T-strings (`t"..."`) are a new string type introduced in Python 3.12 that:
- Provide lazy evaluation of embedded expressions
- Offer better introspection of string structure
- Are designed for use cases where the string structure matters

**Current State:** Project requires Python 3.14+ (fully supports t-strings). Current `.format()` usage:
- `src/agents/generator.py` — GENERATOR_USER_PROMPT_TEMPLATE
- `src/agents/planner.py` — PLANNER_USER_PROMPT_TEMPLATE
- `src/test_generator.py` — `get_skeleton_prompt_template()`
- `src/prompt_utils.py` — multiple template strings

**⚠️ Critical Finding — Jinja2 Conflict:**
The project uses Jinja2-style double-brace placeholders (`{{CLICK:description}}`, `{{FILL:...}}`, `{{ASSERT:...}}`) for LLM prompts. T-strings use `{expression}` syntax which **directly conflicts** with these placeholders.

**Where T-Strings Would Have Most Impact:**
1. **Prompt templates** (`src/prompt_utils.py`, `src/agents/generator.py`, `src/agents/planner.py`) — could enable lazy evaluation of user story/conditions
2. **HTML generation** (`src/cli/evidence_generator.py`) — cleaner string interpolation
3. **Report generation** (`src/cli/report_generator.py`) — structured templates

**Where T-Strings Won't Work (Without Major Changes):**
1. **Skeleton generation** — `{{CLICK:description}}` syntax conflicts with t-string `{expression}` syntax
2. **Credential substitution** (`src/journey_models.py` `substitute_templates()`) — uses `{{username}}`/`{{password}}` pattern
3. **Streamlit UI HTML blocks** — inline HTML with Jinja2-style interpolation

**What We're Waiting For:**
1. **Decision on Jinja2 migration** — Either:
   - Migrate to Jinja2 templates (breaks current LLM prompt format)
   - Use alternative placeholder syntax (e.g., `{{{description}}}` or `$description`)
   - Keep double-brace for LLM prompts, use t-strings only for internal templates
2. **Jinja2 library evaluation** — If Jinja2 is adopted, assess:
   - Version compatibility with Python 3.14
   - Impact on Streamlit rendering
   - Performance for HTML report generation
3. **Migration strategy** — Need clear plan for:
   - Which templates to migrate first (high-impact, low-conflict)
   - Backward compatibility during transition
   - Testing approach for migrated templates

**Potential Approach:**
1. **Phase 1:** Use t-strings for non-LLM templates (logging, report filenames, session state)
2. **Phase 2:** Evaluate Jinja2 adoption for HTML generation (Streamlit, evidence reports)
3. **Phase 3:** Decide on LLM prompt placeholder strategy — migrate to single-brace or adopt Jinja2

**Files to Analyze:**
- `src/prompt_utils.py` — template string usage analysis
- `src/agents/generator.py` — prompt template structure
- `src/agents/planner.py` — prompt template structure
- `src/cli/evidence_generator.py` — HTML generation patterns
- `src/cli/report_generator.py` — report template patterns

**Estimated Sessions:** 1-2 (analysis + proof of concept)

---

## ✅ B-027 — Requirements with distinct concerns generate single test case instead of multiple (FIXED 2026-08-01)

**Status:** ✅ Fixed 2026-08-01 (second attempt — the original 2026-07-24 fix was REVERTED as too aggressive)
**Priority:** Medium  
**Commits:** `db77c46`, `26bb827` (REVERTED in `5071621` 2026-07-29 — naive comma-splitting mangled narrative stories and broke golden-key alignment) → real fix 2026-08-01 (uncommitted at time of writing)
**Impact:** Unstructured requirements with multiple distinct concerns (e.g. "max items, max quantity, filters") produce only one happy-path test case instead of focused boundary/functional tests

**Real fix (2026-08-01):**
1. **Prompt** — `SpecAnalyzer.SYSTEM_PROMPT` gains SPLITTING RULES: one condition per distinct concern, `boundary` for limit questions, DO NOT collapse/skip.
2. **Routing** — `parse_requirements_text` wraps unstructured input as a single numbered item ("1. <story>"); a single numbered criterion with multi-concern signals now routes to the LLM path instead of the deterministic 1:1 mapping.
3. **JSON hardening** — prompt forbids verbatim quoting in `source`; retry-once with CORRECTION on parse failure; partial salvage (silently dropping corrupted objects) now raises so the retry fires.
4. **Conservative fallback** — if the LLM still collapses, split on sentence boundaries only (never mid-sentence commas — the revert lesson) and tag limit sentences `boundary`.

**Verified (real LLM, exact UI flow):** user story → 3 conditions (journey happy_path + 2 boundary). 22 spec_analyzer tests, 1998 total.

**Symptom:**
When a user enters requirements like:
```
changes made to the site around maximum amount of items purchaseable, maximum quantity of items and filters.
```
The pipeline produces only one test case:
```
TC01.01    happy_path    journey_step    ...maximum amount...    Meets acceptance criteria.
```
Expected: three focused test cases:
- TC01.01 — boundary: max different items purchasable
- TC01.02 — boundary: max quantity per item
- TC01.03 — filter functionality (ordering, missing items)

**Root cause:**
1. `FeatureParser.parse()` can't parse unstructured text (no "User Story:" / "Acceptance Criteria:" format) — falls through to `return cleaned, cleaned`
2. `SpecAnalyzer._extract_numbered_criteria()` only handles numbered lists (`1. ...`), not comma-separated concerns
3. LLM collapses three distinct concerns into one "happy_path" test case

**Proposed fix:**
1. **Short term:** Update `SpecAnalyzer._extract_numbered_criteria()` to also detect comma-separated or bullet-point concern lists in unstructured text and split them into separate criteria
2. **Medium term:** Add a pre-processing step that detects multiple distinct domains (amount, quantity, filters) before sending to the LLM and requests separate test conditions per domain
3. **Long term:** Add an LLM prompt instruction: "If the spec text contains multiple distinct concerns separated by commas or conjunctions, generate one test condition per concern"

**Files to modify:**
- `src/spec_analyzer.py` — `_extract_numbered_criteria()` or LLM prompt
- `src/user_story_parser.py` — `FeatureParser.parse()` for unstructured text
- `tests/test_spec_analyzer.py` — add regression test for comma-separated specs

**Estimated sessions:** 0.5-1

---

## ✅ AI-034 — Test Table Generation (COMPLETE 2026-08-01)

**Status:** ✅ Complete — Phases 1-3 shipped 2026-08-01
**Spec:** `docs/specs/FEATURE_SPEC_AI034_test_table_preflight.md`
**Note:** Pre-flight resolution reporting stripped from spec 2026-07-31 — the resolver already surfaces failures via `pytest.skip()` + evidence (AI-028).

**What:** A Test Table between Living Test Plan and skeleton generation. The LLM
expands each condition into one or more concrete test rows (e.g., "4 filters" →
4 rows); the tester reviews/edits/confirms rows before one skeleton is generated
per row.

**Delivered:**
- **Phase 1** — `src/test_table.py` (NEW): `TestRow`/`TestTable` data model + CRUD
  (add/remove/update/confirm per-row & per-condition), `TestTableExpander` (LLM
  expansion, 1-row-per-condition fallback on LLM failure, cap `DEFAULT_MAX_ROWS_PER_CONDITION=10`),
  `build_table()`, `apply_editor_rows()`. 33 unit tests.
- **Phase 2** — editors in **both** UIs: Streamlit `🧪 Test Table` expander
  (data_editor + Save/Confirm-All) and CLI "Expand into Test Rows" menu flow
  (`build_test_table_interactive`); LTP gains a disabled "Tests" column via
  `plan_rows_from_plan(plan, test_table)`.
- **Phase 3** — one skeleton per confirmed row: `table_to_conditions()` converts
  confirmed rows → `TestCondition`s (id=row.id, text=intent+target); wired into
  `reviewed_conditions` (Streamlit) and `_select_conditions_for_generation()` (CLI).
- **UAT** — `scripts/uat/uat_test_table.py` (real LLM): 2 conditions → 8 rows → 8
  skeleton functions (1:1, no skips). UI-verified: 9 rows → 9 test functions, live run.
- **Regressions:** none — full suite 1998 passed, static eval 100%.

---

## 🟡 Active Improvements (Prioritised)

## 📌 LangGraph Pipeline — Dormant / Not Wired into User Flow (documented 2026-08-01)

**Status:** 📌 Documented — no code change required (code-state note; the hybrid plan lives in ROADMAP §12d)
**Related:** Phase 1 Multi-Agent (ROADMAP §12 → hybrid §12d), `src/agents/pipeline_graph.py`

**Finding (2026-08-01):** The Phase 1 Multi-Agent LangGraph pipeline
(`PipelineGraph`, `TestOrchestrator.run_pipeline_via_graph()`) is built and
unit-tested but **NOT active for users**:

- The user-facing path (Streamlit, CLI, `scripts/uat.py`) always calls
  `TestOrchestrator.run_pipeline()` — the **linear** pipeline (single-call
  skeleton → scraper → resolver).
- The graph is reachable only via `eval_harness.py run --use-graph` and its
  own unit tests.
- `langgraph` is a **core dependency** — graph tests run locally AND in CI
  (71/71 pass). The `pytest.importorskip` guards only degrade gracefully in
  minimal installs.
- Code comments previously contradicted each other (default-on vs opt-in) —
  corrected 2026-08-01 in `src/orchestrator.py` + `src/test_generator.py`.
- Doc-mode (`input_mode="document"`, PDF/Markdown parsing + persona routing)
  exists in the graph but has **no UI/CLI entry point** — only tests exercise it.

**Impact on results:** None for published numbers — static eval (100%) and
regeneration eval use the linear path by default, matching what users run.
Graph tests run in CI (langgraph is core) and pass 71/71.

**Decision:** Linear remains the production path; the graph is experimental and
opt-in (reachable via `eval --use-graph` + unit tests). Revisit options:
(1) wire the graph in as default, (2) add a user-facing doc-mode entry
(PDF → LTP conditions).

### ✅ AI-009 — Multi-Page Scraping ✅ Phase A COMPLETE, ✅ Phase B COMPLETE (2026-05-13)
**Phase A:** Static multi-page scraping with placeholder resolution — COMPLETE.
**Phase B (completed 2026-05-13):** Authenticated journey scraping — single browser
session follows user-defined steps (goto, click, fill, capture, wait), credential profiles
in session state, auth redirect detection, SSO/MFA/CAPTCHA explicit errors.

**Phase B deliverables:**
- `src/journey_scraper.py` — `execute_journey()`, `JourneyScraper`, `CartSeedingScraper`, auth redirect/SSO/MFA/CAPTCHA detection
- `src/orchestrator.py` — journey execution integrated via `journey_steps` parameter in `run_pipeline()`; journey results merge with static scrape data
- `src/ui_pipeline.py` — bridges Streamlit UI data to `TestOrchestrator` with `credential_profile` and `journey_steps`
- Live verification: successful saucedemo.com journey (Login → Products → Cart) via Playwright MCP
- Test fix: `tests/test_stateful_scrape_switch.py` FakeStateful mocks updated to accept `credential_profile`
**Spec:** `docs/FEATURE_SPEC_AI009_phase_b.md`
**Priority:** Highest — core value driver

---

### ✅ AI-026 — Persist Generated Tests Across Sessions (COMPLETE — 2026-06-30)
**What:** CLI + Streamlit support to reload and rerun previously generated test packages from disk.

**Implementation:**
- ✅ Streamlit sidebar panel — `src/ui/ui_saved_packages.py` (264 lines) — list, select, re-run saved suites
- ✅ CLI menu — "Load Existing Generated Tests", "View Package Diagnostics" in `src/cli/main.py`
- ✅ Reuses `src/pipeline_writer.py`/`PipelineArtifactWriter` for save/load consistency
- ✅ `package_manifest.json` per saved package
- ✅ Re-run saved suite + re-run failed only
- ✅ Failure diagnostics viewer

**Priority:** Medium — improves workflow and debugging without changing core generation logic

---

## ✅ Completed: Refactor 2026-05-10 (Parts 1-7)

**Status:** Complete — May 2026. REFACTOR_PLAN_2026-05-10.md delivered.

**Summary:** Extracted 11 modules from 5 parent files, reducing `streamlit_app.py` from 918 → 362 lines (60% reduction). All quality gates passing: ruff clean, mypy clean, 541/541 tests passing, 68% coverage.

**Modules extracted:**
- `src/ui_pipeline.py` — Pipeline execution from `streamlit_app.py`
- `src/ui_renderers.py` — UI rendering from `streamlit_app.py`
- `src/evidence_serializer.py` — JSON serialization from `evidence_tracker.py`
- `src/screenshot_capture.py` — Screenshot utilities from `evidence_tracker.py`
- `src/state_tracker.py` — DOM state tracking from `journey_scraper.py`
- `src/form_detector.py` — Form detection constants from `journey_scraper.py`
- `src/semantic_matcher.py` — Token semantic similarity from `placeholder_resolver.py`
- `src/intent_matcher.py` — Intent filtering from `placeholder_resolver.py`
- `src/code_normalizer.py` — Code normalization from `code_postprocessor.py`
- `src/llm_reasoning_filter.py` — Reasoning text detection from `code_postprocessor.py`
- `src/url_inference.py` — URL transition inference from `placeholder_orchestrator.py`

---

## ✅ Completed: Evidence Tracker Feature Chain (AI-016 through AI-022)

**Status:** Complete — April 2026. All seven items delivered.

### Tier 1: Self-Diagnosing Failure Evidence
- `src/failure_reporter.py` — `FailureReporter` class with `diagnose_failure()`, `generate_failure_note()`, `categorize_elements()`, `suggest_locators()`, `snapshot_to_text()`
- `src/evidence_tracker.py` — captures failure_note in result dict, records page URL and screenshot at failure point
- `src/evidence_report.py` — renders failure_note in annotated evidence viewer
- Test: `tests/test_failure_reporter.py` — 10 tests covering all methods
- Behavior: When a test step fails, evidence captures URL, screenshot, available locators, and human-readable failure note. Test still fails — no auto-recovery.

### Tier 2: Locator Scoring + Controlled Fallback
- `src/locator_scorer.py` — `LocatorScorer` class with confidence scoring per locator type (specific ID > aria-label > CSS selector > get_by_label)
- `src/evidence_tracker.py` — `record_step()` checks `fallback_used` flag, sets `partial_pass` status when fallback was used, logs full fallback chain with scores
- `src/failure_reporter.py` — `suggest_locators()` uses scorer to recommend higher-confidence alternatives
- Test: `tests/test_locator_scorer.py` — 10 tests covering all scorer methods
- Behavior: When primary locator fails, tries 1-2 higher-scoring alternatives. Every fallback logged in evidence with scores. Tests using fallbacks marked `partial_pass` — flagged for review.

### Tier 3: Suite Heatmap — Per-URL, Not Per-Test (Redesigned)
- `src/evidence_report.py` — `generate_suite_heatmap()` redesigned from requirements-to-tests table to per-URL element coverage
- Per-URL aggregation: all evidence points for a given URL across ALL tests, grouped together
- Color-coded by test status: green (passed), yellow (partial_pass/fallback), red (failed)
- Circle size proportional to test count (coverage validation)
- Tooltip shows locator, element info, and test results
- Filterable by test status: "All", "Passed", "Partial", "Failed" buttons
- Element details table below heatmap with position, element, locator, and per-status counts
- Legend shows status colors and circle size meaning
- `tests/test_heatmap_utils.py` — 8 tests (2 original + 6 new for Tier 3 features)
- Behavior: Product owner sees "Look at all the elements we covered across the test suite — and here's which ones were hit by every test (possible data-input bias)."

**Files modified/created:**
- `src/failure_reporter.py` (new)
- `src/locator_scorer.py` (new)
- `src/evidence_tracker.py` (modified — fallback chain, status tracking)
- `src/evidence_report.py` (modified — suite heatmap redesign, failure_note rendering)
- `tests/test_failure_reporter.py` (new)
- `tests/test_locator_scorer.py` (new)
- `tests/test_heatmap_utils.py` (modified — 6 new tests)

---

## Feature Context — Evidence Tracker (AI-016 through AI-022)

The evidence tracker feature transforms test outputs from raw pass/fail results
into a fully traceable stakeholder artefact. The chain runs:

  Spec analysis → Tester review → Condition sign-off
  → Annotated screenshot evidence → Gantt timeline
  → Heat map → Evidence bundle export

This was designed to answer the question a tester needs to answer in a sprint
review: "here is what I tested, why I tested it, and proof that it passed."

Three new outputs are produced per test run:

1. `.evidence.json` sidecar — structured interaction record with bounding boxes
2. Annotated screenshot — page screenshot with numbered interaction circles
3. Evidence bundle — per-story document combining all three sources (AI, manual,
   automation) with Gantt timeline and sign-off section

---

### ✅ AI-016 — Spec Analysis Stage (COMPLETE)

**What:** A new pipeline stage that runs before test generation. Reads the
user's input (spec, user story, or acceptance criteria), extracts business rules,
maps boundary values, surfaces assumptions and ambiguities, and derives explicit
test conditions. Produces a structured list of conditions the tester must review
and confirm before generation begins.

**Why:** Documents like functional specs (e.g. Appius baggage calculator format)
contain business rules in prose, not acceptance criteria bullets. The boundary
values, assumptions, and ambiguities must be derived by analysis, not just parsed.
A tester who has confirmed ten conditions has a very different accountability
position than one who ran a tool.

**New file:** `src/spec_analyzer.py`
**New file:** `tests/test_spec_analyzer.py`
**Touches:** `streamlit_app.py` — new stage before "Generate Tests" button
**Touches:** `src/prompt_utils.py` — system prompt updated to receive derived
conditions rather than raw acceptance criteria text

**Design session completed:** 2026-04-04
**Spec:** See docs/PROJECT_KNOWLEDGE.md — Spec Analysis Stage section

**Condition types derived:**
- `happy_path` — valid input within all rules
- `boundary` — value at exactly the rule limit (and ±1 unit either side)
- `negative` — invalid input, error path
- `exploratory` — tester-added, not derivable from spec alone
- `regression` — parameterised automation, cross-boundary combinations
- `ambiguity` — spec gap requiring product owner clarification before sign-off

**Priority:** High — prerequisite for AI-017 and AI-018

---

### ✅ AI-017 — Living Test Plan UI (COMPLETE)

**What:** After spec analysis, the tester sees a full editable test plan showing
all derived conditions. They can edit any condition's text, expected result, or
source reference. They can remove conditions they consider out of scope. They can
add manual tests (with step lists) and automation tests (with locator intent).
They can flag conditions that need product owner clarification. Only when all
conditions are confirmed does the sign-off button unlock, triggering generation.

**Why:** The tester must be the author of the test plan. AI-derived conditions
are a starting point, not a final product. The edit, remove, and add capabilities
make the tester's judgement visible and documented, not invisible.

**New file:** None — UI only, lives in `streamlit_app.py` as a new display
function `display_test_plan()`
**Note:** All testable helpers must be extracted to `src/` per AGENTS.md §3.
Any filtering, sorting, or condition-manipulation logic goes in
`src/test_plan.py`, not directly in `streamlit_app.py`.

**New file:** `src/test_plan.py` — TestPlan dataclass, condition CRUD, flag logic
**New file:** `tests/test_test_plan.py`

**Session state keys added:**
- `test_plan` — list of TestCondition objects (see docs/PROJECT_KNOWLEDGE.md)
- `plan_confirmed` — bool, True when all conditions checked off

**Priority:** High — depends on AI-016

---

### ✅ AI-018 — Evidence Tracker Module (COMPLETE)

**What:** `src/evidence_tracker.py` — wraps Playwright Page interactions to
record element bounding boxes, interaction types, step sequence, and run history.
Writes a `.evidence.json` sidecar file alongside screenshots after each test run.
Accumulates run counts across multiple runs without overwriting history.

**Why:** The annotated screenshot overlay (AI-020) and the Gantt timeline
(AI-021) both read from the sidecar. Without structured interaction data, the
overlay cannot know where to draw circles or how large to make them.

**New file:** `src/evidence_tracker.py`
**New file:** `tests/test_evidence_tracker.py`
**New file:** `generated_tests/conftest.py` — pytest fixture wiring tracker
into every generated test automatically

**Key design decisions (do not change without design session):**

- Tracker wraps the Page object, it does not patch it. Existing tests continue
  to work unchanged.
- Coordinates stored as both absolute pixels (`bbox`) AND viewport percentage
  (`viewport_pct`). The overlay renderer uses percentages so it is
  resolution-independent.
- `run_count` is per-step, not per-test. Elements exercised by multiple test
  paths accumulate independently.
- `write()` is called in pytest teardown via the conftest fixture, not inside
  the test function. This ensures sidecar is written even when a test fails.
- `pytest_runtest_makereport` hook in conftest makes pass/fail status available
  to the teardown fixture.

**Sidecar schema version:** `1.0` (see docs/PROJECT_KNOWLEDGE.md for full schema)

**Priority:** High — blocks AI-019, AI-020, AI-021

---

### ~~AI-019 — Prompt Update: EvidenceTracker Methods~~ (SUPERSEDED — skeleton-first + postprocessor)

**What:** Update `src/prompt_utils.py` to add a new rule block
`_EVIDENCE_TRACKER_RULES` instructing the LLM to use `evidence_tracker.*`
wrapper methods instead of `page.*` directly. Add the `@pytest.mark.evidence`
decorator to the generated test template. Update
`get_streamlit_system_prompt_template()` to include the new rule block.

**Why:** If the LLM generates `page.goto()` instead of
`evidence_tracker.navigate()`, no sidecar is produced and the annotated
screenshot feature produces nothing. The rule must be in the system prompt,
not just documentation.

**Touches:** `src/prompt_utils.py` only
**New constant:** `_EVIDENCE_TRACKER_RULES`

**Six mandatory rules for the LLM (see docs/PROJECT_KNOWLEDGE.md for full text):**
1. Use `evidence_tracker.navigate()` not `page.goto()`
2. Use `evidence_tracker.fill()` not `page.locator().fill()`
3. Use `evidence_tracker.click()` not `page.locator().click()`
4. Use `evidence_tracker.assert_visible()` not `expect().to_be_visible()`
5. Always add `@pytest.mark.evidence(condition_ref=..., story_ref=...)`
6. Never call `page.screenshot()` directly

**Note:** `src/llm_client.py` is PROTECTED — do not modify it.
The rule block goes in `prompt_utils.py` and is injected via the existing
template system.

**Priority:** High — depends on AI-018, blocks usable generated tests

---

### ✅ AI-020 — Annotated Screenshot Evidence View (COMPLETE)

**What:** Extend `src/report_utils.py` to read `.evidence.json` sidecars when
building the HTML evidence bundle. Render an SVG overlay on top of each
screenshot showing: numbered circles at interaction coordinates, circle size
encoding cumulative run count, colour encoding interaction type
(navigate/fill/click/assertion), sequence numbers in execution order.

**Three view modes:**
- `annotated` — numbered circles with type colours (default, for product owner)
- `heatmap` — density rings showing interaction frequency across all runs
  (for QA lead)
- `clean` — raw screenshot with no overlay (baseline for comparison)

**Hover interaction:** Hovering a circle highlights the corresponding step in
the step timeline below the screenshot. Hovering a timeline row highlights the
circle on the screenshot.

**Why:** A screenshot is a frozen moment. An annotated screenshot is a test map
a product owner can read without understanding any code.

**Colour encoding (do not change without updating legend):**
- Navigate: `#993556` (pink-red)
- Fill: `#0F6E56` (teal)
- Click: `#185FA5` (blue)
- Assertion: `#854F0B` (amber)

**Circle size formula:** `base_radius = 14 + min(run_count * 0.7, 20)`

**Coordinate rendering:** Uses `viewport_pct` not absolute `bbox` pixels.
Multiply by container dimensions at render time.

**Touches:** `src/report_utils.py` — new function `generate_annotated_screenshot()`
**Touches:** `streamlit_app.py` — evidence bundle tab shows annotated screenshots

**Priority:** Medium — depends on AI-018

---

### ✅ AI-021 — Gantt Timeline in Evidence Bundle (COMPLETE)

**What:** A per-story, per-sprint test execution timeline showing each condition
as a horizontal bar sized by duration. Bars labelled with the condition ref
(BC01.02) and plain-English description, not the test function name. Dashed bars
for conditions not yet run (pending/open question). Colour encodes status.

**Three grouping modes:**
- By condition type (tester view)
- By sprint (scrum master view)
- By source — AI/manual/automation (product owner view)

**Stakeholder summary row** below the chart: fastest test, slowest test,
automation coverage percentage as plain English sentences.

**Clicking a bar** expands a detail card showing the spec reference, expected
result, evidence note, and step sequence. The card sits below the chart, not
as a modal overlay.

**Why:** Duration differences between tests are meaningful — a boundary rejection
taking 4× longer than a happy path is a conversation starter with developers. The
Gantt makes this visible without the tester having to articulate it.

**New file:** `src/gantt_utils.py` — data preparation, grouping logic
**New file:** `tests/test_gantt_utils.py`
**Touches:** `streamlit_app.py` — new tab in evidence bundle section
**Reads from:** `.evidence.json` sidecar `test.duration_s` and `test.status`

**Priority:** Medium — depends on AI-018

---

### ✅ AI-022 — Coverage Heat Map (COMPLETE)

**What:** A cross-story, cross-sprint grid showing coverage confidence for each
story × condition type combination (or story × sprint, or story × source,
switchable). Each cell coloured by confidence level. Clicking a cell expands
condition detail. Sprint-over-sprint trend bars below the grid.

**Four confidence levels (colours are fixed — do not change):**
- Tester confirmed: `#1D9E75` (dark teal) — tests passed AND tester signed off
- AI covered, unreviewed: `#9FE1CB` (light teal) — tests passed, no tester review
- Partial / pending: `#FAC775` (amber) — some conditions still pending
- Gap / open question: `#F09595` (red) — ambiguity or missing coverage
- Not in scope: `var(--color-background-secondary)` — deliberate exclusion

**The tonal distinction between confirmed and unreviewed is the most important
design decision in the heat map.** Both mean tests passed. Only confirmed means
a human reviewed the conditions and agreed they are the right tests. This is
the visual answer to the question "how much of this did a human actually verify."

**Persistence:** Heat map data aggregated from all `.evidence.json` sidecars in
the evidence directory, plus manual test plan records from session state. No
external database — local file aggregation only.

**New file:** `src/heatmap_utils.py` — aggregation across sidecars
**New file:** `tests/test_heatmap_utils.py`
**Touches:** `streamlit_app.py` — new top-level analytics tab

**Priority:** Medium — depends on AI-016, AI-018, AI-021

---

## Implementation Sequence (AI-016 through AI-022)

Do these in order. Each item is a single Cline session.

| Order | ID | Session scope |
|-------|----|---------------|
| 1 | AI-018 | `src/evidence_tracker.py` + tests + conftest only |
| 2 | AI-019 | `src/prompt_utils.py` rule block only |
| 3 | AI-016 | `src/spec_analyzer.py` + tests — no UI yet |
| 4 | AI-017 | `src/test_plan.py` + tests + `display_test_plan()` in UI |
| 5 | AI-020 | `generate_annotated_screenshot()` in report_utils + UI tab |
| 6 | AI-021 | `src/gantt_utils.py` + tests + UI tab |
| 7 | AI-022 | `src/heatmap_utils.py` + tests + UI tab |

**Rule:** Each session must end with `bash fix.sh` → `pytest tests/ -v` → green
before committing. Do not combine sessions.

---

### ✅ AI-002 — User Story Parser Module (COMPLETE)
**What:** Move criteria extraction into `src/user_story_parser.py` with proper
format support: Gherkin, Jira AC bullets, numbered, free-form
**Status:** Complete — Session 11 (2026-03-29)

### ✅ AI-005 — Move coverage helpers to `src/coverage_utils.py` (COMPLETE)
**What:** Extract remaining coverage helpers out of `streamlit_app.py`
**Status:** Complete — Session 13/April 2026. All display-mapping logic moved explicitly to `src/coverage_utils.py` and stubs fixed.

### ✅ AI-004 — Phase C Run Now gaps (COMPLETE)
**What:** Three gaps in the Run Now workflow:
1. Environment URL dropdown (staging / prod / local) — added to Streamlit sidebar
2. Re-run failed tests only — already implemented
3. Screenshot viewer inline after run — added inline evidence viewer in `src/ui/ui_run_results.py`
**Priority:** Medium

### AI-006 — Test fixture library
**What:** `tests/fixtures/user_stories/` with 10-15 examples in each format
**Why:** Parser regression suite
**Priority:** Medium

### AI-007 — Remove `_generate_test_content()` from CLI orchestrator
**What:** CLI orchestrator has its own generation function duplicating
`src/test_generator.py` logic
**Priority:** Low

---

## 🌟 Future Enhancements

> Note: Each of these needs a detailed design session before handing to Cline.
> They are listed here to capture intent — not ready for implementation yet.

### ✅ AI-023 — Interactive Locator Repair Loop (COMPLETE)
**What:** When a generated test fails with a locator error (TimeoutError or strict
mode violation), the tool offers an interactive repair mode. A headed browser opens
at exactly the page where the test got stuck. The tester clicks the element they
want. The tool captures the locator Playwright reports for that click and patches
it directly into the test file. The tester then re-runs to verify.

**Why:** This closes the loop between "test generated" and "test working." Currently
locator failures require the tester to debug the DOM manually and edit the file
themselves — work the tool should handle. This feature maps directly to what an
automation tester would do: open the page, find the element, copy the locator.

**Implementation:**
- `src/failure_classifier.py` — classify pytest failure type from error message
- `tests/test_failure_classifier.py`
- `src/locator_repair.py` — patch locator in test file + codegen browser session
- `tests/test_locator_repair.py`
- `src/ui/ui_run_results.py` — repair panel, repair buttons on locator failures, browser session state


**Implementation sequence (4 Cline sessions, strict order):**
1. `src/failure_classifier.py` + tests
2. `src/locator_repair.py` patch logic + tests (no browser)
3. `streamlit_app.py` UI — repair button and state transitions (no browser)

**Constraints:**
- Locator failures only — assertion failures get explanation note, no repair button
- Streamlit UI only — not available in CI or headless runs
- One locator repair per invocation — not batch
- Never guesses a replacement — only records what the tester clicks

### ✅ AI-024 — Accessibility Tree Enrichment (COMPLETE — 2026-05-17)
**Implemented:** `src/accessibility_enricher.py`, `tests/test_accessibility_enricher.py`, CDP snapshot in `src/scraper.py` (+ journey/stateful scrapers per B-0XX).
**Spec:** `docs/specs/FEATURE_SPEC_AI024_accessibility_tree_enrichment.md`

### AI-025 — Visual Regression Detection (Planning Required)
**What:** Post-run screenshot comparison against baselines...

### ✅ AI-010 — Page Object Model Generation Mode (COMPLETE — 2026-06-30)
**What:** POM toggle in both Streamlit UI and CLI — generates `class HomePage:` etc. with locators and interaction methods, tests import from `pages/`.

**Implementation vs original spec:**
- ✅ UI toggle — `st.sidebar.toggle("Page Object Model (POM)")` in `src/ui/ui_sidebar.py`
- ✅ CLI toggle — "POM Mode" menu item in `src/cli/main.py`
- ✅ One class per scraped page URL — `src/page_object_builder.py` (292 lines)
- ✅ Evidence-aware POM methods — delegates to `EvidenceTracker` not raw `page.locator()`
- ✅ `ExportMode.POM` / `ExportMode.FLAT` — `src/export_service.py`, `src/pipeline_models.py`
- ✅ POM injection phase — `src/placeholder_orchestrator.py`, `src/orchestrator.py`
- ✅ Separate files in `generated_tests/pages/`
- ✅ 1400+ tests across 8 test files
- ✅ UAT validated — saucedemo: 6 POM classes (HomePage, InventoryPage, CartPage, CheckoutStepOnePage, CheckoutStepTwoPage, CheckoutCompletePage)

---

### ✅ AI-011 — Test Run History Chart (COMPLETE — 2026-07-01)
**What:** A pass/fail trend chart showing test results over time.

**Why it matters:** A single run result tells you pass/fail now. A history chart
tells you whether things are getting better or worse, and when a regression was
introduced.

**Implementation:** 
- Uses existing `src/run_history_chart.py` which aggregates from SQLite database
- Added to `streamlit_app.py` as "📊 Test Run History" section after Evidence Viewer
- Uses `st.plotly_chart` for interactive visualization
- All run results persisted to `evidence/run_results.sqlite` via `src/run_result_persistence.py`
- Modified `src/ui/shared.py` to automatically persist runs
**Priority:** Medium

---

### AI-012 — Selector Confidence Scores
**What:** Score each locator the scraper found by how likely it is to break,
and surface that score in the UI alongside the generated test.

**Why it matters:** Not all selectors are equally reliable. A test built on
`data-testid` attributes will survive UI redesigns. A test built on button
visible text will break the moment someone rewrites the copy. Users should
know which parts of their generated test are fragile before they find out
the hard way in CI.

**How scoring works — based on locator type, not usage frequency:**

| Locator type | Confidence | Reason |
|---|---|---|
| `data-testid` | High | Explicitly added for testing — won't change accidentally |
| `id` attribute | Medium-High | Stable but sometimes auto-generated |
| `name` attribute | Medium | Reliable for forms |
| `aria-label` / role | Medium | Good but changes with UI copy |
| `visible_text` | Low | Breaks when button label changes |
| Bare tag (`input`) | Very Low | Almost always fragile |

The scraper already builds `recommended_locator` for every element — scoring
is a classification step on top of what already exists.

**What the UI shows:** A confidence indicator per test function, and a summary
panel showing how many locators in the generated test are high/medium/low
confidence. Flags tests that are likely to be brittle before they're even run.

**Design session needed:** Yes — scoring thresholds, UI presentation, whether
low-confidence selectors should trigger a warning at generation time
**Priority:** Medium

---

### AI-013 — Coverage Gap Report with Gap Explanations
**What:** A report showing which acceptance criteria have no linked test, with
an explanation of why the gap exists.

**Why it matters:** Knowing a gap exists is useful. Knowing *why* it exists
tells the user what to fix — is it the user story, the scraper, or the LLM?

**Gap explanations the tool can provide:**

| Gap reason | How detected | What user should do |
|---|---|---|
| No matching elements found on page | Scraper found nothing relevant to this criterion | Add the page to the URL list or check the page loads correctly |
| Criterion too ambiguous | No specific keywords the LLM could act on | Rewrite the criterion to be more specific |
| Page not scraped | Relevant page wasn't in the URL list | Add the URL to the additional pages list |
| LLM skipped this criterion | Criterion in the list but no test function references it | Re-run with Always LLM mode or rewrite the criterion |

**Design session needed:** Yes — how to detect each gap type reliably, how to
present the report in the UI, whether this replaces or extends the current
coverage tab
**Priority:** Medium

---

### AI-014 — Test Execution Time Gantt Chart
**What:** A Gantt-style chart showing each test as a horizontal bar, sized by
execution time, so users can understand total suite duration and identify slow tests.

**Why it matters:** QA leads need to know how long a full regression run takes.
If it takes 45 minutes, that affects how often it can run in CI. Identifying
the slowest tests lets users decide which ones to optimise or run separately.

**How it would work:**
- `pytest_output_parser.py` currently stores duration as `0.0` — individual
  test times are in the pytest output but not yet parsed
- Parsing them is a small regex addition to the parser
- The Gantt chart stacks tests horizontally, total width = total suite time
- Colour coded by status (green = passed, red = failed)
- Clicking a bar could expand the error message for failed tests

**Design session needed:** Yes — parsing individual test durations from pytest
output, chart library choice, whether this lives in the run results tab or a
separate analytics tab
**Priority:** Low-Medium

---

### AI-015 — Test Coverage Heat Map
**What:** A visual grid showing which parts of the application have been tested
and how thoroughly, colour coded from red (untested) to green (fully covered).

**Why it matters:** At a glance a QA lead can see where the coverage gaps are
across the whole application — not just for one user story but across all
generated tests. A standard tool in mature QA workflows.

**How it would work:**
- Each cell in the grid represents a page or feature area
- Colour is determined by: number of tests covering that area, confidence
  scores of those tests, pass/fail rate from run history
- Requires run history (AI-011) and selector confidence (AI-012) to be
  meaningful — depends on those features
- Would live in a dedicated "Coverage" or "Analytics" tab

**Design session needed:** Yes — this is the most complex visualisation on
the list. Depends on AI-011 and AI-012 being in place first.
**Priority:** Low — long term goal, needs other features as prerequisites

---

### Cloud LLM Providers
**Goal:** Support OpenRouter, OpenAI, Anthropic alongside Ollama
**Spec:** `LLM_PROVIDER` env var, provider-specific API keys in sidebar, fallback to Ollama
**Status:** Complete — Added multi-provider LLM support architecture.

### n8n Integration
**Goal:** Trigger generation from Jira webhooks, report to Slack
**Status:** Low priority — Phase 4+

---

## 📋 Fix Log

### Session 3 (2026-03-06)
- B-001, B-002, B-003, B-005 closed
- Phase A (auto-save), B (coverage), C (run now core) complete

### Session 4 (2026-03-07)
- AI-001 (page context scraper) complete
- Coverage number-based matching fixed
- Run output persistence fixed
- Jira report download added
- `pytest.ini` — removed `generated_tests` from testpaths

### Session 5 (2026-03-10)
- R-003 complete — `src/report_utils.py` extracted and tested

### Session 8 (2026-03-13)
- R-001 through R-006 complete
- Cline loop recovery applied
- load_dotenv fix, URL normalisation, content persistence, download crash fixed

### Session 9 (2026-03-16)
- BREAK-1 identified — `src/pytest_output_parser.py` missing (CI blocker)
- BREAK-2 identified — session state wipe in `display_run_button()`
- B-006 identified — parser banner wrong on mixed pass/fail
- B-007 identified — error panels duplicated
- B-008 identified — Run Status column never populates
- AI-009 (multi-page scraping) added as critical priority
- `docs/FEATURE_SPEC_multi_page_scraping.md` created

### Session 10 (2026-03-21)
- B-007 fixed — removed duplicate error rendering from `display_coverage()`
- B-006 verified working, 2 regression tests added to `test_pytest_output_parser.py`
- AI-003 closed — `OLLAMA_TIMEOUT=300` added to `.env.example`
- AI-009 Phase A complete — multi-page scraper wired into `streamlit_app.py`
- 121 tests passing, ruff clean, mypy clean

### Session 11 (2026-03-29)
- AI-002 complete — `src/user_story_parser.py`, 23 tests, 100% pass rate
- B-009 fixed — `src/code_validator.py` created, integrated into `file_utils.py`
- AI-003 confirmed complete
- AI-009 Phase B spec written — `docs/FEATURE_SPEC_AI009_phase_b.md`
- BACKLOG.md updated — AI-010 through AI-015 added
- LEARNING_PLAN.md created
- docs/PROJECT_KNOWLEDGE.md refreshed

### Session 12 (2026-03-31)
- Streamlit input mode persistence fixed: "Paste story" selection now survives reruns and login-toggle changes.
- Requirement model consistency improved for no-AC inputs: parsing, criteria count, coverage, and reports now use one derived model.
- Report semantics corrected: pre-run states remain pending/unknown and are no longer counted as failed.
- Run output UX cleaned: noisy/duplicate pytest lines reduced and misleading pytest-cov module coverage removed from UI run flow.
- Prompt/context hardening for generated selectors and URLs: stronger use of scraped locators and context URLs with stricter generation guidance.
- Generation guardrails expanded in `src/code_validator.py` for known flaky SauceDemo patterns:
  - invalid `/checkout.html`
  - invalid checkout title assertions
  - brittle exact base URL assertions pre-login
  - weak negative-only checkout URL assertions
- Multi-page restart-from-base scraping improved:
  - captured page now accepted only when URL matches the requested target
  - mismatch now retries (bounded) and surfaces explicit failure details.
- Credential profile active-selection regressions fixed in Streamlit state handling.

### Session 13 (2026-03-31)
- AI-005 complete: moved remaining coverage display-mapping logic from `streamlit_app.py` into `src/coverage_utils.py` with typed helpers and tests.
- B-008 effectively addressed: Coverage x Run Results now maps run outcomes through shared coverage utilities and no longer defaults to pending when matches exist.
- AI-004 (Phase C) progress: added "Re-run Failed Only" in the Run Now flow.
  - Failed test nodeids are extracted from prior run results and executed directly via pytest.
  - Command construction extracted to `src/run_utils.py` with unit tests.
- Multi-page scraper failure tracking improved to typed structured failures (`failed_pages`) with backward compatibility for legacy `failed_urls` consumers.
- Runtime logic further generalized to site-agnostic behavior (removed site-specific validator/prompt/scraper assumptions).

### April 2026 Updates (Sessions 14+)
- Add anchor link extraction to page context scraper (2026-04-04).
- Add multi-provider LLM support, fix coverage_utils stub, clean up Cline artefacts (2026-04-05).
- Remove Cline scratch files, tighten gitignore for tmp files and PNGs (2026-04-05).
- Refactor: implement pipeline architecture and update dependencies (2026-04-08).
- Utils fix and pip to uv migrations resolved (2026-04-10).
- Stabilized AI test generation pipeline: fixed POM method mismatches, resolved placeholder syntax errors, and implemented structural safety nets (2026-04-19).

### B-015 Fix — dismiss_consent_overlays Rewrite (2026-06-23)
**What:** Rewrote `dismiss_consent_overlays()` in `src/browser_utils.py` to fix B-015
(journey discovery selecting wrong elements due to aggressive consent banner dismissal).

**Root cause:** Old implementation used global text matching (`button:has-text('Continue')`)
that matched `#continue-shopping` on saucedemo's cart page. Called before every click
step, this navigated cart.html → inventory.html, preventing checkout pages from being
scraped. This caused a cascade: wrong click → wrong page → missing scrape → zero
resolution for all checkout FILL fields.

**Fix:** 3-stage replacement:
1. Google Consent TVM — specific `.fc-consent-root` selectors (unchanged)
2. Structural containers — known consent provider classes (`oneTrust`, `cookie-banner`,
   `[role='dialog']`, etc.) — buttons only matched **inside** these containers
3. Position-based detection — JS finds fixed/sticky overlays near bottom of viewport,
   then looks for dismiss buttons inside them
4. Ad overlay removal — specific selectors only (Google Vignette, ASWIFT)

**Removed:** Global text matching, `zIndex > 10000` DOM removal, `allElements` DOM iteration.

**Verification:** saucedemo UAT after fix:
- `#checkout` selected (score=12) for "checkout button" on cart.html ✅
- All checkout pages scraped (`checkout-step-one.html`, `checkout-step-two.html`, `checkout-complete.html`) ✅
- `test_06_complete_checkout` reduced from 8+ skips to 1 skip (ASSERT — B-014) ✅
- 1266 tests pass, 0 regressions ✅
- 10 new unit tests in `tests/test_browser_utils.py` ✅

**Files changed:**
- `src/browser_utils.py` — complete rewrite
- `tests/test_browser_utils.py` — new test file (10 tests)

### Saucedemo UAT Investigation (2026-06-22)
**What:** Full pipeline run against saucedemo.com using `scripts/uat/uat_automationexercise.py --site saucedemo` to validate placeholder resolution findings.

**Key findings:**
1. **B-015 CONFIRMED** — Journey discovery clicks wrong elements:
   - "checkout button" → `#react-burger-menu-btn` (burger menu, score=1)
   - "first name:John" → `<select>` element (not fillable)
   - "zip/postal code:12345" → `<a>` link (not fillable)
   - This prevents checkout pages from ever being scraped

2. **B-014 CONFIRMED** — ASSERT resolves to wrong elements:
   - "product inventory page" → `#login-button`
   - "cart badge shows 1" → `.shopping_cart_link` (cart nav link)
   - "sauce labs backpack in cart" → `#remove-sauce-labs-backpack`
   - Every ASSERT resolves to something, but never the right element

3. **B-017 CORRECTED** — FILL on login works (masked by prerequisite injection):
   - `#user-name`, `#password`, `#login-button` all resolve correctly in final code
   - Resolver logs say `Failed to find` but prerequisite injection provides selectors
   - Checkout FILL fails because checkout pages were never scraped (B-015 consequence)

4. **B-018 CORRECTED** — The resolver gap is real but secondary:
   - Resolver fails on login elements but prerequisite injection masks it
   - The primary failure mode is B-015 (journey wrong clicks → missing pages)

**Cascade chain:** B-015 (journey clicks wrong) → checkout pages not scraped → B-017 (checkout FILL fails) → test_06 pytest.skip()

**No code changes** — investigation only, backlog items corrected to reflect actual root causes.

### Mypy Stubs Fix (2026-04-21)
**What:** Resolved 11 mypy `import-untyped` and type compatibility errors across 4 files.

**Fixes:**
- Installed `pandas-stubs` via `uv add --dev pandas-stubs` — resolves 6 import errors in `gantt_utils.py` and `heatmap_utils.py`
- Added per-module `ignore_missing_imports = true` for `plotly.*` in `pyproject.toml` — resolves 3 import errors (plotly has no official stubs)
- Fixed `src/scraper.py:164` — extracted `tag.get("class")` to walrus operator to resolve type narrowing issue
- Fixed `streamlit_app.py:743` — added `# type: ignore[arg-type]` for `grouping_mode` Literal mismatch (st.selectbox returns str, values are correct at runtime)

**New dev dependency:** `pandas-stubs>=3.0.0.260204` in `pyproject.toml`

### April 2026 — Evidence Tracker Feature Chain (Sessions 17-20)
**What:** Delivered all seven items (AI-016 through AI-022) plus Tier 2 locator scoring and Tier 3 heatmap redesign.

**Deliverables:**
- Tier 1: `src/failure_reporter.py`, `src/evidence_tracker.py` failure_note capture, `src/evidence_report.py` failure rendering
- Tier 2: `src/locator_scorer.py`, fallback chain in evidence_tracker, partial_pass status
- Tier 3: Redesigned `generate_suite_heatmap()` — per-URL aggregation, status overlay, locator info, filter buttons
- Tests: `tests/test_failure_reporter.py` (10 tests), `tests/test_locator_scorer.py` (10 tests), `tests/test_heatmap_utils.py` (8 tests, 6 new)

**All checks passed:** ruff clean, mypy clean, pytest green.

### Session (2026-05-08) — Global Best Resolution Fix
**What:** Placeholder resolution in `src/placeholder_orchestrator.py` was returning the first
per-page match instead of the global best match across all scraped pages. On multi-page sites
like saucedemo.com, this caused login page elements (e.g., `#user-name`, `#password`,
`#login-button`) to be skipped entirely because a low-quality match existed on an earlier page
in dict iteration order (e.g., cart page).

**Root Cause:** `_find_best_element_for_current_page()` iterated through pages sequentially and
returned the first match found per-page, never reaching pages with better matches.

**Fix:** Changed the method to collect ALL ranked candidates from ALL pages into a single list,
sort by score descending, then select the global best match. Threshold-based shortlisting and
semantic ranking operate on the global ranking.

**Files Modified:**
- `src/placeholder_orchestrator.py` — `_find_best_element_for_current_page()` now collects
  candidates globally before selecting the best match
- `tests/test_global_best_resolution.py` — 5 new regression tests covering cross-page resolution,
  password field, login button, checkout button, and no-match scenarios

**Quality Checks:** ruff clean, mypy clean, 45 placeholder-related tests pass.

**Impact:** Fixes all placeholder resolution failures on saucedemo.com and similar multi-page
sites where elements on the login page were being skipped because cart/checkout pages appeared
first in the scraped data dict.

---

### Session 22 (2026-05-01) — CLI entry point cleanup
**What:** Clarified supported CLI ownership after the argparse CLI module superseded
the original root `main.py` menu flow.

**Fix:**
- Root `main.py` is now a deprecated compatibility wrapper that forwards to `cli.main`.
- `AGENTS.md`, `docs/PROJECT_KNOWLEDGE.md`, `README.md`, and `docs/ARCHITECTURE.md`
  now identify `cli/main.py` as the supported CLI entry point.
- Removed stale protection guidance that treated root `main.py` as the active CLI.

**Why:** Avoids two competing terminal workflows and keeps CLI fixes focused on
`cli/main.py`, which is what `launch_cli.sh` runs.


### Session 21 (2026-04-26) — conftest path fix + Tier 1/2 verification
**What:** Generated test evidence sidecars were being written to the wrong directory.
The conftest fixture used `Path(__file__).parent` (conftest location) instead of the
test file's own directory, so evidence from `generated_tests/test_x/` tests was written
to `generated_tests/evidence/` instead of `generated_tests/test_x/evidence/`.

**Fix:** Changed `_get_evidence_refs()` to use `request.fspath` (path to the test file
being executed) and derive `test_package_dir = Path(request.fspath).parent`.

**Verification:** Ran `test_02_go_to_cart` — evidence sidecar correctly written to
`generated_tests/test_20260426_164944_as_a_customer_i_want_to_add_items_to_cart/evidence/test_02_go_to_cart[chromium].evidence.json` (13 KB, contains full failure evidence).

**Tier 1 evidence verified:** The sidecar contains:
- `test.status` = "failed"
- `page.url` = "https://automationexercise.com/view_cart"
- `steps[3].result.failure_note` = human-readable diagnosis with suggested locators
- `steps[3].result.diagnosis.available_elements` = 19 elements found at failure time
- `steps[3].result.diagnosis.suggested_locators` = 15 scored alternatives
- Screenshot captured at failure point

**Tier 2 verified (already complete):** Locator scoring + controlled fallback was
already fully implemented during Session 20. Confirmed working:
- `src/locator_scorer.py` — `LocatorScorer.score_locator()`, `score_candidates()`,
  `get_fallback_candidates()` with 9 locator types scored 0-100
- `src/evidence_tracker.py` — `_try_locator_fallback()` builds DOM candidates,
  scores them, tries up to 2 higher-scoring alternatives, logs full chain
- `partial_pass` status set when fallback succeeds
- Full fallback chain in evidence: locator, type, score, confidence, result, error
- 39 tests pass (15 locator_scorer + 11 evidence_tracker + 13 other evidence)

**Pre-existing bug discovered:** `test_generate_annotated_journey_cleans_placeholder_labels`
fails with `label: "<built-in method title of str object at 0x...>: view cart link"`.
The `clean_placeholder_labels()` function in `evidence_report.py` is calling `.title()`
on a method reference instead of the string value. NOT related to the conftest fix.
Requires separate investigation.

**Test results:** 455/456 tool tests pass. 1 pre-existing failure unrelated to this fix.

---

## Historical Issues (from ISSUES_FOUND_AND_FIXES.md — merged 2026-04-21)

> **Architecture note:** Issues 3 and 4 below were fixed in the pre-session-2 codebase
> and reflect the original standalone async format. The project architecture was
> subsequently decided (2026-03-03) to use **pytest sync format** exclusively.
> Any references to async/await tests or "no pytest" as a fix are superseded.
> See docs/PROJECT_KNOWLEDGE.md — Architecture Decisions for the current standard.

### Session 1-2 Issues (2026-03-01 to 2026-03-04)

#### 1. GitHub Actions CI/CD Pipeline ⚠️
**Problem:** CI/CD badge not properly configured for renamed project.
**Fix:** Updated badge URL to reflect renamed repository.
**Impact:** CI/CD status badge now displays correctly.

#### 2. Path Calculation Problem ⚠️
**Problem:** Paths calculated incorrectly when running from different directories.
**Fix:** Changed to `Path.cwd()` for consistent path resolution.
**Impact:** Script runs correctly from any directory.

#### 4. LLM Prompt Structure ⚠️
**Problem:** Prompt too verbose, used XML tags LLM didn't respect.
**Fix:** Restructured with clear numbered requirements and explicit DO NOT instructions.
**Impact:** More consistent LLM output.

#### 6. CLI Output Formatting ⚠️
**Problem:** CLI output minimal with no visual hierarchy.
**Fix:** Added separator lines, emoji icons, clearer option menus.
**Impact:** Improved developer UX.

#### 7. CLI Module Architecture 🆕
**Problem:** No proper CLI interface with argument parsing.
**Fix:** Implemented complete CLI module with argparse, subcommands, config enums,
modular components (InputParser, UserStoryAnalyzer, TestCaseOrchestrator, etc.)
**Impact:** Tool supports both interactive and programmatic/CI usage.

#### 12. Pre-commit Configuration 🆕
**Problem:** No `.pre-commit-config.yaml` — no automated quality checks before commits.
**Fix:** Created `.pre-commit-config.yaml` with ruff linting and ruff-format.
**Impact:** Automated code quality checks run before every commit.

### Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2026-03-01 | Initial release with interactive CLI |
| 1.1.0 | 2026-03-03 | CLI overhaul with argparse, report generation, multi-format support |
| 1.2.0 | 2026-03-04 | Pre-commit configuration with ruff, automated code quality checks |
| 1.3.0 | 2026-03-06 | Streamlit UI, Phase A/B/C (save/coverage/run), B-001/002/003/005 fixed |
| 1.4.0 | 2026-03-07 | Page context scraper (AI-001), coverage mapping fix, Jira download, git hygiene |
| 1.5.0 | 2026-03-21 | B-006/007 fixed, AI-003 closed, AI-009 Phase A complete (multi-page scraper UI) |
| 1.6.0 | 2026-04-10 | Pipeline architecture added, multi-provider LLM support, anchor link extraction, transitioned pip to uv |
| 1.7.0 | 2026-04-26 | Evidence Tracker Feature Chain complete (AI-016 through AI-022), Tier 2 locator scoring, Tier 3 heatmap redesign |

### Lessons Learned (from Gemini AI session)
- Always run ruff, mypy, pytest before accepting AI-generated code
- Review `git diff --staged --stat` before every commit
- Never let an AI commit directly without human review
- Give implementation AIs the full project rules, not just the spec doc
- One feature per AI session — mixing tools mid-feature creates inconsistency

---

## 🐛 Test Generation Quality Fixes (May 2026)

> Root cause analysis from `generated_tests/test_20260502_123121_as_a_customer_i_want_to_browse_products_add_them/report_local.md`:
> 7 of 8 tests failed because the "Dress" link (`a[href="/category_products/1"]`) exists in DOM but is hidden behind a slider/menu. Test_02 also navigated to `/category_details/1` (404) instead of `/category_products/1`.

### Session 1 — LLM Disambiguation for Placeholder Resolution ✅ DONE (2026-05-13)

**Problem addressed:**
- Rule-based scoring in `PlaceholderResolver.rank_candidates()` produces near-ties (e.g., "Products link" resolves to brand product link instead of navigation link)
- Adding more scoring rules creates layering debt
- LLM understands context that rule-based scoring cannot encode

**Solution implemented:**
- `_disambiguate_with_llm()` method added to `PlaceholderResolver`
- Triggered when top-2 candidate scores differ by ≤ `DISAMBIGUATION_THRESHOLD` (default: 5)
- Sends up to 3 candidates to LLM with structured prompt (action, description, candidate details, optional Aria snapshot)
- Falls back to rule-based scoring when LLM unavailable or response unparsable
- Configuration via `USE_LLM_DISAMBIGUATION` (default: true) and `DISAMBIGUATION_THRESHOLD` (default: 5) env vars
- Aria snapshot context stored as `__meta__` element in `page_elements` (Option A)

**Files modified:**
- `src/placeholder_resolver.py` — `_disambiguate_with_llm()`, `_extract_aria_snapshot()`, `_filter_aria_snapshot()`, config params, integration in `find_best_element()`
- `tests/test_placeholder_resolver_disambiguation.py` — NEW — 17 tests (4 trigger, 6 LLM call, 2 scenario, 2 config, 3 integration)

**Quality gates:**
- `ruff check src/placeholder_resolver.py` — clean
- `mypy src/placeholder_resolver.py` — clean
- `pytest tests/test_placeholder_resolver_disambiguation.py -v` — 17/17 passed
- `pytest tests/ -x -q` — 610 passed (1 pre-existing failure in `test_vision_enricher.py` unrelated)

**Original tasks from Session 1 backlog (Visibility Filtering + Generic Selectors + URL Guessing):**
- Task 1A (visibility filtering): Partially addressed — text-content validation + confidence threshold already implemented
- Task 1B (ASSERT generic selectors): Addressed via LLM disambiguation — generic selectors are deprioritized when LLM picks specific elements
- Task 1C (URL guessing): Deferred to future session — out of scope for LLM disambiguation

**Expected outcome:** When rule-based scoring produces near-ties, the LLM makes the final decision with context — one targeted call replaces dozens of scoring rules.

---

### Session 2 — Visibility Capture in Scraper ✅ COMPLETE (2026-05-15)

**Problem:** Even with improved resolver scoring, we can't perfectly distinguish visible from hidden elements without runtime browser data. The scraper extracts elements from HTML via BeautifulSoup but has no visibility information.

**Solution implemented:**
1. `_capture_element_visibility()` in `src/scraper.py` — calls `page.locator(selector).is_visible()` for each element after networkidle
2. `is_visible` field added to all scraped element dicts (default `True` in `_extract_elements_from_html()`, overwritten with live DOM check)
3. `PlaceholderResolver.rank_candidates()` filters out `is_visible=False` candidates for CLICK/FILL actions; applies -40 score penalty for ASSERT actions

**Files modified:**
- `src/scraper.py` — `_capture_element_visibility()` method (lines 135-160), integrated into `_scrape_url_sync()`
- `src/placeholder_resolver.py` — visibility filtering in `rank_candidates()` (lines 560-581, 723-725), removed unused `score_penalty` variable
- `tests/test_scraper.py` — 4 new tests: default visibility, field presence, empty selector handling, element preservation

**Quality gates:** ruff clean, mypy clean, 651/651 tests pass

**Expected outcome:** Resolver never selects elements that are genuinely hidden at runtime.

---

### Session 3 — Skeleton Prompt: Specific Assertions (Priority: Lower)

**Problem:** Generated ASSERT placeholders are too generic (e.g., `ASSERT:button visible`) leading to assertions that match wrong elements even after resolution.

**Task:** Update the skeleton prompt to generate descriptive ASSERT placeholders.

**Approach:**
1. In `get_skeleton_prompt_template()`, add explicit guidance for ASSERT specificity:
   - "For ASSERT actions, describe WHAT element should be visible (e.g., 'ASSERT:product added confirmation message' not 'ASSERT:button visible')"
   - Show before/after examples of good vs bad ASSERT descriptions
2. In `rank_candidates()`, when resolving ASSERT placeholders, give bonus to elements where text content has high word-overlap with description

**Files to modify:**
- `src/prompt_utils.py` — add ASSERT specificity guidance
- `tests/test_prompt_utils.py` — verify prompt includes new guidance

**Expected outcome:** ASSERT placeholders carry enough context for the resolver to pick specific, meaningful elements instead of generic `.btn` matches.

---

## 🚀 CI/CD Tier 3 — Future Pipeline Enhancements

> Planned additions to the consolidated CI pipeline. Implement when the underlying features exist.

### CI-003 — SQLite Migration Validation
**When:** During AI-012 (SQLite Persistence) implementation
**What:** Add a static-analysis step that creates a fresh in-memory/temp SQLite database
and runs `PRAGMA integrity_check` against any DDL migrations. Catches schema syntax
errors before they hit `main`.
**How:** Small pytest fixture or standalone script that applies migrations to a temp DB
and asserts `integrity_check` returns `ok`.

### CI-004 — Graph-Store Compiler Check
**When:** When `nodes.csv`/`links.csv` are consumed by CI
**What:** After `project_sanitizer.py` audits links.csv, add an explicit SQLite query
assertion that compiles the graph-store and verifies no orphaned relational paths
exist in the static codebase mapping.
**How:** Extend sanitizer Step 3 to compile into an in-memory SQLite DB and run
`SELECT COUNT(*) FROM edges WHERE source_id NOT IN (SELECT id FROM nodes)` —
must return 0.

### CI-005 — Eval Harness Freeze Gate (Phase 5)
**When:** When Phase 5 multi-agent evaluation harness exists
**What:** Secondary `workflow_dispatch` workflow that runs evaluation metrics over
a dataset of generated test slices. Saves expensive token consumption on standard
commits while keeping a clean ledger of score regressions.
**How:** New `.github/workflows/eval-harness.yml` triggered manually. Produces
a markdown summary of pass-rate regressions vs the previous eval run.

### CI-006 — Performance Regression Gate
**When:** When test suite exceeds 5 minutes in CI
**What:** Track test suite duration over time and alert if a single commit adds
>30% to total runtime.
**How:** Store `pytest` summary duration in an artifact, compare against last
10 runs using `gh run view` JSON output.



---

## 🆕 AI-061 — Production project-scoped RAG identity (isolation gap)

**Status:** ✅ Complete (shipped 2026-08-27 — `c0b8820`). Opt-in `AITEST_RAG_SCOPE` isolates projects on the same `host:PORT`; legacy `host[:port]` scoping (B-047) preserved when unset. Not blocking; hardening.
**Priority:** Low–Medium. Affects real multi-project / multi-user localhost usage. The AI-059 lab is already protected by a sentinel (Deliverable 3), so this is the production counterpart.
**Depends on:** none. Folds into: AI-035 self-learning RAG, B-047 port-aware site hashing.

**One-line:** the learned-pattern store scopes by `site_hash = sha256(host[:port])` only, so two different projects (or a user's new project) served on the same `localhost:PORT` share one hash and **bleed** patterns into each other; `lv_insurance` and a solo `ecommerce` run also both map to `localhost:8781` inside the eval.

### Problem
- `src/rag_learn.site_hash` uses only `host[:port]` (B-047 keeps the port so concurrent mocks separate).
- Two logical sites on the same port → identical `site_hash` → learned/golden bonuses apply across both.
- `localhost` vs `127.0.0.1` are *different* strings → spurious separation; order-dependent mock port assignment makes a mock's hash change between build configs.
- The collision only affects the RAG learned-pattern store's scoping (a derived, lossy index). Source-of-truth run/evidence data keeps full `page_url` + `run_id` (`sqlite_persistence.evidence_index`, `evidence_tracker`), so data is fully recoverable/re-scoped.

### Fix
- Add an explicit **project/scope key** (user-supplied, or derived from the project directory) that participates in the identity, so two projects on the same port stay isolated.
- Keep B-047 port-keeping for the eval's concurrent mocks.
- The AI-059 lab already uses a fixed sentinel (`ai059-lab:ecommerce` via `AI059_LAB_SITE_HASH` + `rebuild-warm`) — mirror that pattern for opt-in production scoping.

---

## 🆕 AI-062 — RAG bonus effect trace (does the bonus actually decide?) (MEASUREMENT, prerequisite for any scoring rebalance / AI-058)

**Status:** ✅ Complete (rebalance shipped 2026-08-28 — `d15d66c`): RAG bonus now applied on the haystack fast path; decisive-rate at the scoring level went 0–12% → 44–66% (fastpath) with 100% flip-correctness on the mocks; the magnitude bump (5→25) was tried and rejected (near-inert on 3 of 4 sites). AI-058 no longer blocked by scoring uncertainty.
**Priority:** Medium. Decides whether learned/golden RAG bonuses are worth expanding (AI-058) or need a scoring fix first.
**Depends on:** AI-059 (usage trace), AI-061 (scope). Folds into: AI-035 self-learning RAG, AI-058 contrastive learned store.

**One-line:** we can see a pattern was *retrieved* and *applied* (`bonus>0`), but not whether it *changed the winning element*. `2e0f936` adds a counterfactual `decisive` flag (re-resolve with RAG stripped; `True` when the no-RAG winner differs) + `counterfactual_selector`. Now measure the decisive-rate before touching `SAME_SITE_LEARNED_BONUS` / `GOLDEN_PATTERN_BONUS` or building AI-058.

### Why it matters
- `SAME_SITE_LEARNED_BONUS = 5` vs structural scores that reach `+80` — so the bonus only decides when the top two candidates are within 5 points. Most "applied" bonuses are likely cosmetic (pad an already-winning element), not causal.
- **Root-cause finding (from building this):** `PlaceholderScorer.compute_element_score` adds the golden/learned bonus ONLY on the slow semantic path. The haystack fast path (description substring-matches an element — the common case) returns *before* the bonus section, so the bonus is silently never applied there. Expected signature of an inert pattern: `bonus>0` with `decisive:False`.

### Measurement result (2026-08-27)
- Method: scraped saucedemo inventory (71 real elements), resolved each real element label via the live `ElementMatcher` (same `PlaceholderScorer.compute_element_score` path the orchestrator uses), with vs without a learned pattern for that label; `decisive` = winners differ.
- **65 resolved placeholders measured. Learned pattern APPLIED (matched the winner): 35.4%. DECISIVE (RAG changed the winner): 0.0%.** All CLICK.
- Interpretation: learned bonuses are applied often but NEVER flip the pick — they pad an already-winning element. Confirms the fast-path omission (bonus never added on the haystack early-return) AND that even on the slow path +5 is too small to outrank structural scoring. Learned RAG bonuses currently have ~zero causal effect on outcomes.
- Caveat: synthetic learned pattern per label (not a real learned store); indicative of the *applied-vs-decisive* gap, not an exhaustive multi-site rate.

### Resolution (2026-08-28) — fastpath shipped, magnitude rejected
- **The earlier hypothesis was wrong**: fixing ONLY the fast-path omission DID raise *decisive* (and correctly). Live `verify_production` A/B (RAG on): decisive-rate 0% → 21% of applied bonuses; saucedemo execution identical (5 passed/1 skipped) both configs; the lone automationexercise difference was a generated-URL-assert flake with an identical click selector (not RAG-attributable).
- **Mock flip-correctness** (vs eval golden keys on ecommerce/banking mocks): 100% of golden (5/5 + 2/2) and learned (4/4) fastpath flips landed on the golden-key element; ecommerce resolution accuracy 53.8% → 84.6% (golden store) and 46.2% → 76.9% (learned store). Banking was unchanged (0 learned flips — seed-coverage artifact: banking key descriptions don't overlap element labels).
- **Magnitude (5→25) rejected**: near-inert on saucedemo, ecommerce, banking (0–5.2% delta); only automationexercise moved (0→5.2%). The fast-path omission, not the magnitude, was the whole story.
- Shipped `d15d66c`: bonus applied pre-return on the fast path (both bonus methods are no-ops without RAG patterns/site scope → RAG-off mode untouched). Gates: 2876 passed, smoke 39/39, eval static 97.9% (RAG-off, unchanged), ruff + mypy clean.
- **Next for AI-058**: proceed — the learned-store mechanism now demonstrably steers resolution correctly.

---

## 🟡 AI-065 — Citation/rationale token-overhead watch (16b D8) — MEASUREMENT, no build yet

**Status:** 🟡 ready-for-agent (measurement only — no code change authorised yet)
**Priority:** Low (watch item — act only if the numbers say so).
**Depends on:** 16b Phase 3 (citations per criterion) existing to measure.
**Roadmap ref:** `docs/plans/ROADMAP_ROADTO_PRODUCTION.md` → Tier 5 → **16b** decision D8; full spec `docs/specs/FEATURE_SPEC_test_to_document_traceability.md` §7.

**One-line:** 16b's per-criterion `source_refs` + `justification` add prompt/output tokens to every generation run. D8 mandated tracking so overhead is seen in numbers, not vibes.

**Watch triggers (any one → open a sizing/scoping ticket):**
- citation+rationale tokens add >15% to mean generation-token cost in the eval harness measurement
- generation latency regresses beyond noise on the eval datasets
- rationale text repeatedly hits the ~400-char cap (sign the cap is too tight or the model is rambling)

**Response options if triggered (in order):** tighten the rationale cap → drop rationale to pointer-only `PRIVACY_MODE`-style display → move to structured refs (D8's option C). Do **not** silently raise caps or drop verification.
