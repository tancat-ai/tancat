---
purpose: >
  Data models for the skeleton-first test generation pipeline.
  Defines PlaceholderUse, PageRequirement, TestJourney, TestStep, and pipeline run state.
lines: ~200
created: "2026-05-30"
---

# `src/pipeline_models.py`

## High-Level Purpose

Core data structures that flow through the skeleton-first pipeline: skeleton generation → placeholder extraction → DOM scraping → placeholder resolution → code generation.

## Key Data Models

### `PlaceholderUse`
A single `{{ACTION:description}}` token found in skeleton code.
- `action`: str — CLICK, FILL, GOTO, URL, ASSERT
- `description`: str — human-readable element description
- `token`: str — full placeholder string e.g. `{{CLICK:Login button}}`
- `line_number`: int — line in generated code
- `raw_line`: str — full source line containing placeholder

### `PageRequirement`
A page the test needs to navigate to (from PAGES_NEEDED block).
- `keyword`: str — short keyword e.g. "cart", "checkout"
- `description`: str — parenthetical description from skeleton

### `TestJourney`
Structured representation of one generated test function.
- `test_name`: str — function name e.g. "test_01_login"
- `start_line`, `end_line`: int — code boundaries
- `page_object_names`: list[str] — page objects referenced
- `steps`: list[TestStep] — ordered steps with placeholders

### `TestStep`
A single executable line within a test function.
- `line_number`: int
- `raw_line`: str
- `placeholders`: list[PlaceholderUse]

## Dependencies

- None (pure data models)

## Depended On By

- `src/skeleton_parser.py` — populates models
- `src/placeholder_orchestrator.py` — consumes PlaceholderUse
- `src/orchestrator.py` — orchestrates pipeline using all models
- `src/page_object_builder.py` — uses TestJourney

## Recent API Additions

Symbols present in the source but not covered above (refresh pass, 5 items):

### `ExportMode` (class)

Controls how exported test files are produced.

### `ScrapedPage` (class)

Metadata for one scraped page used by the pipeline.

### `GeneratedPageObject` (class)

A page object module generated from scraped page data.

### `ManifestRecord` (class)

One unresolved or informational record written into the pipeline manifest.

### `PipelineArtifactSet` (class)

The structured output package produced by one pipeline run.

## Public API Additions

Refreshed 2026-10-02: public symbols present in the source and not listed above.

- `PlaceholderUse.to_dict` (method of `PlaceholderUse`): `PlaceholderUse.to_dict() -> dict[str, Any]` - Return a JSON-friendly representation.
- `TestStep.to_dict` (method of `TestStep`): `TestStep.to_dict() -> dict[str, Any]` - Return a JSON-friendly representation.
- `PageRequirement.to_dict` (method of `PageRequirement`): `PageRequirement.to_dict() -> dict[str, Any]` - Return a JSON-friendly representation.
- `TestJourney.to_dict` (method of `TestJourney`): `TestJourney.to_dict() -> dict[str, Any]` - Return a JSON-friendly representation.
- `TestResolutionCounts` (class): Resolved/unresolved placeholder counts for one generated test (B-097). When any placeholder in a test is unresolved, the emitter writes one pytest.skip() at the top of the test, which also hides every step that DI...
- `TestResolutionCounts.total` (method of `TestResolutionCounts`): `TestResolutionCounts.total() -> int` - Total placeholders seen in this test.
- `TestResolutionCounts.to_dict` (method of `TestResolutionCounts`): `TestResolutionCounts.to_dict() -> dict[str, Any]` - Return a JSON-friendly representation.
- `VerificationStatus` (class): How strongly a generated test verified its own criterion (B-100). - VERIFIED_BY_ELEMENT: an ASSERT resolved to a specific element and the emitter wrote a real check against it. - VERIFIED_BY_PAGE_ARRIVAL: the criterio...
- `TestVerificationVerdict` (class): What one generated test proved, decided at emit time (B-100). The eval harness has to *guess* this from the emitted code alone. The resolver knows it: it saw which page a locator was resolved against, and whether the...
- `TestVerificationVerdict.label` (method of `TestVerificationVerdict`): `TestVerificationVerdict.label() -> str` - Human-readable status phrase (e.g. verified by element).
- `TestVerificationVerdict.to_dict` (method of `TestVerificationVerdict`): `TestVerificationVerdict.to_dict() -> dict[str, Any]` - Return a JSON-friendly representation.
- `ScrapedPage.to_dict` (method of `ScrapedPage`): `ScrapedPage.to_dict() -> dict[str, Any]` - Return a JSON-friendly representation.
- `GeneratedPageObject.to_dict` (method of `GeneratedPageObject`): `GeneratedPageObject.to_dict() -> dict[str, Any]` - Return a JSON-friendly representation.
- `ManifestRecord.to_dict` (method of `ManifestRecord`): `ManifestRecord.to_dict() -> dict[str, Any]` - Return a JSON-friendly representation.
- `PipelineArtifactSet.to_dict` (method of `PipelineArtifactSet`): `PipelineArtifactSet.to_dict() -> dict[str, Any]` - Return a JSON-friendly representation.
