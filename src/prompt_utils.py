"""Prompt helpers for both the intelligent pipeline and compatibility flows."""

from __future__ import annotations

import re
from typing import Any

_EVIDENCE_TRACKER_RULES = """=== EVIDENCE TRACKER RULES ===
1. Use evidence_tracker.navigate(url) instead of page.goto(url)
2. Use evidence_tracker.fill(locator, value, label=...) instead of page.locator(locator).fill(value)
3. Use evidence_tracker.click(locator, label=...) instead of page.locator(locator).click()
4. Use evidence_tracker.assert_visible(locator, label=...) instead of expect(page.locator(locator)).to_be_visible()
5. Always add @pytest.mark.evidence(condition_ref=..., story_ref=...) to every generated test function
6. Never call page.screenshot() directly
"""


def get_skeleton_prompt_template() -> str:
    """Return the Phase 1 skeleton-generation prompt."""
    return """You are a Playwright Python test engineer.

Generate a pytest sync Playwright skeleton from the specification below.

MANDATORY RULES:
- Use pytest format with the sync API only.
- Never use async/await, async def, asyncio.run(), or async_playwright.
- Never invent CSS selectors, XPath, or locator strings.
- Whenever a locator or destination is unknown, use placeholders in the exact format `{{{{ACTION:description}}}}`.
- Every acceptance criterion must become runnable structural test logic.
- Include a `# PAGES_NEEDED:` block listing every page URL required for the journey.
- In `# PAGES_NEEDED:`, every entry must be a real absolute URL beginning with `http://` or `https://`.
- NEVER use single-brace placeholders like `{{CLICK:...}}` written with only one outer brace pair, or `{{GOTO:...}}` written with only one outer brace pair.
- NEVER put placeholders inside the `# PAGES_NEEDED:` block.
- In Page Object methods, always use `self.page`, never bare `page`.
- Prefer standalone placeholder statements such as `{{{{CLICK:cart link}}}}` or `{{{{GOTO:cart page}}}}`.
- Do not wrap `CLICK`, `FILL`, or `ASSERT` placeholders in `page.locator(...)`.

ALLOWED PLACEHOLDERS:
- `{{{{CLICK:description}}}}`
- `{{{{FILL:description}}}}`
- `{{{{GOTO:description}}}}`
- `{{{{URL:description}}}}`
- `{{{{ASSERT:description}}}}`

OUTPUT RULES:
- Return valid Python code only.
- Use `from playwright.sync_api import Page, expect`.
- Create one test function per criterion.
- Keep Page Object classes as structural stubs only; do not guess selectors inside them.
- If you need a page URL but do not know it, infer a real candidate URL from the provided starting page or additional pages. Do not emit `{{URL:...}}` written with one brace pair, or `{{{{URL:...}}}}`, inside `# PAGES_NEEDED:`.

Known Target URLs:
{known_urls_block}

User Story:
{user_story}

Derived Test Conditions:
{conditions}
"""


def get_streamlit_system_prompt_template() -> str:
    """Return the fallback prompt used when running standard direct generation."""
    return (
        """You are an expert QA engineer writing Playwright Python tests in pytest format using the sync API.

REQUIREMENTS:
- Generate exactly {count} test functions from the acceptance criteria below.
- Use pytest format and Playwright sync API only.
- Do not use async/await or async_playwright.
- Each test runs in a FRESH browser context, so never assume login or cart state carries across tests.
- Use ONLY LOCATORS LISTED IN THE PAGE CONTEXT ABOVE.
- NEVER invent, guess, or create locators that are not present in the PAGE CONTEXT.

"""
        + _EVIDENCE_TRACKER_RULES
        + """

User Story:
{user_story}

Derived Test Conditions:
{conditions}
"""
    )


def build_page_context_prompt_block(page_context: Any) -> str:
    """Format page context into an approved-locators block for prompt injection."""
    raw_context = str(page_context or "").strip()
    if not raw_context:
        return """=== PAGE CONTEXT ===
No context available.

No PAGE CONTEXT is available, so only generate structural test logic and leave unknown interactions explicit.
"""

    truncated = raw_context
    truncation_note = ""
    if len(truncated) > 5000:
        truncated = truncated[:5000]
        truncation_note = "\nNOTE: PAGE CONTEXT was truncated to keep prompt size bounded.\n"

    locators = re.findall(r"(page\.[^\n]+)", truncated)
    if not locators:
        locators_block = "- No approved locators were extracted from PAGE CONTEXT."
    else:
        locators_block = "\n".join(f"- {locator.strip()}" for locator in locators)

    return f"""=== PAGE CONTEXT ===
{truncated}
{truncation_note}
=== APPROVED LOCATORS ===
{locators_block}
"""
