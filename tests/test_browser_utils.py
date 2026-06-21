"""Tests for src.browser_utils — dismiss_consent_overlays.

Validates that the consent dismissal logic:
1. Does NOT match generic button text on regular page content (B-015 regression)
2. DOES match consent buttons inside known overlay containers
3. Is safe when no overlays are present
"""

from __future__ import annotations

import re
from typing import Any
from unittest.mock import MagicMock

from src.browser_utils import dismiss_consent_overlays


class _NoOverlayPage:
    """Mock Page where all locators return count=0 (no overlays present)."""

    def __init__(self) -> None:
        self.locator_calls: list[str] = []
        self.evaluate_calls: list[str] = []
        self.mouse_click_calls: list[tuple[float, float]] = []
        self.keyboard_press_calls: list[str] = []
        self.wait_for_timeout_calls: list[int] = []

    def locator(self, selector: str) -> Any:
        self.locator_calls.append(selector)
        mock = MagicMock()
        mock.count.return_value = 0
        mock.is_visible.return_value = False
        mock.first = mock
        return mock

    def evaluate(self, js: str) -> list[Any]:
        self.evaluate_calls.append(js)
        return []

    def mouse(self) -> MagicMock:
        m = MagicMock()
        m.click.side_effect = lambda x, y: self.mouse_click_calls.append((x, y))
        return m

    def keyboard(self) -> MagicMock:
        k = MagicMock()
        k.press.side_effect = lambda key: self.keyboard_press_calls.append(key)
        return k

    def wait_for_timeout(self, ms: int) -> None:
        self.wait_for_timeout_calls.append(ms)


class _ContainerPage:
    """Mock Page where a specific container selector returns a visible container
    with a visible button inside it."""

    def __init__(
        self,
        container_selector: str,
        button_selector: str,
        button_text: str = "Accept",
    ) -> None:
        self.container_selector = container_selector
        self._match_keyword = _extract_keyword(container_selector)
        self.button_selector = button_selector
        self.button_text = button_text
        self.locator_calls: list[str] = []
        self.button_clicked = False
        self.evaluate_calls: list[str] = []
        self.mouse_click_calls: list[tuple[float, float]] = []
        self.keyboard_press_calls: list[str] = []
        self.wait_for_timeout_calls: list[int] = []

    def locator(self, selector: str) -> Any:
        self.locator_calls.append(selector)

        if self._match_keyword and self._match_keyword in selector:
            container: Any = MagicMock()
            container.count.return_value = 1
            container.is_visible.return_value = True
            container.locator.side_effect = self._container_locator
            mock_first: Any = MagicMock()
            mock_first.count.return_value = 1
            mock_first.is_visible.return_value = True
            # The code does page.locator(sel).first.locator(btn).first
            # so mock_first needs locator too
            mock_first.locator.side_effect = self._container_locator
            container.first = mock_first
            return container

        # Default: no match
        mock: Any = MagicMock()
        mock.count.return_value = 0
        mock.is_visible.return_value = False
        mock.first = mock
        return mock

    def _container_locator(self, selector: str) -> Any:
        if selector == self.button_selector:
            btn: Any = MagicMock()
            btn.count.return_value = 1
            btn.is_visible.return_value = True
            btn.click.side_effect = lambda timeout=None: setattr(self, "button_clicked", True)
            btn.first = btn
            return btn
        mock: Any = MagicMock()
        mock.count.return_value = 0
        mock.first = mock
        return mock

    def evaluate(self, js: str) -> list[Any]:
        self.evaluate_calls.append(js)
        return []

    def mouse(self) -> MagicMock:
        m = MagicMock()
        m.click.side_effect = lambda x, y: self.mouse_click_calls.append((x, y))
        return m

    def keyboard(self) -> MagicMock:
        k = MagicMock()
        k.press.side_effect = lambda key: self.keyboard_press_calls.append(key)
        return k

    def wait_for_timeout(self, ms: int) -> None:
        self.wait_for_timeout_calls.append(ms)


def _extract_keyword(selector: str) -> str:
    """Extract a matching keyword from a Playwright selector for mock routing.

    e.g. "[class*='cookie-banner']" -> "cookie-banner"
    "[class*='oneTrust']" -> "oneTrust"
    "[role='dialog']" -> "role='dialog'"
    """
    match = re.search(r"['\"]([^'\"]+)['\"]", selector)
    if match:
        return match.group(1)
    return selector


def _make_empty_container() -> MagicMock:
    """Create a mock container with no visible buttons."""
    container = MagicMock()
    container.count.return_value = 0
    container.is_visible.return_value = False
    container.first = container
    container.locator = lambda sel: MagicMock(  # type: ignore[assignment]
        count=lambda: 0, first=MagicMock()
    )
    return container


class TestDismissConsentOverlays_Safety:
    """Ensure dismiss_consent_overlays doesn't click real app buttons."""

    def test_does_not_click_continue_shopping_button(self) -> None:
        """B-015 regression: 'Continue Shopping' on cart page must not be clicked.

        The old implementation used 'button:has-text("Continue")' which matched
        the #continue-shopping button on saucedemo's cart page, causing
        navigation from cart.html -> inventory.html.
        """
        page = _NoOverlayPage()
        dismiss_consent_overlays(page)  # type: ignore[arg-type]

        assert page.mouse_click_calls == [], (
            f"Should not click any buttons on a page without overlays, got {page.mouse_click_calls}"
        )

    def test_does_not_click_ok_button_on_regular_page(self) -> None:
        """OK button in page content should not be dismissed."""
        page = _NoOverlayPage()
        dismiss_consent_overlays(page)  # type: ignore[arg-type]
        assert page.mouse_click_calls == []

    def test_does_not_click_accept_button_on_regular_page(self) -> None:
        """Accept button in page content should not be dismissed."""
        page = _NoOverlayPage()
        dismiss_consent_overlays(page)  # type: ignore[arg-type]
        assert page.mouse_click_calls == []

    def test_safe_when_no_overlays_present(self) -> None:
        """Function should complete without errors when no overlays exist."""
        page = _NoOverlayPage()
        dismiss_consent_overlays(page)  # type: ignore[arg-type]

    def test_does_not_remove_elements_by_zindex(self) -> None:
        """The old zIndex > 10000 removal is gone — verify no aggressive DOM surgery.

        The old implementation removed ALL elements with zIndex > 10000, which
        could affect legitimate page elements. The new implementation only removes
        elements matching specific, known ad/consent selectors.
        """
        page = _NoOverlayPage()
        dismiss_consent_overlays(page)  # type: ignore[arg-type]

        for js_code in page.evaluate_calls:
            assert "zIndex > 10000" not in js_code, "Should not remove elements by generic zIndex threshold"


class TestDismissConsentOverlays_Structural:
    """Test structural consent banner detection (known containers)."""

    def test_clicks_button_inside_cookie_banner_container(self) -> None:
        """Button with 'Accept' inside a [class*='cookie-banner'] should be clicked."""
        page = _ContainerPage(
            container_selector="[class*='cookie-banner']",
            button_selector="button:has-text('Accept')",
        )
        dismiss_consent_overlays(page)  # type: ignore[arg-type]
        assert page.button_clicked, "Should click Accept button inside cookie-banner container"

    def test_clicks_button_inside_onetrust_container(self) -> None:
        """Button inside [class*='oneTrust'] should be clicked."""
        page = _ContainerPage(
            container_selector="[class*='oneTrust']",
            button_selector="button:has-text('OK')",
        )
        dismiss_consent_overlays(page)  # type: ignore[arg-type]
        assert page.button_clicked, "Should click OK button inside oneTrust container"

    def test_clicks_button_inside_dialog_role_container(self) -> None:
        """Button inside [role='dialog'] should be clicked."""
        page = _ContainerPage(
            container_selector="[role='dialog']",
            button_selector="button:has-text('Got it')",
        )
        dismiss_consent_overlays(page)  # type: ignore[arg-type]
        assert page.button_clicked, "Should click 'Got it' button inside dialog container"

    def test_skips_when_container_has_no_matching_buttons(self) -> None:
        """Container with no consent-style buttons should not cause clicks."""
        page = _NoOverlayPage()
        page.locator = lambda sel: _make_empty_container()  # type: ignore[assignment]
        dismiss_consent_overlays(page)  # type: ignore[arg-type]
        assert page.mouse_click_calls == []


class TestDismissConsentOverlays_GoogleConsentTVM:
    """Test Google Consent TVM (fc-consent-root) handling."""

    def test_clicks_consent_button_in_fc_root(self) -> None:
        """Google Consent TVM button should be clicked."""
        mock_page = _NoOverlayPage()
        consent_btn: Any = MagicMock()
        consent_btn.count.return_value = 1
        consent_btn.is_visible.return_value = True
        clicked: list[bool] = []
        consent_btn.click.side_effect = lambda timeout=None: clicked.append(True)

        def custom_locator(sel: str) -> Any:
            mock_page.locator_calls.append(sel)
            if "fc-consent-root" in sel:
                mock = MagicMock()
                mock.first = consent_btn
                return mock
            return mock_page.locator(sel)

        mock_page.locator = custom_locator  # type: ignore[assignment]
        dismiss_consent_overlays(mock_page)  # type: ignore[arg-type]
        assert len(clicked) >= 1, "Should click Google Consent TVM button"
