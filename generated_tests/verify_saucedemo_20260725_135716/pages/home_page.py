"""Auto-generated page object module."""

from playwright.sync_api import Page
from src.evidence_tracker import EvidenceTracker


class HomePage:
    """Page Object for https://www.saucedemo.com/. Scraped elements: 22."""

    URL = "https://www.saucedemo.com/"

    def __init__(self, page: Page, tracker: EvidenceTracker) -> None:
        self.page = page
        self.tracker = tracker

    def navigate(self) -> None:
        self.tracker.navigate(self.URL)

    def click(self, description: str) -> None:
        """Click by semantic description — resolve to POM method or delegate to tracker."""
        import re
        clean = description.lower().strip().strip(chr(39) + chr(34))
        method_name = 'click_' + re.sub(r'[^a-z0-9]', '_', clean)
        method_name = re.sub(r'_+', '_', method_name).strip('_')
        # Use dir() to avoid triggering __getattr__ which calls pytest.skip()
        # Search click_ methods AND navigate_ methods (e.g. navigate_to_cart)
        action_methods = {m for m in dir(self) if m.startswith('click_') or m.startswith('navigate_')}
        if method_name in action_methods:
            # If the exact match is a click_ method but there's also a
            # navigate_ method covering the same target, prefer navigate_.
            if method_name.startswith('click_'):
                target = method_name[len('click_'):]
                for method in dir(self):
                    if method.startswith('navigate_'):
                        if target.split('_')[-1] in method:
                            getattr(self, method)()
                            return
            getattr(self, method_name)()
            return
        # Partial match: score action methods by keyword overlap.
        # Remove noise words (link, button, section, navigation, category, page, etc.)
        # and action prefixes (click, navigate) so that click_view_cart and
        # navigate_to_cart are scored equally on their semantic content.
        noise = {'the', 'a', 'an', 'in', 'on', 'at', 'to', 'for', 'with', 'by', 'from',
                'of', 'and', 'or', 'link', 'button', 'section', 'navigation',
                'category', 'page', 'header', 'popup', 'menu', 'item', 'list',
                'click', 'navigate'}
        desc_parts = [p for p in method_name.split('_') if p and p not in noise]
        # Minimum score: when the description has multiple significant words
        # (e.g. 'add_to_cart' -> ['add', 'cart']), require at least 2 matches
        # to avoid false positives like 'navigate_to_cart' matching on just 'cart'.
        # Single-word descriptions still match on 1 (e.g. 'Dress' -> click_dress).
        min_score = 2 if len(desc_parts) >= 2 else 1
        best_method, best_score = None, 0
        # Sort so navigate_ methods come FIRST (key=0) and click_ after (key=1).
        # Then use >= so the FIRST best match wins — preferring navigate_.
        for method in sorted(action_methods, key=lambda m: not m.startswith('navigate_')):
            score = sum(1 for p in desc_parts if p in method)
            # navigate_ methods use a[href=...] locators and are inherently reliable,
            # so they only need score >= 1 even for multi-word descriptions.
            nav_min = 1 if method.startswith('navigate_') else min_score
            if score < nav_min:
                continue
            # Penalize very long method names that match on coincidence.
            # e.g. click_your_product_has_been_added_to_cart (6 words) matching
            # 'add'+'cart' is a false positive. Use match-ratio (score/words)
            # so click_view_cart (2/2=1.0) beats click_..._added_to_cart (2/6=0.33).
            method_words = len([w for w in method.split('_') if w not in {'click', 'navigate'}])
            ratio = score / max(method_words, 1)
            # Only boost navigate_ if the description suggests navigation
            # (contains words like 'view', 'go', 'page') — not for actions like 'Add to cart'.
            nav_keywords = {'view', 'go', 'page', 'home', 'login', 'signup', 'checkout'}
            if method.startswith('navigate_') and any(k in desc_parts for k in nav_keywords):
                ratio += 0.5
            if ratio > best_score:
                best_method, best_score = method, ratio
        # Require a minimum match ratio to avoid false positives.
        # e.g. 'add_to_cart' matching click_..._added_to_cart (ratio=0.29)
        # is worse than falling through to text-matching last resort.
        if best_method and best_score > 0.5:
            getattr(self, best_method)()
            return
        # Last resort: use page.locator with text matching (fast-fail).
        # Avoids delegating to evidence_tracker with a raw description
        # which Playwright tries as a CSS selector and hangs on 5s timeout.
        try:
            self.tracker.click('text=' + description, label=description)
        except Exception:
            self.page.locator('text=' + description).first.click(timeout=3000)
            raise

    def __getattr__(self, name):
        def fallback(*args, **kwargs):
            import pytest
            pytest.skip(f"Method '{name}' not found on {self.__class__.__name__}. The scraper may have missed this element or its label changed.")
        return fallback

    def fill_user_name(self, value: str) -> None:
        self.tracker.fill('#user-name', value, label='user name')
    def fill_password(self, value: str) -> None:
        self.tracker.fill('#password', value, label='password')
    def click_login_button(self) -> None:
        self.tracker.click('#login-button', label='login button')
    def click_swag_labs(self) -> None:
        self.tracker.click('title', label='swag labs')
    def click_accepted_usernames_are_standard_user_locked_out_user_problem_user_performance_glitch_user_error_user_visual_user_password_for_all_users_secret_sauce(self) -> None:
        self.tracker.click('[data-test="login-container"]', label='accepted usernames are standard user locked out user problem user performance glitch user error user visual user password for all users secret sauce')
    def click_accepted_usernames_are_standard_user_locked_out_user_problem_user_performance_glitch_user_error_user_visual_user(self) -> None:
        self.tracker.click('#login_credentials', label='accepted usernames are standard user locked out user problem user performance glitch user error user visual user')
    def click_accepted_usernames_are(self) -> None:
        self.tracker.click('h4', label='accepted usernames are')
    def click_password_for_all_users_secret_sauce(self) -> None:
        self.tracker.click('[data-test="login-password"]', label='password for all users secret sauce')
    def click_password_for_all_users(self) -> None:
        self.tracker.click('h4', label='password for all users')
    def fill_unnamed(self, value: str) -> None:
        self.tracker.fill('#user-name', value, label='unnamed')
    def click_unnamed(self) -> None:
        self.tracker.click('#login-button', label='unnamed')
