# AI-Playwright-Test-Generator

A tool that generates Playwright Python test scripts from user stories using a local LLM. Takes acceptance criteria, scrapes target pages, resolves placeholders against scraped DOM data, and outputs runnable pytest tests.

## Language

**Placeholder**:
A token in skeleton test code (e.g. `{{CLICK:login button}}`) representing an unknown locator. The resolver replaces it with a concrete Playwright selector.
_Avoid_: token, marker, stub

**Skeleton**:
A test function containing placeholder tokens instead of real selectors. Produced in Phase 1 of the generation pipeline before placeholder resolution.
_Avoid_: template, draft, outline

**Resolution** (or **placeholder resolution**):
The process of replacing a placeholder with a concrete Playwright locator by scoring scraped elements against the placeholder's description.
_Avoid_: matching, filling, replacement

**Display element**:
An element whose primary role is presenting information (heading, paragraph, text, status, region, listitem, cell, generic). Contrasts with interactive elements (button, link, textbox) that are targets for CLICK/FILL.
_Avoid_: text element, content element, read-only element

**Interactive element**:
An element whose primary role is receiving user input (button, link, textbox, checkbox, combobox, etc.). Target for CLICK/FILL actions.
_Avoid_: clickable element, input element, action element

**Scoring pipeline**:
The multi-pass process that ranks scraped elements against a placeholder description. Pass 1 is text matching, Pass 2 is structural matching, Pass 3 is scoring with optional LLM assistance.
_Avoid_: resolver pipeline, matching pipeline

**Step-context**:
The immediately preceding interactive step (CLICK/FILL) in a test's execution sequence. Used to exclude its resolved element from ASSERT resolution to prevent self-matching.
_Avoid_: previous step, last action, context

**Soft filtering**:
A filtering strategy that applies a preference (e.g., display-only elements for ASSERT) but falls back to all elements if no preferred candidates score above threshold. Logged as low-confidence but never produces a skip solely due to filtering.
_Avoid_: best-effort filtering, graceful degradation

### Insurance Domain (LV Mock Site)

**Underwriting Guide**:
A document containing the business rules, rating factors, and decline criteria that determine policy pricing and eligibility. The Ingestion Agent parses these to provide domain context to the resolver.
_Avoid_: rate book, risk manual, pricing guide

**Quote Flow**:
The multi-step user journey through an insurance quotation system: Account → Product → Policy → Drivers → Vehicles → Extras → Quote & Payment. Each step has distinct page elements and validation rules.
_Avoid_: application flow, purchase journey, wizard

**Compulsory Excess**:
The minimum amount a policyholder must pay towards any claim, set by the insurer based on risk factors (driver age, penalty points, vehicle engine size). Displayed as informational text, not an interactive field.
_Avoid_: mandatory excess, minimum excess

**Voluntary Excess**:
An additional excess amount chosen by the policyholder. Higher voluntary excess reduces the premium. Represented as a range slider in the quote flow.
_Avoid_: optional excess, chosen excess

**Decline Rule**:
A business rule that prevents a quote from being offered. Examples: commercial use, 12+ penalty points, vehicle value over £100K. The system displays a decline banner instead of a premium.
_Avoid_: rejection rule, exclusion, hard stop

## Decisions

### ASSERT role filtering uses DISPLAY_ROLES, not INTERACTIVE_ROLES (2026-06-25)
B-016: For ASSERT resolution, prefer elements whose ARIA role is in a fixed
`DISPLAY_ROLES` set (`heading`, `paragraph`, `text`, `status`, `alert`,
`listitem`, `cell`, `columnheader`, `rowheader`, `image`, `strong`, `em`,
`caption`, `figure`). Roles are resolved via `computed_role` (from CDP AX tree)
with fallback to the raw `role` field. If no display-role element scores above
threshold, fall back to all elements (logged as low-confidence). The resolver
keeps this self-contained — no import from `AccessibilityEnricher` needed.
`link` and `textbox` are excluded from DISPLAY_ROLES even though they are leaf
roles, because ASSERT descriptions like "cart badge" should not match cart
links by keyword overlap.
