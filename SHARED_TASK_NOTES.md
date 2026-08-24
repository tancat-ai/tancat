# SHARED_TASK_NOTES — AI-045 #4 Overnight Run

**Started:** 2026-08-24
**Plan:** `docs/plans/AI-045_4_pdf_ocr_dedup_plan.md`

## Progress
- [x] Step 1: OCR wiring in pdf_ingest.py (22 passed / 1 skipped on the two OCR/PDF test files)
- [x] Step 2: Dedup key in rag_store.py (99 passed / 1 skipped across rag_store/rag_bundled/rag_retriever/pdf_ingest)
- [x] Step 3: Update callers + CLI surface (--prune-dupes flag, insert/skip summary)
- [x] Step 4: New tests (OCR wiring x5 + dedup key x3 + prune x2; full suite 2750 passed / 1 skipped)
- [x] Step 5: De-sloppify + verify — ruff clean, ruff format clean, mypy clean (140 files), smoke 39/39, full pytest 2750 passed / 1 skipped, eval static 97.9% (no regression)

## Findings / Decisions
- `add_docs` return changed int → `tuple[int, int]` (inserted, skipped); all 6 callers updated (rag_bundled, rag_ingest x2, test fakes).
- Dedup key = `sha256(source \x00 heading_path \x00 normalised_text)`; normalise = collapse whitespace + strip + lower.
- OCR fallback is page-scoped (only image-only pages hit OCR); `OcrBackend.parse_page` default returns ""; UnlimitedOCR implements single-page 300DPI OCR.
- `--prune-dupes` keeps lowest id per dedup_key group; legacy no-key rows untouched (cleaned by --reindex).
- pre-commit mypy runs on staged test files too — inner test fns/lambdas need full annotations (disallow_untyped_defs).
- [ ] Step 6: Documentation + session record + CHANGELOG

## Findings / Decisions
(record any design changes, surprises, or deviations from the plan here)

## Next Steps
(what the next iteration should do)

## Blockers / Open Questions
(anything that needs the user's input — do NOT block the loop on these; record and move on)
