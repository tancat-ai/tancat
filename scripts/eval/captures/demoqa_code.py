from playwright.sync_api import Page, expect
import pytest
from playwright.sync_api import Page
from pages.automation_practice_form_page import AutomationPracticeFormPage


@pytest.mark.evidence(condition_ref="TC-01", story_ref="S01")
def test_01_navigate_to_the_demoqa_com_practice_form_page(page: Page, evidence_tracker):
    automation_practice_form_page = AutomationPracticeFormPage(page, evidence_tracker)
    evidence_tracker.navigate('https://demoqa.com/automation-practice-form')

@pytest.mark.evidence(condition_ref="TC-02", story_ref="S01")
def test_02_fill_in_the_first_name_field_with_a_value(page: Page, evidence_tracker):
    automation_practice_form_page = AutomationPracticeFormPage(page, evidence_tracker)
    evidence_tracker.navigate('https://demoqa.com/automation-practice-form')
    automation_practice_form_page.fill('First Name', 'John')

@pytest.mark.evidence(condition_ref="TC-03", story_ref="S01")
def test_03_fill_in_the_last_name_field_with_a_value(page: Page, evidence_tracker):
    automation_practice_form_page = AutomationPracticeFormPage(page, evidence_tracker)
    evidence_tracker.navigate('https://demoqa.com/automation-practice-form')
    automation_practice_form_page.fill('Last Name', 'Doe')

@pytest.mark.evidence(condition_ref="TC-04", story_ref="S01")
def test_04_fill_in_the_email_address_field_with_a_value(page: Page, evidence_tracker):
    automation_practice_form_page = AutomationPracticeFormPage(page, evidence_tracker)
    evidence_tracker.navigate('https://demoqa.com/automation-practice-form')
    automation_practice_form_page.fill('Email Address', 'test@example.com')

@pytest.mark.evidence(condition_ref="TC-05", story_ref="S01")
def test_05_select_a_radio_button_option_(page: Page, e.g._Male, evidence_tracker)(page, evidence_tracker):
    automation_practice_form_page = AutomationPracticeFormPage(page, evidence_tracker)
    evidence_tracker.navigate('https://demoqa.com/automation-practice-form')
    automation_practice_form_page.click('Male')

@pytest.mark.evidence(condition_ref="TC-06", story_ref="S01")
def test_06_click_the_submit_button_at_the_bottom_of_the_form(page: Page, evidence_tracker):
    automation_practice_form_page = AutomationPracticeFormPage(page, evidence_tracker)
    evidence_tracker.navigate('https://demoqa.com/automation-practice-form')
    automation_practice_form_page.fill('First Name', 'John')
    automation_practice_form_page.fill('Last Name', 'Doe')
    automation_practice_form_page.fill('Email Address', 'test@example.com')
    automation_practice_form_page.click('Male')
    automation_practice_form_page.click('Submit')
    evidence_tracker.assert_visible('.text-center', label='Thank You')