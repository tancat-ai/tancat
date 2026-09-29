"""B-100: the product reports its own verification strength per test.

The eval harness has to *guess* whether a passing test verified its criterion,
because it only sees the emitted code. The emitter knows better: it saw which
page a locator resolved against and whether the emitted check is an element
check or a page arrival. These tests pin the verdict at the emit chokepoint, in
the pipeline result, and in the written evidence bundle -- and prove that an
``unverified`` criterion reports a reason rather than silence.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from src.orchestrator import PipelineRunResult
from src.pipeline_models import (
    PageRequirement,
    PlaceholderUse,
    TestJourney,
    TestResolutionCounts,
    TestStep,
    TestVerificationVerdict,
    VerificationStatus,
)
from src.pipeline_writer import PipelineArtifactWriter
from src.placeholder_orchestrator import PlaceholderOrchestrator
from src.verification_strength import (
    ResolvedAssertion,
    compute_test_verification_verdicts,
)


def _placeholder(action: str, description: str, line_number: int) -> PlaceholderUse:
    token = f"{{{{{action}:{description}}}}}"
    return PlaceholderUse(
        action=action,
        description=description,
        token=token,
        line_number=line_number,
        raw_line=token,
    )


def _journey(test_name: str, descriptions: list[tuple[str, str]]) -> TestJourney:
    steps = [
        TestStep(
            line_number=index + 2,
            raw_line="x",
            placeholders=[_placeholder(action, description, index + 2)],
        )
        for index, (action, description) in enumerate(descriptions)
    ]
    return TestJourney(test_name=test_name, start_line=1, end_line=len(steps) + 2, steps=steps)


def _counts(test_name: str, resolved: int, unresolved: int) -> TestResolutionCounts:
    return TestResolutionCounts(test_name=test_name, resolved=resolved, unresolved=unresolved)


# ---------------------------------------------------------------------------
# Classifier: the emit-time decision
# ---------------------------------------------------------------------------


class TestComputeVerdicts:
    def test_resolved_element_assert_is_verified_by_element(self) -> None:
        journey = _journey("test_01", [("ASSERT", "backpack in cart")])
        assertions = {
            "test_01": [
                ResolvedAssertion(
                    description="backpack in cart",
                    resolved_value="'#remove-sauce-labs-backpack'",
                    page_url="https://example.com/cart",
                )
            ]
        }

        verdicts = compute_test_verification_verdicts([journey], assertions, {}, {"test_01": _counts("test_01", 1, 0)})

        assert len(verdicts) == 1
        assert verdicts[0].status == VerificationStatus.VERIFIED_BY_ELEMENT
        assert verdicts[0].label == "verified by element"
        assert "backpack" in verdicts[0].checked
        assert verdicts[0].page_url == "https://example.com/cart"
        assert verdicts[0].reason == ""

    def test_resolved_url_assert_is_verified_by_page_arrival(self) -> None:
        journey = _journey("test_01", [("ASSERT", "cart page loaded")])
        assertions = {
            "test_01": [
                ResolvedAssertion(
                    description="cart page loaded",
                    resolved_value='expect(page).to_have_url("https://example.com/cart")',
                    assertion_type="url",
                    page_url="https://example.com/cart",
                )
            ]
        }

        verdicts = compute_test_verification_verdicts([journey], assertions, {}, {"test_01": _counts("test_01", 1, 0)})

        assert verdicts[0].status == VerificationStatus.VERIFIED_BY_PAGE_ARRIVAL
        assert verdicts[0].label == "verified by page arrival"
        assert "to_have_url" in verdicts[0].checked
        assert verdicts[0].reason == ""

    def test_element_check_beats_page_arrival(self) -> None:
        """A test that checks a real element is stronger than one that only
        proves it arrived on a page."""
        journey = _journey("test_01", [("ASSERT", "cart page loaded"), ("ASSERT", "backpack in cart")])
        assertions = {
            "test_01": [
                ResolvedAssertion(
                    description="cart page loaded",
                    resolved_value='expect(page).to_have_url("https://example.com/cart")',
                    assertion_type="url",
                ),
                ResolvedAssertion(description="backpack in cart", resolved_value="'#backpack'"),
            ]
        }

        verdicts = compute_test_verification_verdicts([journey], assertions, {}, {"test_01": _counts("test_01", 2, 0)})

        assert verdicts[0].status == VerificationStatus.VERIFIED_BY_ELEMENT
        assert verdicts[0].checked == "'#backpack'"

    def test_unresolved_criterion_reports_a_reason_not_silence(self) -> None:
        """The required proof: an unverified criterion names why, and names the
        step that could not be resolved."""
        journey = _journey("test_01", [("CLICK", "add to cart"), ("ASSERT", "order success message")])
        assertions: dict[str, list[ResolvedAssertion]] = {}

        verdicts = compute_test_verification_verdicts(
            [journey],
            assertions,
            {"test_01": ["order success message"]},
            {"test_01": _counts("test_01", 1, 1)},
        )

        assert verdicts[0].status == VerificationStatus.UNVERIFIED
        assert verdicts[0].label == "unverified"
        assert verdicts[0].reason, "an unverified verdict must carry a reason"
        assert "order success message" in verdicts[0].reason
        assert "1 of 2" in verdicts[0].reason

    def test_criterion_without_any_assertion_reports_a_reason(self) -> None:
        journey = _journey("test_01", [("CLICK", "add to cart")])
        verdicts = compute_test_verification_verdicts([journey], {}, {}, {"test_01": _counts("test_01", 1, 0)})

        assert verdicts[0].status == VerificationStatus.UNVERIFIED
        assert verdicts[0].reason
        assert "assertion" in verdicts[0].reason

    def test_skip_valued_assert_does_not_verify_an_element(self) -> None:
        """A B-069 fallback assert emits a skip instead of a check; it must not
        be reported as verified by element even if the counts say all resolved."""
        journey = _journey("test_01", [("ASSERT", "widget")])
        assertions = {
            "test_01": [
                ResolvedAssertion(
                    description="widget",
                    resolved_value="pytest.skip(\"Assertion for 'widget' could not be verified on this page\")",
                )
            ]
        }
        verdicts = compute_test_verification_verdicts([journey], assertions, {}, {"test_01": _counts("test_01", 1, 0)})
        assert verdicts[0].status == VerificationStatus.UNVERIFIED
        assert verdicts[0].reason

    def test_page_level_assert_with_skip_value_is_an_element_check(self) -> None:
        """Page-level families keep a skip VALUE but the emitter overrides it
        into a real structural check -- it verified by element."""
        journey = _journey("test_01", [("ASSERT", "no broken images")])
        assertions = {
            "test_01": [
                ResolvedAssertion(
                    description="no broken images",
                    resolved_value='pytest.skip("page-level check")',
                    is_page_level=True,
                )
            ]
        }
        verdicts = compute_test_verification_verdicts([journey], assertions, {}, {"test_01": _counts("test_01", 1, 0)})
        assert verdicts[0].status == VerificationStatus.VERIFIED_BY_ELEMENT

    def test_global_container_assert_is_not_verified_by_element(self) -> None:
        """B-093 regression guard: a ``body`` check passes on any page, so it
        must not be recorded as a real element verification."""
        journey = _journey("test_01", [("ASSERT", "account balances")])
        assertions = {"test_01": [ResolvedAssertion(description="account balances", resolved_value="'body'")]}
        verdicts = compute_test_verification_verdicts([journey], assertions, {}, {"test_01": _counts("test_01", 1, 0)})

        assert verdicts[0].status == VerificationStatus.UNVERIFIED
        assert verdicts[0].reason, "a global-container check must carry a reason"
        assert "body" in verdicts[0].reason
        assert "global container" in verdicts[0].reason

    def test_global_container_with_has_text_is_not_verified(self) -> None:
        journey = _journey("test_01", [("ASSERT", "account balances")])
        assertions = {
            "test_01": [
                ResolvedAssertion(description="account balances", resolved_value="'main:has-text(\"Welcome\")'")
            ]
        }
        verdicts = compute_test_verification_verdicts([journey], assertions, {}, {"test_01": _counts("test_01", 1, 0)})
        assert verdicts[0].status == VerificationStatus.UNVERIFIED

    def test_real_element_beats_a_global_container(self) -> None:
        journey = _journey("test_01", [("ASSERT", "backpack in cart"), ("ASSERT", "account balances")])
        assertions = {
            "test_01": [
                ResolvedAssertion(description="backpack in cart", resolved_value="'#backpack'"),
                ResolvedAssertion(description="account balances", resolved_value="'body'"),
            ]
        }
        verdicts = compute_test_verification_verdicts([journey], assertions, {}, {"test_01": _counts("test_01", 2, 0)})
        assert verdicts[0].status == VerificationStatus.VERIFIED_BY_ELEMENT
        assert verdicts[0].checked == "'#backpack'"

    def test_page_arrival_beats_a_global_container(self) -> None:
        journey = _journey("test_01", [("ASSERT", "cart page loaded"), ("ASSERT", "account balances")])
        assertions = {
            "test_01": [
                ResolvedAssertion(
                    description="cart page loaded",
                    resolved_value='expect(page).to_have_url("https://example.com/cart")',
                    assertion_type="url",
                ),
                ResolvedAssertion(description="account balances", resolved_value="'body'"),
            ]
        }
        verdicts = compute_test_verification_verdicts([journey], assertions, {}, {"test_01": _counts("test_01", 2, 0)})
        assert verdicts[0].status == VerificationStatus.VERIFIED_BY_PAGE_ARRIVAL

    def test_verdict_serializes_with_a_label(self) -> None:
        verdict = TestVerificationVerdict(
            test_name="test_01",
            status=VerificationStatus.UNVERIFIED,
            reason="nothing checked",
        )
        assert verdict.to_dict() == {
            "test_name": "test_01",
            "status": "unverified",
            "label": "unverified",
            "checked": "",
            "page_url": "",
            "reason": "nothing checked",
        }


# ---------------------------------------------------------------------------
# End-to-end: the real resolution path emits the verdicts
# ---------------------------------------------------------------------------


class TestEndToEndEmit:
    def test_element_assert_is_verified_by_element(self) -> None:
        from unittest.mock import AsyncMock

        skeleton = "def test_assert(page):\n    page.assert_visible('{{ASSERT:widget}}')\n"
        scraped_data = {
            "https://example.com/": [
                {"selector": "#widget", "tag": "div", "role": "div", "text": "Widget"},
            ]
        }
        journey = _journey("test_assert", [("ASSERT", "widget")])
        orch = PlaceholderOrchestrator(starting_url="https://example.com/")
        orch._element_matcher.find_best_elements_batch = AsyncMock(  # type: ignore[method-assign]
            return_value=[{"selector": "#widget"}]
        )

        async def run() -> str:
            return await orch._replace_placeholders_sequentially(
                skeleton_code=skeleton,
                journeys=[journey],
                page_requirements=[PageRequirement(keyword="home")],
                seed_urls=["https://example.com/"],
                scraped_data=scraped_data,
                scraped_errors={},
            )

        asyncio.run(run())

        verdicts = orch.test_verification_verdicts
        assert len(verdicts) == 1
        assert verdicts[0].status == VerificationStatus.VERIFIED_BY_ELEMENT
        assert "#widget" in verdicts[0].checked

    def test_unresolved_assert_reports_a_reason_not_silence(self) -> None:
        """The B-100 case end to end: an ASSERT the resolver cannot verify is
        reported as unverified WITH the reason, not left blank."""
        from unittest.mock import AsyncMock

        skeleton = "def test_assert(page):\n    page.assert_visible('{{ASSERT:order success message}}')\n"
        scraped_data = {
            "https://example.com/": [
                {"selector": "#place-order", "tag": "button", "role": "button", "text": "Place Order"},
            ]
        }
        journey = _journey("test_assert", [("ASSERT", "order success message")])
        orch = PlaceholderOrchestrator(starting_url="https://example.com/")
        orch._element_matcher.find_best_elements_batch = AsyncMock(  # type: ignore[method-assign]
            return_value=[None]
        )

        async def run() -> str:
            return await orch._replace_placeholders_sequentially(
                skeleton_code=skeleton,
                journeys=[journey],
                page_requirements=[PageRequirement(keyword="home")],
                seed_urls=["https://example.com/"],
                scraped_data=scraped_data,
                scraped_errors={},
            )

        emitted = asyncio.run(run())

        verdicts = orch.test_verification_verdicts
        assert len(verdicts) == 1
        assert verdicts[0].status == VerificationStatus.UNVERIFIED
        assert verdicts[0].reason
        assert "order success message" in verdicts[0].reason
        # The skip and the verdict agree: both name the unresolved criterion.
        assert "order success message" in emitted

    def test_page_state_assert_is_verified_by_page_arrival(self) -> None:
        skeleton = "def test_nav(page):\n    page.assert_page('{{ASSERT:cart page loaded}}')\n"
        scraped_data = {
            "https://example.com/": [
                {"selector": "#home", "tag": "div", "role": "div", "text": "Home"},
            ],
            "https://example.com/cart": [
                {"selector": "#cart-item", "tag": "div", "role": "div", "text": "Item"},
            ],
        }
        journey = _journey("test_nav", [("ASSERT", "cart page loaded")])
        orch = PlaceholderOrchestrator(starting_url="https://example.com/")

        async def run() -> str:
            return await orch._replace_placeholders_sequentially(
                skeleton_code=skeleton,
                journeys=[journey],
                page_requirements=[PageRequirement(keyword="cart")],
                seed_urls=["https://example.com/"],
                scraped_data=scraped_data,
                scraped_errors={},
            )

        emitted = asyncio.run(run())

        verdicts = orch.test_verification_verdicts
        assert len(verdicts) == 1
        assert verdicts[0].status == VerificationStatus.VERIFIED_BY_PAGE_ARRIVAL
        assert "to_have_url" in verdicts[0].checked
        assert "to_have_url" in emitted

    def test_global_container_assert_reports_a_reason(self) -> None:
        """The resolver picked a container (``body``): the emitted test cannot
        claim it verified the criterion, end to end through the real emitter."""
        from unittest.mock import AsyncMock

        skeleton = "def test_assert(page):\n    page.assert_visible('{{ASSERT:account balances}}')\n"
        scraped_data = {
            "https://example.com/": [
                {"selector": "body", "tag": "body", "role": "body", "text": "Content"},
            ]
        }
        journey = _journey("test_assert", [("ASSERT", "account balances")])
        orch = PlaceholderOrchestrator(starting_url="https://example.com/")
        orch._element_matcher.find_best_elements_batch = AsyncMock(  # type: ignore[method-assign]
            return_value=[{"selector": "body"}]
        )

        async def run() -> str:
            return await orch._replace_placeholders_sequentially(
                skeleton_code=skeleton,
                journeys=[journey],
                page_requirements=[PageRequirement(keyword="home")],
                seed_urls=["https://example.com/"],
                scraped_data=scraped_data,
                scraped_errors={},
            )

        asyncio.run(run())

        verdicts = orch.test_verification_verdicts
        assert len(verdicts) == 1
        assert verdicts[0].status == VerificationStatus.UNVERIFIED
        assert verdicts[0].reason
        assert "body" in verdicts[0].reason

    def test_stale_verdicts_cleared_at_entry(self) -> None:
        orch = PlaceholderOrchestrator(starting_url="https://example.com/")
        orch._test_verification_verdicts = [
            TestVerificationVerdict(
                test_name="old_test",
                status=VerificationStatus.VERIFIED_BY_ELEMENT,
                checked="#old",
            )
        ]

        async def run() -> str:
            return await orch._replace_placeholders_sequentially(
                skeleton_code="",
                journeys=[],
                page_requirements=[PageRequirement(keyword="home")],
                seed_urls=["https://example.com/"],
                scraped_data={"https://example.com/": []},
                scraped_errors={},
            )

        asyncio.run(run())
        assert orch.test_verification_verdicts == []


# ---------------------------------------------------------------------------
# Evidence bundle: the written artifact carries the verdicts
# ---------------------------------------------------------------------------


class TestWrittenBundle:
    def test_run_artifacts_carry_verdicts(self, tmp_path: Path) -> None:
        writer = PipelineArtifactWriter(output_dir=str(tmp_path))
        run_result = PipelineRunResult(
            skeleton_code="",
            final_code="def test_checkout(page):\n    pass\n",
            journeys=[_journey("test_checkout", [("ASSERT", "backpack in cart")])],
            test_verification_verdicts=[
                TestVerificationVerdict(
                    test_name="test_checkout",
                    status=VerificationStatus.VERIFIED_BY_ELEMENT,
                    checked="'#backpack'",
                    page_url="https://example.com/cart",
                ),
                TestVerificationVerdict(
                    test_name="test_checkout_unverified",
                    status=VerificationStatus.UNVERIFIED,
                    reason="1 of 1 placeholders unresolved: 'order success message'",
                ),
            ],
        )

        artifact_set = writer.write_run_artifacts(
            run_result=run_result,
            story_text="Checkout flow",
            base_url="https://example.com/",
        )

        assert artifact_set.verification_strength_path
        strength_path = Path(artifact_set.verification_strength_path)
        assert strength_path.exists()
        payload = json.loads(strength_path.read_text(encoding="utf-8"))
        assert payload["verdicts"][0]["status"] == "verified_by_element"
        assert payload["verdicts"][0]["checked"] == "'#backpack'"
        # The unverified verdict must carry its reason, not silence.
        assert payload["verdicts"][1]["status"] == "unverified"
        assert payload["verdicts"][1]["reason"]

        manifest = json.loads(Path(artifact_set.manifest_path).read_text(encoding="utf-8"))
        assert manifest["verification_strength_path"].endswith("verification_strength.json")
        assert manifest["test_verification_verdicts"][1]["reason"]

        coverage = json.loads(
            (Path(artifact_set.test_file_path).parent / "coverage_summary.json").read_text(encoding="utf-8")
        )
        assert coverage["test_verification_verdicts"][0]["status"] == "verified_by_element"

    def test_run_artifacts_without_verdicts_write_an_empty_list(self, tmp_path: Path) -> None:
        """Backward compatible: a run that classified nothing writes an empty
        list, not a missing file."""
        writer = PipelineArtifactWriter(output_dir=str(tmp_path))
        run_result = PipelineRunResult(
            skeleton_code="",
            final_code="def test_checkout(page):\n    pass\n",
        )
        artifact_set = writer.write_run_artifacts(
            run_result=run_result,
            story_text="Checkout flow",
            base_url="https://example.com/",
        )
        payload = json.loads(Path(artifact_set.verification_strength_path).read_text(encoding="utf-8"))
        assert payload["verdicts"] == []
