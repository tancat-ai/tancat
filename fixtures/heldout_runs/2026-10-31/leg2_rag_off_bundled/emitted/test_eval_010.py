from playwright.sync_api import Page, expect
import pytest
from playwright.sync_api import Page


@pytest.mark.evidence(condition_ref="TC-01", story_ref="S01")
def test_01_navigate_to_home(page: Page, evidence_tracker):
    evidence_tracker.navigate('http://localhost:8781/index.html', expected_page='http://localhost:8781/index.html')
    # Page arrival check: expected 'http://localhost:8781/index.html', browser observed on 'http://localhost:8781/index.html'
    evidence_tracker.record_page_expectation(expected_url='http://localhost:8781/index.html', observed_url='http://localhost:8781/index.html', trail_step="index=1; action=scrape; description='home page loaded'; from_url='http://localhost:8781/index.html'; to_url='http://localhost:8781/index.html'; navigated=False; timestamp=1793479749.6672955", producer='keyword', description='home page loaded', reason='', query_rule='identity', query_reason='story names no query in an address context; page identity decided')
    expect(page).to_have_url("http://localhost:8781/index.html")


@pytest.mark.evidence(condition_ref="TC-02", story_ref="S01")
def test_02_select_item_and_quantity(page: Page, evidence_tracker):
    evidence_tracker.navigate('http://localhost:8781/index.html', expected_page='http://localhost:8781/index.html')
    evidence_tracker.click('#item', label='select item', expected_page='http://localhost:8781/index.html')
    evidence_tracker.fill('#quantity', '1', label='quantity', expected_page='http://localhost:8781/index.html')


@pytest.mark.evidence(condition_ref="TC-03", story_ref="S01")
def test_03_click_place_order(page: Page, evidence_tracker):
    evidence_tracker.navigate('http://localhost:8781/index.html', expected_page='http://localhost:8781/index.html')
    evidence_tracker.click('#item', label='select item', expected_page='http://localhost:8781/index.html')
    evidence_tracker.fill('#quantity', '1', label='quantity', expected_page='http://localhost:8781/index.html')
    evidence_tracker.click('#place-order', label='Place Order', expected_page='http://localhost:8781/index.html')


@pytest.mark.evidence(condition_ref="TC-04", story_ref="S01")
def test_04_verify_success_message(page: Page, evidence_tracker):
    evidence_tracker.navigate('http://localhost:8781/index.html', expected_page='http://localhost:8781/index.html')
    evidence_tracker.click('#item', label='select item', expected_page='http://localhost:8781/index.html')
    evidence_tracker.fill('#quantity', '1', label='quantity', expected_page='http://localhost:8781/index.html')
    evidence_tracker.click('#place-order', label='Place Order', expected_page='http://localhost:8781/index.html')
    evidence_tracker.assert_visible('#order-success-title', label='order success message', expected_page='http://localhost:8781/success.html?item=blue-top&qty=1')