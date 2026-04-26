"""Generate self-diagnosing failure evidence for failed test steps.

When a Playwright step fails, this module captures diagnostic context:
- Current page URL and title
- All available interactive elements on the page (categorized by action type)
- Suggested alternative locators that match the intended action description
- A human-readable failure note suitable for the evidence file

This is NOT auto-recovery — the test still fails, but the reporter captures
actionable debug information so the developer knows exactly what went wrong.
"""

from __future__ import annotations

import logging
from typing import Any

from playwright.sync_api import Page

from src.locator_scorer import LocatorScorer

logger = logging.getLogger(__name__)


class FailureReporter:
    """Generate self-diagnosing failure evidence for failed test steps."""

    __test__ = False

    @classmethod
    def diagnose_failure(
        cls,
        page: Page,
        locator: str | None,
        step_type: str,
        error: str,
    ) -> dict[str, Any]:
        """Return diagnostic context for a failed step.

        Args:
            page: The current Playwright Page instance.
            locator: The locator that failed (may be None for navigate steps).
            step_type: One of "click", "fill", "navigate", "assertion".
            error: The exception message from the failed step.

        Returns:
            A dict with keys: url, title, available_elements, suggested_locators,
            page_snapshot, error_summary.
        """
        diagnosis: dict[str, Any] = {
            "url": "",
            "title": "",
            "available_elements": [],
            "suggested_locators": [],
            "error_summary": error[:500] if error else "",
        }

        try:
            diagnosis["url"] = page.url or ""
        except Exception:
            diagnosis["url"] = "unknown"

        try:
            diagnosis["title"] = page.title() or ""
        except Exception:
            diagnosis["title"] = "unknown"

        # Capture interactive elements categorized by action type
        diagnosis["available_elements"] = cls._categorize_elements(page, step_type)

        # Suggest alternative locators
        diagnosis["suggested_locators"] = cls._suggest_locators(page, locator, step_type)

        # Capture accessibility snapshot for context
        diagnosis["page_snapshot"] = cls._capture_snapshot(page)

        logger.info(
            "Failure diagnosis for %s step on %s: %d elements, %d suggestions",
            step_type,
            diagnosis["url"],
            len(diagnosis["available_elements"]),
            len(diagnosis["suggested_locators"]),
        )

        return diagnosis

    @classmethod
    def _categorize_elements(
        cls,
        page: Page,
        step_type: str,
        max_elements: int = 20,
    ) -> list[dict[str, str]]:
        """Capture all interactive elements on the page, categorized.

        Returns a list of dicts with selector_hint, text, role, and category.
        Limited to max_elements to avoid bloating the evidence file.
        """
        elements: list[dict[str, str]] = []

        try:
            # Use Playwright's built-in accessibility snapshot for a structured
            # view of all focusable/interactive elements.
            tree = page.accessibility.snapshot()  # type: ignore[attr-defined]
            if isinstance(tree, dict):
                elements = cls._flatten_accessibility_tree(tree, max_elements)
            elif isinstance(tree, list):
                for node in tree[:max_elements]:
                    if isinstance(node, dict):
                        elements.append(
                            {
                                "name": str(node.get("name", "")),
                                "role": str(node.get("role", "")),
                                "value": str(node.get("value", "")),
                                "key": cls._make_key(node),
                            }
                        )
        except Exception as e:
            logger.debug("Accessibility snapshot failed: %s", e)

        # Fallback: use evaluate to grab all interactive elements
        if not elements:
            try:
                raw = page.evaluate("""() => {
                    const results = [];
                    const selectors = [
                        'a[href]', 'button', 'input[type="submit"]',
                        'input[type="button"]', 'input[type="text"]',
                        'input[type="email"]', 'input[type="password"]',
                        'textarea', 'select', '[role="button"]',
                        '[role="link"]', '[role="textbox"]',
                        '[role="combobox"]', '[role="listbox"]',
                        '[tabindex]:not([tabindex="-1"])',
                    ];
                    document.querySelectorAll(selectors.join(',')).forEach(el => {
                        results.push({
                            tag: el.tagName.toLowerCase(),
                            text: (el.textContent || '').trim().substring(0, 100),
                            id: el.id || '',
                            name: el.name || el.getAttribute('aria-label') || '',
                            role: el.getAttribute('role') || '',
                            type: el.type || '',
                            selector_hint: el.id ? '#' + el.id :
                                (el.className ? '.' + String(el.className).split(' ')[0] : ''),
                        });
                    });
                    return results;
                }""")
                if isinstance(raw, list):
                    elements = [
                        {
                            "tag": str(e.get("tag", ""))[:50],
                            "text": str(e.get("text", ""))[:100],
                            "id": str(e.get("id", ""))[:50],
                            "name": str(e.get("name", ""))[:50],
                            "role": str(e.get("role", ""))[:30],
                            "selector_hint": str(e.get("selector_hint", ""))[:80],
                        }
                        for e in raw[:max_elements]
                    ]
            except Exception as e:
                logger.debug("Fallback element capture failed: %s", e)

        return elements

    @classmethod
    def _flatten_accessibility_tree(
        cls,
        node: dict,
        max_count: int,
    ) -> list[dict[str, str]]:
        """Recursively flatten an accessibility tree into a flat list of nodes."""
        results: list[dict[str, str]] = []
        if len(results) >= max_count:
            return results

        if isinstance(node, dict):
            results.append(
                {
                    "name": str(node.get("name", ""))[:100],
                    "role": str(node.get("role", ""))[:30],
                    "value": str(node.get("value", ""))[:100],
                    "key": cls._make_key(node),
                }
            )
            for child in node.get("children") or []:
                if len(results) < max_count:
                    results.extend(cls._flatten_accessibility_tree(child, max_count - len(results)))

        return results

    @staticmethod
    def _make_key(node: dict) -> str:
        """Create a unique key for an accessibility node."""
        parts: list[str] = []
        if "name" in node:
            parts.append(str(node["name"])[:30])
        if "role" in node:
            parts.append(str(node["role"]))
        if "child_index" in node:
            parts.append(str(node["child_index"]))
        return " | ".join(parts) if parts else ""

    @classmethod
    def _suggest_locators(
        cls,
        page: Page,
        original_locator: str | None,
        step_type: str,
    ) -> list[dict[str, str]]:
        """Suggest alternative locators based on the page state.

        Uses LocatorScorer to score candidates and return them with consistent
        confidence levels. Returns a list of dicts with locator, type, score,
        confidence, and fragility_reason.
        """
        # Build raw candidate list from the page DOM
        raw_candidates = cls._extract_raw_candidates(page)

        # Score all candidates using LocatorScorer
        scored = LocatorScorer.score_candidates(raw_candidates)

        # Convert to the format expected by generate_failure_note
        suggestions: list[dict[str, str]] = []
        for candidate in scored[:15]:  # Limit to top 15
            suggestions.append(
                {
                    "locator": candidate["selector"],
                    "type": candidate["type"],
                    "score": str(candidate["score"]),
                    "confidence": candidate["confidence"],
                    "fragility_reason": candidate["fragility_reason"],
                }
            )

        return suggestions

    @classmethod
    def _extract_raw_candidates(cls, page: Page) -> list[dict[str, Any]]:
        """Extract raw locator candidates from the current page DOM.

        Returns a list of dicts with 'selector' and optional 'element' keys.
        """
        candidates: list[dict[str, Any]] = []

        try:
            raw = page.evaluate("""() => {
                const results = [];

                // Collect all elements with data-testid
                document.querySelectorAll('[data-testid]').forEach(el => {
                    results.push({
                        selector: '[data-testid="' + el.dataset.testid + '"]',
                        element_data: {
                            tag: el.tagName.toLowerCase(),
                            element_id: el.id || null,
                            test_id: el.dataset.testid || null,
                            aria_label: el.getAttribute('aria-label') || null,
                            name: el.name || null,
                        },
                    });
                });

                // Collect all elements with IDs (high confidence)
                document.querySelectorAll('[id]').forEach(el => {
                    results.push({
                        selector: '#' + el.id,
                        element_data: {
                            tag: el.tagName.toLowerCase(),
                            element_id: el.id || null,
                            test_id: el.dataset.testid || null,
                            aria_label: el.getAttribute('aria-label') || null,
                            name: el.name || null,
                        },
                    });
                });

                // Collect buttons
                document.querySelectorAll('button, [role="button"]').forEach(el => {
                    const id = el.id || '';
                    const ariaLabel = el.getAttribute('aria-label') || '';
                    const testid = el.dataset?.testid || '';
                    const className = el.className?.split?.(' ')?.[0] || '';

                    if (id) {
                        results.push({
                            selector: '#' + id,
                            element_data: {
                                tag: el.tagName.toLowerCase(),
                                element_id: id,
                                test_id: testid,
                                aria_label: ariaLabel,
                                name: el.name || null,
                            },
                        });
                    } else if (ariaLabel) {
                        results.push({
                            selector: '[aria-label="' + ariaLabel + '"]',
                            element_data: {
                                tag: el.tagName.toLowerCase(),
                                element_id: id,
                                test_id: testid,
                                aria_label: ariaLabel,
                                name: el.name || null,
                            },
                        });
                    }
                });

                // Collect inputs with names or IDs
                document.querySelectorAll('input, textarea, select').forEach(el => {
                    const id = el.id || '';
                    const name = el.name || '';
                    const ariaLabel = el.getAttribute('aria-label') || '';
                    if (id || name || ariaLabel) {
                        results.push({
                            selector: id ? '#' + id :
                                (name ? 'input[name="' + name + '"]' :
                                    (ariaLabel ? '[aria-label="' + ariaLabel + '"]' : '')),
                            element_data: {
                                tag: el.tagName.toLowerCase(),
                                element_id: id,
                                test_id: el.dataset?.testid || null,
                                aria_label: ariaLabel,
                                name: name,
                            },
                        });
                    }
                });

                // Collect links with text
                document.querySelectorAll('a[href]').forEach(el => {
                    const text = (el.textContent || '').trim().substring(0, 30);
                    if (text && text.length > 2 && !el.id) {
                        results.push({
                            selector: ':has-text("' + text + '")',
                            element_data: {
                                tag: 'a',
                                element_id: el.id || null,
                                test_id: el.dataset?.testid || null,
                                aria_label: el.getAttribute('aria-label') || null,
                                name: null,
                            },
                        });
                    }
                });

                return results;
            }""")
            if isinstance(raw, list):
                candidates = raw
        except Exception as e:
            logger.debug("Raw candidate extraction failed: %s", e)

        # Deduplicate by selector
        seen_selectors: set[str] = set()
        unique_candidates: list[dict[str, Any]] = []
        for c in candidates:
            sel = c.get("selector", "")
            if sel and sel not in seen_selectors:
                seen_selectors.add(sel)
                unique_candidates.append(c)

        return unique_candidates

    @classmethod
    def _capture_snapshot(cls, page: Page) -> str | None:
        """Capture a lightweight accessibility snapshot of the current page.

        Returns a markdown-like string summarizing the page structure,
        or None if snapshot capture fails.
        """
        try:
            snapshot = page.accessibility.snapshot()  # type: ignore[attr-defined]
            if isinstance(snapshot, dict):
                return cls._snapshot_to_text(snapshot, max_lines=50)
            return None
        except Exception as e:
            logger.debug("Snapshot capture failed: %s", e)
            return None

    @classmethod
    def _snapshot_to_text(cls, node: dict, max_lines: int = 50, depth: int = 0) -> str:
        """Convert an accessibility node tree to a text summary."""
        lines: list[str] = []
        if depth > max_lines:
            return ""

        indent = "  " * min(depth, 3)
        name = str(node.get("name", "")).strip()
        role = str(node.get("role", "")).strip()
        value = str(node.get("value", "")).strip()

        if name or role:
            line = f"{indent}[{role}] {name}"
            if value:
                line += f" = {value}"
            lines.append(line)

        for child in node.get("children") or []:
            if isinstance(child, dict):
                child_lines = cls._snapshot_to_text(child, max_lines, depth + 1)
                if child_lines:
                    lines.extend(child_lines.split("\n")[: max_lines - len(lines)])
            if len(lines) >= max_lines:
                break

        return "\n".join(lines)

    @classmethod
    def generate_failure_note(cls, diagnosis: dict[str, Any]) -> str:
        """Generate a human-readable failure note for the evidence file.

        This is designed to be actionable — a developer reading this note
        should immediately understand what went wrong and how to fix it.

        Args:
            diagnosis: The output from diagnose_failure().

        Returns:
            A formatted string suitable for the evidence file's failure_note field.
        """
        url = diagnosis.get("url", "unknown")
        title = diagnosis.get("title", "unknown")
        error_summary = diagnosis.get("error_summary", "Unknown error")

        lines: list[str] = [
            f"STEP FAILED on {url}",
            f"Page title: {title}",
            f"Error: {error_summary}",
        ]

        # Suggest locators if available (now scored by LocatorScorer)
        suggestions = diagnosis.get("suggested_locators", [])
        if suggestions:
            high_conf = [s for s in suggestions if s.get("confidence") == "high"]
            medium_high = [s for s in suggestions if s.get("confidence") == "medium-high"]
            medium = [s for s in suggestions if s.get("confidence") == "medium"]

            if high_conf:
                lines.append(
                    "Suggested high-confidence locators: " + ", ".join(f"'{s['locator']}'" for s in high_conf[:3])
                )
            if medium_high:
                lines.append(
                    "Medium-high confidence locators: " + ", ".join(f"'{s['locator']}'" for s in medium_high[:3])
                )
            if medium:
                lines.append("Medium-confidence locators: " + ", ".join(f"'{s['locator']}'" for s in medium[:3]))

        # Show available interactive elements
        elements = diagnosis.get("available_elements", [])
        if elements:
            # Group by role for readability
            by_role: dict[str, list[str]] = {}
            for elem in elements[:15]:
                role = elem.get("role", "unknown")
                name = elem.get("name", elem.get("text", ""))
                if name:
                    by_role.setdefault(role, []).append(name[:50])

            if by_role:
                lines.append("Interactive elements on page:")
                for role, names in sorted(by_role.items()):
                    if names:
                        lines.append(f"  [{role}] {', '.join(names[:5])}")

        return "\n".join(lines)
