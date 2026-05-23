# AI-019 Section 1: Audit & Context Gathering

## Objective
Identify exactly how the `evidence_tracker` is provided to tests and where the final code generation occurs to ensure prompts are updated correctly.

## Findings

### 1. Fixture Definition (`tests/conftest.py`)
- **Status**: Not found in `conftest.py`.
- **Implication**: The fixture must be defined elsewhere (likely via a plugin or manually injected) OR we need to ensure the generation process includes it in the imports/signatures. Since `get_streamlit_system_prompt_template` mandates its presence in the signature, we must ensure the test runner environment provides it.

### 2. Prompt Templates (`src/prompt_utils.py`)
- **`_EVIDENCE_TRACKER_RULES`**: Already contains strict instructions for mandatory signature, forbidden methods, and mandatory decorator.
- **`get_streamlit_pattern_template`**: Successfully appends `_EVIDENCE_TRACKER_RULES`. 
- **`get_skeleton_prompt_template`**: Does not explicitly mention `evidence_tracker`, which is acceptable as it only generates structural placeholders (Phase 1).

### 3. Code Realization Logic (`src/orchestrator.py`)
- **CRITICAL FINDING**: The method `_replace_token_in_line` (Lines 268-343) is currently hardcoded to generate standard Playwright code:
    - `CLICK` action generates `page.locator(...).click()`.
    - `ASSERT` action generates `expect(page.locator(...)).to_be_visible()`.
    - `FILL` action generates `page.locator(...).fill("")`.
    - `GOTO`/`URL` action generates `page.goto(...)`.
- **Requirement**: This method must be refactored to use the `evidence_tracker` methods (e.g., `evidence_tracker.click(...)`, `evidence_tracker.navigate(...)`) as defined in the new rules.

## Tasks Completed
- [x] Analyze `tests/conftest.py` to determine the `evidence_tracker` fixture definition and signature requirements.
- [x] Audit `src/prompt_utils.py` for all templates used in the final realization phase (converting placeholders to real code).
- [x] Review `src/orchestrator.py` to identify which prompt template is invoked during a final test emission.

## Success Criteria Verification
- [x] Clear understanding of the fixture name and how it must be injected into generated tests.
- [x] List of all templates that need updating to force `EvidenceTracker` usage (Identified: `src/orchestrator.py` implementation logic).