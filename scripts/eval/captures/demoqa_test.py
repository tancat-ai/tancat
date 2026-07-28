import pytest
from playwright.sync_api import Page, expect
from pages.automation_practice_form_page import AutomationPracticeFormPage


@pytest.mark.evidence(condition_ref="TC-01", story_ref="S01")
def test_01_navigate_to_practice_form(page: Page, evidence_tracker):
    automation_practice_form_page = AutomationPracticeFormPage(page, evidence_tracker)
    evidence_tracker.navigate('https://demoqa.com/automation-practice-form')
    evidence_tracker.assert_visible('.text-center', label='practice form title')

@pytest.mark.evidence(condition_ref="TC-02", story_ref="S01")
def test_02_fill_first_name(page: Page, evidence_tracker):
    automation_practice_form_page = AutomationPracticeFormPage(page, evidence_tracker)
    evidence_tracker.navigate('https://demoqa.com/automation-practice-form')
    automation_practice_form_page.fill('First Name', 'John')
    evidence_tracker.assert_visible('.text-center', label='first name filled')

@pytest.mark.evidence(condition_ref="TC-03", story_ref="S01")
def test_03_fill_last_name(page: Page, evidence_tracker):
    automation_practice_form_page = AutomationPracticeFormPage(page, evidence_tracker)
    evidence_tracker.navigate('https://demoqa.com/automation-practice-form')
    automation_practice_form_page.fill('Last Name', 'Doe')
    evidence_tracker.assert_visible('h5:has-text("Student Registration Form")', label='last name filled')

@pytest.mark.evidence(condition_ref="TC-04", story_ref="S01")
def test_04_fill_email_address(page: Page, evidence_tracker):
    automation_practice_form_page = AutomationPracticeFormPage(page, evidence_tracker)
    evidence_tracker.navigate('https://demoqa.com/automation-practice-form')
    automation_practice_form_page.fill('Email Address', 'john.doe@example.com')
    evidence_tracker.assert_visible('.text-center', label='email filled')

@pytest.mark.evidence(condition_ref="TC-05", story_ref="S01")
def test_05_select_gender_radio(page: Page, evidence_tracker):
    automation_practice_form_page = AutomationPracticeFormPage(page, evidence_tracker)
    evidence_tracker.navigate('https://demoqa.com/automation-practice-form')
    automation_practice_form_page.click('Male radio')
    evidence_tracker.assert_checked('#gender-radio-1', label='male radio selected')

@pytest.mark.evidence(condition_ref="TC-06", story_ref="S01")
def test_06_submit_form(page: Page, evidence_tracker):
    automation_practice_form_page = AutomationPracticeFormPage(page, evidence_tracker)
    evidence_tracker.navigate('https://demoqa.com/automation-practice-form')
    automation_practice_form_page.fill('First Name', 'John')
    automation_practice_form_page.fill('Last Name', 'Doe')
    automation_practice_form_page.fill('Email Address', 'john.doe@example.com')
    automation_practice_form_page.click('Submit button')
    evidence_tracker.assert_visible('.text-center', label='submission confirmation')