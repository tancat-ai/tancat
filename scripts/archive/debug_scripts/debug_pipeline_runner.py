#!/usr/bin/env python
"""Unified pipeline runner for both POM and Standard modes.

Runs the full end-to-end pipeline, verifies parity between modes,
and generates a comparison report.

Usage:
    # Run with POM mode
    python scripts/debug/debug_pipeline_runner.py --mode pom

    # Run with Standard mode
    python scripts/debug/debug_pipeline_runner.py --mode standard

    # Run BOTH modes on the same skeleton and verify identical resolution
    python scripts/debug/debug_pipeline_runner.py --mode compare

    # Custom URL and user story
    python scripts/debug/debug_pipeline_runner.py --mode pom --url https://saucedemo.com --story "..."

Architecture:
    - Single pipeline path for both modes
    - Resolution code is identical regardless of pom_mode
    - pom_mode only changes OUTPUT RENDERING (POM method calls vs evidence_tracker calls)
    - Compare mode proves this by running both on the same skeleton
"""

from __future__ import annotations

import argparse
import asyncio
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from src.code_postprocessor import normalise_generated_code
from src.llm_client import LLMClient
from src.orchestrator import PipelineRunResult, TestOrchestrator
from src.pipeline_writer import PipelineArtifactWriter
from src.test_generator import TestGenerator
from src.user_story_parser import FeatureParser

DEFAULT_URL = "https://automationexercise.com"
OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "generated_tests"

DEFAULT_STORY = """As a shopper on AutomationExercise.com, I want to:
1. Browse the product catalog by category
2. Add items to my shopping cart
3. View and verify cart contents
4. Complete the checkout process

So that I can purchase products online with confidence."""

DEFAULT_CONDITIONS = """1. Navigate to home page and verify product categories are visible
2. Select a product category (e.g., Dress) and verify product listings appear
3. Add a product to cart and verify confirmation popup appears
4. View cart and verify the added item is listed with correct details
5. Proceed to checkout and verify order summary is displayed
6. Verify login status or prompt on checkout page"""


def _count_test_results(stdout: str) -> dict[str, int]:
    return {
        "passed": stdout.count("PASSED"),
        "failed": stdout.count("FAILED"),
        "skipped": stdout.count("SKIPPED"),
        "errors": stdout.count("ERROR"),
    }


async def run_pipeline(
    user_story: str,
    conditions: str,
    base_url: str,
    pom_mode: bool,
    client: LLMClient,
    generator: TestGenerator,
    save: bool = True,
    skeleton_override: str | None = None,
    run_tests: bool = False,
    shared_scraped_data: dict | None = None,
) -> dict:
    """Full pipeline run: skeleton -> scrape -> resolve -> (POM injection) -> normalize.

    Args:
        skeleton_override: If provided, use this skeleton instead of generating one.
            Compare mode uses this to pass the exact same skeleton to both modes.

    Returns diagnostics including final code and resolution stats.
    """
    orchestrator = TestOrchestrator(generator, credential_profile=None, pom_mode=pom_mode)
    orchestrator._starting_url = base_url
    orchestrator._placeholder_orchestrator._starting_url = base_url

    mode_label = "POM" if pom_mode else "Standard"

    # 1. Parse user story
    parser = FeatureParser()
    pr = parser.parse(user_story)
    assert pr.specification is not None
    spec = pr.specification

    # 2. Generate skeleton (or use override from compare mode)
    if skeleton_override is not None:
        skeleton = skeleton_override
    else:
        skeleton = await generator.generate_skeleton(
            spec.user_story, conditions, target_urls=[base_url], expected_count=6,
        )
    skeleton = orchestrator.parser.normalise_placeholder_actions(skeleton)

    journeys = orchestrator.parser.parse_test_journeys(skeleton)
    page_reqs = orchestrator.parser.parse_page_requirements(skeleton)
    ph_count = skeleton.count("{{")

    # 3. Scrape (reuse shared data if provided — compare mode optimisation)
    pages_to_scrape = orchestrator._build_candidate_urls(
        seed_urls=[base_url], page_requirements=page_reqs,
        journeys=journeys, user_story=spec.user_story, conditions=conditions,
    )
    if shared_scraped_data is not None:
        scraped = dict(shared_scraped_data)
        errors = {}
    else:
        raw = await orchestrator._scraper.scrape_all(pages_to_scrape)
        scraped = {u: e for u, (e, err, _) in raw.items()}
        errors = {u: err for u, (_, err, _) in raw.items() if err}

        if base_url:
            disc, _ = await orchestrator._scrape_journeys_statefully(journeys, base_url)
            for url, elems in disc.items():
                if elems:
                    scraped[url] = elems

            # Upgrade stateful pages with cart-seeding scraper
            scraped = await orchestrator._placeholder_orchestrator._upgrade_stateful_pages(scraped)

    # 4. Build URL resolver
    if base_url:
        keywords = [pr.keyword for pr in page_reqs]
        orchestrator._placeholder_orchestrator.url_resolver.build_mapping(
            keywords=keywords, scraped_urls=list(scraped.keys()), seed_url=base_url,
        )

    # 5. Build page objects from all scraped URLs
    all_urls = list(scraped.keys())
    records = orchestrator._placeholder_orchestrator._build_scraped_page_records(all_urls, scraped, errors)
    page_objs = orchestrator._placeholder_orchestrator._build_page_object_artifacts(records)

    # 6. Resolve placeholders (IDENTICAL path for both modes)
    code = await orchestrator._placeholder_orchestrator._replace_placeholders_sequentially(
        skeleton_code=skeleton, journeys=journeys, page_requirements=page_reqs,
        seed_urls=[base_url], scraped_data=scraped, scraped_errors=errors,
    )

    # 7. POM injection (only in pom_mode — purely cosmetic rendering change)
    if pom_mode and page_objs:
        imports = orchestrator._placeholder_orchestrator._build_pom_imports(page_objs)
        instantiation = orchestrator._placeholder_orchestrator._build_pom_instantiation(page_objs)
        if imports:
            code = orchestrator._inject_pom_imports(code, imports)
        if instantiation:
            code = orchestrator._inject_pom_instantiation(code, instantiation)

    # 8. Normalize
    code = normalise_generated_code(code, consent_mode="auto-dismiss", target_url=base_url)
    unresolved = [l for l in code.splitlines() if "pytest.skip(" in l]

    # 9. Save
    run_result = PipelineRunResult(
        final_code=code, skeleton_code=skeleton,
        pages_to_scrape=pages_to_scrape, scraped_pages=scraped,
        scraped_errors=errors, page_requirements=page_reqs,
        journeys=journeys, scraped_page_records=records,
        generated_page_objects=page_objs, unresolved_placeholders=unresolved,
        pages_visited=[], pom_mode=pom_mode,
    )

    test_pkg = None
    test_results = {"passed": 0, "failed": 0, "skipped": 0, "errors": 0}

    if save:
        writer = PipelineArtifactWriter(output_dir=str(OUTPUT_DIR))
        artifact = writer.write_run_artifacts(
            run_result=run_result, story_text=user_story,
            base_url=base_url, provider=client.provider_name, model=client.model,
        )
        test_pkg = Path(artifact.test_file_path).resolve().parent
        test_files = list(test_pkg.glob("test_*.py"))

        # Run pytest only when explicitly requested via run_tests=True.
        # Generated tests interact with live websites and will hang if the
        # site is slow or elements are not found (Playwright 30s timeout
        # per action × multiple actions × multiple tests).
        if run_tests and test_files:
            result = subprocess.run(
                ["pytest", str(test_files[0]), "-v", "--tb=line"],
                capture_output=True, text=True, cwd=str(test_pkg), timeout=300,
            )
            test_results = _count_test_results(result.stdout)

    rate = 1.0 - (len(unresolved) / max(len(journeys), 1))

    result: dict = {
        "mode": mode_label,
        "journeys": len(journeys),
        "placeholders": ph_count,
        "page_objects": len(page_objs),
        "page_object_names": [po.class_name for po in page_objs],
        "unresolved": len(unresolved),
        "resolution_rate": f"{rate:.0%}",
        "test_results": test_results,
        "code": code,
        "pkg": test_pkg,
        "pom_calls": code.count(".click(") + code.count(".fill(") if pom_mode else 0,
        "ev_calls": code.count("evidence_tracker."),
        "_scraped_data": scraped,  # shared between POM/Standard in compare mode
    }
    return result


def run_compare(user_story: str, conditions: str, base_url: str, run_tests: bool = False) -> None:
    """Run BOTH modes on the same skeleton and verify identical resolution.

    This is the key diagnostic: both modes share the resolution path.
    Any difference in resolution rate is a bug.
    """
    print("=" * 70)
    print("PARITY VERIFICATION: POM vs Standard")
    print("=" * 70)
    print()
    print("  Both modes get the EXACT same skeleton and EXACT same")
    print("  resolution pipeline. pom_mode only affects output rendering.")
    print()

    client = LLMClient()
    gen = TestGenerator(client=client, model_name=client.model)

    print("  [1/5] Generating shared skeleton (one LLM call)...")
    parser = FeatureParser()
    pr = parser.parse(user_story)
    assert pr.specification is not None
    spec = pr.specification

    skeleton = asyncio.run(gen.generate_skeleton(
        spec.user_story, conditions, target_urls=[base_url], expected_count=6,
    ))
    from src.skeleton_parser import SkeletonParser
    skeleton = SkeletonParser().normalise_placeholder_actions(skeleton)
    print(f"  Skeleton: {len(skeleton)} chars, ~{skeleton.count('{{')} placeholders\n")

    print("  [2/5] Running POM mode (includes shared scrape)...")
    pom = asyncio.run(run_pipeline(user_story, conditions, base_url, True, client, gen,
                                   skeleton_override=skeleton, run_tests=run_tests))

    print("  [3/5] Running Standard mode (same skeleton, same scraped data)...")
    # Standard mode uses the EXACT same scraped data from POM mode —
    # resolution is identical, only output rendering differs.
    std = asyncio.run(run_pipeline(user_story, conditions, base_url, False, client, gen,
                                   skeleton_override=skeleton, run_tests=run_tests,
                                   shared_scraped_data=pom.get("_scraped_data")))

    print("  [4/5] Verifying parity...\n")

    # ── Assert identical resolution ──
    parity_ok = True
    checks = [
        ("Test count", pom["journeys"], std["journeys"]),
        ("Unresolved", pom["unresolved"], std["unresolved"]),
        ("Resolution rate", pom["resolution_rate"], std["resolution_rate"]),
    ]
    for label, pv, sv in checks:
        ok = pv == sv
        status = "PASS" if ok else "FAIL"
        if not ok:
            parity_ok = False
        print(f"    [{status}] {label}: POM={pv}, Standard={sv}")

    # ── Show output shape differences ──
    print()
    print("  [5/5] Results\n")

    print("=" * 70)
    print(f"{'Metric':<35} {'POM Mode':<15} {'Standard':<15}")
    print("-" * 70)
    print(f"{'Tests generated':<35} {pom['journeys']:<15} {std['journeys']:<15}")
    print(f"{'Page objects':<35} {pom['page_objects']:<15} {std['page_objects']:<15}")
    if pom["page_objects"] > 0:
        print(f"{'Page object types':<35} {', '.join(pom['page_object_names']):<30}")
    print(f"{'Placeholders in skeleton':<35} {pom['placeholders']:<15} {std['placeholders']:<15}")
    print(f"{'Unresolved':<35} {pom['unresolved']:<15} {std['unresolved']:<15}")
    print(f"{'Resolution rate':<35} {pom['resolution_rate']:<15} {std['resolution_rate']:<15}")
    print(f"{'Tests passed':<35} {pom['test_results']['passed']:<15} {std['test_results']['passed']:<15}")
    print(f"{'Tests failed':<35} {pom['test_results']['failed']:<15} {std['test_results']['failed']:<15}")
    print(f"{'Tests skipped':<35} {pom['test_results']['skipped']:<15} {std['test_results']['skipped']:<15}")
    print(f"{'Code size (lines)':<35} {len(pom['code'].splitlines()):<15} {len(std['code'].splitlines()):<15}")
    print(f"{'POM method calls':<35} {pom['pom_calls']:<15} {'N/A':<15}")
    print(f"{'evidence_tracker calls':<35} {pom['ev_calls']:<15} {std['ev_calls']:<15}")
    print("-" * 70)

    if parity_ok:
        print("\n  RESULT: PARITY VERIFIED [OK]")
        print("  POM mode and Standard mode produce identical resolution.")
        print("  Only the output rendering differs (POM vs direct calls).")
    else:
        print("\n  RESULT: PARITY FAILED [FAIL]")
        print("  Resolution rates differ between modes. This is a bug.")

    print(f"\n  Pom package:      {pom['pkg']}")
    print(f"  Standard package: {std['pkg']}")

    # Print code snippets side by side
    pom_lines = pom["code"].splitlines()
    std_lines = std["code"].splitlines()
    max_lines = max(len(pom_lines), len(std_lines))
    print()
    print("=" * 70)
    print("CODE COMPARISON (first 20 lines)")
    print("=" * 70)
    print(f"{'Line':<5} {'POM Mode':<62} {'Standard':<62}")
    print("-" * 130)
    for i in range(min(20, max_lines)):
        pl = pom_lines[i] if i < len(pom_lines) else ""
        sl = std_lines[i] if i < len(std_lines) else ""
        print(f"{i+1:<5} {pl:<62} {sl:<62}")

    sys.exit(0 if parity_ok else 1)


def run_single(mode: str, user_story: str, conditions: str, base_url: str, run_tests: bool = False) -> None:
    """Run in single mode (pom or standard)."""
    pom_mode = mode == "pom"
    label = "POM" if pom_mode else "Standard"

    print("=" * 70)
    print(f"{label} MODE PIPELINE")
    print("=" * 70)

    client = LLMClient()
    gen = TestGenerator(client=client, model_name=client.model)

    result = asyncio.run(run_pipeline(
        user_story=user_story, conditions=conditions,
        base_url=base_url, pom_mode=pom_mode,
        client=client, generator=gen, run_tests=run_tests,
    ))

    print(f"\n  {label} Pipeline Complete")
    print(f"  Tests: {result['journeys']}")
    print(f"  Page objects: {result['page_objects']}")
    print(f"  Resolution rate: {result['resolution_rate']}")
    print(f"  Test results: {result['test_results']['passed']} passed, "
          f"{result['test_results']['failed']} failed, "
          f"{result['test_results']['skipped']} skipped")
    print(f"  Package: {result['pkg']}")
    print(f"  Output preview:\n{result['code'][:500]}")


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Unified pipeline runner for POM and Standard modes",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    ap.add_argument("--mode", choices=["pom", "standard", "compare"], default="compare",
                    help="Pipeline mode to run (default: compare)")
    ap.add_argument("--url", default=DEFAULT_URL, help=f"Base URL (default: {DEFAULT_URL})")
    ap.add_argument("--story", default=DEFAULT_STORY, help="User story text")
    ap.add_argument("--conditions", default=DEFAULT_CONDITIONS, help="Acceptance criteria")
    ap.add_argument("--run-tests", action="store_true",
                    help="Also execute generated tests via pytest (slow — interacts with live site)")
    args = ap.parse_args()

    run_tests = args.run_tests
    if args.mode == "compare":
        run_compare(args.story, args.conditions, args.url, run_tests=run_tests)
    else:
        run_single(args.mode, args.story, args.conditions, args.url, run_tests=run_tests)


if __name__ == "__main__":
    main()
