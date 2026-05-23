# Session Plan: AI-019 Prompt Update: EvidenceTracker Methods

## Goal
Update `src/prompt_utils.py` to add instructions guiding the LLM to use the `evidence_tracker.*` wrapper methods instead of raw Playwright `page.*` methods directly. 

## Target Files
- **Modified:** `src/prompt_utils.py`

## Implementation Specs & Rules
1. **New Constant:** Add `_EVIDENCE_TRACKER_RULES` alongside `_BASE_PLAYWRIGHT_RULES`, `_PAGE_CONTEXT_RULES`, etc.
2. **Mandatory Prompt Rules (Exact inclusion required):**
   - Use `evidence_tracker.navigate(url)` instead of `page.goto(url)`.
   - Use `evidence_tracker.fill(locator, value, label=...)` instead of `page.locator(locator).fill(value)`.
   - Use `evidence_tracker.click(locator, label=...)` instead of `page.locator(locator).click()`.
   - Use `evidence_tracker.assert_visible(locator, label=...)` instead of `expect(page.locator(locator)).to_be_visible()`.
   - Always add `@pytest.mark.evidence(condition_ref=..., story_ref=...)` to every generated test function.
   - Never call `page.screenshot()` directly.
3. **Template Update:** Update `get_streamlit_system_prompt_template()` to include the `_EVIDENCE_TRACKER_RULES` block.
4. **Protection:** `src/llm_client.py` and `src/test_generator.py` are PROTECTED. Do not modify them; rely strictly on `prompt_utils.py` updates.

## Completion Criteria
- Code must be fully typed.
- `bash fix.sh` (ruff + mypy) passes cleanly.
- (If applicable) Unit tests for prompts remain green (`pytest tests/ -v`).
