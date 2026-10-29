from playwright.sync_api import Page, expect
import pytest
from playwright.sync_api import Page


@pytest.mark.evidence(condition_ref="TC-01", story_ref="S01")
def test_01_navigate_to_practice_form(page: Page, evidence_tracker):
    evidence_tracker.navigate("https://demoqa.com/automation-practice-form")
    evidence_tracker.click('a[href="/automation-practice-form"]', label='practice form', expected_page='https://demoqa.com/automation-practice-form')
    evidence_tracker.assert_visible('h1.text-center', label='practice form loaded', expected_page='https://demoqa.com/automation-practice-form')


@pytest.mark.evidence(condition_ref="TC-02", story_ref="S01")
def test_02_fill_first_name(page: Page, evidence_tracker):
    evidence_tracker.navigate("https://demoqa.com/automation-practice-form")
    evidence_tracker.click('a[href="/automation-practice-form"]', label='practice form', expected_page='https://demoqa.com/automation-practice-form')
    evidence_tracker.fill('#firstName', 'John', label='First Name', expected_page='https://demoqa.com/automation-practice-form')
    evidence_tracker.assert_visible('#firstName', label='First Name field filled', expected_page='https://demoqa.com/automation-practice-form')


@pytest.mark.evidence(condition_ref="TC-03", story_ref="S01")
def test_03_fill_last_name(page: Page, evidence_tracker):
    evidence_tracker.navigate("https://demoqa.com/automation-practice-form")
    evidence_tracker.click('a[href="/automation-practice-form"]', label='practice form', expected_page='https://demoqa.com/automation-practice-form')
    evidence_tracker.fill('#lastName', 'Doe', label='Last Name', expected_page='https://demoqa.com/automation-practice-form')
    evidence_tracker.assert_visible('#lastName', label='Last Name field filled', expected_page='https://demoqa.com/automation-practice-form')


@pytest.mark.evidence(condition_ref="TC-04", story_ref="S01")
def test_04_fill_email(page: Page, evidence_tracker):
    evidence_tracker.navigate("https://demoqa.com/automation-practice-form")
    evidence_tracker.click('a[href="/automation-practice-form"]', label='practice form', expected_page='https://demoqa.com/automation-practice-form')
    evidence_tracker.fill('#userNumber', 'john.doe@example.com', label='User Name', expected_page='https://demoqa.com/automation-practice-form')
    evidence_tracker.assert_visible('#userName-wrapper', label='User Name field filled', expected_page='https://demoqa.com/automation-practice-form')


@pytest.mark.evidence(condition_ref="TC-05", story_ref="S01")
def test_05_select_male_radio(page: Page, evidence_tracker):
    evidence_tracker.navigate("https://demoqa.com/automation-practice-form")
    evidence_tracker.click('a[href="/automation-practice-form"]', label='practice form', expected_page='https://demoqa.com/automation-practice-form')
    evidence_tracker.click('#gender-radio-1', label='Male', expected_page='https://demoqa.com/automation-practice-form')
    evidence_tracker.assert_checked('#gender-radio-1', label='Male radio selected')


@pytest.mark.evidence(condition_ref="TC-06", story_ref="S01")
def test_06_submit_form(page: Page, evidence_tracker):
    evidence_tracker.navigate("https://demoqa.com/automation-practice-form")
    evidence_tracker.click('a[href="/automation-practice-form"]', label='practice form', expected_page='https://demoqa.com/automation-practice-form')
    evidence_tracker.fill('#firstName', 'John', label='First Name', expected_page='https://demoqa.com/automation-practice-form')
    evidence_tracker.fill('#lastName', 'Doe', label='Last Name', expected_page='https://demoqa.com/automation-practice-form')
    evidence_tracker.fill('#userNumber', 'john.doe@example.com', label='User Name', expected_page='https://demoqa.com/automation-practice-form')
    evidence_tracker.click('#gender-radio-1', label='Male', expected_page='https://demoqa.com/automation-practice-form')
    evidence_tracker.click('#submit', label='Submit', expected_page='https://demoqa.com/automation-practice-form')
    evidence_tracker.assert_visible('#hobbies-checkbox-2', label='form submitted', expected_page='https://demoqa.com/automation-practice-form')