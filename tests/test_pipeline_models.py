"""Tests for shared intelligent-pipeline data models."""

from src.pipeline_models import (
    GeneratedPageObject,
    ManifestRecord,
    PageRequirement,
    PipelineArtifactSet,
    PlaceholderUse,
    ScrapedPage,
    TestJourney,
    TestStep,
)


def test_models_serialize_to_json_friendly_dicts() -> None:
    placeholder = PlaceholderUse(
        action="CLICK",
        description="cart link",
        token="{{CLICK:cart link}}",
        line_number=12,
        raw_line="    {{CLICK:cart link}}",
    )
    step = TestStep(line_number=12, raw_line="    {{CLICK:cart link}}", placeholders=[placeholder])
    journey = TestJourney(
        test_name="test_checkout",
        start_line=10,
        end_line=18,
        page_object_names=["CartPage"],
        steps=[step],
    )
    page = ScrapedPage(url="https://example.com/cart", element_count=4, elements=[{"selector": "#checkout"}])
    page_object = GeneratedPageObject(
        class_name="CartPage",
        module_name="cart_page",
        file_path="generated_tests/run_1/pages/cart_page.py",
        url="https://example.com/cart",
        methods=["goto", "proceed_to_checkout"],
    )
    record = ManifestRecord(
        kind="unresolved_placeholder",
        message="checkout button missing",
        test_name="test_checkout",
        placeholder="{{CLICK:checkout button}}",
        page_url="https://example.com/cart",
    )
    artifact_set = PipelineArtifactSet(
        run_id="run_1",
        test_file_path="generated_tests/run_1/test_checkout.py",
        page_object_paths=[page_object.file_path],
        manifest_path="generated_tests/run_1/scrape_manifest.json",
        pages=[page],
        records=[record],
    )

    assert placeholder.to_dict()["action"] == "CLICK"
    assert step.to_dict()["placeholders"][0]["description"] == "cart link"
    assert journey.to_dict()["page_object_names"] == ["CartPage"]
    pr = PageRequirement(keyword="home", description="homepage")
    assert pr.to_dict()["keyword"] == "home"
    assert page.to_dict()["element_count"] == 4
    assert page_object.to_dict()["module_name"] == "cart_page"
    assert record.to_dict()["kind"] == "unresolved_placeholder"
    assert artifact_set.to_dict()["manifest_path"].endswith("scrape_manifest.json")
