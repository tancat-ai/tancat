# `src/hover_click_utils.py`

## Purpose
Hover-reveal click strategies for hidden elements. Handles elements hidden via CSS (display:none, visibility:hidden, opacity:0) that only become visible on parent mouseenter events — common in e-commerce product grids and navigation menus.

## Metadata
- **Lines:** 208
- **Imports:** typing.Any

## Functions
| Function | Description |
|----------|-------------|
| `try_hover_and_click(page, loc, locator)` | Public entry — attempts 5 progressive hover strategies, returns True on first success |
| `_attempt_hover_then_click(loc)` | Strategy 1: hover element directly, then click |
| `_attempt_mouseenter_then_click(loc)` | Strategy 2: dispatch mouseenter via JS, then click |
| `_attempt_ancestors_mouseenter(page, locator, loc)` | Strategy 3: dispatch mouseenter on all ancestors up to BODY, then click |
| `_attempt_parent_category_hover(page, locator, loc)` | Strategy 4: find visible parent category triggers, hover them, then click |
| `_attempt_force_show_and_click(page, locator)` | Strategy 5: JS force-show all hidden ancestors + remove hidden CSS classes, then el.click() |
| `_try_click(loc)` | Helper: attempts loc.click(timeout=5000), returns True/False |

## Strategy Chain (executed in order)
1. **Direct hover** — `loc.hover(timeout=2000)` then click
2. **JS mouseenter** — dispatch `MouseEvent('mouseenter', bubbles=true)` on target, then click
3. **Ancestor mouseenter** — walk `parentElement` chain to BODY, dispatch mouseenter on each, then click
4. **Parent category hover** — finds visible sibling A/LI elements, dispatches mouseenter, checks if target becomes visible
5. **Force-show** — walks up ancestors, forces `display:block`, `visibility:visible`, `opacity:1` with `!important`, removes hidden/collapse/invisible CSS classes, calls `el.click()` directly

## Key Patterns
- All strategies are non-blocking — exceptions caught silently, returns False on failure
- Strategy 4 targets automationexercise.com-style sidebar menus (Women→Dress pattern)
- Strategy 5 is last resort: modifies DOM styles with `!important` override
- `_try_click` uses 5s timeout for the final click attempt