#!/usr/bin/env python
"""Compare POM vs Standard mode using ONE shared skeleton.

1. Parse user story once
2. Generate ONE skeleton (one LLM call)
3. Pass that exact skeleton to both modes
4. Resolution rates must be identical
"""

from __future__ import annotations

import asyncio
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.llm_client import LLMClient
from src.orchestrator import TestOrchestrator
from src.pipeline_writer import PipelineArtifactWriter
from src.test_generator import TestGenerator
from src.user_story_parser import FeatureParser

BASE_URL = "https://automationexercise.com"
OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "generated_tests"

USER_STORY = """As a shopper on AutomationExercise.com, I want to:
1. Browse the product catalog by category
2. Add items to my shopping cart
3. View and verify cart contents
4. Complete the checkout process

So that I can purchase products online with confidence."""

CONDITIONS = """1. Navigate to home page and verify product categories are visible
2. Select a product category (e.g., Dress) and verify product listings appear
3. Add a product to cart and verify confirmation popup appears
4. View cart and verify the added item is listed with correct details
5. Proceed to checkout and verify order summary is displayed
6. Verify login status or prompt on checkout page"""


def _count_results(stdout: str) -> tuple[int, int, int]:
    return (stdout.count("PASSED"), stdout.count("FAILED"), stdout.count("SKIPPED"))


async def run_once(
    skeleton: str, user_story: str, pom_mode: bool,
    client: LLMClient, gen: TestGenerator,
) -> dict:
    """Run pipeline with the given skeleton (no LLM call for generation)."""
    orch = TestOrchestrator(gen, credential_profile=None, pom_mode=pom_mode)
    orch._starting_url = BASE_URL
    orch._placeholder_orchestrator._starting_url = BASE_URL

    journeys = orch.parser.parse_test_journeys(skeleton)
    page_reqs = orch.parser.parse_page_requirements(skeleton)

    pages = orch._build_candidate_urls(
        seed_urls=[BASE_URL], page_requirements=page_reqs,
        journeys=journeys, user_story=user_story, conditions=CONDITIONS,
    )
    raw = await orch._scraper.scrape_all(pages)
    scraped = {u: e for u, (e, err, _) in raw.items()}
    errors = {u: err for u, (_, err, _) in raw.items() if err}

    if BASE_URL:
        disc, _ = await orch._scrape_journeys_statefully(journeys, BASE_URL)
        for url, elems in disc.items():
            if elems:
                scraped[url] = elems

    if BASE_URL:
        keywords = [pr.keyword for pr in page_reqs]
        orch._placeholder_orchestrator.url_resolver.build_mapping(
            keywords=keywords, scraped_urls=list(scraped.keys()), seed_url=BASE_URL,
        )

    all_urls = list(scraped.keys())
    records = orch._placeholder_orchestrator._build_scraped_page_records(all_urls, scraped, errors)
    page_objs = orch._placeholder_orchestrator._build_page_object_artifacts(records)

    code = await orch._placeholder_orchestrator._replace_placeholders_sequentially(
        skeleton_code=skeleton, journeys=journeys, page_requirements=page_reqs,
        seed_urls=[BASE_URL], scraped_data=scraped, scraped_errors=errors,
    )

    if pom_mode and page_objs:
        imports = orch._placeholder_orchestrator._build_pom_imports(page_objs)
        instantiation = orch._placeholder_orchestrator._build_pom_instantiation(page_objs)
        if imports:
            code = orch._inject_pom_imports(code, imports)
        if instantiation:
            code = orch._inject_pom_instantiation(code, instantiation)

    from src.code_postprocessor import normalise_generated_code
    code = normalise_generated_code(code, consent_mode="auto-dismiss", target_url=BASE_URL)
    unresolved = [l for l in code.splitlines() if "pytest.skip(" in l]

    from src.orchestrator import PipelineRunResult
    run_result = PipelineRunResult(
        final_code=code, skeleton_code=skeleton,
        pages_to_scrape=pages, scraped_pages=scraped, scraped_errors=errors,
        page_requirements=page_reqs, journeys=journeys,
        scraped_page_records=records, generated_page_objects=page_objs,
        unresolved_placeholders=unresolved, pages_visited=[], pom_mode=pom_mode,
    )
    writer = PipelineArtifactWriter(output_dir=str(OUTPUT_DIR))
    artifact = writer.write_run_artifacts(
        run_result=run_result, story_text=USER_STORY,
        base_url=BASE_URL, provider=client.provider_name, model=client.model,
    )
    test_pkg = Path(artifact.test_file_path).resolve().parent
    test_files = list(test_pkg.glob("test_*.py"))
    test_code = test_files[0].read_text() if test_files else ""

    passed, failed, skipped = 0, 0, 0
    if test_files:
        result = subprocess.run(
            ["pytest", str(test_files[0]), "-v", "--tb=line"],
            capture_output=True, text=True, cwd=str(test_pkg), timeout=300,
        )
        passed, failed, skipped = _count_results(result.stdout)

    rate = 1.0 - (len(unresolved) / max(len(journeys), 1))
    return {"journeys": len(journeys), "objects": len(page_objs),
                "unresolved": len(unresolved), "rate": rate,
                "passed": passed, "failed": failed, "skipped": skipped,
                "code": test_code, "pkg": test_pkg,
                "ev_calls": test_code.count("evidence_tracker."),
                "pom_calls": test_code.count(".click(") + test_code.count(".fill(")}


def main() -> None:
    print("=" * 60)
    print("POM vs Standard: Same-Skeleton Comparison")
    print("=" * 60)
    print()
    print("  Both modes receive the EXACT same skeleton code.")
    print("  Only the pom_mode flag differs between runs.")
    print("  Resolution rates MUST be equal.")
    print()

    client = LLMClient()
    gen = TestGenerator(client=client, model_name=client.model)

    parser = FeatureParser()
    pr = parser.parse(USER_STORY)
    assert pr.specification is not None
    spec = pr.specification

    print("  [1] Generating shared skeleton (one LLM call)...")
    skeleton = asyncio.run(gen.generate_skeleton(
        spec.user_story, CONDITIONS, target_urls=[BASE_URL], expected_count=6,
    ))
    ph_count = skeleton.count("{{")
    print(f"  Skeleton: {len(skeleton)} chars, ~{ph_count} placeholders\n")

    print("  [2] Running POM mode...")
    pom = asyncio.run(run_once(skeleton, spec.user_story, True, client, gen))

    print("  [3] Running Standard mode (same skeleton)...")
    std = asyncio.run(run_once(skeleton, spec.user_story, False, client, gen))

    print("  [4] Results\n")
    print("=" * 60)
    print(f"{'Metric':<30} {'POM':<13} {'Standard':<13}")
    print("-" * 60)
    print(f"{'Tests generated':<30} {pom['journeys']:<13} {std['journeys']:<13}")
    print(f"{'Page objects':<30} {pom['objects']:<13} {std['objects']:<13}")
    print(f"{'Unresolved':<30} {pom['unresolved']:<13} {std['unresolved']:<13}")
    print(f"{'Resolution rate':<30} {pom['rate']:.0%:<13} {std['rate']:.0%:<13}")
    parity = "IDENTICAL" if pom["rate"] == std["rate"] else "DIFFERENT!"
    print(f"{'Parity check':<30} {parity:<13} {parity:<13}")
    print(f"{'Passed / Failed / Skipped':<30} {pom['passed']}/{pom['failed']}/{pom['skipped']:<13} {std['passed']}/{std['failed']}/{std['skipped']:<13}")
    print(f"{'evidence_tracker calls':<30} {pom['ev_calls']:<13} {std['ev_calls']:<13}")
    print(f"{'POM method calls':<30} {pom['pom_calls']:<13} {'N/A':<13}")
    print()

    if pom["rate"] == std["rate"]:
        print("  PASS: Resolution rates are identical across modes.")
        print("  The pom_mode flag only changes output rendering, not resolution.")
    else:
        print("  FAIL: Resolution rates differ!")
        print(f"  POM pkg:      {pom['pkg']}")
        print(f"  Standard pkg: {std['pkg']}")
        sys.exit(1)

    print(f"\n  POM package:      {pom['pkg']}")
    print(f"  Standard package: {std['pkg']}")


if __name__ == "__main__":
    main()
