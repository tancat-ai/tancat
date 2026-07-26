from playwright.sync_api import Page, expect
import pytest
from playwright.sync_api import Page
from pages.automation_practice_form_page import AutomationPracticeFormPage


@pytest.mark.evidence(condition_ref="TC-01", story_ref="S01")
def test_01_navigate_to_demoqa_form(page: Page, evidence_tracker):
    automation_practice_form_page = AutomationPracticeFormPage(page, evidence_tracker)
    evidence_tracker.navigate('https://demoqa.com/automation-practice-form')
    automation_practice_form_page.click('Forms')
    automation_practice_form_page.click('Practice Form')
    evidence_tracker.assert_visible('.text-center', label='Practice Form page is displayed')

@pytest.mark.evidence(condition_ref="TC-02", story_ref="S01")
def test_02_fill_first_name(page: Page, evidence_tracker):
    automation_practice_form_page = AutomationPracticeFormPage(page, evidence_tracker)
    evidence_tracker.navigate('https://demoqa.com/automation-practice-form')
    automation_practice_form_page.click('Forms')
    automation_practice_form_page.click('Practice Form')
    automation_practice_form_page.fill('first name', 'value')
    evidence_tracker.assert_value('#firstName', label='first name field contains the entered value')

@pytest.mark.evidence(condition_ref="TC-03", story_ref="S01")
def test_03_fill_last_name(page: Page, evidence_tracker):
    automation_practice_form_page = AutomationPracticeFormPage(page, evidence_tracker)
    evidence_tracker.navigate('https://demoqa.com/automation-practice-form')
    automation_practice_form_page.click('Forms')
    automation_practice_form_page.click('Practice Form')
    automation_practice_form_page.fill('last name', 'value')
    evidence_tracker.assert_value('#lastName', label='last name field contains the entered value')

@pytest.mark.evidence(condition_ref="TC-04", story_ref="S01")
def test_04_fill_email(page: Page, evidence_tracker):
    automation_practice_form_page = AutomationPracticeFormPage(page, evidence_tracker)
    evidence_tracker.navigate('https://demoqa.com/automation-practice-form')
    automation_practice_form_page.click('Forms')
    automation_practice_form_page.click('Practice Form')
    automation_practice_form_page.fill('email address', 'value')
    evidence_tracker.assert_value('#userEmail', label='email address field contains the entered value')

@pytest.mark.evidence(condition_ref="TC-05", story_ref="S01")
def test_05_select_radio_button(page: Page, evidence_tracker):
    automation_practice_form_page = AutomationPracticeFormPage(page, evidence_tracker)
    evidence_tracker.navigate('https://demoqa.com/automation-practice-form')
    automation_practice_form_page.click('Forms')
    automation_practice_form_page.click('Practice Form')
    automation_practice_form_page.click('Male radio button option')
    evidence_tracker.assert_checked('#gender-radio-1', label='Male radio button is selected')

@pytest.mark.evidence(condition_ref="TC-06", story_ref="S01")
def test_06_click_submit(page: Page, evidence_tracker):
    automation_practice_form_page = AutomationPracticeFormPage(page, evidence_tracker)
    evidence_tracker.navigate('https://demoqa.com/automation-practice-form')
    automation_practice_form_page.click('Forms')
    automation_practice_form_page.click('Practice Form')
    automation_practice_form_page.click('Submit button at the bottom of the form')
    evidence_tracker.assert_visible('h5:has-text("Student Registration Form")', label='form is submitted successfully')