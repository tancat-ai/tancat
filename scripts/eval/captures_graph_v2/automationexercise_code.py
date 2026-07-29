from playwright.sync_api import Page, expect
import pytest
from playwright.sync_api import Page

@pytest.mark.evidence(condition_ref="TC-01", story_ref="S01")
def test_01_navigate_to_home(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://automationexercise.com')
    expect(page).to_have_url("https://automationexercise.com")

@pytest.mark.evidence(condition_ref="TC-02", story_ref="S01")
def test_02_click_products_link(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://automationexercise.com')
    evidence_tracker.click('a[href="/products"]', label='Products')
    evidence_tracker.assert_visible('a[href="/products"]', label='Products')

@pytest.mark.evidence(condition_ref="TC-03", story_ref="S01")
def test_03_add_to_cart(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://automationexercise.com')
    evidence_tracker.click('a[href="/products"]', label='Products')
    evidence_tracker.click('.add-to-cart.btn[data-product-id="1"]', label='Add to cart Blue Top')

@pytest.mark.evidence(condition_ref="TC-04", story_ref="S01")
def test_04_verify_add_to_cart_message(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://automationexercise.com')
    evidence_tracker.click('a[href="/products"]', label='Products')
    evidence_tracker.click('.add-to-cart.btn[data-product-id="1"]', label='Add to cart Blue Top')
    evidence_tracker.assert_visible('.text-center', label='Product added to cart')

@pytest.mark.evidence(condition_ref="TC-05", story_ref="S01")
def test_05_click_cart_link(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://automationexercise.com')
    evidence_tracker.click('a[href="/products"]', label='Products')
    evidence_tracker.click('.add-to-cart.btn[data-product-id="1"]', label='Add to cart Blue Top')
    evidence_tracker.click('a[href="/view_cart"]', label='Cart')
    evidence_tracker.assert_visible('a[href="/view_cart"]', label='Cart')

@pytest.mark.evidence(condition_ref="TC-06", story_ref="S01")
def test_06_verify_cart_contents(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://automationexercise.com')
    evidence_tracker.click('a[href="/products"]', label='Products')
    evidence_tracker.click('.add-to-cart.btn[data-product-id="1"]', label='Add to cart Blue Top')
    evidence_tracker.click('a[href="/view_cart"]', label='Cart')
    evidence_tracker.assert_visible('p:has-text("Get the most recent updates from our site and be updated your self...")', label='Blue Top')
    evidence_tracker.assert_visible('p:has-text("Get the most recent updates from our site and be updated your self...")', label='Price')