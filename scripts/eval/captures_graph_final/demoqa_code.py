from playwright.sync_api import Page, expect
import pytest
from playwright.sync_api import Page

@pytest.mark.evidence(condition_ref="TC-01", story_ref="S01")
def test_01_navigate_to_the_demoqa_com_practice_form_page(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://demoqa.com/automation-practice-form')

@pytest.mark.evidence(condition_ref="TC-02", story_ref="S01")
def test_02_fill_in_the_first_name_field_with_a_value(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://demoqa.com/automation-practice-form')
    evidence_tracker.fill('#firstName', 'a value', label='first name field')

@pytest.mark.evidence(condition_ref="TC-03", story_ref="S01")
def test_03_fill_in_the_last_name_field_with_a_value(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://demoqa.com/automation-practice-form')
    evidence_tracker.fill('#firstName', 'a value', label='last name field')

@pytest.mark.evidence(condition_ref="TC-04", story_ref="S01")
def test_04_fill_in_the_email_address_field_with_a_value(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://demoqa.com/automation-practice-form')
    evidence_tracker.fill('#firstName', 'a value', label='email address field')

@pytest.mark.evidence(condition_ref="TC-05", story_ref="S01")
def test_05_select_a_radio_button_option_e_g_Male(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://demoqa.com/automation-practice-form')

@pytest.mark.evidence(condition_ref="TC-06", story_ref="S01")
def test_06_click_the_Submit_button_at_the_bottom_of_the_form(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://demoqa.com/automation-practice-form')
    evidence_tracker.click('#submit', label='Submit button at the bottom of the form')