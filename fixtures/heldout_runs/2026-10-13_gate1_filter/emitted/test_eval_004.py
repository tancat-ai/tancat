from playwright.sync_api import Page, expect
import pytest
from playwright.sync_api import Page


@pytest.mark.evidence(condition_ref="TC-01", story_ref="S01")
def test_01_navigate_to_main_page(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://the-internet.herokuapp.com/')
    expect(page).to_have_url("https://the-internet.herokuapp.com/")


@pytest.mark.evidence(condition_ref="TC-02", story_ref="S01")
def test_02_click_javascript_alerts_link(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://the-internet.herokuapp.com/')
    evidence_tracker.click('a[href="/javascript_alerts"]', label='JavaScript Alerts', expected_page='https://the-internet.herokuapp.com')
    expect(page).to_have_url("https://the-internet.herokuapp.com/javascript_alerts")


@pytest.mark.evidence(condition_ref="TC-03", story_ref="S01")
def test_03_click_js_alert_button(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://the-internet.herokuapp.com/')
    evidence_tracker.click('a[href="/javascript_alerts"]', label='JavaScript Alerts', expected_page='https://the-internet.herokuapp.com')
    evidence_tracker.click('button:has-text("Click for JS Alert")', label='Click for JS Alert', expected_page='https://the-internet.herokuapp.com/javascript_alerts')


@pytest.mark.evidence(condition_ref="TC-04", story_ref="S01")
def test_04_accept_javascript_alert(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://the-internet.herokuapp.com/')
    evidence_tracker.click('a[href="/javascript_alerts"]', label='JavaScript Alerts', expected_page='https://the-internet.herokuapp.com')
    evidence_tracker.click('button:has-text("Click for JS Alert")', label='Click for JS Alert', expected_page='https://the-internet.herokuapp.com/javascript_alerts')
    evidence_tracker.assert_visible('#result', label='alert popup accepted', expected_page='https://the-internet.herokuapp.com/javascript_alerts')


@pytest.mark.evidence(condition_ref="TC-05", story_ref="S01")
def test_05_verify_result_message(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://the-internet.herokuapp.com/')
    evidence_tracker.click('a[href="/javascript_alerts"]', label='JavaScript Alerts', expected_page='https://the-internet.herokuapp.com')
    evidence_tracker.click('button:has-text("Click for JS Alert")', label='Click for JS Alert', expected_page='https://the-internet.herokuapp.com/javascript_alerts')
    evidence_tracker.assert_visible('#result', label='result message', expected_page='https://the-internet.herokuapp.com/javascript_alerts')