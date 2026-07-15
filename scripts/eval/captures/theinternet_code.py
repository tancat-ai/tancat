import pytest
from playwright.sync_api import Page

from src.browser_utils import dismiss_consent_overlays


@pytest.mark.evidence(condition_ref="TC-01", story_ref="S01")
def test_01_navigate_to_main_page(page: Page, evidence_tracker):
    evidence_tracker.navigate("https://the-internet.herokuapp.com")
    dismiss_consent_overlays(page)
    evidence_tracker.assert_visible(".heading", label="all elements listing")


@pytest.mark.evidence(condition_ref="TC-02", story_ref="S01")
def test_02_click_javascript_alerts_link(page: Page, evidence_tracker):
    evidence_tracker.navigate("https://the-internet.herokuapp.com")
    dismiss_consent_overlays(page)
    evidence_tracker.click('a[href="/javascript_alerts"]', label="JavaScript Alerts")
    evidence_tracker.assert_visible('h3:has-text("JavaScript Alerts")', label="alert demonstration header")


@pytest.mark.evidence(condition_ref="TC-03", story_ref="S01")
def test_03_click_for_js_alert_button(page: Page, evidence_tracker):
    evidence_tracker.navigate("https://the-internet.herokuapp.com/javascript_alerts")
    dismiss_consent_overlays(page)
    evidence_tracker.click('button:has-text("Click for JS Alert")', label="Click for JS Alert")
    evidence_tracker.assert_visible(
        'p:has-text("Here are some examples of different JavaScript alerts which can be troublesome for automation")',
        label="javascript alert popup",
    )


@pytest.mark.evidence(condition_ref="TC-04", story_ref="S01")
def test_04_accept_javascript_alert_popup(page: Page, evidence_tracker):
    evidence_tracker.navigate("https://the-internet.herokuapp.com/javascript_alerts")
    dismiss_consent_overlays(page)
    evidence_tracker.click('button:has-text("Click for JS Alert")', label="Click for JS Alert")
    evidence_tracker.assert_visible('h4:has-text("Result:")', label="alert accepted")


@pytest.mark.evidence(condition_ref="TC-05", story_ref="S01")
def test_05_verify_result_message(page: Page, evidence_tracker):
    evidence_tracker.navigate("https://the-internet.herokuapp.com/javascript_alerts")
    dismiss_consent_overlays(page)
    evidence_tracker.click('button:has-text("Click for JS Alert")', label="Click for JS Alert")
    evidence_tracker.assert_visible('h4:has-text("Result:")', label="result message text")
