# Ingestion Improvements (Local) — Tiered CPU-First OCR + Format Scope + Quality Summary

**Created:** 2026-08-24
**Status:** Spec — Draft (open questions in §9 to grill before build)
**Depends on:** AI-045 #4 (PDF OCR wiring + dedup — shipped 2026-08-24), Phase 3 RAG (shipped), Phase 6 6b embedding-stamp (shipped)
**Companion (later):** `docs/specs/FEATURE_SPEC_tancat_cloud_ingestion.md` (post-launch, separate product) — *not* part of this build.

---

## 1. What This Is

Ingestion is how a customer's **own domain documents** (insurance policies, underwriting
guides, claims wordings, Playwright docs) become the RAG knowledge store that makes
generated tests accurate *for their domain*. It is a **one-time onboarding step** —
run once, write a durable store, reuse forever. It is **not** a CI/CD concern (CI
restores the pre-built store from cache; it never re-ingests or re-OCRs).

This spec improves the **local** ingestion path so it:

1. **Works on any customer hardware** (CPU-first, no GPU required) — the default must
   "just work" on a laptop, Windows or Mac, with or without a GPU.
2. **Handles the documentation scope customers actually have** — text PDFs, scanned
   PDFs, Markdown (v1); a defined set of "not yet" formats rather than silent failure.
3. **Tells the customer what happened** — an ingestion quality/summary signal so they
   know when a doc was only partially ingested and should be re-run at a higher tier.

The guiding principle from the commercial discussion: **ingestion is the trust
differentiator** ("your generator learns *your* domain, on *your* hardware, no
egress"). Quality here *is* product quality — a garbage ingested PDF produces garbage
tests and the customer blames the product, not the scan.

**What this is NOT:**
- A PDF tool. The customer buys "your generator understands our domain," not "OCR."
- A GPU feature. The default is CPU. GPU tiers are opt-in accuracy boosts.
- A cloud feature. Cloud ingestion is a *separate later product* (TanCat Cloud),
  deliberately kept out of the air-gapped local product.

---

## 2. The Tiered OCR Fallback (the core change)

Today (post-AI-045 #4) the path is: **PyMuPDF (text) → [gap: no OCR without a
dedicated-GPU Unlimited-OCR] → skip with WARNING.** The gap is "no dedicated NVIDIA/
ROCm GPU = no OCR ever," even though CPU OCR engines exist and would cover the
majority of customer hardware (including integrated-GPU machines like Strix Halo).

Introduce a **default CPU OCR tier** so scanned pages are handled on any machine, and
keep the GPU VLM as an optional top tier.

### 2.1 Tiers

| Tier | Engine (candidate) | Hardware | Role | Size (approx) |
|---|---|---|---|---|
| 0 | PyMuPDF (existing) | Any | Text-based PDFs, zero deps. **Default, always on.** | in the `[pdf]` extra |
| **1** | **RapidOCR** (PP-OCRv5/v6 via ONNX Runtime) | **CPU only** | **Scanned pages, any machine. The new default OCR tier.** | ~50–80 MB |
| 2 | PaddleOCR-VL (~0.9B) *or* Surya (multi-column) | Small GPU / high-spec CPU | Better layout/table/reading-order accuracy. **Opt-in "high-accuracy" mode.** | ~200 MB–1.5 GB |
| 3 | olmOCR / dots.ocr (3B+ VLM) *(re-pick from Unlimited-OCR)* | Dedicated GPU | RAG-ready markdown for the hardest complex docs. **Opt-in power mode.** | ~3–7 GB |

**Default selection:** Tier 0 → fall through to **Tier 1 (CPU)** automatically.
Tiers 2–3 are only used when the customer explicitly opts in (a `--ocr-tier` flag /
setting), because they pull heavier dependencies.

**Why RapidOCR as tier 1 (not Tesseract, not PaddleOCR-VL):**
- PaddleOCR-level recognition accuracy, but runs on **ONNX Runtime = pure CPU, no
  framework dependency, ~50–80 MB, 0.5–1 s/page** — the lightest deploy that is still
  accurate enough for real-world insurance scans.
- Tesseract is lighter (~10 MB) but measurably weaker on complex layouts/poor scans —
  not good enough to be the default for *our* doc class.
- PaddleOCR-VL (0.9B) is more accurate on layout but needs a real inference runtime
  and is slow on CPU — better as the opt-in tier-2 "high-accuracy" mode than the
  everywhere default.

### 2.2 Selection mechanics

`get_ocr_backend()` (src/ocr_backends.py) currently returns `pymupdf` or
`unlimited-ocr`. Extend the backend set + selection:

```
ocr_backend setting / OCR_BACKEND env  →  resolve tier
  "auto" (default)   → tier 0 (PyMuPDF); if a page is image-only, try tier 1 (CPU)
  "cpu"              → tier 1 forced
  "high-accuracy"    → tier 2 (PaddleOCR-VL / Surya)
  "power"            → tier 3 (VLM)
  "unlimited-ocr"    → (legacy alias → maps to a tier-3 VLM; re-pointed, see §5)
```

The `ocr_fallback` hook added in AI-045 #4 (`Callable[[Path, int], str]` on
`ingest_pdf`) is exactly the seam this plugs into — a **per-page** callable. The CPU
tier's `parse_page(path, page_number)` renders the single page to an image (300 DPI,
already done in the Unlimited-OCR path) and runs the ONNX OCR on it. **No whole-document
re-OCR** — only image-only pages hit OCR, so a mostly-text PDF stays fast.

### 2.3 Availability + graceful degradation (unchanged principle)

Each backend reports `.available`. A tier that isn't installed / can't run on this
machine is skipped and the path falls to the next-lower tier, then to "skip + WARNING."
**Never fail the ingestion because an optional OCR tier is missing.** The WARNING names
what would improve it (`Set OCR_BACKEND=high-accuracy ...`).

---

## 3. Format Scope (what v1 ingestion *promises*)

"Wide documentation scope" is real, but we must promise a defined set rather than
silently half-handle everything. v1:

| Format | Status | Notes |
|---|---|---|
| PDF (text) | ✅ | PyMuPDF — headings by font size, tables as markdown, chunked |
| PDF (scanned / image-only) | ✅ (new) | Tier-1 CPU OCR per page |
| Markdown | ✅ | `chunk_markdown_file` (existing) |
| PDF tables (large) | ⚠️ known limit | kept whole, never split (AI-045 §8.2 Medium) — acceptable for v1; document it |
| .docx / .html / .txt | ❌ not yet | **Out of v1.** Document as "coming soon"; reject cleanly with a clear message (no silent skip). |
| PDF chunk dedup | ✅ (new) | `dedup_key` — re-ingest is idempotent (AI-045 #4) |

**Decision needed (§9):** do we add `.txt` (trivial) in v1? Do we *reject* unknown
formats loudly, or warn-and-skip? Leaning: reject unknown extensions with a clear
"unsupported format X — supported: pdf, md" message (loud > silent).

---

## 4. Ingestion Quality Summary (the trust signal)

The customer needs to know **what happened** to their docs. Add a summary to the
ingestion CLI + the onboarding flow:

```
Ingestion summary (42 docs):
  ✅  38 docs fully ingested → 380 chunks
  ⚠️   3 docs partially ingested (12 pages OCR'd, 4 pages skipped — no text/OCR)
  ⚠️   1 doc skipped (unsupported format: report.docx)
  Store: 412 doc chunks (38 new, 374 already present / deduped)
  Suggested: re-run 3 docs with --ocr-tier high-accuracy for the skipped pages
```

Components:
- Per-doc outcome: full / partial / skipped(+reason).
- Page-level: how many pages OCR'd vs skipped (a doc with 50% skipped pages is a
  yellow flag, not green).
- **Dedup transparency** (new, from AI-045 #4): how many chunks were new vs
  already-present — so a re-ingest visibly does nothing rather than looking broken.
- **Actionable suggestion** when pages were skipped: "re-run at a higher tier."

This is cheap (we already log per-page skip/OCR events) and is the difference between
"it ingested" and "the customer trusts the ingestion."

---

## 5. Re-pointing the GPU VLM tier (housekeeping from the research)

AI-045 #4 built tier-3 as **Baidu Unlimited-OCR** (3B, `transformers` +
`trust_remote_code`, recommended serving via a dedicated vLLM Docker image, "tested on
python 3.12 + CUDA 12.9"). Research (2026-08-24) shows this is the **least portable**
choice for a tier we'll rarely run:

- It's DeepSeek-OCR-lineage — fine as a *class*, but the specific model's
  `trust_remote_code` + vLLM-Docker-only story is a maintenance burden.
- 2026 SOTA in this class: **dots.ocr**, **olmOCR**, **Qwen2.5-VL**. Any of these is a
  cleaner tier-3 than Unlimited-OCR.

**Decision (§9):** for v1 local, do we (a) *keep* Unlimited-OCR as the single tier-3
(least work, already wired), or (b) *abstract* tier-3 behind the same `OcrBackend`
seam and let the customer name the model, deferring the "which VLM" choice to when a
customer actually needs it? Leaning (a) for v1 — the CPU tiers are where the value is;
don't over-invest in a tier most customers won't use. Revisit at TanCat Cloud.

---

## 6. Dependencies & Protected Files

- **Uses (not modifies):** `src/ocr_backends.py` (extend), `src/pdf_ingest.py`
  (`ocr_fallback` seam from AI-045 #4), `scripts/rag_ingest.py` (CLI + summary),
  `src/rag_store.py` (dedup from AI-045 #4).
- **Protected files:** none in scope (`src/test_generator.py`, `src/llm_client.py`,
  `src/agents/`, `src/llm_providers/`, `.github/workflows/ci.yml` untouched).
- **New optional dep:** the CPU OCR engine (RapidOCR → `rapidocr-onnxruntime` or
  `rapidocr`), added as a **new optional extra** (e.g. `[ocr]`) so the default install
  stays light and the air-gapped customer who doesn't need OCR doesn't pull it. CI
  runs `--all-extras` so it's tested there.
- **Egress:** a *local* CPU OCR tier makes **zero** network calls. No egress-audit
  impact. (Any cloud path is TanCat Cloud, separate.)

---

## 7. Definition of Done

- [ ] Tier-1 CPU OCR backend (`OcrBackend` impl) — per-page, ONNX, pure CPU, no network.
- [ ] `get_ocr_backend()` selection extended (`auto`/`cpu`/`high-accuracy`/`power`).
- [ ] `ingest_pdf` default path: text page → PyMuPDF; image-only page → tier-1 CPU OCR;
      still-image-only-with-no-OCR → skip + loud WARNING (AI-045 #4 behavior preserved).
- [ ] New optional extra (`[ocr]`) for the CPU engine; default install unchanged.
- [ ] Ingestion **quality summary** in `rag_ingest.py` (per-doc outcome, page OCR/skip
      counts, dedup new-vs-present, actionable re-run suggestion).
- [ ] Format scope: pdf + md in; unknown formats rejected loudly with a clear message.
- [ ] Tests (hermetic, no GPU, no network): tier selection, CPU-OCR routing (real
      image-only PDF → OCR'd), graceful degradation when the engine is absent, summary
      output, unknown-format rejection. (Follow the AI-045 #4 lesson: install the
      `[ocr]` extra locally before validating — optional extras skip their tests
      otherwise.)
- [ ] Gates: full suite green (with `[ocr]` installed for parity with CI), smoke,
      ruff, mypy, eval static (no regression).
- [ ] Docs: `markdown_docs/src/ocr_backends.py.md`, `scripts/rag_ingest.py` usage,
      a user-facing "Ingest your docs" onboarding note.

---

## 8. Estimated Sessions

- Tier-1 CPU OCR backend + selection: 1–2
- Ingestion quality summary: 1
- Format scope + rejection + tests + docs: 1
- **Total: ~3–4 sessions** (CPU tier is the bulk; summary is the cheap high-value part)

---

## 9. Open Questions (grill before build)

1. **Default OCR engine** — confirm **RapidOCR** (PP-OCRv5/v6, ONNX) as tier-1 over
   Tesseract/PaddleOCR. Need: current package name + install size + a rough
   per-page CPU latency on a representative machine (is 0.5–1 s/page real here?).
2. **Exact current PaddleOCR-VL version** — research surfaced PP-OCRv6 (May 2026) and
   PaddleOCR-VL-1.5 (Jan 2026); confirm the current release for tier-2 (we may not
   build tier-2 in v1 — see Q3).
3. **Do we build tier-2 (PaddleOCR-VL/Surya) in v1 at all?** Leaning **no** — ship
   tier-0 + tier-1 (the everywhere default) + the summary, and defer tier-2/3 to
   "high-accuracy mode" when a customer asks. Reduces v1 scope to ~2 sessions.
4. **Tier-3 VLM** — keep Unlimited-OCR (already wired, least work) vs abstract + defer
   the model choice (§5). Leaning keep for v1.
5. **Format scope** — add `.txt` in v1? Reject-vs-warn on unknown formats (§3).
6. **Where does the quality summary surface** — CLI only, or also a small onboarding
   panel in the Streamlit UI? (UI is nicer but is Streamlit-work; CLI is enough for v1.)
7. **Optional extra naming + whether the CPU engine is a hard or soft dep** of the
   "scanned PDF" feature. Confirm the air-gapped customer can install `[ocr]`
   offline (wheel availability / no network at install).

---

## Appendix A — Research (2026-08-24, via Tavily)

- **Strix Halo (gfx1151) + ROCm:** works on *Linux* (ROCm 7.2, `torch.cuda.is_available()`
  → True, ~103 GB unified memory visible) but gfx1151 is **not** on AMD's official ROCm
  support matrix (runs via `gfx11-generic`); unstable across kernel/firmware versions;
  Windows support weak. ⇒ Do **not** rely on the GPU path for a Windows Strix-Halo
  customer; the CPU tier is the reliable answer there.
- **OCR engine landscape (2026):** Tesseract (~10 MB, CPU, weak on complex scans) ·
  RapidOCR (~50–80 MB, CPU/ONNX, PaddleOCR-accuracy, fastest) · PaddleOCR /
  PaddleOCR-VL (~0.9B–200 MB, best general, layout) · Surya (multi-column layout,
  PyTorch-scale) · dots.ocr / olmOCR / Qwen2.5-VL (3B+ VLMs, SOTA, need real GPU).
- **Unlimited-OCR (our current tier-3):** 3B, ~6.7 GB BF16, ≥8 GB VRAM,
  `trust_remote_code`, recommended via vLLM Docker image, "tested on python 3.12 +
  CUDA 12.9." DeepSeek-OCR-lineage. ⇒ Correct class (top tier), but the least portable
  specific choice; re-pick candidate (dots.ocr / olmOCR).
- **Decision matrix (refined, from discussion):**

  | Tool / Model | Type | Hardware | Primary Strength |
  |---|---|---|---|
  | RapidOCR / PP-OCRv6 | Traditional modular pipeline | CPU / lightweight GPU | Highest page-per-minute speed + boxes; **v1 default** |
  | Tesseract 5.x | Pattern matcher | CPU-only | Smallest footprint, clean printed text |
  | Surya OCR | Layout + reading-order engine | Modern CPU / edge GPU | Multi-column layout, reading order (tier-2) |
  | PaddleOCR-VL (~0.9B) | Compact hybrid VLM | Small GPU / high-spec CPU | Best layout-accuracy/throughput balance (tier-2) |
  | DeepSeek-OCR / olmOCR (~3B) | Dedicated OCR-VLM | Dedicated GPU (VRAM-bound) | Complex PDFs/charts → RAG-ready markdown (tier-3) |
  | Qwen2.5-VL / GLM-4.5V (7B–72B) | Large multimodal VLM | Heavy GPU / cloud | Deep reasoning over charts / visual Q&A (beyond our scope) |

  *Corrections applied vs the original matrix: Surya is a tier-2 layout engine, not a
  Tesseract-replacement default; add footprint + integrated/unofficial-GPU as decision
  axes (they decide the choice for air-gapped heterogeneous hardware).*
