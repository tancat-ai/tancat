from playwright.sync_api import Page, expect
import pytest
from playwright.sync_api import Page

@pytest.mark.evidence(condition_ref="AC-01", story_ref="S01")
def test_01_create_account(page: Page, evidence_tracker):
    evidence_tracker.navigate('http://localhost:8781/generated_tests/mock_insurance_site.html')
    pytest.skip("Skipping: unresolved placeholders for: 'email'; 'password'; 'name'; 'DOB'; 'address'")
    evidence_tracker.click('p:has-text("Error code explanation: 404 - Nothing matches the given URI.")', label='Create Account')
    evidence_tracker.click('p:has-text("Error code explanation: 404 - Nothing matches the given URI.")', label='Submit Account')
    evidence_tracker.assert_visible('p:has-text("Error code explanation: 404 - Nothing matches the given URI.")', label='account created successfully')

@pytest.mark.evidence(condition_ref="AC-02", story_ref="S01")
def test_02_select_car_insurance(page: Page, evidence_tracker):
    evidence_tracker.navigate('http://localhost:8781/generated_tests/mock_insurance_site.html')
    evidence_tracker.click('p:has-text("Error code: 404")', label='Select Product')
    evidence_tracker.click('p:has-text("Error code explanation: 404 - Nothing matches the given URI.")', label='Car Insurance')
    evidence_tracker.assert_visible('h1:has-text("Error response")', label='Car Insurance product selected')

@pytest.mark.evidence(condition_ref="AC-03", story_ref="S01")
def test_03_enter_policy_details(page: Page, evidence_tracker):
    evidence_tracker.navigate('http://localhost:8781/generated_tests/mock_insurance_site.html')
    pytest.skip("Skipping: unresolved placeholders for: 'scheme'; 'start date'")
    evidence_tracker.click('p:has-text("Error code: 404")', label='Select Product')
    evidence_tracker.click('p:has-text("Error code explanation: 404 - Nothing matches the given URI.")', label='Car Insurance')
    evidence_tracker.click('p:has-text("Error code explanation: 404 - Nothing matches the given URI.")', label='Enter Policy Details')
    evidence_tracker.click('p:has-text("Error code explanation: 404 - Nothing matches the given URI.")', label='Next')
    evidence_tracker.assert_visible('h1:has-text("Error response")', label='policy details entered')

@pytest.mark.evidence(condition_ref="AC-04", story_ref="S01")
def test_04_enter_driver_details(page: Page, evidence_tracker):
    evidence_tracker.navigate('http://localhost:8781/generated_tests/mock_insurance_site.html')
    pytest.skip("Skipping: unresolved placeholders for: 'license'; 'years licensed'; 'occupation'")
    evidence_tracker.click('p:has-text("Error code: 404")', label='Select Product')
    evidence_tracker.click('p:has-text("Error code explanation: 404 - Nothing matches the given URI.")', label='Car Insurance')
    evidence_tracker.click('p:has-text("Error code explanation: 404 - Nothing matches the given URI.")', label='Enter Driver Details')
    evidence_tracker.click('p:has-text("Error code: 404")', label='Next')
    evidence_tracker.assert_visible('h1:has-text("Error response")', label='driver details entered')

@pytest.mark.evidence(condition_ref="AC-05", story_ref="S01")
def test_05_add_vehicle_via_registration_lookup(page: Page, evidence_tracker):
    evidence_tracker.navigate('http://localhost:8781/generated_tests/mock_insurance_site.html')
    pytest.skip("Skipping: unresolved placeholders for: 'registration lookup'")
    evidence_tracker.click('p:has-text("Error code: 404")', label='Select Product')
    evidence_tracker.click('p:has-text("Error code explanation: 404 - Nothing matches the given URI.")', label='Car Insurance')
    evidence_tracker.click('p:has-text("Error code explanation: 404 - Nothing matches the given URI.")', label='Add Vehicle')
    evidence_tracker.click('p:has-text("Message: File not found.")', label='Look Up')
    evidence_tracker.assert_visible('p:has-text("Error code explanation: 404 - Nothing matches the given URI.")', label='Honda CR-V')

@pytest.mark.evidence(condition_ref="AC-06", story_ref="S01")
def test_06_select_usage_type(page: Page, evidence_tracker):
    evidence_tracker.navigate('http://localhost:8781/generated_tests/mock_insurance_site.html')
    evidence_tracker.click('p:has-text("Error code explanation: 404 - Nothing matches the given URI.")', label='Select Product')
    evidence_tracker.click('p:has-text("Error code explanation: 404 - Nothing matches the given URI.")', label='Car Insurance')
    evidence_tracker.click('p:has-text("Error code explanation: 404 - Nothing matches the given URI.")', label='Select Usage Type')
    evidence_tracker.click('p:has-text("Error code explanation: 404 - Nothing matches the given URI.")', label='Social, Domestic & Pleasure')
    evidence_tracker.click('p:has-text("Error code explanation: 404 - Nothing matches the given URI.")', label='Next')
    evidence_tracker.assert_visible('p:has-text("Error code explanation: 404 - Nothing matches the given URI.")', label='Social, Domestic & Pleasure usage type selected')

@pytest.mark.evidence(condition_ref="AC-07", story_ref="S01")
def test_07_set_ncl_and_parking(page: Page, evidence_tracker):
    evidence_tracker.navigate('http://localhost:8781/generated_tests/mock_insurance_site.html')
    pytest.skip("Skipping: unresolved placeholders for: 'No Claims Discount'; 'overnight parking location'")
    evidence_tracker.click('p:has-text("Error code: 404")', label='Select Product')
    evidence_tracker.click('p:has-text("Error code explanation: 404 - Nothing matches the given URI.")', label='Car Insurance')
    evidence_tracker.click('p:has-text("Error code explanation: 404 - Nothing matches the given URI.")', label='Set Details')
    evidence_tracker.click('p:has-text("Error code explanation: 404 - Nothing matches the given URI.")', label='Next')
    evidence_tracker.assert_visible('h1:has-text("Error response")', label='No Claims Discount and overnight parking location set')

@pytest.mark.evidence(condition_ref="AC-08", story_ref="S01")
def test_08_verify_extras_page(page: Page, evidence_tracker):
    evidence_tracker.navigate('http://localhost:8781/generated_tests/mock_insurance_site.html')
    pytest.skip("Skipping: unresolved placeholders for: 'Next'")
    evidence_tracker.click('p:has-text("Error code explanation: 404 - Nothing matches the given URI.")', label='Select Product')
    evidence_tracker.click('p:has-text("Error code explanation: 404 - Nothing matches the given URI.")', label='Car Insurance')
    evidence_tracker.click('p:has-text("Error code explanation: 404 - Nothing matches the given URI.")', label='Next')
    evidence_tracker.click('p:has-text("Error code explanation: 404 - Nothing matches the given URI.")', label='Next')
    evidence_tracker.click('p:has-text("Error code: 404")', label='Next')
    evidence_tracker.click('p:has-text("Error code explanation: 404 - Nothing matches the given URI.")', label='Next')
    evidence_tracker.click('p:has-text("Error code explanation: 404 - Nothing matches the given URI.")', label='Next')
    evidence_tracker.assert_visible('p:has-text("Error code explanation: 404 - Nothing matches the given URI.")', label='estimated premium')
    evidence_tracker.assert_visible('p:has-text("Error code explanation: 404 - Nothing matches the given URI.")', label='compulsory excess')

@pytest.mark.evidence(condition_ref="AC-09", story_ref="S01")
def test_09_select_payment_method_and_submit(page: Page, evidence_tracker):
    evidence_tracker.navigate('http://localhost:8781/generated_tests/mock_insurance_site.html')
    evidence_tracker.click('p:has-text("Error code explanation: 404 - Nothing matches the given URI.")', label='Select Product')
    evidence_tracker.click('p:has-text("Error code explanation: 404 - Nothing matches the given URI.")', label='Car Insurance')
    evidence_tracker.click('p:has-text("Message: File not found.")', label='Next')
    evidence_tracker.click('p:has-text("Error code: 404")', label='Next')
    evidence_tracker.click('p:has-text("Error code explanation: 404 - Nothing matches the given URI.")', label='Next')
    evidence_tracker.click('p:has-text("Error code explanation: 404 - Nothing matches the given URI.")', label='Next')
    evidence_tracker.click('p:has-text("Error code: 404")', label='Next')
    evidence_tracker.click('p:has-text("Error code explanation: 404 - Nothing matches the given URI.")', label='Next')
    evidence_tracker.click('p:has-text("Error code explanation: 404 - Nothing matches the given URI.")', label='Pay in Full')
    evidence_tracker.click('p:has-text("Error code explanation: 404 - Nothing matches the given URI.")', label='Submit Quote')
    evidence_tracker.assert_visible('h1:has-text("Error response")', label='quote submitted')

@pytest.mark.evidence(condition_ref="AC-10", story_ref="S01")
def test_10_verify_quote_confirmation(page: Page, evidence_tracker):
    evidence_tracker.navigate('http://localhost:8781/generated_tests/mock_insurance_site.html')
    evidence_tracker.click('p:has-text("Error code explanation: 404 - Nothing matches the given URI.")', label='Select Product')
    evidence_tracker.click('p:has-text("Error code explanation: 404 - Nothing matches the given URI.")', label='Car Insurance')
    evidence_tracker.click('p:has-text("Error code explanation: 404 - Nothing matches the given URI.")', label='Next')
    evidence_tracker.click('p:has-text("Error code explanation: 404 - Nothing matches the given URI.")', label='Next')
    evidence_tracker.click('p:has-text("Error code: 404")', label='Next')
    evidence_tracker.click('p:has-text("Error code: 404")', label='Next')
    evidence_tracker.click('p:has-text("Error code explanation: 404 - Nothing matches the given URI.")', label='Next')
    evidence_tracker.click('p:has-text("Error code explanation: 404 - Nothing matches the given URI.")', label='Next')
    evidence_tracker.click('p:has-text("Error code explanation: 404 - Nothing matches the given URI.")', label='Pay in Full')
    evidence_tracker.click('p:has-text("Error code explanation: 404 - Nothing matches the given URI.")', label='Submit Quote')
    evidence_tracker.assert_visible('p:has-text("Error code explanation: 404 - Nothing matches the given URI.")', label='quote confirmation page')
    evidence_tracker.assert_visible('p:has-text("Error code explanation: 404 - Nothing matches the given URI.")', label='reference number')
    evidence_tracker.assert_visible('h1:has-text("Error response")', label='premium')