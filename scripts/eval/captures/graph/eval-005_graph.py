from playwright.sync_api import Page, expect
import pytest
from playwright.sync_api import Page
from pages.mock_insurance_site_page import MockInsuranceSitePage


@pytest.mark.evidence(condition_ref="TC-01", story_ref="S01")
def test_01_Create_account_with_personal_details(page: Page, evidence_tracker):
    mock_insurance_site_page = MockInsuranceSitePage(page, evidence_tracker)
    evidence_tracker.navigate('http://localhost:8781/generated_tests/mock_insurance_site.html')
    pytest.skip("Skipping: unresolved placeholders for: 'Sign Up / Register'; 'email'; 'password'; 'name'; 'DOB'; 'address'; 'Create Account / Register'; 'Account created successfully'")

@pytest.mark.evidence(condition_ref="TC-02", story_ref="S01")
def test_02_Select_Car_Insurance_product(page: Page, evidence_tracker):
    mock_insurance_site_page = MockInsuranceSitePage(page, evidence_tracker)
    evidence_tracker.navigate('http://localhost:8781/generated_tests/mock_insurance_site.html')
    pytest.skip("Skipping: unresolved placeholders for: 'username'; 'password'; 'Login'; 'Dashboard'; 'Car Insurance'")
    expect(page).to_have_url("http://localhost:8781/generated_tests/mock_insurance_site.html")

@pytest.mark.evidence(condition_ref="TC-03", story_ref="S01")
def test_03_Enter_policy_details_with_Standard_scheme_and_start_date(page: Page, evidence_tracker):
    mock_insurance_site_page = MockInsuranceSitePage(page, evidence_tracker)
    evidence_tracker.navigate('http://localhost:8781/generated_tests/mock_insurance_site.html')
    pytest.skip("Skipping: unresolved placeholders for: 'username'; 'password'; 'Login'; 'Dashboard'; 'Car Insurance'; 'Get a Quote'; 'Start date'; 'Next / Continue'; 'Policy details entered'")

@pytest.mark.evidence(condition_ref="TC-04", story_ref="S01")
def test_04_Enter_account_holder_driver_details(page: Page, evidence_tracker):
    mock_insurance_site_page = MockInsuranceSitePage(page, evidence_tracker)
    evidence_tracker.navigate('http://localhost:8781/generated_tests/mock_insurance_site.html')
    pytest.skip("Skipping: unresolved placeholders for: 'username'; 'password'; 'Login'; 'Dashboard'; 'Car Insurance'; 'Get a Quote'; 'Start date'; 'Next / Continue'; 'Policy details entered'; 'License number'; 'Years licensed'; 'Occupation'; 'Save / Continue'; 'Driver details saved'")

@pytest.mark.evidence(condition_ref="TC-05", story_ref="S01")
def test_05_Add_a_vehicle_via_registration_lookup(page: Page, evidence_tracker):
    mock_insurance_site_page = MockInsuranceSitePage(page, evidence_tracker)
    evidence_tracker.navigate('http://localhost:8781/generated_tests/mock_insurance_site.html')
    pytest.skip("Skipping: unresolved placeholders for: 'username'; 'password'; 'Login'; 'Dashboard'; 'Car Insurance'; 'Get a Quote'; 'Start date'; 'Next / Continue'; 'Policy details entered'; 'License number'; 'Years licensed'; 'Occupation'; 'Save / Continue'; 'Driver details saved'; 'Registration'; 'Lookup Vehicle'; 'Vehicle found: Honda CR-V'; 'Confirm Vehicle'; 'Vehicle added'")

@pytest.mark.evidence(condition_ref="TC-06", story_ref="S01")
def test_06_Select_Social_Domestic_and_Pleasure_usage_type(page: Page, evidence_tracker):
    mock_insurance_site_page = MockInsuranceSitePage(page, evidence_tracker)
    evidence_tracker.navigate('http://localhost:8781/generated_tests/mock_insurance_site.html')
    pytest.skip("Skipping: unresolved placeholders for: 'username'; 'password'; 'Login'; 'Dashboard'; 'Car Insurance'; 'Get a Quote'; 'Start date'; 'Next / Continue'; 'Policy details entered'; 'License number'; 'Years licensed'; 'Occupation'; 'Save / Continue'; 'Driver details saved'; 'Registration'; 'Lookup Vehicle'; 'Vehicle found: Honda CR-V'; 'Confirm Vehicle'; 'Vehicle added'; 'Usage selected'")

@pytest.mark.evidence(condition_ref="TC-07", story_ref="S01")
def test_07_Set_No_Claims_Discount_and_overnight_parking_location(page: Page, evidence_tracker):
    mock_insurance_site_page = MockInsuranceSitePage(page, evidence_tracker)
    evidence_tracker.navigate('http://localhost:8781/generated_tests/mock_insurance_site.html')
    pytest.skip("Skipping: unresolved placeholders for: 'username'; 'password'; 'Login'; 'Dashboard'; 'Car Insurance'; 'Get a Quote'; 'Start date'; 'Next / Continue'; 'Policy details entered'; 'License number'; 'Years licensed'; 'Occupation'; 'Save / Continue'; 'Driver details saved'; 'Registration'; 'Lookup Vehicle'; 'Vehicle found: Honda CR-V'; 'Confirm Vehicle'; 'Vehicle added'; 'Usage selected'; 'No Claims Discount'; 'Continue'; 'No Claims Discount and parking set'")

@pytest.mark.evidence(condition_ref="TC-08", story_ref="S01")
def test_08_Verify_extras_page_displays_estimated_premium_and_compulsory_excess(page: Page, evidence_tracker):
    mock_insurance_site_page = MockInsuranceSitePage(page, evidence_tracker)
    evidence_tracker.navigate('http://localhost:8781/generated_tests/mock_insurance_site.html')
    pytest.skip("Skipping: unresolved placeholders for: 'username'; 'password'; 'Login'; 'Dashboard'; 'Car Insurance'; 'Get a Quote'; 'Start date'; 'Next / Continue'; 'Policy details entered'; 'License number'; 'Years licensed'; 'Occupation'; 'Save / Continue'; 'Driver details saved'; 'Registration'; 'Lookup Vehicle'; 'Vehicle found: Honda CR-V'; 'Confirm Vehicle'; 'Vehicle added'; 'Usage selected'; 'No Claims Discount'; 'Continue'; 'No Claims Discount and parking set'; 'Next / Continue to Extras'; 'Estimated premium displayed'; 'Compulsory excess displayed'")

@pytest.mark.evidence(condition_ref="TC-09", story_ref="S01")
def test_09_Select_payment_method_Pay_in_Full_and_submit_quote(page: Page, evidence_tracker):
    mock_insurance_site_page = MockInsuranceSitePage(page, evidence_tracker)
    evidence_tracker.navigate('http://localhost:8781/generated_tests/mock_insurance_site.html')
    pytest.skip("Skipping: unresolved placeholders for: 'username'; 'password'; 'Login'; 'Dashboard'; 'Car Insurance'; 'Get a Quote'; 'Start date'; 'Next / Continue'; 'Policy details entered'; 'License number'; 'Years licensed'; 'Occupation'; 'Save / Continue'; 'Driver details saved'; 'Registration'; 'Lookup Vehicle'; 'Vehicle found: Honda CR-V'; 'Confirm Vehicle'; 'Vehicle added'; 'Usage selected'; 'No Claims Discount'; 'Continue'; 'No Claims Discount and parking set'; 'Next / Continue to Extras'; 'Estimated premium displayed'; 'Compulsory excess displayed'; 'Next / Continue to Payment'; 'Submit Quote'; 'Quote submitted'")

@pytest.mark.evidence(condition_ref="TC-10", story_ref="S01")
def test_10_Verify_quote_confirmation_page_with_reference_number_and_premium(page: Page, evidence_tracker):
    mock_insurance_site_page = MockInsuranceSitePage(page, evidence_tracker)
    evidence_tracker.navigate('http://localhost:8781/generated_tests/mock_insurance_site.html')
    pytest.skip("Skipping: unresolved placeholders for: 'username'; 'password'; 'Login'; 'Dashboard'; 'Car Insurance'; 'Get a Quote'; 'Start date'; 'Next / Continue'; 'Policy details entered'; 'License number'; 'Years licensed'; 'Occupation'; 'Save / Continue'; 'Driver details saved'; 'Registration'; 'Lookup Vehicle'; 'Vehicle found: Honda CR-V'; 'Confirm Vehicle'; 'Vehicle added'; 'Usage selected'; 'No Claims Discount'; 'Continue'; 'No Claims Discount and parking set'; 'Next / Continue to Extras'; 'Estimated premium displayed'; 'Compulsory excess displayed'; 'Next / Continue to Payment'; 'Submit Quote'; 'Quote submitted'; 'Quote confirmation page displayed'; 'Reference number displayed'; 'Premium displayed'")