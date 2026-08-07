import pytest
from playwright.sync_api import Page, expect


@pytest.mark.evidence(condition_ref="TC-01", story_ref="S01")
def test_01_navigate_sign_in(page: Page, evidence_tracker):
    evidence_tracker.navigate('http://localhost:8781/index.html')
    expect(page).to_have_url("http://localhost:8781/index.html")


@pytest.mark.evidence(condition_ref="TC-02", story_ref="S01")
def test_02_sign_in_credentials(page: Page, evidence_tracker):
    evidence_tracker.navigate('http://localhost:8781/index.html')
    evidence_tracker.fill('#user-name', 'demo', label='username')
    evidence_tracker.fill('#password', 'password', label='password')
    evidence_tracker.click('#login-button', label='sign in button')


@pytest.mark.evidence(condition_ref="TC-03", story_ref="S01")
def test_03_verify_balances(page: Page, evidence_tracker):
    evidence_tracker.navigate('http://localhost:8781/index.html')
    evidence_tracker.fill('#user-name', 'demo', label='username')
    evidence_tracker.fill('#password', 'password', label='password')
    evidence_tracker.click('#login-button', label='sign in button')
    evidence_tracker.assert_visible('p.account_balance', label='account balances')


@pytest.mark.evidence(condition_ref="TC-04", story_ref="S01")
def test_04_click_transfer_link(page: Page, evidence_tracker):
    evidence_tracker.navigate('http://localhost:8781/index.html')
    evidence_tracker.fill('#user-name', 'demo', label='username')
    evidence_tracker.fill('#password', 'password', label='password')
    evidence_tracker.click('#login-button', label='sign in button')
    evidence_tracker.click('#transfer-link', label='Transfer Money')


@pytest.mark.evidence(condition_ref="TC-05", story_ref="S01")
def test_05_fill_transfer_form(page: Page, evidence_tracker):
    evidence_tracker.navigate('http://localhost:8781/index.html')
    evidence_tracker.fill('#user-name', 'demo', label='username')
    evidence_tracker.fill('#password', 'password', label='password')
    evidence_tracker.click('#login-button', label='sign in button')
    evidence_tracker.click('#transfer-link', label='Transfer Money')
    evidence_tracker.fill('#from-account', 'checking', label='from account')
    evidence_tracker.fill('#to-account', 'savings', label='to account')
    evidence_tracker.fill('#amount', '100', label='amount')
    evidence_tracker.click('#transfer-submit', label='submit button')


@pytest.mark.evidence(condition_ref="TC-06", story_ref="S01")
def test_06_verify_transfer_success(page: Page, evidence_tracker):
    evidence_tracker.navigate('http://localhost:8781/index.html')
    evidence_tracker.fill('#user-name', 'demo', label='username')
    evidence_tracker.fill('#password', 'password', label='password')
    evidence_tracker.click('#login-button', label='sign in button')
    evidence_tracker.click('#transfer-link', label='Transfer Money')
    evidence_tracker.fill('#from-account', 'checking', label='from account')
    evidence_tracker.fill('#to-account', 'savings', label='to account')
    evidence_tracker.fill('#amount', '100', label='amount')
    evidence_tracker.click('#transfer-submit', label='submit button')
    evidence_tracker.assert_visible('#transfer-success-title', label='transfer success message')


@pytest.mark.evidence(condition_ref="TC-07", story_ref="S01")
def test_07_pay_bill(page: Page, evidence_tracker):
    evidence_tracker.navigate('http://localhost:8781/index.html')
    evidence_tracker.fill('#user-name', 'demo', label='username')
    evidence_tracker.fill('#password', 'password', label='password')
    evidence_tracker.click('#login-button', label='sign in button')
    evidence_tracker.click('a[href="/payments.html"]', label='Pay Bills')
    evidence_tracker.fill('#payee', 'Electric Company', label='payee name')
    evidence_tracker.fill('#payment-amount', '200', label='payment amount')
    evidence_tracker.click('#pay-bill', label='pay bill button')


@pytest.mark.evidence(condition_ref="TC-08", story_ref="S01")
def test_08_verify_payment_success(page: Page, evidence_tracker):
    evidence_tracker.navigate('http://localhost:8781/index.html')
    evidence_tracker.fill('#user-name', 'demo', label='username')
    evidence_tracker.fill('#password', 'password', label='password')
    evidence_tracker.click('#login-button', label='sign in button')
    evidence_tracker.click('a[href="/payments.html"]', label='Pay Bills')
    evidence_tracker.fill('#payee', 'Electric Company', label='payee name')
    evidence_tracker.fill('#payment-amount', '200', label='payment amount')
    evidence_tracker.click('#pay-bill', label='pay bill button')
    evidence_tracker.assert_visible('#payment-success-title', label='payment success message')