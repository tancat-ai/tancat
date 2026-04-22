# AI-019 Section 1: Audit & Context Gathering - COMPLETED

## Objective
Identify exactly how the `evidence_tracker` is provided to tests and where the final code generation occurs to ensure prompts are updated correctly.

## Findings

### 1. Fixture Definition (`tests/conftest.py`)
- **Current State**: The `evidence_tracker` fixture is **missing** from `tests/conftest.py`. Generated tests attempting to use it will fail with a `FixtureError`.
- **Requirement**: A new fixture named `evidence_tracker` must be implemented and exposed to the test execution context so that generated tests can inject it as an argument (e.g., `def test_xxx(page, evidence_tracker):`).

### 2. Prompt Templates (`src/prompt_utils.py`)
- **Direct Generation Mode**: The template `get_streamlit_system_prompt_template` is already updated with `_EVIDENCE_TRACKER_RULES`. This handles cases where the LLM generates the final code directly from context.
- **Skeleton Generation Mode**: The template `get_skeleton_prompt_template` does not require these rules, as it only produces structural placeholders (e.g., `{{{{CLICK:...}}}}`).

### 3. Final Code Realization (`src/orchestrator.py`)
- **Critical Issue Found**: In the Intelligent Pipeline, "final realization" is performed **programmatically** via `TestOrchestrator._replace_placeholders_sequentially`.
- **The Gap**: This method uses Python string replacement to inject standard Playwright commands (e.g., `page.locator(...).click()`). It currently **bypasses** the `evidence_tracker` entirely because it does not attempt to wrap these calls in the tracker pattern.
- **Requirement**: The logic in `src/orcheragstrator.py` (specifically within `_replace_token_in_line`) must be updated to produce code that utilizes the `evidence_tracker` (e.g., wrapping actions in a way that logs evidence).

## Success Criteria Status
- [x] Clear understanding of the fixture name and how it must be injected into generated tests.
- [x] List of all templates/logic that need updating to force `EvidenceTracker` usage.