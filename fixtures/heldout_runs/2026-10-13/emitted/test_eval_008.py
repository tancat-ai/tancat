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
    evidence_tracker.click('#login-button', label='Sign in', expected_page='http://localhost:8781/index.html')


@pytest.mark.evidence(condition_ref="TC-03", story_ref="S01")
def test_03_verify_dashboard(page: Page, evidence_tracker):
    evidence_tracker.navigate('http://localhost:8781/index.html')
    evidence_tracker.fill('#user-name', 'admin', label='username', expected_page='http://localhost:8781/index.html')
    evidence_tracker.fill('#password', 'secret', label='password', expected_page='http://localhost:8781/index.html')
    evidence_tracker.click('#login-button', label='Sign in', expected_page='http://localhost:8781/index.html')
    evidence_tracker.assert_visible('#accounts-list', label='accounts dashboard loaded', expected_page='http://localhost:8781/dashboard.html')


@pytest.mark.evidence(condition_ref="TC-04", story_ref="S01")
def test_04_go_to_transfer(page: Page, evidence_tracker):
    evidence_tracker.navigate('http://localhost:8781/index.html')
    evidence_tracker.fill('#user-name', 'admin', label='username', expected_page='http://localhost:8781/index.html')
    evidence_tracker.fill('#password', 'secret', label='password', expected_page='http://localhost:8781/index.html')
    evidence_tracker.click('#login-button', label='Sign in', expected_page='http://localhost:8781/index.html')
    evidence_tracker.click('main:has-text("Welcome to Mock Bank Sign in to view your accounts, transfer money, and pay bills. Username Password Sign In Please enter a username and password.")', label='Transfer', expected_page='http://localhost:8781/index.html?username=admin&password=secret')
    expect(page).to_have_url("http://localhost:8781/index.html?username=admin&password=secret")


@pytest.mark.evidence(condition_ref="TC-05", story_ref="S01")
def test_05_fill_transfer_amount(page: Page, evidence_tracker):
    evidence_tracker.navigate('http://localhost:8781/index.html')
    evidence_tracker.fill('#user-name', 'admin', label='username', expected_page='http://localhost:8781/index.html')
    evidence_tracker.fill('#password', 'secret', label='password', expected_page='http://localhost:8781/index.html')
    evidence_tracker.click('#login-button', label='Sign in', expected_page='http://localhost:8781/index.html')
    evidence_tracker.click('a[href="/transfer.html"]', label='Transfer', expected_page='http://localhost:8781/dashboard.html')
    evidence_tracker.fill('#amount', '100', label='transfer amount', expected_page='http://localhost:8781/transfer.html')
    evidence_tracker.click('#transfer-submit', label='Submit', expected_page='http://localhost:8781/transfer.html')


@pytest.mark.evidence(condition_ref="TC-06", story_ref="S01")
def test_06_verify_transfer_success(page: Page, evidence_tracker):
    evidence_tracker.navigate('http://localhost:8781/index.html')
    evidence_tracker.fill('#user-name', 'admin', label='username', expected_page='http://localhost:8781/index.html')
    evidence_tracker.fill('#password', 'secret', label='password', expected_page='http://localhost:8781/index.html')
    evidence_tracker.click('#login-button', label='Sign in', expected_page='http://localhost:8781/index.html')
    evidence_tracker.click('a[href="/transfer.html"]', label='Transfer', expected_page='http://localhost:8781/dashboard.html')
    evidence_tracker.fill('#amount', '100', label='transfer amount', expected_page='http://localhost:8781/transfer.html')
    evidence_tracker.click('#transfer-submit', label='Submit', expected_page='http://localhost:8781/transfer.html')
    evidence_tracker.assert_visible('#transfer-success-title', label='transfer success message', expected_page='http://localhost:8781/transfer_success.html?amount=100.00')


@pytest.mark.evidence(condition_ref="TC-07", story_ref="S01")
def test_07_navigate_to_bill_payments(page: Page, evidence_tracker):
    evidence_tracker.navigate('http://localhost:8781/index.html')
    evidence_tracker.fill('#user-name', 'admin', label='username', expected_page='http://localhost:8781/index.html')
    evidence_tracker.fill('#password', 'secret', label='password', expected_page='http://localhost:8781/index.html')
    evidence_tracker.click('#login-button', label='Sign in', expected_page='http://localhost:8781/index.html')
    evidence_tracker.click('#pay-bill-link', label='Bill Payments', expected_page='http://localhost:8781/dashboard.html')
    expect(page).to_have_url("http://localhost:8781/payments.html")


@pytest.mark.evidence(condition_ref="TC-08", story_ref="S01")
def test_08_fill_payment_amount(page: Page, evidence_tracker):
    evidence_tracker.navigate('http://localhost:8781/index.html')
    evidence_tracker.fill('#user-name', 'admin', label='username', expected_page='http://localhost:8781/index.html')
    evidence_tracker.fill('#password', 'secret', label='password', expected_page='http://localhost:8781/index.html')
    evidence_tracker.click('#login-button', label='Sign in', expected_page='http://localhost:8781/index.html')
    evidence_tracker.click('#pay-bill-link', label='Bill Payments', expected_page='http://localhost:8781/dashboard.html')
    evidence_tracker.fill('#payment-amount', '50', label='payment amount', expected_page='http://localhost:8781/payments.html')
    evidence_tracker.click('#pay-bill', label='Submit', expected_page='http://localhost:8781/payments.html')


@pytest.mark.evidence(condition_ref="TC-09", story_ref="S01")
def test_09_verify_payment_success(page: Page, evidence_tracker):
    evidence_tracker.navigate('http://localhost:8781/index.html')
    evidence_tracker.fill('#user-name', 'admin', label='username', expected_page='http://localhost:8781/index.html')
    evidence_tracker.fill('#password', 'secret', label='password', expected_page='http://localhost:8781/index.html')
    evidence_tracker.click('#login-button', label='Sign in', expected_page='http://localhost:8781/index.html')
    evidence_tracker.click('#pay-bill-link', label='Bill Payments', expected_page='http://localhost:8781/dashboard.html')
    evidence_tracker.fill('#payment-amount', '50', label='payment amount', expected_page='http://localhost:8781/payments.html')
    evidence_tracker.click('#pay-bill', label='Submit', expected_page='http://localhost:8781/payments.html')
    evidence_tracker.assert_visible('#payment-success-title', label='payment success message', expected_page='http://localhost:8781/payment_success.html?amount=50.00')