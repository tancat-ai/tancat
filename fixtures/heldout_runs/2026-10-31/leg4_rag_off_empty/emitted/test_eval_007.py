from playwright.sync_api import Page, expect
import pytest
from playwright.sync_api import Page


@pytest.mark.evidence(condition_ref="TC-01", story_ref="S01")
def test_01_navigate_to_sign_in(page: Page, evidence_tracker):
    evidence_tracker.navigate('http://localhost:8781/index.html', expected_page='http://localhost:8781/index.html')
    # Page arrival check: expected 'http://localhost:8781/index.html', browser observed on 'http://localhost:8781/index.html'
    evidence_tracker.record_page_expectation(expected_url='http://localhost:8781/index.html', observed_url='http://localhost:8781/index.html', trail_step="index=1; action=scrape; description='sign in page loaded'; from_url='http://localhost:8781/index.html'; to_url='http://localhost:8781/index.html'; navigated=False; timestamp=1793484746.9447365", producer='keyword', description='sign in page loaded', reason='', query_rule='identity', query_reason='story names no query in an address context; page identity decided')
    expect(page).to_have_url("http://localhost:8781/index.html")


@pytest.mark.evidence(condition_ref="TC-02", story_ref="S01")
def test_02_sign_in(page: Page, evidence_tracker):
    evidence_tracker.navigate('http://localhost:8781/index.html', expected_page='http://localhost:8781/index.html')
    evidence_tracker.fill('#user-name', 'admin', label='username', expected_page='http://localhost:8781/index.html')
    evidence_tracker.fill('#password', 'secret', label='password', expected_page='http://localhost:8781/index.html')
    evidence_tracker.click('#login-button', label='Sign In', expected_page='http://localhost:8781/index.html')
    # Page arrival check: expected 'http://localhost:8781/dashboard.html', browser observed on 'http://localhost:8781/dashboard.html'
    evidence_tracker.record_page_expectation(expected_url='http://localhost:8781/dashboard.html', observed_url='http://localhost:8781/dashboard.html', trail_step="index=4; action=scrape; description='accounts dashboard loaded'; from_url='http://localhost:8781/dashboard.html'; to_url='http://localhost:8781/dashboard.html'; navigated=False; timestamp=1793484751.594024", producer='keyword', description='accounts dashboard loaded', reason='', query_rule='identity', query_reason='story names no query in an address context; page identity decided')
    expect(page).to_have_url("http://localhost:8781/dashboard.html")


@pytest.mark.evidence(condition_ref="TC-03", story_ref="S01")
def test_03_verify_balances(page: Page, evidence_tracker):
    evidence_tracker.navigate('http://localhost:8781/index.html', expected_page='http://localhost:8781/index.html')
    evidence_tracker.fill('#user-name', 'admin', label='username', expected_page='http://localhost:8781/index.html')
    evidence_tracker.fill('#password', 'secret', label='password', expected_page='http://localhost:8781/index.html')
    evidence_tracker.click('#login-button', label='Sign In', expected_page='http://localhost:8781/index.html')
    evidence_tracker.assert_visible('p.account_balance', label='account balances', expected_page='http://localhost:8781/dashboard.html')


@pytest.mark.evidence(condition_ref="TC-04", story_ref="S01")
def test_04_click_transfer_link(page: Page, evidence_tracker):
    evidence_tracker.navigate('http://localhost:8781/index.html', expected_page='http://localhost:8781/index.html')
    evidence_tracker.fill('#user-name', 'admin', label='username', expected_page='http://localhost:8781/index.html')
    evidence_tracker.fill('#password', 'secret', label='password', expected_page='http://localhost:8781/index.html')
    evidence_tracker.click('#login-button', label='Sign In', expected_page='http://localhost:8781/index.html')
    evidence_tracker.click('#transfer-link', label='Transfer Money', expected_page='http://localhost:8781/dashboard.html')
    evidence_tracker.assert_visible('.title', label='transfer form loaded', expected_page='http://localhost:8781/transfer.html')


@pytest.mark.evidence(condition_ref="TC-05", story_ref="S01")
def test_05_fill_transfer_form(page: Page, evidence_tracker):
    evidence_tracker.navigate('http://localhost:8781/index.html', expected_page='http://localhost:8781/index.html')
    evidence_tracker.fill('#user-name', 'admin', label='username', expected_page='http://localhost:8781/index.html')
    evidence_tracker.fill('#password', 'secret', label='password', expected_page='http://localhost:8781/index.html')
    evidence_tracker.click('#login-button', label='Sign In', expected_page='http://localhost:8781/index.html')
    evidence_tracker.click('#transfer-link', label='Transfer Money', expected_page='http://localhost:8781/dashboard.html')
    evidence_tracker.fill('#from-account', 'Checking', label='from account', expected_page='http://localhost:8781/transfer.html')
    evidence_tracker.fill('#to-account', 'Savings', label='to account', expected_page='http://localhost:8781/transfer.html')
    evidence_tracker.fill('#amount', '100', label='amount', expected_page='http://localhost:8781/transfer.html')
    evidence_tracker.click('#transfer-submit', label='Submit', expected_page='http://localhost:8781/transfer.html')


@pytest.mark.evidence(condition_ref="TC-06", story_ref="S01")
def test_06_verify_transfer_success(page: Page, evidence_tracker):
    evidence_tracker.navigate('http://localhost:8781/index.html', expected_page='http://localhost:8781/index.html')
    evidence_tracker.fill('#user-name', 'admin', label='username', expected_page='http://localhost:8781/index.html')
    evidence_tracker.fill('#password', 'secret', label='password', expected_page='http://localhost:8781/index.html')
    evidence_tracker.click('#login-button', label='Sign In', expected_page='http://localhost:8781/index.html')
    evidence_tracker.click('#transfer-link', label='Transfer Money', expected_page='http://localhost:8781/dashboard.html')
    evidence_tracker.fill('#from-account', 'Checking', label='from account', expected_page='http://localhost:8781/transfer.html')
    evidence_tracker.fill('#to-account', 'Savings', label='to account', expected_page='http://localhost:8781/transfer.html')
    evidence_tracker.fill('#amount', '100', label='amount', expected_page='http://localhost:8781/transfer.html')
    evidence_tracker.click('#transfer-submit', label='Submit', expected_page='http://localhost:8781/transfer.html')
    evidence_tracker.assert_visible('#transfer-success-title', label='transfer success message', expected_page='http://localhost:8781/transfer_success.html?amount=100.00')


@pytest.mark.evidence(condition_ref="TC-07", story_ref="S01")
def test_07_pay_bill(page: Page, evidence_tracker):
    evidence_tracker.navigate('http://localhost:8781/index.html', expected_page='http://localhost:8781/index.html')
    evidence_tracker.fill('#user-name', 'admin', label='username', expected_page='http://localhost:8781/index.html')
    evidence_tracker.fill('#password', 'secret', label='password', expected_page='http://localhost:8781/index.html')
    evidence_tracker.click('#login-button', label='Sign In', expected_page='http://localhost:8781/index.html')
    evidence_tracker.click('a[href="/payments.html"]', label='Pay Bills', expected_page='http://localhost:8781/dashboard.html')
    evidence_tracker.fill('#payment-amount', '50', label='bill amount', expected_page='http://localhost:8781/payments.html')
    evidence_tracker.click('#pay-bill', label='Pay', expected_page='http://localhost:8781/payments.html')


@pytest.mark.evidence(condition_ref="TC-08", story_ref="S01")
def test_08_verify_payment_success(page: Page, evidence_tracker):
    evidence_tracker.navigate('http://localhost:8781/index.html', expected_page='http://localhost:8781/index.html')
    evidence_tracker.fill('#user-name', 'admin', label='username', expected_page='http://localhost:8781/index.html')
    evidence_tracker.fill('#password', 'secret', label='password', expected_page='http://localhost:8781/index.html')
    evidence_tracker.click('#login-button', label='Sign In', expected_page='http://localhost:8781/index.html')
    evidence_tracker.click('a[href="/payments.html"]', label='Pay Bills', expected_page='http://localhost:8781/dashboard.html')
    evidence_tracker.fill('#payment-amount', '50', label='bill amount', expected_page='http://localhost:8781/payments.html')
    evidence_tracker.click('#pay-bill', label='Pay', expected_page='http://localhost:8781/payments.html')
    evidence_tracker.assert_visible('#payment-success-title', label='payment success message', expected_page='http://localhost:8781/payment_success.html?amount=50.00')