# AI-019 Section 2: Prompt Engineering & Template Updates - COMPLETED

## Objective
Inject strict rules into final generation prompts to force the use of `EvidenceTracker` and required metadata markers.

## Tasks
- [x] Enhance `_EVERS_TRACKER_RULES` in `src/prompt_utils.py` to be more explicit about fixture injection (e.g., "You MUST include `evidence_tracker` in the test function signature").
- [x] Update final realization templates (specifically ensuring rules from system prompts are propagated) to include these rules.
- [x] Add strict requirements for the `@pytest.mark.evidence` decorator on every test function in the prompt instructions.

## Success Criteria
- Prompt templates explicitly forbid raw Playwright calls without tracking (goto, click, fill, screenshot).
- Prompt templates require the `evidence_tracker` fixture in the function signature.
- Prompt templates mandate the use of the evidence marker (`@pytest.mark.evidence`).