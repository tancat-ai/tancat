from playwright.sync_api import Page, expect
import pytest
from playwright.sync_api import Page


@pytest.mark.evidence(condition_ref="TC-01", story_ref="S01")
def test_01_navigate_to_sign_in(page: Page, evidence_tracker):
    evidence_tracker.navigate('http://localhost:8781/index.html')
    expect(page).to_have_url("http://localhost:8781/index.html")


@pytest.mark.evidence(condition_ref="TC-02", story_ref="S01")
def test_02_sign_in(page: Page, evidence_tracker):
    evidence_tracker.navigate('http://localhost:8781/index.html')
    evidence_tracker.fill('#user-name', 'admin', label='username', expected_page='http://localhost:8781/index.html')
    evidence_tracker.fill('#password', 'secret', label='password', expected_page='http://localhost:8781/index.html')
    evidence_tracker.click('#login-button', label='Sign In', expected_page='http://localhost:8781/index.html')
    expect(page).to_have_url("http://localhost:8781/dashboard.html")


@pytest.mark.evidence(condition_ref="TC-03", story_ref="S01")
def test_03_verify_balances(page: Page, evidence_tracker):
    evidence_tracker.navigate('http://localhost:8781/index.html')
    evidence_tracker.fill('#user-name', 'admin', label='username', expected_page='http://localhost:8781/index.html')
    evidence_tracker.fill('#password', 'secret', label='password', expected_page='http://localhost:8781/index.html')
    evidence_tracker.click('#login-button', label='Sign In', expected_page='http://localhost:8781/index.html')
    evidence_tracker.assert_visible('p.account_balance', label='account balances', expected_page='http://localhost:8781/dashboard.html')


@pytest.mark.evidence(condition_ref="TC-04", story_ref="S01")
def test_04_click_transfer_link(page: Page, evidence_tracker):
    evidence_tracker.navigate('http://localhost:8781/index.html')
    evidence_tracker.fill('#user-name', 'admin', label='username', expected_page='http://localhost:8781/index.html')
    evidence_tracker.fill('#password', 'secret', label='password', expected_page='http://localhost:8781/index.html')
    evidence_tracker.click('#login-button', label='Sign In', expected_page='http://localhost:8781/index.html')
    evidence_tracker.click('#transfer-link', label='Transfer Money', expected_page='http://localhost:8781/dashboard.html')
    evidence_tracker.assert_visible('.title', label='transfer form loaded', expected_page='http://localhost:8781/transfer.html')


@pytest.mark.evidence(condition_ref="TC-05", story_ref="S01")
def test_05_fill_transfer_form(page: Page, evidence_tracker):
    evidence_tracker.navigate('http://localhost:8781/index.html')
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
    evidence_tracker.navigate('http://localhost:8781/index.html')
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
    evidence_tracker.navigate('http://localhost:8781/index.html')
    evidence_tracker.fill('#user-name', 'admin', label='username', expected_page='http://localhost:8781/index.html')
    evidence_tracker.fill('#password', 'secret', label='password', expected_page='http://localhost:8781/index.html')
    evidence_tracker.click('#login-button', label='Sign In', expected_page='http://localhost:8781/index.html')
    evidence_tracker.click('a[href="/payments.html"]', label='Pay Bills', expected_page='http://localhost:8781/dashboard.html')
    evidence_tracker.fill('#payment-amount', '50', label='bill amount', expected_page='http://localhost:8781/payments.html')
    evidence_tracker.click('#pay-bill', label='Pay', expected_page='http://localhost:8781/payments.html')


@pytest.mark.evidence(condition_ref="TC-08", story_ref="S01")
def test_08_verify_payment_success(page: Page, evidence_tracker):
    evidence_tracker.navigate('http://localhost:8781/index.html')
    evidence_tracker.fill('#user-name', 'admin', label='username', expected_page='http://localhost:8781/index.html')
    evidence_tracker.fill('#password', 'secret', label='password', expected_page='http://localhost:8781/index.html')
    evidence_tracker.click('#login-button', label='Sign In', expected_page='http://localhost:8781/index.html')
    evidence_tracker.click('a[href="/payments.html"]', label='Pay Bills', expected_page='http://localhost:8781/dashboard.html')
    evidence_tracker.fill('#payment-amount', '50', label='bill amount', expected_page='http://localhost:8781/payments.html')
    evidence_tracker.click('#pay-bill', label='Pay', expected_page='http://localhost:8781/payments.html')
    evidence_tracker.assert_visible('#payment-success-title', label='payment success message', expected_page='http://localhost:8781/payment_success.html?amount=50.00')