from playwright.sync_api import Page, expect
import pytest
from playwright.sync_api import Page


@pytest.mark.evidence(condition_ref="TC-01", story_ref="S01")
def test_01_navigate_to_main_page(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://the-internet.herokuapp.com/', expected_page='https://the-internet.herokuapp.com/')
    # Page arrival check: expected 'https://the-internet.herokuapp.com/', browser observed on 'https://the-internet.herokuapp.com/'
    evidence_tracker.record_page_expectation(expected_url='https://the-internet.herokuapp.com/', observed_url='https://the-internet.herokuapp.com/', trail_step="index=1; action=scrape; description='home page loaded'; from_url='https://the-internet.herokuapp.com'; to_url='https://the-internet.herokuapp.com/'; navigated=True; timestamp=1793481802.1943772", producer='keyword', description='home page loaded', reason='', query_rule='identity', query_reason='story names no query in an address context; page identity decided')
    expect(page).to_have_url("https://the-internet.herokuapp.com/")


@pytest.mark.evidence(condition_ref="TC-02", story_ref="S01")
def test_02_click_javascript_alerts_link(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://the-internet.herokuapp.com/', expected_page='https://the-internet.herokuapp.com/')
    evidence_tracker.click('a[href="/javascript_alerts"]', label='JavaScript Alerts', expected_page='https://the-internet.herokuapp.com')
    # Page arrival check: expected 'https://the-internet.herokuapp.com/javascript_alerts', browser observed on 'https://the-internet.herokuapp.com/javascript_alerts'
    evidence_tracker.record_page_expectation(expected_url='https://the-internet.herokuapp.com/javascript_alerts', observed_url='https://the-internet.herokuapp.com/javascript_alerts', trail_step="index=2; action=scrape; description='JavaScript Alerts page loaded'; from_url='https://the-internet.herokuapp.com'; to_url='https://the-internet.herokuapp.com/javascript_alerts'; navigated=True; timestamp=1793481808.485714", producer='keyword', description='JavaScript Alerts page loaded', reason='', query_rule='identity', query_reason='story names no query in an address context; page identity decided')
    expect(page).to_have_url("https://the-internet.herokuapp.com/javascript_alerts")


@pytest.mark.evidence(condition_ref="TC-03", story_ref="S01")
def test_03_click_for_js_alert_button(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://the-internet.herokuapp.com/', expected_page='https://the-internet.herokuapp.com/')
    evidence_tracker.click('a[href="/javascript_alerts"]', label='JavaScript Alerts', expected_page='https://the-internet.herokuapp.com')
    evidence_tracker.click('button:has-text("Click for JS Alert")', label='Click for JS Alert', expected_page='https://the-internet.herokuapp.com/javascript_alerts')


@pytest.mark.evidence(condition_ref="TC-04", story_ref="S01")
def test_04_accept_javascript_alert_popup(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://the-internet.herokuapp.com/', expected_page='https://the-internet.herokuapp.com/')
    evidence_tracker.click('a[href="/javascript_alerts"]', label='JavaScript Alerts', expected_page='https://the-internet.herokuapp.com')
    evidence_tracker.click('button:has-text("Click for JS Alert")', label='Click for JS Alert', expected_page='https://the-internet.herokuapp.com/javascript_alerts')
    evidence_tracker.assert_visible('#result', label='alert popup accepted', expected_page='https://the-internet.herokuapp.com/javascript_alerts')


@pytest.mark.evidence(condition_ref="TC-05", story_ref="S01")
def test_05_verify_result_message_displays(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://the-internet.herokuapp.com/', expected_page='https://the-internet.herokuapp.com/')
    evidence_tracker.click('a[href="/javascript_alerts"]', label='JavaScript Alerts', expected_page='https://the-internet.herokuapp.com')
    evidence_tracker.click('button:has-text("Click for JS Alert")', label='Click for JS Alert', expected_page='https://the-internet.herokuapp.com/javascript_alerts')
    evidence_tracker.assert_visible('#result', label='result message', expected_page='https://the-internet.herokuapp.com/javascript_alerts')