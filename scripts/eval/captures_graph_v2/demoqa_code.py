from playwright.sync_api import Page, expect
import pytest
from playwright.sync_api import Page

@pytest.mark.evidence(condition_ref="TC-01", story_ref="S01")
def test_01_navigate_to_demoqa_form(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://demoqa.com/automation-practice-form')
    evidence_tracker.assert_visible('a[href="/automation-practice-form"]', label='practice form')

@pytest.mark.evidence(condition_ref="TC-02", story_ref="S01")
def test_02_fill_first_name(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://demoqa.com/automation-practice-form')
    evidence_tracker.fill('#firstName', 'John', label='first name field')

@pytest.mark.evidence(condition_ref="TC-03", story_ref="S01")
def test_03_fill_last_name(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://demoqa.com/automation-practice-form')
    evidence_tracker.fill('#firstName', 'Doe', label='last name field')

@pytest.mark.evidence(condition_ref="TC-04", story_ref="S01")
def test_04_fill_email(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://demoqa.com/automation-practice-form')
    evidence_tracker.fill('#firstName', 'john@example.com', label='email address field')

@pytest.mark.evidence(condition_ref="TC-05", story_ref="S01")
def test_05_select_radio_button(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://demoqa.com/automation-practice-form')
    evidence_tracker.click('a[href="/radio-button"]', label='Male radio button')

@pytest.mark.evidence(condition_ref="TC-06", story_ref="S01")
def test_06_click_submit(page: Page, evidence_tracker):
    evidence_tracker.navigate('https://demoqa.com/automation-practice-form')
    evidence_tracker.fill('#firstName', 'John', label='first name field')
    evidence_tracker.fill('#firstName', 'Doe', label='last name field')
    evidence_tracker.fill('#firstName', 'john@example.com', label='email address field')
    evidence_tracker.click('a[href="/radio-button"]', label='Male radio button')
    evidence_tracker.click('a[href="/radio-button"]', label='Submit button')
    evidence_tracker.assert_visible('.group-header', label='Successfully submitted')