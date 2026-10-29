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
    evidence_tracker.click('#item', label='select item', expected_page='http://localhost:8781/index.html')
    evidence_tracker.fill('#quantity', '1', label='quantity', expected_page='http://localhost:8781/index.html')


@pytest.mark.evidence(condition_ref="TC-03", story_ref="S01")
def test_03_click_place_order(page: Page, evidence_tracker):
    evidence_tracker.navigate('http://localhost:8781/index.html')
    evidence_tracker.click('#item', label='select item', expected_page='http://localhost:8781/index.html')
    evidence_tracker.fill('#quantity', '1', label='quantity', expected_page='http://localhost:8781/index.html')
    evidence_tracker.click('#place-order', label='Place Order', expected_page='http://localhost:8781/index.html')


@pytest.mark.evidence(condition_ref="TC-04", story_ref="S01")
def test_04_verify_success_message(page: Page, evidence_tracker):
    evidence_tracker.navigate('http://localhost:8781/index.html')
    evidence_tracker.click('#item', label='select item', expected_page='http://localhost:8781/index.html')
    evidence_tracker.fill('#quantity', '1', label='quantity', expected_page='http://localhost:8781/index.html')
    evidence_tracker.click('#place-order', label='Place Order', expected_page='http://localhost:8781/index.html')
    evidence_tracker.assert_visible('#order-success-title', label='order success message', expected_page='http://localhost:8781/success.html?item=blue-top&qty=1')