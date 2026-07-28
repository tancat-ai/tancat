import pytest
from playwright.sync_api import Page

from src.browser_utils import dismiss_consent_overlays
from src.evidence_tracker import EvidenceTracker


@pytest.mark.evidence(condition_ref="TC-01", story_ref="S05")
def test_01_create_account(page: Page, evidence_tracker: EvidenceTracker) -> None:
    evidence_tracker.navigate("http://localhost:8781/generated_tests/mock_insurance_site.html")
    dismiss_consent_overlays(page)
    evidence_tracker.fill("#email", "john@example.com", label="email address")
    evidence_tracker.fill("#password", "Password123!", label="password")
    evidence_tracker.fill("#firstName", "John", label="first name")
    evidence_tracker.fill("#lastName", "Smith", label="last name")
    evidence_tracker.fill("#postcode", "SW1A 1AA", label="postcode")
    evidence_tracker.click("#accountNext", label="Next button on account page")


@pytest.mark.evidence(condition_ref="TC-02", story_ref="S05")
def test_02_select_car_insurance(page: Page, evidence_tracker: EvidenceTracker) -> None:
    evidence_tracker.navigate("http://localhost:8781/generated_tests/mock_insurance_site.html")
    dismiss_consent_overlays(page)
    evidence_tracker.click("#productCar", label="Car Insurance product card")


@pytest.mark.evidence(condition_ref="TC-03", story_ref="S05")
def test_03_enter_policy_details(page: Page, evidence_tracker: EvidenceTracker) -> None:
    evidence_tracker.navigate("http://localhost:8781/generated_tests/mock_insurance_site.html")
    dismiss_consent_overlays(page)
    evidence_tracker.fill("#startDate", "2026-08-01", label="cover start date")
    evidence_tracker.fill("#scheme", "Standard", label="scheme")


@pytest.mark.evidence(condition_ref="TC-04", story_ref="S05")
def test_04_enter_driver_details(page: Page, evidence_tracker: EvidenceTracker) -> None:
    evidence_tracker.navigate("http://localhost:8781/generated_tests/mock_insurance_site.html")
    dismiss_consent_overlays(page)
    evidence_tracker.fill("#mainLicenseNumber", "AB123456CD", label="driving license number")
    evidence_tracker.fill("#mainLicenseYears", "10", label="years licensed")
    evidence_tracker.fill("#mainOccupation", "Engineer", label="occupation select")


@pytest.mark.evidence(condition_ref="TC-05", story_ref="S05")
def test_05_add_vehicle_via_reg(page: Page, evidence_tracker: EvidenceTracker) -> None:
    evidence_tracker.navigate("http://localhost:8781/generated_tests/mock_insurance_site.html")
    dismiss_consent_overlays(page)
    evidence_tracker.fill("#vehicleReg", "AB12CDE", label="vehicle registration number")
    evidence_tracker.click("#lookupRegBtn", label="Look Up registration button")


@pytest.mark.evidence(condition_ref="TC-06", story_ref="S05")
def test_06_select_usage_type(page: Page, evidence_tracker: EvidenceTracker) -> None:
    evidence_tracker.navigate("http://localhost:8781/generated_tests/mock_insurance_site.html")
    dismiss_consent_overlays(page)
    evidence_tracker.click("input[name='usageType'][value='SDP']", label="usage type")


@pytest.mark.evidence(condition_ref="TC-07", story_ref="S05")
def test_07_set_ncd_and_parking(page: Page, evidence_tracker: EvidenceTracker) -> None:
    evidence_tracker.navigate("http://localhost:8781/generated_tests/mock_insurance_site.html")
    dismiss_consent_overlays(page)
    evidence_tracker.fill("#ncdYears", "5", label="No Claims Discount (Years)")
    evidence_tracker.fill("#overnightLocation", "Private Garage", label="overnight location")
    evidence_tracker.click("#addVehicleBtn", label="Add Vehicle button")


@pytest.mark.evidence(condition_ref="TC-08", story_ref="S05")
def test_08_verify_extras_page(page: Page, evidence_tracker: EvidenceTracker) -> None:
    evidence_tracker.navigate("http://localhost:8781/generated_tests/mock_insurance_site.html")
    dismiss_consent_overlays(page)
    evidence_tracker.assert_visible("#premiumPrice", label="estimated annual premium displayed")
    evidence_tracker.assert_visible("#excessInfo", label="compulsory excess information")


@pytest.mark.evidence(condition_ref="TC-09", story_ref="S05")
def test_09_submit_quote(page: Page, evidence_tracker: EvidenceTracker) -> None:
    evidence_tracker.navigate("http://localhost:8781/generated_tests/mock_insurance_site.html")
    dismiss_consent_overlays(page)
    evidence_tracker.click("#paymentFull", label="Pay in Full payment option")
    evidence_tracker.click("#quoteSubmit", label="Submit and Get Quote button")


@pytest.mark.evidence(condition_ref="TC-10", story_ref="S05")
def test_10_verify_quote_confirmation(page: Page, evidence_tracker: EvidenceTracker) -> None:
    evidence_tracker.navigate("http://localhost:8781/generated_tests/mock_insurance_site.html")
    dismiss_consent_overlays(page)
    evidence_tracker.assert_visible("#quoteSuccess", label="quote generated successfully message")
    evidence_tracker.assert_visible("#quoteRef", label="quote reference number")
