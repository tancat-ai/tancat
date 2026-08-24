# TanCat Cloud — Ingestion Service (Separate Product, Post-Launch)

**Created:** 2026-08-24
**Status:** Roadmap item (NOT a build) — decision record only. No code, no schedule.
**Relationship to local product:** Deliberately **separate**. The local product is the
air-gapped offer ("your data never leaves your deployment"). TanCat Cloud is a distinct,
clearly-labeled offering so the cloud path can *never* blur that line.
**Companion spec (shippable now):** `docs/specs/FEATURE_SPEC_ingestion_local.md` — the
local ingestion improvements this item defers the cloud side of.

---

## 1. Why a Separate Product

From the commercial discussion (2026-08-24):

- Our #1 sales claim is the **air-gap / no-egress wedge**. Customer insurance PDFs are
  their most sensitive documents. A "cloud ingestion" path is, by definition, *their
  docs leaving their deployment* — putting it inside the local product would create a
  contradiction in the sales story.
- Making it a **separate product** (TanCat Cloud) keeps the local product's scope honest
  for launch and lets the cloud be marketed to a different buyer (the one who will trade
  egress for zero-setup), without diluting the air-gapped offer.
- It also mirrors the decision we already made for the **LLM**: BYO-LLM has local /
  self-hosted / cloud-API options. Ingestion gets the *same axis* — local / self-hosted
  / cloud — one mental model, two features.

**Post-launch** is the right timing: launch the air-gapped local product first (the
wedge), then offer TanCat Cloud to the segment that wants managed convenience.

---

## 2. The Ingestion-Backend Triad (mirrors the LLM triad)

```
Ingestion backend:
  1. Local              (the local product — default, air-gapped)
     tiers 0–3, CPU-first, full air-gap.  ← FEATURE_SPEC_ingestion_local.md
  2. Self-hosted service  (customer deploys it IN THEIR VPC / on-prem)
     we run it, their infra, full air-gap, hardware-agnostic.
     = the analogue of the *self-hosted LLM* option.
  3. Cloud API (convenience)  (docs go to a cloud OCR/embed provider)
     zero-setup, but EGRESS — docs leave the customer's boundary.
     = the analogue of the *cloud-API-key LLM* option.
```

**The strategic center is option 2 (self-hosted service):** it **kills the hardware
heterogeneity problem** (we control the OCR stack; customer hardware is irrelevant)
**without breaking the air-gap claim** (it runs in *their* boundary). Option 3 is the
cheap "cloud API key" analogue for customers who'll trade egress for zero-setup. Option 1
is what the local product ships.

This is *better* than a simple "cloud vs local" split because option 2 is the
combination a compliance-minded insurance customer actually wants.

---

## 3. What "TanCat Cloud" Would Be (sketch — to spec later)

- A **managed ingestion service**: customer sends docs (or points us at a location) →
  TanCat Cloud runs the tiered OCR + chunking + embedding → returns the store / chunks →
  persisted to the customer's local `rag_store.db` (or their workspace).
- **Runs the same ingestion code** as the local product (the tiered `OcrBackend` seam),
  just deployed by us / in their VPC instead of on their laptop.
- **Hardware-agnostic by construction** — no RapidOCR-on-a-laptop debugging, no ROCm
  fiddling, consistent accuracy.
- Likely a **Docker image / container** the customer runs in their VPC (option 2), and/or
  a hosted endpoint (option 3) for the convenience tier.

---

## 4. Hard Requirements (the ones that can't be skipped)

These are non-negotiable because they protect the wedge:

1. **Egress must be explicit and labeled on every path.** Option 3 (cloud API) *egresses*
   — the UI/docs must say "this sends your docs to {provider}." Option 2 (self-hosted)
   must be verifiably in-boundary. The no-egress claim lives or dies on this clarity.
2. **Any cloud provider call goes through the egress audit** (`scripts/audit_egress.py`,
   `docs/security/egress-audit.md`). We built that as a *security claim* (43 tests,
   "0 flagged"). A cloud-ingestion path that bypasses it silently undoes our own story.
   New cloud vendors = new audit entries + updated egress doc.
3. **It must reuse the local ingestion code path** (the tiered `OcrBackend` +
   `ingest_pdf` + dedup from AI-045 #4), not fork it. One ingestion implementation, two
   deployment targets.
4. **Data minimization + retention policy** for the convenience tier (option 3): what
   does the provider keep? For how long? This is a legal/ToS question, not just
   technical — needs a documented answer before option 3 ships.

---

## 5. Open Questions (to grill when it becomes a real spec)

1. **Is TanCat Cloud a product, or a deployment mode of the local product?** (The
   discussion leaned "separate product" — confirm. A separate product means separate
   repo/packaging/pricing/ToS.)
2. **Which option(s) first?** Leaning: **option 2 (self-hosted service) first** (it's
   the differentiator, preserves the wedge, and is mostly "package the local ingestion
   in a container + run it in their VPC"). Option 3 (cloud-API convenience) later —
   cheapest to build but the one most likely to muddle the no-egress message.
3. **Pricing/packaging** — separate SKU? Bundled with a license tier? (Ties to Phase 6
   license model + runs/credits metering.)
4. **The tier-3 VLM choice** (dots.ocr / olmOCR vs Unlimited-OCR) is the *natural* place
   to re-pick, because TanCat Cloud controls the GPU stack. Defer the decision until we
   know what hardware the cloud runs on.
5. **Embedding in the cloud** — do we also offer a cloud *embedding* API (parallel to
   the cloud-LLM option), or keep embeddings local? (Embeddings of their docs are
   sensitive — a cloud embedding endpoint is another egress decision.)
6. **Self-hosted service shape** — single container? Per-deployment (matches Phase 6
   Part-1 "one shared server per company")? How does it auth (same offline ed25519
   license key as the local product?).

---

## 6. Sequencing / Relationship to Launch

```
Now (pre-launch):   FEATURE_SPEC_ingestion_local.md  → local tiers 0–1 + summary
                    (air-gapped, CPU-first, the wedge)
Launch:             local product ships (air-gapped headline)
Post-launch:        TanCat Cloud → spec this, build option 2 (self-hosted) first,
                    option 3 (cloud-API convenience) after, VLM re-pick folded in
```

**Do NOT** let TanCat Cloud scope leak into the local product's launch scope. The local
product's ingestion is tiers 0–1 (+ summary) and nothing cloud-shaped.

---

## Appendix — Research pointers (2026-08-24)

- Egress/audit: `docs/security/egress-audit.md`, `scripts/audit_egress.py`, `src/url_guard.py`.
- Local ingestion code: `src/ocr_backends.py`, `src/pdf_ingest.py` (AI-045 #4 `ocr_fallback`
  seam), `scripts/rag_ingest.py`, `src/rag_store.py` (dedup).
- LLM triad precedent (D1): `docs/plans/RESEARCH_SAAS_AND_LAUNCH.md` §D1 (BYO-LLM: local /
  self-hosted / cloud-API-key).
- Phase 6 Part-1 (per-company deployment, the shape option-2 self-hosted service would
  match): `docs/plans/ROADMAP_ROADTO_PRODUCTION.md` §13.
- OCR tier research: `docs/specs/FEATURE_SPEC_ingestion_local.md` Appendix A.
