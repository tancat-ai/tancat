# UX Cleanup — Streamlit App Layout Overhaul

## Problem

The current layout is ordered for a developer, not a manual tester. A first-time user sees: Base URL → auth toggle → journey builder wall-of-text → additional URLs → input mode → story → (Generate button hidden until text applied). The primary action is buried under optional configuration.

## UX Issues Found

| # | Issue | Severity |
|---|-------|----------|
| 1 | **Story input buried** under 4 optional config sections | High |
| 2 | **Generate button invisible** until text is entered and applied | High |
| 3 | **Journey builder expanded by default** with a wall of instructions | Medium |
| 4 | **Base URL feels mandatory** but isn't — blocks mental flow | Medium |
| 5 | **No grouping** — scraping config is scattered, equally weighted with primary inputs | Medium |
| 6 | **Credential profile selector** has no descriptive label ("Choose an option") | Low |
| 7 | **Criteria count** only in sidebar — easy to miss | Low |

## Proposed Layout (new order)

```
┌─────────────────────────────────────────────────┐
│  🤖 AI-Powered Playwright Test Generator        │
│─────────────────────────────────────────────────│
│                                                 │
│  📝 Input mode: [Upload .md] [Paste story]      │
│  [Story text area / file uploader]              │
│                                                 │
│  🌐 Target URL                                  │
│     [Base URL input]                            │
│     help: "URL of the page under test"          │
│                                                 │
│  [Generate Tests] button (always visible)       │
│                                                 │
│  ▸ ⚙️ Advanced Scraping Options (collapsed)     │
│     ├─ ➕ Additional pages                      │
│     ├─ 🔐 Authentication                       │
│     └─ 🗺️ Journey steps                        │
│                                                 │
│  ── Results area (code / coverage / run) ───    │
└─────────────────────────────────────────────────┘
```

## Proposed Changes

### [MODIFY] [streamlit_app.py](file:///c:/Users/l_a_c/code/AI-Playwright-Test-Generator/streamlit_app.py)

**1. Reorder main() layout** — story input first, URL second, Generate button third, advanced settings below

Move the input mode radio + story textarea/file uploader **above** the Base URL field. Move the Generate button to appear right after Base URL, always visible (disabled when no content).

**2. Group advanced scraping into one expander**

Wrap the following three sections into a single `st.expander("⚙️ Advanced Scraping Options", expanded=False)`:
- Additional pages textarea
- Credential profiles (toggle + profiles)
- Journey builder

This collapses ~200 lines of optional UI into one click.

**3. Keep Journey builder collapsed by default**

Change `st.session_state.journey_expanded` default to `False` and remove the line that sets it to `True` on render (line 364).

**4. Simplify journey builder instructions**

Replace the 8-line bullet list with a one-liner + "Learn more" expander:
```
"Define scraper navigation steps. Add a Capture step where you want context collected."
```
Move the detailed step-type descriptions into a nested `st.expander("ℹ️ Step type reference")`.

**5. Fix credential profile label**

Replace `label_visibility="collapsed"` on the active profile selectbox with a visible label: `"Active profile for scraping"`.

**6. Show criteria summary near Generate button**

After parsing, show `st.info(f"✅ Found {criteria_count} acceptance criteria — ready to generate")` directly above the Generate button instead of only in the sidebar.

**7. Always show Generate button**

Move the `if st.button("Generate Tests")` block outside the `if not content: return` guard. Show it disabled with a help message when no content is entered.

## Files Changed

Only [streamlit_app.py](file:///c:/Users/l_a_c/code/AI-Playwright-Test-Generator/streamlit_app.py) is modified. No backend, test, or protected file changes.

## Verification Plan

### Manual Verification
1. `uv run streamlit run streamlit_app.py`
2. First-time view: story input is the first thing visible, Generate button visible (disabled)
3. Paste a story → criteria count appears near button → Generate enables
4. Advanced section is collapsed — expanding it reveals additional pages, credentials, journey
5. Journey builder instructions are concise, not a wall of text
6. Active credential profile has a visible label
7. Existing functionality (scraping, generation, coverage, run) all still works

### Automated
```bash
pytest tests/ -v
ruff check streamlit_app.py
mypy streamlit_app.py
```
