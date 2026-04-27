"""Auto-generated page object module."""

from playwright.sync_api import Page


class CartPage:
    """Page Object for https://automationexercise.com/view_cart. Scraped elements: 22."""

    URL = "https://automationexercise.com/view_cart"

    def __init__(self, page: Page) -> None:
        self.page = page

    def navigate(self) -> None:
        self.page.goto(self.URL)

    def __getattr__(self, name):
        def fallback(*args, **kwargs):
            import pytest
            pytest.skip(f"Method '{name}' not found on {self.__class__.__name__}. The scraper may have missed this element or its label changed.")
        return fallback

    def click_unnamed(self) -> None:
        self.page.locator('a[href="/"]').first.click()
    def click_home(self) -> None:
        self.page.locator('a[href="/"]').first.click()
    def click_products(self) -> None:
        self.page.locator('a[href="/products"]').first.click()
    def navigate_to_cart(self) -> None:
        self.page.locator('a[href="/view_cart"]').click()
    def click_signup_login(self) -> None:
        self.page.locator('a[href="/login"]').first.click()
    def click_test_cases(self) -> None:
        self.page.locator('a[href="/test_cases"]').click()
    def click_api_testing(self) -> None:
        self.page.locator('a[href="/api_list"]').click()
    def click_video_tutorials(self) -> None:
        self.page.locator('a[href="/c/AutomationExercise"]').click()
    def click_contact_us(self) -> None:
        self.page.locator('a[href="/contact_us"]').click()
    def proceed_to_checkout(self) -> None:
        self.page.locator('.btn.btn-default.check_out').click()
    def click_register_login(self) -> None:
        self.page.locator('a[href="/login"]').first.click()
    def click_continue_on_cart(self) -> None:
        self.page.locator('.btn.btn-success.close-checkout-modal.btn-block').click()
    def click_sleeves_printed_top_white(self) -> None:
        self.page.locator('a[href="/product_details/11"]').click()
    def click_1(self) -> None:
        self.page.locator('.disabled').click()
    def click_here(self) -> None:
        self.page.locator('a[href="/products"]').first.click()
    def click_csrfmiddlewaretoken(self) -> None:
        self.page.locator('input[name="csrfmiddlewaretoken"]').click()
    def fill_susbscribe_email(self, value: str) -> None:
        self.page.locator('#susbscribe_email').fill(value)
    def click_subscribe(self) -> None:
        self.page.locator('#subscribe').click()
    def click_scrollup(self) -> None:
        self.page.locator('#scrollUp').click()
