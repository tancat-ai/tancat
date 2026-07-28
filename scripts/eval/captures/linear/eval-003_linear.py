from playwright.sync_api import Page, expect
import pytest
from playwright.sync_api import Page
from pages.automation_practice_form_page import AutomationPracticeFormPage


@pytest.mark.evidence(condition_ref="TC-01", story_ref="S01")
def test_01_navigate_to_practice_form(page: Page, evidence_tracker):
    automation_practice_form_page = AutomationPracticeFormPage(page, evidence_tracker)
    evidence_tracker.navigate('https://demoqa.com/automation-practice-form')
    evidence_tracker.assert_visible('h5:has-text("Student Registration Form")', label='practice form page loaded')

@pytest.mark.evidence(condition_ref="TC-02", story_ref="S01")
def test_02_fill_first_name(page: Page, evidence_tracker):
    automation_practice_form_page = AutomationPracticeFormPage(page, evidence_tracker)
    evidence_tracker.navigate('https://demoqa.com/automation-practice-form')
    automation_practice_form_page.fill('first name', 'John')
    evidence_tracker.assert_value('#firstName', label='first name filled')

@pytest.mark.evidence(condition_ref="TC-03", story_ref="S01")
def test_03_fill_last_name(page: Page, evidence_tracker):
    automation_practice_form_page = AutomationPracticeFormPage(page, evidence_tracker)
    evidence_tracker.navigate('https://demoqa.com/automation-practice-form')
    automation_practice_form_page.fill('first name', 'John')
    automation_practice_form_page.fill('last name', 'Doe')
    evidence_tracker.assert_value('#lastName', label='last name filled')

@pytest.mark.evidence(condition_ref="TC-04", story_ref="S01")
def test_04_fill_email(page: Page, evidence_tracker):
    automation_practice_form_page = AutomationPracticeFormPage(page, evidence_tracker)
    evidence_tracker.navigate('https://demoqa.com/automation-practice-form')
    automation_practice_form_page.fill('first name', 'John')
    automation_practice_form_page.fill('last name', 'Doe')
    automation_practice_form_page.fill('email', 'john.doe@example.com')
    evidence_tracker.assert_value('#userEmail', label='email filled')

@pytest.mark.evidence(condition_ref="TC-05", story_ref="S01")
def test_05_select_radio_button(page: Page, evidence_tracker):
    automation_practice_form_page = AutomationPracticeFormPage(page, evidence_tracker)
    evidence_tracker.navigate('https://demoqa.com/automation-practice-form')
    automation_practice_form_page.fill('first name', 'John')
    automation_practice_form_page.fill('last name', 'Doe')
    automation_practice_form_page.fill('email', 'john.doe@example.com')
    automation_practice_form_page.click('Male radio')
    evidence_tracker.assert_checked('#gender-radio-1', label='Male selected')

@pytest.mark.evidence(condition_ref="TC-06", story_ref="S01")
def test_06_submit_form(page: Page, evidence_tracker):
    automation_practice_form_page = AutomationPracticeFormPage(page, evidence_tracker)
    evidence_tracker.navigate('https://demoqa.com/automation-practice-form')
    automation_practice_form_page.fill('first name', 'John')
    automation_practice_form_page.fill('last name', 'Doe')
    automation_practice_form_page.fill('email', 'john.doe@example.com')
    automation_practice_form_page.click('Male radio')
    automation_practice_form_page.click('Submit button')
    evidence_tracker.assert_visible('h5:has-text("Student Registration Form")', label='form submitted successfully')