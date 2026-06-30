#!/usr/bin/env python
"""Multi-run skeleton variability analyzer.

Runs the skeleton-generation phase multiple times with identical inputs
and compares token-level differences between runs to identify which
steps are included/omitted inconsistently.

Usage:
    python -m scripts.debug.debug_skeleton_variability --runs 5 --provider lm-studio
"""

from __future__ import annotations

import argparse
import asyncio
import re
from collections import Counter
from dataclasses import dataclass, field
from difflib import unified_diff
from pathlib import Path

from src.llm_client import LLMClient
from src.pipeline_models import TestJourney
from src.skeleton_parser import SkeletonParser

# ── Token extraction helpers ──────────────────────────────────────────────

_TOKEN_RE = re.compile(
    r"\{\{?(\w+):[^}]+?\}?\}?"  # matches both {{TYPE:desc}} and {TYPE:desc}
)


@dataclass
class RunResult:
    """Holds the raw and parsed output of a single skeleton run."""

    run_index: int
    raw: str
    skeletons: list[TestJourney]
    raw_skeleton_code: str  # the raw LLM output (for token extraction)
    tokens: list[str]  # flattened, ordered
    per_skeleton_tokens: list[list[str]]
    pages_needed: set[str]
    errors: list[str] = field(default_factory=list)


def extract_tokens(text: str) -> list[str]:
    return _TOKEN_RE.findall(text)


def extract_pages_needed(text: str) -> set[str]:
    """Extract page keywords from the PAGES_NEEDED block."""
    pages: set[str] = set()
    in_block = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# PAGES_NEEDED"):
            in_block = True
            continue
        if in_block:
            if stripped.startswith("# - "):
                page = re.sub(r"\s*\(.*\)", "", stripped.split("# - ", 1)[1]).strip()
                pages.add(page)
            elif not stripped.startswith("#"):
                break
    return pages


def format_token_summary(tokens: list[str]) -> str:
    """Format token list with counts grouped by type."""
    by_type: dict[str, list[str]] = {}
    for t in tokens:
        type_, _, desc = t.partition(":")
        by_type.setdefault(type_, []).append(t)
    lines = [f"{'Type':<10} {'Count':>5}  Tokens:"]
    for typ in sorted(by_type):
        for token in by_type[typ]:
            lines.append(f"{typ:<10} {len(by_type[typ]):>5}  {token}")
    return "\n".join(lines)


# ── Comparison helpers ────────────────────────────────────────────────────


def find_missing_tokens(all_tokens: list[list[str]]) -> list[dict[str, str]]:
    """Find tokens that are missing in some runs but present in others."""
    token_presence: dict[str, int] = Counter()
    for tokens in all_tokens:
        for t in set(tokens):
            token_presence[t] += 1

    total_runs = len(all_tokens)
    inconsistent = []
    for token, count in sorted(token_presence.items(), key=lambda x: x[1]):
        if 0 < count < total_runs:
            inconsistent.append(
                {
                    "token": token,
                    "present_in": count,
                    "total_runs": total_runs,
                    "pct": f"{count / total_runs * 100:.0f}%",
                }
            )
    return inconsistent


def find_missing_steps(all_per_skeleton_tokens: list[list[list[str]]]) -> list[dict[str, str]]:
    """Find skeleton functions that are sometimes generated and sometimes omitted."""
    all_skeleton_signatures: list[set[str]] = []
    for per_run in all_per_skeleton_tokens:
        signatures = set()
        for skel_tokens in per_run:
            sig = " + ".join(sorted(set(skel_tokens)))
            signatures.add(sig)
        all_skeleton_signatures.append(signatures)

    union = set().union(*all_skeleton_signatures) if all_skeleton_signatures else set()
    inconsistent = []
    for sig in sorted(union):
        count = sum(1 for s in all_skeleton_signatures if sig in s)
        if 0 < count < len(all_skeleton_signatures):
            inconsistent.append(
                {
                    "signature": sig[:80] + "..." if len(sig) > 80 else sig,
                    "present_in": count,
                    "total_runs": len(all_skeleton_signatures),
                    "pct": f"{count / len(all_skeleton_signatures) * 100:.0f}%",
                }
            )
    return inconsistent


def diff_raw_skeletons(runs: list[RunResult]) -> str:
    """Produce unified diff between first and last run raw output."""
    if len(runs) < 2:
        return "Need at least 2 runs for diff."
    first = runs[0].raw
    last = runs[-1].raw
    diff = list(
        unified_diff(
            first.splitlines(),
            last.splitlines(),
            fromfile=f"run_{runs[0].run_index}",
            tofile=f"run_{runs[-1].run_index}",
            lineterm="",
        )
    )
    return "\n".join(diff[:100]) + ("\n...\n" if len(diff) > 100 else "")


# ── Main orchestration ───────────────────────────────────────────────────


async def run_skeleton_generation(
    client: LLMClient,
    prompt: str,
    runs: int = 5,
) -> list[RunResult]:
    results: list[RunResult] = []
    parser = SkeletonParser()

    for i in range(1, runs + 1):
        print(f"\n{'=' * 60}")
        print(f"Run {i}/{runs}")
        print(f"{'=' * 60}")

        try:
            raw = await client.generate(prompt)
            if not raw:
                results.append(
                    RunResult(
                        run_index=i,
                        raw="",
                        skeletons=[],
                        raw_skeleton_code="",
                        tokens=[],
                        per_skeleton_tokens=[],
                        pages_needed=set(),
                        errors=["Empty response from LLM"],
                    )
                )
                continue

            skeletons = parser.parse_test_journeys(raw)
            # Extract tokens from the raw LLM output (contains {{TYPE:desc}} markers)
            all_tokens = extract_tokens(raw)
            # Extract tokens per skeleton by matching test function name boundaries
            per_skel_tokens: list[list[str]] = []
            for journey in skeletons:
                # Find the test function code segment and extract its tokens
                func_tokens = []
                for step in journey.steps:
                    for ph in step.placeholders:
                        token_str = f"{ph.action}:{ph.description}"
                        if token_str not in func_tokens:
                            func_tokens.append(token_str)
                per_skel_tokens.append(func_tokens)
            pages = extract_pages_needed(raw)

            print(f"  → {len(skeletons)} skeleton(s), {len(all_tokens)} token(s)")
            print(f"  → PAGES_NEEDED: {pages or '(none)'}")

            results.append(
                RunResult(
                    run_index=i,
                    raw=raw,
                    skeletons=skeletons,
                    raw_skeleton_code=raw,
                    tokens=all_tokens,
                    per_skeleton_tokens=per_skel_tokens,
                    pages_needed=pages,
                )
            )
        except Exception as exc:
            print(f"  → ERROR: {exc}")
            results.append(
                RunResult(
                    run_index=i,
                    raw="",
                    skeletons=[],
                    raw_skeleton_code="",
                    tokens=[],
                    per_skeleton_tokens=[],
                    pages_needed=set(),
                    errors=[str(exc)],
                )
            )

    return results


def print_analysis(runs: list[RunResult], output_path: str | None = None) -> None:
    """Print consolidated analysis."""
    valid = [r for r in runs if not r.errors]
    if not valid:
        print("\n❌ No valid runs — cannot analyze.")
        return

    print("\n" + "=" * 70)
    print("SKELETON VARIABILITY ANALYSIS")
    print("=" * 70)

    # ── Per-run summary ──
    print("\n── Per-Run Summary ──")
    for r in runs:
        status = "✅" if not r.errors else "❌"
        names = [s.test_name for s in r.skeletons] if r.skeletons else ["(none)"]
        print(
            f"  {status} Run {r.run_index}: {len(r.skeletons)} skeleton(s), "
            f"{len(r.tokens)} token(s), "
            f"names={names}, "
            f"pages={r.pages_needed or '∅'}"
        )

    # ── Token consistency ──
    print("\n── Token Consistency ──")
    inconsistent_tokens = find_missing_tokens([r.tokens for r in valid])
    if inconsistent_tokens:
        print(f"  Found {len(inconsistent_tokens)} token(s) present in some runs but not all:")
        for item in inconsistent_tokens:
            print(f"    [{item['pct']}] {item['token']} (in {item['present_in']}/{item['total_runs']} runs)")
    else:
        print("  All tokens identical across runs.")

    # ── PAGES_NEEDED consistency ──
    print("\n── PAGES_NEEDED Consistency ──")
    all_pages_sets = [r.pages_needed for r in valid]
    union_pages = set().union(*all_pages_sets) if all_pages_sets else set()
    for page in sorted(union_pages):
        count = sum(1 for p in all_pages_sets if page in p)
        marker = "✅" if count == len(valid) else "⚠️"
        print(f"  {marker} '{page}': {count}/{len(valid)} runs")

    # ── Skeleton count variance ──
    print("\n── Skeleton Count Variance ──")
    counts = [len(r.skeletons) for r in valid]
    if min(counts) == max(counts):
        print(f"  Stable: always {counts[0]} skeleton(s)")
    else:
        print(f"  Varies: min={min(counts)}, max={max(counts)}, values={counts}")

    # ── Raw diff (first vs last) ──
    print(f"\n── Raw Diff (Run 1 vs Run {valid[-1].run_index if len(valid) > 1 else 1}) ──")
    if len(valid) > 1:
        diff = diff_raw_skeletons(valid)
        print(diff[:1500])
    else:
        print("  Only 1 valid run — no diff.")

    # ── Per-run token inventory ──
    print("\n── Per-Run Token Inventory ──")
    for r in valid:
        print(f"\n  Run {r.run_index}:")
        print("  " + format_token_summary(r.tokens).replace("\n", "\n  "))

    # ── Save report ──
    if output_path:
        report_lines = [
            "#" + "=" * 68,
            f"# Skeleton Variability Report — {len(valid)} valid runs",
            "#" + "=" * 68,
            "",
        ]
        for r in valid:
            report_lines.append(f"## Run {r.run_index}")
            report_lines.append(f"Skeletons: {len(r.skeletons)}, Tokens: {len(r.tokens)}")
            report_lines.append(f"PAGES_NEEDED: {r.pages_needed or '(none)'}")
            report_lines.append("")
            if r.skeletons:
                report_lines.append("Test functions:")
                for s in r.skeletons:
                    report_lines.append(f"  - {s.test_name} ({len(s.steps)} steps)")
            report_lines.append("")
            report_lines.append("Tokens:")
            for t in r.tokens:
                report_lines.append(f"  - {t}")
            report_lines.append("")
            report_lines.append("Raw skeleton:")
            report_lines.append(r.raw_skeleton_code)
            report_lines.append("")

        Path(output_path).write_text("\n".join(report_lines), encoding="utf-8")
        print(f"\n📄 Full report saved to {output_path}")


# ── CLI entry point ──────────────────────────────────────────────────────


def build_prompt(user_story: str, conditions: str, target_urls: list[str]) -> str:
    """Build the exact same prompt the orchestrator uses."""
    from src.prompt_utils import get_skeleton_prompt_template

    known_urls_block = "\n".join(f"- {url}" for url in target_urls) if target_urls else "- No URLs were supplied."
    count_label_upper = "N"
    expected_count = None

    return get_skeleton_prompt_template(expected_count=expected_count).format(
        user_story=user_story,
        conditions=conditions,
        known_urls_block=known_urls_block,
        count_label_upper=count_label_upper,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Skeleton variability analyzer")
    parser.add_argument("--runs", type=int, default=5, help="Number of runs to compare")
    parser.add_argument("--provider", type=str, default="lm-studio")
    parser.add_argument("--model", type=str, default=None)
    parser.add_argument("--url", type=str, default="https://www.saucedemo.com", help="Target URL")
    parser.add_argument(
        "--story",
        type=str,
        default=(
            "As a shopper, I want to browse products, add items to my cart, "
            "and complete checkout so that I can purchase products online."
        ),
    )
    parser.add_argument(
        "--conditions",
        type=str,
        default=(
            "1. Navigate to the saucedemo homepage\n"
            "2. Log in with valid credentials\n"
            "3. Add a product to the cart\n"
            "4. Click the cart link to view the cart page\n"
            "5. Click 'Continue Shopping' to return to products\n"
            "6. Proceed through checkout and verify order confirmation"
        ),
    )
    parser.add_argument("--output", type=str, default=None, help="Save report to file")

    args = parser.parse_args()

    print("Skeleton Variability Analyzer")
    print(f"  Runs:     {args.runs}")
    print(f"  Provider: {args.provider}")
    print(f"  URL:      {args.url}")
    print(f"  Story:    {args.story[:80]}...")

    prompt = build_prompt(args.story, args.conditions, [args.url])

    client = LLMClient(
        provider_name=args.provider,
        model=args.model,
    )

    async def _run():
        results = await run_skeleton_generation(client, prompt, runs=args.runs)
        print_analysis(results, output_path=args.output)

    asyncio.run(_run())


if __name__ == "__main__":
    main()
