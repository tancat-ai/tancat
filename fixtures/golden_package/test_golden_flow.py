"""
Auto-generated Playwright test package entrypoint
Generated: 2026-08-03T00:00:00.000000
Base URL:  http://127.0.0.1:8123/index.html
"""

from playwright.sync_api import Page, expect
import pytest
from pages.home_page import HomePage
from pages.cart_page import CartPage


@pytest.mark.evidence(condition_ref="T01", story_ref="S01")
def test_t01_home_page_loads(page: Page, evidence_tracker):
    home_page = HomePage(page, evidence_tracker)
    evidence_tracker.navigate('http://127.0.0.1:8123/index.html')
    evidence_tracker.assert_visible('#title', label='home page loaded')


@pytest.mark.evidence(condition_ref="T02", story_ref="S02")
def test_t02_navigate_to_cart(page: Page, evidence_tracker):
    home_page = HomePage(page, evidence_tracker)
    cart_page = CartPage(page, evidence_tracker)
    evidence_tracker.navigate('http://127.0.0.1:8123/index.html')
    home_page.click('go to cart', selector='#go-cart')
    evidence_tracker.assert_visible('#cart-title', label='cart page loaded')
