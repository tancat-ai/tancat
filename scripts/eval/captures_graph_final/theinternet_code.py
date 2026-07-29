from playwright.sync_api import Page, expect
import pytest
from playwright.sync_api import Page

@pytest.mark.evidence(condition_ref="TC-01", story_ref="S01")
def test_01_navigate_to_the_the_internet_herokuapp_com_main_page(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://the-internet.herokuapp.com')

@pytest.mark.evidence(condition_ref="TC-02", story_ref="S01")
def test_02_click_the_javascript_alerts_link(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://the-internet.herokuapp.com')
    evidence_tracker.click('a[href="/javascript_alerts"]', label='JavaScript Alerts')

@pytest.mark.evidence(condition_ref="TC-03", story_ref="S01")
def test_03_click_the_click_for_js_alert_button(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://the-internet.herokuapp.com')
    evidence_tracker.click('a[href="/javascript_alerts"]', label='JavaScript Alerts')
    evidence_tracker.click('button:has-text("Click for JS Alert")', label='Click for JS Alert')

@pytest.mark.evidence(condition_ref="TC-04", story_ref="S01")
def test_04_accept_the_javascript_alert_popup(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://the-internet.herokuapp.com')
    evidence_tracker.click('a[href="/javascript_alerts"]', label='JavaScript Alerts')
    evidence_tracker.click('button:has-text("Click for JS Alert")', label='Click for JS Alert')
    evidence_tracker.click('button:has-text("Click for JS Alert")', label='OK')

@pytest.mark.evidence(condition_ref="TC-05", story_ref="S01")
def test_05_verify_the_result_message_displays_on_the_page(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://the-internet.herokuapp.com')
    evidence_tracker.click('a[href="/javascript_alerts"]', label='JavaScript Alerts')
    evidence_tracker.click('button:has-text("Click for JS Alert")', label='Click for JS Alert')
    evidence_tracker.click('button:has-text("Click for JS Alert")', label='OK')
    evidence_tracker.assert_visible('#result', label='Result message')