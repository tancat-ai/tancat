from pages.home_page import HomePage
from playwright.sync_api import Page


@pytest.mark.evidence(condition_ref="TC-01", story_ref="S01")
def test_01_browse_dress_add_to_cart_and_verify(page: Page, evidence_tracker):
    home_page = HomePage(page, evidence_tracker)
    evidence_tracker.navigate('https://automationexercise.com/')
    home_page.click('Dress category link')
    evidence_tracker.fill('a[href="/products"]', 'Black Dress', label='search bar for dress products')
    evidence_tracker.click('.add-to-cart.btn[data-product-id="2"]', label='add to cart button for Black Dress')
    evidence_tracker.assert_visible('a[href="/view_cart"]', label='confirmation message that product is added to cart')
    evidence_tracker.click('a[href="/view_cart"]', label='view cart button')
    evidence_tracker.assert_visible('a[href="/view_cart"]', label='Black Dress item is visible in the cart')
