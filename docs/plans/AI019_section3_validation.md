# AI-019 Section 3: End-to-End Validation

## Objective
Verify that the updated prompts generate tests that correctly use `EvidenceTracker` and that these tests execute successfully without errors.

## Tasks
- [x] Generate a new set of tests using a standard user story via the Streamlit UI or CLI.
- [ ] Inspect generated code to ensure:
    - `evidence_tracker` is in the test function signature.
    - `@pytest.mark.evidence` is present.
    - Playwright methods are wrapped by `evidence_tracker`.
- [ ] Run the generated tests via `pytest`.
- [ ] Verify that evidence (screenshots/logs) is actually being captured by checking the output directories or logs.

## Success Criteria
- Generated tests compile and run without syntax errors.
- All test interactions are routed through the tracker.
- Evidence files are created for each step of the test execution.