#!/usr/bin/env python3
"""Debug comparison runner — executes key debug scripts and compares results.

Runs multiple debug scenarios and collects pass/fail patterns across:
  1. Text validation (offline — no LLM needed)
  2. Skeleton inspection (offline — no LLM needed)
  3. Placeholder resolution (scraping only — no LLM needed)
  4. Full pipeline (requires LLM)
  5. SauceDemo login + resolution (scraping only)
  6. SauceDemo scraping (scraping only)
  7. Scoring debug (scraping only)

Dynamic LLM provider support:
  --provider  auto|ollama|lm-studio|openai|openai-local
  --base-url  Provider base URL
  --model     Model name

When --provider is "auto", the script probes local services and falls back
to openai-local (OpenAI-compatible local server on common ports).

Usage:
    python scripts/debug/debug_compare.py
    python scripts/debug/debug_compare.py --provider ollama --model qwen3.5:9b
    python scripts/debug/debug_compare.py --provider openai-local --base-url http://localhost:8080/v1
    python scripts/debug/debug_compare.py --provider lm-studio
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

# Ensure project root is on sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv  # noqa: E402

# ---------------------------------------------------------------------------
# Result tracking
# ---------------------------------------------------------------------------

@dataclass
class TestResult:
    """Single test/check result."""
    category: str
    name: str
    passed: bool
    details: str = ""
    duration: float = 0.0


@dataclass
class SuiteResult:
    """Collection of results for one category."""
    category: str
    results: list[TestResult] = field(default_factory=list)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.results if not r.passed)

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def rate(self) -> str:
        if not self.results:
            return "N/A"
        return f"{self.passed}/{self.total} ({self.passed/self.total*100:.0f}%)"


# ---------------------------------------------------------------------------
# Phase 1: Text Validation (offline)
# ---------------------------------------------------------------------------

def run_text_validation() -> SuiteResult:
    """Run text_matches_description validation — no LLM needed."""
    from src.placeholder_resolver import PlaceholderResolver

    suite = SuiteResult(category="Text Validation")
    resolver = PlaceholderResolver()

    test_cases = [
        ("Add to cart", "Add to cart button next to a product", True),
        ("Cart", "Cart link or cart icon in the page header", True),
        ("Continue Shopping", "Continue Shopping button", True),
        ("Add to cart", "Cart link or cart icon in the page header", False),
        ("Subscribe", "Continue Shopping button", False),
        ("View cart", "Go to cart", True),
        ("Checkout", "Proceed to checkout", True),
        ("Home", "Navigate to home page", True),
        ("", "Continue Shopping button", False),
        ("Login", "Sign in button", True),
        ("Dress", "product category link", True),
        ("Blue Top", "a product name", True),
        ("Your cart is empty!", "cart content with items", False),
        ("Cart is empty", "cart page with selected items", False),
        ("Items in your cart", "cart content with items", True),
    ]

    for element_text, description, expected in test_cases:
        start = time.time()
        result = resolver.text_matches_description(element_text, description)
        passed = result == expected
        duration = time.time() - start
        details = f"got {result}, expected {expected}"
        suite.results.append(TestResult(
            category="Text Validation",
            name=f"'{element_text}' vs '{description}'",
            passed=passed,
            details=details,
            duration=duration,
        ))
    return suite


# ---------------------------------------------------------------------------
# Phase 2: Skeleton Inspection (offline)
# ---------------------------------------------------------------------------

def run_skeleton_inspection() -> SuiteResult:
    """Run skeleton placeholder extraction — no LLM needed."""
    from src.skeleton_parser import SkeletonParser

    suite = SuiteResult(category="Skeleton Inspection")
    parser = SkeletonParser()

    sample = """
def test_01_browse(page):
    page.goto("{{GOTO:home page}}")
    page.locator("{{{{CLICK:product category link}}}}").click()

def test_02_add_to_cart(page):
    page.locator("{{{{FILL:search bar}}}}").fill("dress")
    page.locator("{{{{CLICK:search button}}}}").click()
    page.locator("{{{{ASSERT:product listing}}}}").is_visible()

def test_03_view_cart(page):
    page.locator("{{{{CLICK:Cart link}}}}").click()
    page.locator("{{{{ASSERT:cart contents}}}}").is_visible()
"""

    # Test placeholder parsing
    placeholders = parser.parse_placeholders(sample)
    # Actually GOTO is single-brace, so parse_placeholders catches double-brace ones
    suite.results.append(TestResult(
        category="Skeleton Inspection",
        name=f"parse_placeholders found {len(placeholders)} (expected >= 5)",
        passed=len(placeholders) >= 5,
        details=f"found {len(placeholders)}: {[(a, d) for a, d in placeholders]}",
    ))

    # Test journey parsing
    journeys = parser.parse_test_journeys(sample)
    suite.results.append(TestResult(
        category="Skeleton Inspection",
        name=f"parse_test_journeys found {len(journeys)} (expected 3)",
        passed=len(journeys) == 3,
        details=f"journeys: {[j.test_name for j in journeys]}",
    ))

    # Test normalise_placeholder_actions
    raw = 'page.locator("{{{{CLICK:product link}}}}").click()'
    normalised = parser.normalise_placeholder_actions(raw)
    suite.results.append(TestResult(
        category="Skeleton Inspection",
        name="normalise_placeholder_actions preserves valid tokens",
        passed="{{{{CLICK" in normalised or "{{{" in normalised,
        details=f"input: {raw!r} -> output: {normalised!r}",
    ))

    # Test placeholder action extraction
    actions = {a for a, _ in placeholders}
    expected_actions = {"CLICK", "FILL", "ASSERT"}
    suite.results.append(TestResult(
        category="Skeleton Inspection",
        name=f"Placeholder actions: {actions}",
        passed=expected_actions.issubset(actions),
        details=f"expected {expected_actions} subset of {actions}",
    ))

    return suite


# ---------------------------------------------------------------------------
# Phase 3: Placeholder Resolution (scraping only, no LLM)
# ---------------------------------------------------------------------------

async def run_placeholder_resolution(url: str) -> SuiteResult:
    """Run placeholder resolution against a real URL — scraping only."""
    from src.placeholder_resolver import PlaceholderResolver
    from src.scraper import PageScraper

    suite = SuiteResult(category=f"Placeholder Resolution ({url})")
    scraper = PageScraper()
    resolver = PlaceholderResolver()

    # Scrape
    start = time.time()
    elements, error, final_url = await scraper.scrape_url(url)
    scrape_duration = time.time() - start

    suite.results.append(TestResult(
        category="Placeholder Resolution",
        name="Scrape succeeded",
        passed=error is None and len(elements) > 0,
        details=f"{len(elements)} elements, error={error}, duration={scrape_duration:.1f}s",
    ))

    # Define test placeholders
    placeholders = [
        ("GOTO", "home page"),
        ("CLICK", "product category link"),
        ("CLICK", "Add to cart button"),
        ("ASSERT", "cart content"),
        ("CLICK", "Cart link"),
        ("FILL", "username field"),
        ("FILL", "password field"),
        ("CLICK", "login button"),
        ("ASSERT", "login success"),
        ("CLICK", "search button"),
        ("FILL", "search bar"),
    ]

    # Try to resolve each
    for action, description in placeholders:
        start = time.time()

        ranked = resolver.rank_candidates(action, description, elements)
        duration = time.time() - start

        # Check if top candidate has meaningful score
        if ranked:
            top_score = ranked[0][0]
            top_text = str(ranked[0][1].get("text", ""))[:40]
            top_sel = str(ranked[0][1].get("selector", ""))[:50]
            details = f"score={top_score}, text='{top_text}', selector='{top_sel}'"
            # Score > 0 means something matched
            passed = top_score > 0
        else:
            details = "no candidates ranked"
            passed = False

        suite.results.append(TestResult(
            category="Placeholder Resolution",
            name=f"({action}) '{description}'",
            passed=passed,
            details=details,
            duration=duration,
        ))

    return suite


# ---------------------------------------------------------------------------
# Phase 4: SauceDemo Login + Resolution (scraping only)
# ---------------------------------------------------------------------------

def _saucedemo_sync_scrape() -> list:
    """Run SauceDemo login + scrape in a sync context (called via asyncio.to_thread)."""
    from playwright.sync_api import sync_playwright

    from src.scraper import PageScraper

    scraper = PageScraper()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        )
        page = context.new_page()

        page.goto("https://www.saucedemo.com", wait_until="networkidle")
        page.fill("#user-name", "standard_user")
        page.fill("#password", "secret_sauce")
        page.click("#login-button")
        page.wait_for_load_state("networkidle")

        html = page.content()
        elements = scraper._extract_elements_from_html(html, base_url=page.url)
        browser.close()
    return elements


async def run_saucedemo_resolution() -> SuiteResult:
    """Login to SauceDemo, scrape inventory, test resolution."""
    from src.placeholder_resolver import PlaceholderResolver

    suite = SuiteResult(category="SauceDemo Login + Resolution")
    resolver = PlaceholderResolver()

    elements = []
    try:
        # Run sync Playwright off the event loop
        elements = await asyncio.to_thread(_saucedemo_sync_scrape)

        suite.results.append(TestResult(
            category="SauceDemo",
            name="Login + scrape succeeded",
            passed=len(elements) > 0,
            details=f"{len(elements)} elements on inventory page",
        ))

        # Test resolution for key SauceDemo placeholders
        test_placeholders = [
            ("CLICK", "add to cart button for Sauce Labs Backpack"),
            ("CLICK", "add to cart button"),
            ("CLICK", "shopping cart icon"),
            ("CLICK", "cart icon"),
            ("ASSERT", "inventory page visible"),
            ("CLICK", "shopping cart"),
        ]

        for action, description in test_placeholders:
            ranked = resolver.rank_candidates(action, description, elements)
            if ranked and ranked[0][0] > 0:
                top_text = str(ranked[0][1].get("text", ""))[:40]
                details = f"score={ranked[0][0]}, text='{top_text}'"
                passed = True
            else:
                details = "no good match"
                passed = False

            suite.results.append(TestResult(
                category="SauceDemo",
                name=f"({action}) '{description}'",
                passed=passed,
                details=details,
            ))

        # Check for cart-related elements
        cart_terms = ["cart", "basket", "bag", "shopping", "badge", "checkout"]
        cart_elements = [
            e for e in elements
            if any(
                term in (
                    str(e.get("text", ""))
                    + str(e.get("selector", ""))
                    + str(e.get("id", ""))
                    + str(e.get("classes", ""))
                    + str(e.get("aria_label", ""))
                ).lower()
                for term in cart_terms
            )
        ]
        suite.results.append(TestResult(
            category="SauceDemo",
            name="Cart-related elements found",
            passed=len(cart_elements) > 0,
            details=f"{len(cart_elements)} cart-related elements",
        ))

    except Exception as e:
        suite.results.append(TestResult(
            category="SauceDemo",
            name="Login + scrape",
            passed=False,
            details=f"Exception: {e}",
        ))

    return suite


# ---------------------------------------------------------------------------
# Phase 5: Full Pipeline (requires LLM)
# ---------------------------------------------------------------------------

async def run_full_pipeline(
    url: str,
    user_story: str,
    conditions: str,
    provider: str | None = None,
    model: str | None = None,
    base_url: str | None = None,
) -> SuiteResult:
    """Run the full skeleton-first pipeline."""
    from src.llm_client import LLMClient
    from src.orchestrator import TestOrchestrator
    from src.test_generator import TestGenerator

    suite = SuiteResult(category=f"Full Pipeline ({url})")

    # Configure provider
    if provider:
        LLMClient.set_session_provider(provider, base_url=base_url, model=model)

    try:
        client = LLMClient()
        suite.results.append(TestResult(
            category="Full Pipeline",
            name=f"LLMClient configured: {client.provider_name} / {client.model}",
            passed=True,
            details=f"base_url={client.base_url}",
        ))
    except Exception as e:
        suite.results.append(TestResult(
            category="Full Pipeline",
            name="LLMClient configuration",
            passed=False,
            details=f"Exception: {e}",
        ))
        return suite

    generator = TestGenerator(client=client)
    orchestrator = TestOrchestrator(generator)

    # Phase 1: Skeleton generation
    try:
        start = time.time()
        skeleton = await generator.generate_skeleton(
            user_story, conditions, target_urls=[url], expected_count=3,
        )
        duration = time.time() - start
        suite.results.append(TestResult(
            category="Full Pipeline",
            name="Skeleton generation",
            passed=len(skeleton) > 50,
            details=f"{len(skeleton)} chars, {duration:.1f}s",
        ))

        # Check for placeholder tokens — LLM outputs single-brace {ACTION:desc}
        # which normalise_placeholder_actions converts to double-brace {{ACTION:desc}}
        raw_ph_tokens = re.findall(r"\{([A-Z_]+):[^}]+\}", skeleton)
        # After normalisation
        normalised = parser.normalise_placeholder_actions(skeleton) if (parser := __import__("src.skeleton_parser", fromlist=["SkeletonParser"]).SkeletonParser()) else skeleton
        double_ph_tokens = re.findall(r"\{\{(CLICK|FILL|GOTO|URL|ASSERT):[^}]+\}\}", normalised)
        suite.results.append(TestResult(
            category="Full Pipeline",
            name=f"Skeleton contains placeholders ({len(raw_ph_tokens)} raw -> {len(double_ph_tokens)} normalised)",
            passed=len(double_ph_tokens) > 0,
            details=f"raw single-brace: {len(raw_ph_tokens)}, normalised double-brace: {len(double_ph_tokens)}",
        ))

        # Check for test functions
        test_funcs = re.findall(r"def test_\w+", skeleton)
        suite.results.append(TestResult(
            category="Full Pipeline",
            name="Skeleton contains test functions",
            passed=len(test_funcs) > 0,
            details=f"{len(test_funcs)} test functions: {test_funcs}",
        ))

        # Record skeleton preview for debugging
        skeleton_preview = "\n".join(skeleton.splitlines()[:15])
        suite.results.append(TestResult(
            category="Full Pipeline",
            name="Skeleton preview (first 15 lines)",
            passed=True,
            details=skeleton_preview,
        ))

    except Exception as e:
        suite.results.append(TestResult(
            category="Full Pipeline",
            name="Skeleton generation",
            passed=False,
            details=f"Exception: {e}",
        ))
        return suite

    # Phase 2: Full pipeline run
    try:
        start = time.time()
        final_code = await orchestrator.run_pipeline(
            user_story=user_story,
            conditions=conditions,
            target_urls=[url],
        )
        duration = time.time() - start
        suite.results.append(TestResult(
            category="Full Pipeline",
            name="Full pipeline execution",
            passed=len(final_code) > 100,
            details=f"{len(final_code)} chars, {duration:.1f}s",
        ))

        result = orchestrator.last_result

        # Check for unresolved placeholders
        unresolved = [l.strip() for l in final_code.splitlines() if "pytest.skip(" in l]
        suite.results.append(TestResult(
            category="Full Pipeline",
            name="No unresolved placeholders",
            passed=len(unresolved) == 0,
            details=f"{len(unresolved)} unresolved (pytest.skip) lines",
        ))

        # Check for placeholder artifacts in final code
        ph_artifacts = re.findall(r"\{\{\{\{(\w+):", final_code)
        suite.results.append(TestResult(
            category="Full Pipeline",
            name="No placeholder artifacts in output",
            passed=len(ph_artifacts) == 0,
            details=f"{len(ph_artifacts)} placeholder tokens remaining",
        ))

        # Check for evidence_tracker calls
        has_evidence = "evidence_tracker." in final_code
        suite.results.append(TestResult(
            category="Full Pipeline",
            name="Evidence tracker calls present",
            passed=has_evidence,
            details="evidence_tracker calls found" if has_evidence else "no evidence_tracker calls",
        ))

        # Check for pytest.mark.evidence
        has_evidence_mark = "@pytest.mark.evidence" in final_code
        suite.results.append(TestResult(
            category="Full Pipeline",
            name="pytest.mark.evidence decorators present",
            passed=has_evidence_mark,
            details="@pytest.mark.evidence found" if has_evidence_mark else "no @pytest.mark.evidence",
        ))

        # Check test count matches criteria
        criteria_count = len(re.findall(r"^\d+\.", conditions, re.M))
        test_count = len(re.findall(r"^def\s+test_\d+", final_code, re.M))
        suite.results.append(TestResult(
            category="Full Pipeline",
            name=f"Test count matches criteria ({test_count} tests, {criteria_count} criteria)",
            passed=test_count >= criteria_count,
            details=f"{test_count} tests vs {criteria_count} criteria",
        ))

        if result:
            suite.results.append(TestResult(
                category="Full Pipeline",
                name=f"Scraped pages: {len(result.scraped_pages)}",
                passed=len(result.scraped_pages) > 0,
                details=f"{len(result.scraped_pages)} pages scraped",
            ))

    except Exception as e:
        suite.results.append(TestResult(
            category="Full Pipeline",
            name="Full pipeline execution",
            passed=False,
            details=f"Exception: {e}",
        ))

    return suite


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def print_results(suites: list[SuiteResult]) -> None:
    """Print formatted results."""
    print("\n" + "=" * 80)
    print("DEBUG COMPARISON RESULTS")
    print("=" * 80)

    all_passed = 0
    all_failed = 0

    for suite in suites:
        print(f"\n{'─' * 80}")
        print(f"  {suite.category.upper()}")
        print(f"  {suite.rate} ({suite.passed} passed, {suite.failed} failed)")
        print(f"{'─' * 80}")

        for r in suite.results:
            status = "✅" if r.passed else "❌"
            dur = f" ({r.duration:.2f}s)" if r.duration > 0.1 else ""
            print(f"  {status} {r.name}{dur}")
            if r.details:
                print(f"     └─ {r.details}")

            all_passed += 1 if r.passed else 0
            all_failed += 1 if not r.passed else 0

    print(f"\n{'═' * 80}")
    print(f"  TOTAL: {all_passed} passed, {all_failed} failed "
          f"({all_passed + all_failed} checks)")
    print(f"{'═' * 80}")

    # Pattern analysis
    if all_failed > 0:
        print("\n🔍 FAILURE PATTERNS:")
        _analyse_failures(suites)


def _analyse_failures(suites: list[SuiteResult]) -> None:
    """Look for patterns in failures."""
    failures = [r for s in suites for r in s.results if not r.passed]
    categories = {}

    for f in failures:
        cat = f.category
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(f)

    for cat, fails in categories.items():
        print(f"\n  [{cat}] {len(fails)} failure(s):")
        # Look for common patterns
        texts = []
        for f in fails:
            # Extract key info
            if "placeholder" in f.name.lower() or "resolution" in f.name.lower():
                texts.append("placeholder resolution")
            elif "cart" in f.name.lower() or "cart" in f.details.lower():
                texts.append("cart-related")
            elif "login" in f.name.lower() or "login" in f.details.lower():
                texts.append("login-related")
            elif "scrape" in f.name.lower():
                texts.append("scraping")
            elif "pipeline" in f.name.lower() or "skeleton" in f.name.lower():
                texts.append("pipeline/LLM")
            else:
                texts.append(f.name.split("'")[0] if "'" in f.name else "other")

        # Count patterns
        from collections import Counter
        pattern_counts = Counter(texts)
        for pattern, count in pattern_counts.most_common(3):
            print(f"    • {pattern}: {count} failure(s)")
            # Show specific failures
            matching = [f for f in fails if pattern in f.name.lower() or pattern in f.details.lower()]
            for m in matching[:3]:
                print(f"      └─ {m.name}: {m.details}")


def save_results(suites: list[SuiteResult], output_path: Path) -> None:
    """Save results as JSON for later comparison."""
    data = {
        "timestamp": datetime.now().isoformat(),
        "suites": [],
    }

    for suite in suites:
        suite_data = {
            "category": suite.category,
            "summary": f"{suite.rate}",
            "results": [
                {
                    "name": r.name,
                    "passed": r.passed,
                    "details": r.details,
                    "duration": r.duration,
                }
                for r in suite.results
            ],
        }
        data["suites"].append(suite_data)

    output_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"\n📋 Results saved to: {output_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Debug comparison runner — execute debug scripts and compare results",
    )
    parser.add_argument(
        "--provider",
        choices=["auto", "ollama", "lm-studio", "openai", "openai-local"],
        default=None,
        help="LLM provider for pipeline tests (default: auto-detect from .env)",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Model name override",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="Provider base URL override",
    )
    parser.add_argument(
        "--site",
        choices=["saucedemo", "automationexercise"],
        default="automationexercise",
        help="Target site for full pipeline test",
    )
    parser.add_argument(
        "--skip-pipeline",
        action="store_true",
        help="Skip full pipeline tests (no LLM needed)",
    )
    parser.add_argument(
        "--skip-saucedemo",
        action="store_true",
        help="Skip SauceDemo login + resolution tests",
    )
    parser.add_argument(
        "--output",
        default=None,
        type=Path,
        help="Save results to JSON file",
    )
    return parser.parse_args()


SITES = {
    "automationexercise": {
        "url": "https://automationexercise.com",
        "user_story": (
            "As a customer, I want to browse products on the website and add them "
            "to my cart so that I can purchase them later."
        ),
        "conditions": (
            "1. Navigate to the home page\n"
            "2. Click a product category link\n"
            "3. Add a product to cart and verify confirmation\n"
            "(Total: 3 criteria)"
        ),
    },
    "saucedemo": {
        "url": "https://www.saucedemo.com",
        "user_story": (
            "As a user, I want to log in, add items to my cart, and checkout."
        ),
        "conditions": (
            "1. Log in with username standard_user and password secret_sauce\n"
            "2. Add an item to the cart\n"
            "3. Verify the item appears in the cart\n"
            "(Total: 3 criteria)"
        ),
    },
}


async def main() -> None:
    args = parse_args()
    load_dotenv()

    site = SITES[args.site]
    suites: list[SuiteResult] = []

    # Phase 1: Text Validation (offline)
    print("\n[1/5] Text Validation (offline)...")
    suites.append(run_text_validation())

    # Phase 2: Skeleton Inspection (offline)
    print("[2/5] Skeleton Inspection (offline)...")
    suites.append(run_skeleton_inspection())

    # Phase 3: Placeholder Resolution (scraping only)
    print(f"[3/5] Placeholder Resolution ({site['url']})...")
    suites.append(await run_placeholder_resolution(site["url"]))

    # Phase 4: SauceDemo Login + Resolution (if not skipped)
    if not args.skip_saucedemo:
        print("[4/5] SauceDemo Login + Resolution...")
        suites.append(await run_saucedemo_resolution())

    # Phase 5: Full Pipeline (requires LLM, skip if requested)
    if not args.skip_pipeline:
        print(f"[5/5] Full Pipeline ({site['url']}) with provider={args.provider or 'auto'}...")
        suites.append(await run_full_pipeline(
            url=site["url"],
            user_story=site["user_story"],
            conditions=site["conditions"],
            provider=args.provider or "openai-local",
            model=args.model,
            base_url=args.base_url,
        ))
    else:
        print("[5/5] Full Pipeline — SKIPPED (--skip-pipeline)")

    # Print results
    print_results(suites)

    # Save if requested
    if args.output:
        save_results(suites, args.output)
    else:
        # Default: save to debug_compare_results.json
        default_output = PROJECT_ROOT / "debug_compare_results.json"
        save_results(suites, default_output)


if __name__ == "__main__":
    configure_windows_console_encoding = None
    try:
        import io as _io
        if sys.platform == "win32":
            sys.stdout = _io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
            sys.stderr = _io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")
    except Exception:
        pass

    asyncio.run(main())
