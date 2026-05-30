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