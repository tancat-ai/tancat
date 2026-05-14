"""Hover-reveal click strategies for hidden elements.

Handles elements that are hidden via CSS (display:none, visibility:hidden,
opacity:0) and only become visible when parent elements receive mouseenter
events — common in e-commerce product grids and navigation menus.

Strategies (attempted in order):
1. Hover target element directly, then click
2. Dispatch mouseenter on target element, then click
3. Dispatch mouseenter on all ancestors, then click
4. Find and hover visible parent category triggers
5. Force-show via JavaScript and click programmatically
"""

from __future__ import annotations

from typing import Any


def try_hover_and_click(
    page: Any,
    loc: Any,
    locator: str,
) -> bool:
    """Attempt progressive hover strategies to make an element clickable.

    Returns True if any strategy succeeded, False if all failed.
    The caller is responsible for recording evidence steps.
    """
    # Attempt 1: Hover the element itself
    if _attempt_hover_then_click(loc):
        return True

    # Attempt 2: Dispatch mouseenter on element
    if _attempt_mouseenter_then_click(loc):
        return True

    # Attempt 3: Dispatch mouseenter on all ancestors
    if _attempt_ancestors_mouseenter(page, locator, loc):
        return True

    # Attempt 4: Find and hover visible parent category triggers
    if _attempt_parent_category_hover(page, locator, loc):
        return True

    # Attempt 5: Force-show via JavaScript
    if _attempt_force_show_and_click(page, locator):
        return True

    return False


# ── Private strategies ───────────────────────────────────────────


def _attempt_hover_then_click(loc: Any) -> bool:
    """Hover the element directly, then click."""
    try:
        loc.hover(timeout=2000, force=False)
    except Exception:
        pass
    return _try_click(loc)


def _attempt_mouseenter_then_click(loc: Any) -> bool:
    """Dispatch mouseenter on the target element, then click."""
    try:
        loc.evaluate("el => el.dispatchEvent(new MouseEvent('mouseenter', { bubbles: true }))")
    except Exception:
        pass
    return _try_click(loc)


def _attempt_ancestors_mouseenter(page: Any, locator: str, loc: Any) -> bool:
    """Dispatch mouseenter on all ancestors (for overlay patterns), then click."""
    try:
        page.evaluate(
            """
            (selector) => {
                const el = document.querySelector(selector);
                if (!el) return false;
                const mouseEnter = new MouseEvent('mouseenter', { bubbles: true });
                el.dispatchEvent(mouseEnter);
                let parent = el.parentElement;
                while (parent && parent.tagName !== 'BODY') {
                    parent.dispatchEvent(new MouseEvent('mouseenter', { bubbles: true }));
                    parent = parent.parentElement;
                }
                return true;
            }
            """,
            locator,
        )
    except Exception:
        pass
    return _try_click(loc)


def _attempt_parent_category_hover(page: Any, locator: str, loc: Any) -> bool:
    """Find and hover visible parent category triggers, then click.

    On sites like automationexercise.com, subcategory links (e.g., "Dress") are
    hidden inside a sidebar menu until you hover the parent category header
    (e.g., "Women", "Men", "Kids").
    """
    try:
        result = page.evaluate(
            """
            (targetSelector) => {
                const target = document.querySelector(targetSelector);
                if (!target) return { madeVisible: false };

                let el = target;
                while (el && el.tagName !== 'BODY') {
                    const parent = el.parentElement;
                    if (parent) {
                        for (const sibling of parent.children) {
                            const sibStyle = window.getComputedStyle(sibling);
                            const isVisible = sibStyle.display !== 'none' &&
                                              sibStyle.visibility !== 'hidden' &&
                                              sibStyle.opacity !== '0';
                            if (isVisible && (sibling.tagName === 'A' || sibling.tagName === 'LI') &&
                                sibling.textContent.trim().length > 0 && sibling.textContent.trim().length < 50) {
                                const mouseEnter = new MouseEvent('mouseenter', { bubbles: true });
                                sibling.dispatchEvent(mouseEnter);
                                sibling.style.visibility = 'visible';
                                sibling.style.display = 'block';
                            }
                        }
                    }

                    const ancestorStyle = window.getComputedStyle(el);
                    if (ancestorStyle.display !== 'none' && el.tagName === 'A' && el.textContent.trim()) {
                        const mouseEnter = new MouseEvent('mouseenter', { bubbles: true });
                        el.dispatchEvent(mouseEnter);
                        el.dispatchEvent(new MouseEvent('mouseover', { bubbles: true }));

                        const targetStyle2 = window.getComputedStyle(target);
                        if (targetStyle2.display !== 'none' && targetStyle2.visibility !== 'hidden') {
                            return { madeVisible: true };
                        }
                    }
                    el = el.parentElement;
                }
                return { madeVisible: false };
            }
            """,
            locator,
        )
        if result and result.get("madeVisible"):
            return _try_click(loc)
    except Exception:
        pass
    return False


def _attempt_force_show_and_click(page: Any, locator: str) -> bool:
    """Force-show the element via JavaScript and click programmatically.

    Last resort for elements hidden behind CSS hover menus.
    """
    try:
        page.evaluate(
            """
            (selector) => {
                const el = document.querySelector(selector);
                if (!el) return false;

                let current = el;
                while (current && current.tagName !== 'BODY') {
                    const style = window.getComputedStyle(current);
                    if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') {
                        current.style.display = '';
                        current.style.visibility = '';
                        current.style.opacity = '1';

                        const classesToRemove = [];
                        for (const cls of current.classList) {
                            if (cls.includes('hidden') || cls.includes('collapse') ||
                                cls.includes('invisible') || cls.includes('collapsed')) {
                                classesToRemove.push(cls);
                            }
                        }
                        classesToRemove.forEach(c => current.classList.remove(c));
                        current.style.setProperty('display', 'block', 'important');
                        current.style.setProperty('visibility', 'visible', 'important');
                    }
                    current = current.parentElement;
                }

                el.click();
                return true;
            }
            """,
            locator,
        )
        return True
    except Exception:
        return False


def _try_click(loc: Any) -> bool:
    """Attempt to click a locator, return True on success."""
    try:
        loc.click(timeout=5000)
        return True
    except Exception:
        return False
