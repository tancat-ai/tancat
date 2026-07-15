import pytest
from playwright.sync_api import Page

from src.browser_utils import dismiss_consent_overlays


@pytest.mark.evidence(condition_ref="TC-01", story_ref="S01")
def test_01_navigate_to_practice_form(page: Page, evidence_tracker):
    evidence_tracker.navigate("https://demoqa.com/automation-practice-form")
    dismiss_consent_overlays(page)
    evidence_tracker.assert_visible(".text-center", label="practice form page title")


@pytest.mark.evidence(condition_ref="TC-02", story_ref="S01")
def test_02_fill_first_name(page: Page, evidence_tracker):
    evidence_tracker.navigate("https://demoqa.com/automation-practice-form")
    dismiss_consent_overlays(page)
    evidence_tracker.fill("#firstName", "John", label="First Name")
    evidence_tracker.assert_value("#react-select-3-placeholder", label="First Name field filled")


@pytest.mark.evidence(condition_ref="TC-03", story_ref="S01")
def test_03_fill_last_name(page: Page, evidence_tracker):
    evidence_tracker.navigate("https://demoqa.com/automation-practice-form")
    dismiss_consent_overlays(page)
    evidence_tracker.fill("#firstName", "Doe", label="Last Name")
    evidence_tracker.assert_visible('h5:has-text("Student Registration Form")', label="Last Name field filled")


@pytest.mark.evidence(condition_ref="TC-04", story_ref="S01")
def test_04_fill_email_address(page: Page, evidence_tracker):
    evidence_tracker.navigate("https://demoqa.com/automation-practice-form")
    dismiss_consent_overlays(page)
    evidence_tracker.fill("#userEmail", "john.doe@example.com", label="Email")
    evidence_tracker.assert_visible(".text-center", label="Email field filled")


@pytest.mark.evidence(condition_ref="TC-05", story_ref="S01")
def test_05_select_gender_radio_button(page: Page, evidence_tracker):
    evidence_tracker.navigate("https://demoqa.com/automation-practice-form")
    dismiss_consent_overlays(page)
    evidence_tracker.click("#gender-radio-1", label="Male radio")
    evidence_tracker.assert_checked("#gender-radio-1", label="Male radio selected")


@pytest.mark.evidence(condition_ref="TC-06", story_ref="S01")
def test_06_submit_form(page: Page, evidence_tracker):
    evidence_tracker.navigate("https://demoqa.com/automation-practice-form")
    dismiss_consent_overlays(page)
    evidence_tracker.fill("#firstName", "John", label="First Name")
    evidence_tracker.fill("#firstName", "Doe", label="Last Name")
    evidence_tracker.fill("#userEmail", "john.doe@example.com", label="Email")
    evidence_tracker.click("#submit", label="Submit")
    evidence_tracker.assert_visible(".group-header", label="submission success message")
