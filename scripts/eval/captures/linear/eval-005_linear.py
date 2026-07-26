from playwright.sync_api import Page, expect
import pytest
from playwright.sync_api import Page
from pages.mock_insurance_site_page import MockInsuranceSitePage


@pytest.mark.evidence(condition_ref="TC-01", story_ref="S01")
def test_01_create_account(page: Page, evidence_tracker):
    mock_insurance_site_page = MockInsuranceSitePage(page, evidence_tracker)
    evidence_tracker.navigate('http://localhost:8781/generated_tests/mock_insurance_site.html')
    pytest.skip("Skipping: unresolved placeholders for: 'email'; 'password'; 'name'; 'DOB'; 'address'; 'account created'")

@pytest.mark.evidence(condition_ref="TC-02", story_ref="S01")
def test_02_select_car_insurance(page: Page, evidence_tracker):
    mock_insurance_site_page = MockInsuranceSitePage(page, evidence_tracker)
    evidence_tracker.navigate('http://localhost:8781/generated_tests/mock_insurance_site.html')
    pytest.skip("Skipping: unresolved placeholders for: 'email'; 'password'; 'name'; 'DOB'; 'address'; 'Car Insurance'; 'car insurance selected'")

@pytest.mark.evidence(condition_ref="TC-03", story_ref="S01")
def test_03_enter_policy_details(page: Page, evidence_tracker):
    mock_insurance_site_page = MockInsuranceSitePage(page, evidence_tracker)
    evidence_tracker.navigate('http://localhost:8781/generated_tests/mock_insurance_site.html')
    pytest.skip("Skipping: unresolved placeholders for: 'email'; 'password'; 'name'; 'DOB'; 'address'; 'Car Insurance'; 'Standard scheme'; 'start date'; 'policy details saved'")

@pytest.mark.evidence(condition_ref="TC-04", story_ref="S01")
def test_04_enter_driver_details(page: Page, evidence_tracker):
    mock_insurance_site_page = MockInsuranceSitePage(page, evidence_tracker)
    evidence_tracker.navigate('http://localhost:8781/generated_tests/mock_insurance_site.html')
    pytest.skip("Skipping: unresolved placeholders for: 'email'; 'password'; 'name'; 'DOB'; 'address'; 'Car Insurance'; 'Standard scheme'; 'start date'; 'license'; 'years licensed'; 'occupation'; 'driver details saved'")

@pytest.mark.evidence(condition_ref="TC-05", story_ref="S01")
def test_05_add_vehicle_registration(page: Page, evidence_tracker):
    mock_insurance_site_page = MockInsuranceSitePage(page, evidence_tracker)
    evidence_tracker.navigate('http://localhost:8781/generated_tests/mock_insurance_site.html')
    pytest.skip("Skipping: unresolved placeholders for: 'email'; 'password'; 'name'; 'DOB'; 'address'; 'Car Insurance'; 'Standard scheme'; 'start date'; 'license'; 'years licensed'; 'occupation'; 'vehicle registration'; 'Honda CR-V'")

@pytest.mark.evidence(condition_ref="TC-06", story_ref="S01")
def test_06_select_usage_type(page: Page, evidence_tracker):
    mock_insurance_site_page = MockInsuranceSitePage(page, evidence_tracker)
    evidence_tracker.navigate('http://localhost:8781/generated_tests/mock_insurance_site.html')
    pytest.skip("Skipping: unresolved placeholders for: 'email'; 'password'; 'name'; 'DOB'; 'address'; 'Car Insurance'; 'Standard scheme'; 'start date'; 'license'; 'years licensed'; 'occupation'; 'vehicle registration'; 'Social, Domestic & Pleasure'; 'usage type selected'")

@pytest.mark.evidence(condition_ref="TC-07", story_ref="S01")
def test_07_set_ncd_and_parking(page: Page, evidence_tracker):
    mock_insurance_site_page = MockInsuranceSitePage(page, evidence_tracker)
    evidence_tracker.navigate('http://localhost:8781/generated_tests/mock_insurance_site.html')
    pytest.skip("Skipping: unresolved placeholders for: 'email'; 'password'; 'name'; 'DOB'; 'address'; 'Car Insurance'; 'Standard scheme'; 'start date'; 'license'; 'years licensed'; 'occupation'; 'vehicle registration'; 'Social, Domestic & Pleasure'; 'no claims discount'; 'overnight parking'; 'NCD and parking saved'")

@pytest.mark.evidence(condition_ref="TC-08", story_ref="S01")
def test_08_verify_extras_page(page: Page, evidence_tracker):
    mock_insurance_site_page = MockInsuranceSitePage(page, evidence_tracker)
    evidence_tracker.navigate('http://localhost:8781/generated_tests/mock_insurance_site.html')
    pytest.skip("Skipping: unresolved placeholders for: 'email'; 'password'; 'name'; 'DOB'; 'address'; 'Car Insurance'; 'Standard scheme'; 'start date'; 'license'; 'years licensed'; 'occupation'; 'vehicle registration'; 'Social, Domestic & Pleasure'; 'no claims discount'; 'overnight parking'; 'Continue to extras'; 'estimated premium'; 'compulsory excess'")

@pytest.mark.evidence(condition_ref="TC-09", story_ref="S01")
def test_09_select_payment_and_submit(page: Page, evidence_tracker):
    mock_insurance_site_page = MockInsuranceSitePage(page, evidence_tracker)
    evidence_tracker.navigate('http://localhost:8781/generated_tests/mock_insurance_site.html')
    pytest.skip("Skipping: unresolved placeholders for: 'email'; 'password'; 'name'; 'DOB'; 'address'; 'Car Insurance'; 'Standard scheme'; 'start date'; 'license'; 'years licensed'; 'occupation'; 'vehicle registration'; 'Social, Domestic & Pleasure'; 'no claims discount'; 'overnight parking'; 'Continue to extras'; 'Pay in Full'; 'Submit quote'; 'quote submitted'")

@pytest.mark.evidence(condition_ref="TC-10", story_ref="S01")
def test_10_verify_quote_confirmation(page: Page, evidence_tracker):
    mock_insurance_site_page = MockInsuranceSitePage(page, evidence_tracker)
    evidence_tracker.navigate('http://localhost:8781/generated_tests/mock_insurance_site.html')
    pytest.skip("Skipping: unresolved placeholders for: 'email'; 'password'; 'name'; 'DOB'; 'address'; 'Car Insurance'; 'Standard scheme'; 'start date'; 'license'; 'years licensed'; 'occupation'; 'vehicle registration'; 'Social, Domestic & Pleasure'; 'no claims discount'; 'overnight parking'; 'Continue to extras'; 'Pay in Full'; 'Submit quote'; 'quote confirmation'; 'reference number'; 'premium amount'")