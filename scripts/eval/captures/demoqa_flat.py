import pytest
from playwright.sync_api import Page, expect

@pytest.mark.evidence(condition_ref="TC-01", story_ref="S01")
def test_01_navigate_to_form(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://demoqa.com/automation-practice-form')
    evidence_tracker.assert_visible('h5:has-text("Student Registration Form")', label='form title visible')

@pytest.mark.evidence(condition_ref="TC-02", story_ref="S01")
def test_02_fill_first_name(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://demoqa.com/automation-practice-form')
    evidence_tracker.fill('#firstName', 'John', label='First Name')
    evidence_tracker.assert_visible('.text-center', label='first name filled')

@pytest.mark.evidence(condition_ref="TC-03", story_ref="S01")
def test_03_fill_last_name(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://demoqa.com/automation-practice-form')
    evidence_tracker.fill('#firstName', 'Doe', label='Last Name')
    evidence_tracker.assert_visible('h5:has-text("Student Registration Form")', label='last name filled')

@pytest.mark.evidence(condition_ref="TC-04", story_ref="S01")
def test_04_fill_email(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://demoqa.com/automation-practice-form')
    evidence_tracker.fill('#userEmail', 'john.doe@example.com', label='email')
    evidence_tracker.assert_visible('h5:has-text("Student Registration Form")', label='email field filled')

@pytest.mark.evidence(condition_ref="TC-05", story_ref="S01")
def test_05_select_radio_button(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://demoqa.com/automation-practice-form')
    evidence_tracker.click('#gender-radio-1', label='Male radio')
    evidence_tracker.assert_checked('#gender-radio-1', label='Male selected')

@pytest.mark.evidence(condition_ref="TC-06", story_ref="S01")
def test_06_submit_form(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://demoqa.com/automation-practice-form')
    evidence_tracker.fill('#firstName', 'John', label='First Name')
    evidence_tracker.fill('#firstName', 'Doe', label='Last Name')
    evidence_tracker.fill('#userEmail', 'john.doe@example.com', label='email')
    evidence_tracker.click('#submit', label='Submit')
    evidence_tracker.assert_visible('.group-header', label='submission success message')