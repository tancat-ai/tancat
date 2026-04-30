"""Auto-generated page object module."""

from playwright.sync_api import Page


class ProductsPage:
    """Page Object for https://automationexercise.com/products. Scraped elements: 137."""

    URL = "https://automationexercise.com/products"

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
        self.page.locator('a[href="/products"]').click()
    def navigate_to_cart(self) -> None:
        self.page.locator('a[href="/view_cart"]').first.click()
    def click_signup_login(self) -> None:
        self.page.locator('a[href="/login"]').click()
    def click_test_cases(self) -> None:
        self.page.locator('a[href="/test_cases"]').click()
    def click_api_testing(self) -> None:
        self.page.locator('a[href="/api_list"]').click()
    def click_video_tutorials(self) -> None:
        self.page.locator('a[href="/c/AutomationExercise"]').click()
    def click_contact_us(self) -> None:
        self.page.locator('a[href="/contact_us"]').click()
    def fill_search(self, value: str) -> None:
        self.page.locator('#search_product').fill(value)
    def click_submit_search(self) -> None:
        self.page.locator('#submit_search').click()
    def click_women(self) -> None:
        self.page.locator('a').first.click()
    def click_dress(self) -> None:
        self.page.locator('a[href="/category_products/1"]').click()
    def click_tops(self) -> None:
        self.page.locator('a[href="/category_products/2"]').click()
    def click_saree(self) -> None:
        self.page.locator('a[href="/category_products/7"]').click()
    def click_men(self) -> None:
        self.page.locator('a').first.click()
    def click_tshirts(self) -> None:
        self.page.locator('a[href="/category_products/3"]').click()
    def click_jeans(self) -> None:
        self.page.locator('a[href="/category_products/6"]').click()
    def click_kids(self) -> None:
        self.page.locator('a').first.click()
    def click_tops_shirts(self) -> None:
        self.page.locator('a[href="/category_products/5"]').click()
    def click_6_polo(self) -> None:
        self.page.locator('a[href="/brand_products/Polo"]').click()
    def click_5_h_m(self) -> None:
        self.page.locator('a[href="/brand_products/H&M"]').click()
    def click_5_madame(self) -> None:
        self.page.locator('a[href="/brand_products/Madame"]').click()
    def click_3_mast_harbour(self) -> None:
        self.page.locator('a[href="/brand_products/Mast & Harbour"]').click()
    def click_4_babyhug(self) -> None:
        self.page.locator('a[href="/brand_products/Babyhug"]').click()
    def click_3_allen_solly_junior(self) -> None:
        self.page.locator('a[href="/brand_products/Allen Solly Junior"]').click()
    def click_3_kookie_kids(self) -> None:
        self.page.locator('a[href="/brand_products/Kookie Kids"]').click()
    def click_5_biba(self) -> None:
        self.page.locator('a[href="/brand_products/Biba"]').click()
    def click_continue_shopping(self) -> None:
        self.page.locator('.btn.btn-success.close-modal.btn-block').click()
    def click_view_product(self) -> None:
        self.page.locator('a[href="/product_details/1"]').click()
    def click_csrfmiddlewaretoken(self) -> None:
        self.page.locator('input[name="csrfmiddlewaretoken"]').click()
    def fill_susbscribe_email(self, value: str) -> None:
        self.page.locator('#susbscribe_email').fill(value)
    def click_subscribe(self) -> None:
        self.page.locator('#subscribe').click()
    def click_scrollup(self) -> None:
        self.page.locator('#scrollUp').click()
