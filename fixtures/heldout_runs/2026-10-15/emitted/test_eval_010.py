from playwright.sync_api import Page, expect
import pytest
from playwright.sync_api import Page


@pytest.mark.evidence(condition_ref="TC-01", story_ref="S01")
def test_01_navigate_to_home(page: Page, evidence_tracker):
    evidence_tracker.navigate('http://localhost:8781/index.html')
    expect(page).to_have_url("http://localhost:8781/index.html")


@pytest.mark.evidence(condition_ref="TC-02", story_ref="S01")
def test_02_select_item_and_quantity(page: Page, evidence_tracker):
    evidence_tracker.navigate('http://localhost:8781/index.html')
    pytest.skip("Skipping: unresolved placeholders for: 'quantity'. 2 of 3 placeholders resolved")
    evidence_tracker.click('#place-order', label='select item', expected_page='http://localhost:8781/index.html')


@pytest.mark.evidence(condition_ref="TC-03", story_ref="S01")
def test_03_click_place_order(page: Page, evidence_tracker):
    evidence_tracker.navigate('http://localhost:8781/index.html')
    pytest.skip("Skipping: unresolved placeholders for: 'quantity'. 3 of 4 placeholders resolved")
    evidence_tracker.click('#place-order', label='select item', expected_page='http://localhost:8781/index.html')
    evidence_tracker.click('#back-to-store', label='Place Order', expected_page='http://localhost:8781/success.html?item=blue-top&qty=1')


@pytest.mark.evidence(condition_ref="TC-04", story_ref="S01")
def test_04_verify_success_message(page: Page, evidence_tracker):
    evidence_tracker.navigate('http://localhost:8781/index.html')
    pytest.skip("Skipping: unresolved placeholders for: 'quantity'. 4 of 5 placeholders resolved")
    evidence_tracker.click('#place-order', label='select item', expected_page='http://localhost:8781/index.html')
    evidence_tracker.click('#back-to-store', label='Place Order', expected_page='http://localhost:8781/success.html?item=blue-top&qty=1')
    evidence_tracker.assert_visible(':has-text("Item Blue Top Grey Hoodie Quantity Place Order Your order could not be completed. Please fill in all fields and try again.")', label='order success message', expected_page='http://localhost:8781/index.html')