# Session 05: Intelligent Pipeline Rebuild Plan

## Why This Session Exists

The current intelligent pipeline is only partially aligned with the intended design in
[docs/specs/FEATURE_SPEC_intelligent_scraping_pipeline.md](c:/Users/l_a_c/code/AI-Playwright-Test-Generator/docs/specs/FEATURE_SPEC_intelligent_scraping_pipeline.md).

What was intended:
- Generate a placeholder-first skeleton from the story.
- Resolve test steps progressively across the user journey.
- Scrape the current page, fill the current page object, then move to the next page needed.
- Reuse page objects across tests.
- Save a structured output package.
- Run generated tests from the Streamlit UI.
- Show tables and downloadable artifacts.

What exists today:
- A skeleton-first pipeline is present.
- Placeholder replacement works better than before, but it is still largely global and page-pool based.
- Generated output is still a single flat test file.
- Page objects are inline stubs rather than generated reusable modules.
- Streamlit does not yet expose the full run/report/download workflow.

---

## Already Broken Before This Rewrite

These issues were present before the recent pipeline changes:

1. The old flow relied on a single-page scrape and the LLM guessing locators for later pages.
2. The intended stepwise multi-page page-object pipeline from the feature spec had not been implemented yet.
3. Running generated pytest tests directly as plain Python in VSCode was not a supported execution path.

---

## Current Gaps To Fix

1. The orchestrator still resolves placeholders against a combined scraped-page pool rather than a per-test, per-step journey.
2. There is no `page_object_builder.py`, even though it is part of the feature design.
3. Generated outputs are not saved as a package with `pages/`, test module, and manifest.
4. The Streamlit UI does not yet wire in generated-test execution, run results tables, or downloadable evidence/report artifacts.
5. Generated tests are valid pytest tests, but the UI does not teach or support the correct execution path clearly enough.

---

## Implementation Strategy

This work should be done in staged sessions. Do not try to finish it all in one pass.

### Stage 1: Lock The Pipeline Data Model

Goal:
- Define the exact intermediate structures the pipeline will use.

Create:
- `src/pipeline_models.py`

Dataclasses to add:
- `PlaceholderUse`
- `TestStep`
- `TestJourney`
- `ScrapedPage`
- `GeneratedPageObject`
- `PipelineArtifactSet`
- `ManifestRecord`

Why first:
- The parser, builder, orchestrator, and UI need a shared contract.

Acceptance:
- Unit tests prove the dataclasses serialize cleanly to dict/JSON-friendly structures.

---

### Stage 2: Upgrade The Skeleton Parser From Flat To Journey-Aware

Goal:
- Parse the skeleton into test-level and step-level structures, not just raw placeholders.

Modify:
- `src/skeleton_parser.py`

Add tests:
- `tests/test_skeleton_parser.py`

New parser responsibilities:
- Extract each `test_*` function separately.
- Preserve placeholder order within each test.
- Identify page object classes referenced by each test.
- Identify navigation transitions per test.
- Extract `# PAGES_NEEDED:` into stable typed records.

Acceptance:
- Given one skeleton containing multiple tests, the parser returns separate structured journeys.

---

### Stage 3: Build Real Page Objects From Scraped Pages

Goal:
- Stop keeping page objects as inline LLM stubs and generate them from real scraped data.

Create:
- `src/page_object_builder.py`

Add tests:
- `tests/test_page_object_builder.py`

Responsibilities:
- Build one class per resolved page.
- Include `URL` constant and `goto()` where appropriate.
- Generate methods only for actions backed by real scraped locators.
- Keep method names deterministic and reusable.

Output target:
- `generated_tests/<run_id>/pages/home_page.py`
- `generated_tests/<run_id>/pages/cart_page.py`
- etc.

Acceptance:
- Builder turns scraped metadata into stable Python page object modules.

---

### Stage 4: Rewrite The Orchestrator As A Sequential Journey Resolver

Goal:
- Resolve test 1 step-by-step through the user journey, then reuse or extend coverage for test 2.

Modify:
- `src/orchestrator.py`

Likely helper modules:
- `src/page_flow_discovery.py`
- `src/navigation_resolver.py`

Required behavior:
- Start from the provided starting URL.
- Resolve the first page object and first step.
- Detect or infer the next page needed.
- Scrape next page when required.
- Reuse existing page objects if already built.
- Continue until the full first test is resolved.
- Then evaluate test 2 for missing pieces only.

Important:
- This should no longer be â€œall placeholders vs all pages globallyâ€.

Acceptance:
- A multi-step cart journey resolves in order and records which page each step belongs to.

---

### Stage 5: Save Structured Artifacts Instead Of One Flat File

Goal:
- Match the intended output package described in the feature spec.

Modify or create:
- `src/file_utils.py`
- `src/pipeline_writer.py`

Output structure:
```text
generated_tests/
  test_<timestamp>_<slug>/
    pages/
      home_page.py
      product_page.py
      cart_page.py
      checkout_page.py
    test_<slug>.py
    scrape_manifest.json
    coverage_summary.json
```

Manifest contents:
- pages scraped
- element counts
- unresolved placeholders
- page object files generated
- tests generated
- run command

Acceptance:
- A pipeline run produces a complete, browsable folder package.

---

### Stage 6: Restore Streamlit Run/Report/Download Workflow

Goal:
- Make the generated tests runnable and reviewable from the app.

Modify:
- `streamlit_app.py`

Reuse existing modules:
- `src/run_utils.py`
- `src/pytest_output_parser.py`
- `src/coverage_utils.py`
- `src/report_utils.py`

UI features to add:
- Run generated test package with pytest
- Re-run failed only
- Results table
- Coverage/status table
- Raw pytest output panel
- Download buttons for:
  - generated test package
  - final test file
  - manifest JSON
  - local markdown report
  - Jira report
  - HTML report

Important note:
- Testable run/report helpers must stay in `src/`, not in `streamlit_app.py`.

Acceptance:
- A user can generate, run, inspect, and download artifacts from the Streamlit UI.

---

### Stage 7: Fix The VSCode Execution Story

Goal:
- Make the correct execution path obvious and easy.

This does not mean making pytest tests runnable as plain scripts.

Instead:
- Display the correct pytest command in the UI.
- Save a helper command in the manifest.
- Optionally generate a `.vscode/tasks.json` snippet or helper script later.

Correct path:
```bash
pytest generated_tests/<run_dir>/test_<slug>.py -v
```

Acceptance:
- The saved artifact package tells the user exactly how to run it correctly.

---

### Stage 8: Add Real UAT Coverage

Goal:
- Prove the pipeline on a real target flow, not only unit tests.

Add:
- stronger `tests/uat_pipeline_test.py`
- one mocked end-to-end pipeline integration test
- one real UAT checklist document

Real UAT checkpoints:
- skeleton generation
- page-by-page scraping
- page object generation
- final test package creation
- pytest run from generated package
- Streamlit run surface

Acceptance:
- We can demonstrate one real journey from the UI through to pytest execution.

---

## Suggested Session Order

1. `pipeline_models.py` + parser refactor
2. `page_object_builder.py`
3. orchestrator rewrite
4. pipeline artifact writer
5. Streamlit run/report/download integration
6. UAT hardening

---

## Risks

1. Dynamic sites may require the browser-backed scraper in `src/page_context_scraper.py`, not the lightweight HTML scraper in `src/scraper.py`.
2. The current intelligent pipeline touches protected or previously stable areas indirectly, so changes should be staged carefully.
3. UI work will be tempting to mix with backend work; resist that and finish one layer at a time.

---

## Definition Of Done

The feature is only done when all of the following are true:

1. The pipeline resolves user journeys step-by-step, not as a flat global replacement pass.
2. Generated output is a structured package with real page object modules.
3. The Streamlit app can generate and run the produced tests.
4. The UI shows tables and downloadable artifacts.
5. The saved package includes a manifest and the correct pytest run command.
6. A real UAT path works end-to-end.
7. `ruff`, `mypy`, and `pytest` all pass after implementation.
