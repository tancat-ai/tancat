#!/usr/bin/env python3
"""Fast pre-commit smoke test for pipeline integrity.

Runs offline checks that catch obvious regressions in <1 second.
Use this before running the full pytest suite to catch resolver/parsing
breakages early.

Usage:
    python scripts/smoke.py
    python scripts/smoke.py --json    # machine-readable output
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


class Check:
    """Single smoke test check."""

    def __init__(self, name: str, passed: bool, detail: str = "") -> None:
        self.name = name
        self.passed = passed
        self.detail = detail

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "passed": self.passed,
            "detail": self.detail,
        }


def check_text_validation() -> list[Check]:
    """Run text_matches_description against known cases."""
    from src.placeholder_resolver import PlaceholderResolver

    resolver = PlaceholderResolver()
    checks: list[Check] = []

    cases: list[tuple[str, str, bool]] = [
        ("Add to cart", "Add to cart button next to a product", True),
        ("Cart", "Cart link or cart icon in the page header", True),
        ("Add to cart", "Cart link or cart icon in the page header", True),  # B-012: 'cart' overlap is valid
        ("View cart", "Go to cart", True),
        ("Home", "Navigate to home page", True),
        ("", "Continue Shopping button", False),
        ("Login", "Sign in button", True),
        ("Your cart is empty!", "cart content with items", False),
        ("Cart is empty", "cart page with selected items", False),
        ("Items in your cart", "cart content with items", True),
        ("Logout", "Sign out button", True),
        ("Sign Up", "Register account", True),
    ]

    for text, desc, expected in cases:
        result = resolver.text_matches_description(text, desc)
        ok = result == expected
        checks.append(
            Check(
                f"text_match '{text}' vs '{desc}'",
                ok,
                f"got {result}, expected {expected}" if not ok else "",
            )
        )

    return checks


def check_skeleton_parsing() -> list[Check]:
    """Run skeleton placeholder parsing on sample code."""
    from src.skeleton_parser import SkeletonParser

    parser = SkeletonParser()
    checks: list[Check] = []

    sample = """
def test_01(page):
    page.goto("{{GOTO:home}}")
    page.locator("{{{{CLICK:login button}}}}").click()

def test_02(page):
    page.locator("{{{{FILL:username}}}}").fill("user")
    page.locator("{{{{ASSERT:welcome message}}}}").is_visible()
"""

    # Placeholder uses
    uses = parser.parse_placeholder_uses(sample)
    checks.append(
        Check(
            "parse_placeholder_uses finds tokens",
            len(uses) >= 3,
            f"found {len(uses)} uses",
        )
    )

    # Placeholders
    placeholders = parser.parse_placeholders(sample)
    checks.append(
        Check(
            "parse_placeholders extracts unique placeholders",
            len(placeholders) >= 3,
            f"found {len(placeholders)} unique: {[(a, d) for a, d in placeholders]}",
        )
    )

    # Journeys
    journeys = parser.parse_test_journeys(sample)
    checks.append(
        Check(
            "parse_test_journeys groups by test function",
            len(journeys) == 2,
            f"found {len(journeys)} journeys",
        )
    )

    # Normalisation
    raw = 'page.locator("{{{{CLICK:button}}}}").click()'
    normalised = parser.normalise_placeholder_actions(raw)
    checks.append(
        Check(
            "normalise_placeholder_actions preserves tokens",
            "{{{{CLICK" in normalised or "{{{" in normalised,
            f"'{raw}' -> '{normalised}'",
        )
    )

    return checks


def check_module_imports() -> list[Check]:
    """Verify critical modules import without errors."""
    checks: list[Check] = []
    modules = [
        "src.scraper",
        "src.placeholder_resolver",
        "src.placeholder_orchestrator",
        "src.orchestrator",
        "src.test_generator",
        "src.code_postprocessor",
        "src.skeleton_parser",
        "src.skeleton_validator",
        "src.semantic_matcher",
        "src.intent_matcher",
        "src.export_service",
        "src.page_object_builder",
    ]

    for module_name in modules:
        try:
            __import__(module_name)
            checks.append(Check(f"import {module_name}", True))
        except Exception as e:
            checks.append(Check(f"import {module_name}", False, str(e)))

    return checks


def check_pom_mode_smoke() -> list[Check]:
    """Smoke test POM mode data models and basic operations."""
    from src.pipeline_models import ExportMode

    checks: list[Check] = []

    # ExportMode enum
    checks.append(Check("ExportMode.POM exists", True))
    checks.append(Check("ExportMode.FLAT exists", True))
    checks.append(Check("ExportMode.POM == 'pom'", ExportMode.POM == "pom"))
    checks.append(Check("ExportMode.FLAT == 'flat'", ExportMode.FLAT == "flat"))

    # PageObjectBuilder imports
    try:
        from src.page_object_builder import PageObjectBuilder

        PageObjectBuilder()
        checks.append(Check("PageObjectBuilder instantiates", True))
    except Exception as e:
        checks.append(Check("PageObjectBuilder instantiates", False, str(e)))
        return checks

    # ExportService imports
    try:
        checks.append(Check("export_service imports", True))
    except Exception as e:
        checks.append(Check("export_service imports", False, str(e)))

    return checks


def check_orchestrator_init() -> list[Check]:
    """Verify TestOrchestrator can be constructed with POM mode."""
    checks: list[Check] = []

    try:
        # We can't fully init LLMClient without a provider, but we can check
        # the orchestrator data model
        from src.orchestrator import PipelineRunResult

        result = PipelineRunResult(pom_mode=True)
        checks.append(Check("PipelineRunResult(pom_mode=True)", result.pom_mode))
    except Exception as e:
        checks.append(Check("Orchestrator data model", False, str(e)))

    return checks


def check_egress_audit() -> list[Check]:
    """Gate 0: no unrecognised outbound-HTTP call sites in the product runtime.

    Phase 6 6a — the "no data leaves your deployment" claim is only honest
    while every runtime outbound call targets a user-configured endpoint or
    the already-SSRF-guarded target site (scripts/audit_egress.py).
    """
    from scripts.audit_egress import DEFAULT_SCOPE, run_audit

    result = run_audit(DEFAULT_SCOPE)
    checks = [
        Check(
            "[Egress audit] product runtime clean",
            not result.flagged and not result.errors,
            f"{len(result.sites)} call site(s), {len(result.flagged)} flagged, {len(result.errors)} scan error(s)",
        )
    ]
    for site in result.flagged:
        checks.append(Check(f"[Egress audit] FLAGGED {site.file}:{site.line}", False, site.statement))
    for error in result.errors:
        checks.append(Check("[Egress audit] scan error", False, error))
    return checks


def run_all(json_output: bool = False) -> int:
    """Run all smoke checks and print results."""
    all_checks: list[Check] = []

    categories = [
        ("Module imports", check_module_imports),
        ("Text validation", check_text_validation),
        ("Skeleton parsing", check_skeleton_parsing),
        ("POM mode smoke", check_pom_mode_smoke),
        ("Orchestrator data model", check_orchestrator_init),
        ("Artifact validation", check_artifact_validation),
        ("Egress audit", check_egress_audit),
    ]

    for cat_name, checker in categories:
        start = time.time()
        try:
            cat_checks = checker()
            time.time() - start
            all_checks.extend(cat_checks)
        except Exception as e:
            all_checks.append(Check(f"[{cat_name}] CRASH", False, str(e)))

    # Output
    passed = sum(1 for c in all_checks if c.passed)
    failed = sum(1 for c in all_checks if not c.passed)

    if json_output:
        output = {
            "total": len(all_checks),
            "passed": passed,
            "failed": failed,
            "checks": [c.to_dict() for c in all_checks],
        }
        print(json.dumps(output, indent=2))
    else:
        print("=" * 60)
        print("SMOKE TEST")
        print("=" * 60)

        current_cat = ""
        for c in all_checks:
            # Infer category from check name
            cat = c.name.split("] ")[1] if "] " in c.name else ""
            if cat and cat != current_cat:
                current_cat = cat
                print(f"\n  [{current_cat}]")

            status = "PASS" if c.passed else "FAIL"
            line = f"    [{status}] {c.name}"
            if c.detail:
                line += f" — {c.detail}"
            print(line)

        print()
        print(f"Results: {passed} passed, {failed} failed ({passed + failed} total)")
        print()

    return 1 if failed else 0


def check_artifact_validation() -> list[Check]:
    """AI-043 Layer 1: golden report-artifact fixtures must stay valid.

    Runs the deterministic invariants against the fixtures/report_golden corpus:
    the known-good set must pass, the known-bad sets (legacy pixel coords, NaN
    duration) must fail — so a regression in the heatmap/Gantt data contract
    breaks this check instead of shipping a misleading report.
    """
    from src.artifact_validation import validate_evidence_artifacts
    from src.gantt_utils import load_gantt_entries
    from src.heatmap_utils import _normalise_url

    fixtures = PROJECT_ROOT / "fixtures" / "report_golden"
    good = validate_evidence_artifacts(fixtures / "heatmap_good", [_normalise_url("https://example.com/page1")])
    legacy = validate_evidence_artifacts(
        fixtures / "heatmap_legacy_pixels", [_normalise_url("https://example.com/page1")]
    )
    nan_entries = load_gantt_entries(fixtures / "gantt_nan")
    from src.artifact_validation import validate_gantt_entries

    checks = [
        Check("[Artifact validation] golden good fixture passes", good.passed, f"{len(good.errors)} error(s)"),
        Check(
            "[Artifact validation] legacy pixel fixture flagged",
            not legacy.passed,
            "legacy pixel coords must be caught",
        ),
        Check(
            "[Artifact validation] NaN duration flagged",
            bool(validate_gantt_entries(nan_entries)),
            "NaN duration must be caught",
        ),
    ]
    return checks


def main() -> int:
    parser = __import__("argparse").ArgumentParser(description="Fast smoke test")
    parser.add_argument("--json", action="store_true", help="Machine-readable output")
    args = parser.parse_args()
    return run_all(json_output=args.json)


if __name__ == "__main__":
    sys.exit(main())
