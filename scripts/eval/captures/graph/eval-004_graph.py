from playwright.sync_api import Page, expect
import pytest
from playwright.sync_api import Page
from pages.home_page import HomePage
from pages.home_page import HomePage
from pages.javascript_alerts_page import JavascriptAlertsPage


@pytest.mark.evidence(condition_ref="TC-01", story_ref="S01")
def test_01_navigate_to_main_page(page: Page, evidence_tracker):
    home_page = HomePage(page, evidence_tracker)
    home_page = HomePage(page, evidence_tracker)
    javascript_alerts_page = JavascriptAlertsPage(page, evidence_tracker)
    evidence_tracker.navigate('https://the-internet.herokuapp.com')
    evidence_tracker.assert_visible('.heading', label='main page is displayed')

@pytest.mark.evidence(condition_ref="TC-02", story_ref="S01")
def test_02_click_javascript_alerts_link(page: Page, evidence_tracker):
    home_page = HomePage(page, evidence_tracker)
    home_page = HomePage(page, evidence_tracker)
    javascript_alerts_page = JavascriptAlertsPage(page, evidence_tracker)
    evidence_tracker.navigate('https://the-internet.herokuapp.com')
    evidence_tracker.click('a[href="/javascript_alerts"]', label='JavaScript Alerts link')
    expect(page).to_have_url("https://the-internet.herokuapp.com")

@pytest.mark.evidence(condition_ref="TC-03", story_ref="S01")
def test_03_click_for_js_alert_button(page: Page, evidence_tracker):
    home_page = HomePage(page, evidence_tracker)
    home_page = HomePage(page, evidence_tracker)
    javascript_alerts_page = JavascriptAlertsPage(page, evidence_tracker)
    evidence_tracker.navigate('https://the-internet.herokuapp.com')
    evidence_tracker.click('a[href="/javascript_alerts"]', label='JavaScript Alerts link')
    javascript_alerts_page.click('Click for JS Alert button')
    evidence_tracker.assert_visible('#result', label='JavaScript alert popup appears')

@pytest.mark.evidence(condition_ref="TC-04", story_ref="S01")
def test_04_accept_javascript_alert_popup(page: Page, evidence_tracker):
    home_page = HomePage(page, evidence_tracker)
    home_page = HomePage(page, evidence_tracker)
    javascript_alerts_page = JavascriptAlertsPage(page, evidence_tracker)
    evidence_tracker.navigate('https://the-internet.herokuapp.com')
    evidence_tracker.click('a[href="/javascript_alerts"]', label='JavaScript Alerts link')
    javascript_alerts_page.click('Click for JS Alert button')
    evidence_tracker.assert_visible('#result', label='alert popup is dismissed')

@pytest.mark.evidence(condition_ref="TC-05", story_ref="S01")
def test_05_verify_result_message_appears_on_the_page(page: Page, evidence_tracker):
    home_page = HomePage(page, evidence_tracker)
    home_page = HomePage(page, evidence_tracker)
    javascript_alerts_page = JavascriptAlertsPage(page, evidence_tracker)
    evidence_tracker.navigate('https://the-internet.herokuapp.com')
    evidence_tracker.click('a[href="/javascript_alerts"]', label='JavaScript Alerts link')
    javascript_alerts_page.click('Click for JS Alert button')
    evidence_tracker.assert_visible('#result', label='result message displays on the page')