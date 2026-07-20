"""CLI for evidence search, inspection, rerun, and export (AI-028).

Usage::

    # Search with timestamps
    python -m cli.evidence_cli search --query "cart" --status failed --verbose

    # Inspect a specific result
    python -m cli.evidence_cli search --query "cart" --status failed
    python -m cli.evidence_cli detail 3     # drill into result #3 from last search

    # Rerun matching tests
    python -m cli.evidence_cli search --query "cart" --status failed --rerun

    # Export
    python -m cli.evidence_cli export --format csv --status failed -o evidence.csv
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

from src.evidence_export import export_csv, export_junit_xml, export_ndjson
from src.evidence_index import EvidenceIndex

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _build_index() -> EvidenceIndex:
    """Build or refresh the evidence index."""
    index = EvidenceIndex()
    count = index.build_or_refresh()
    if count:
        print(f"Indexed {count} new/updated sidecar(s).")
    return index


def _filter_kwargs(args: argparse.Namespace) -> dict:
    """Extract filter kwargs from parsed args."""
    return {
        "query": getattr(args, "query", "") or "",
        "status": getattr(args, "status", None),
        "url_domain": getattr(args, "domain", None),
        "condition_prefix": getattr(args, "condition_prefix", None),
        "story_ref": getattr(args, "story_ref", None),
        "step_type": getattr(args, "step_type", None),
    }


def _format_timestamp(iso_str: str) -> str:
    """Convert ISO-8601 to a human-readable local timestamp."""
    if not iso_str:
        return "—"
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        local = dt.astimezone()
        return local.strftime("%Y-%m-%d %H:%M")
    except ValueError, TypeError:
        return iso_str[:16] if len(iso_str) >= 16 else iso_str


def _print_search_table(
    results: list,
    verbose: bool = False,
) -> None:
    """Print search results as a numbered table."""
    if verbose:
        header = f"{'#':<4} {'St':<3} {'Condition':<12} {'Test Name':<50} {'Story':<8} {'Recorded':<17} URL"
    else:
        header = f"{'#':<4} {'St':<3} {'Condition':<12} {'Test Name':<55} {'Story':<8} URL"
    print(header)
    print("-" * len(header))

    status_icon = {
        "failed": "\u274c",
        "passed": "\u2705",
        "skipped": "\u23ed\ufe0f",
        "error": "\u274c",
    }

    for i, r in enumerate(results, 1):
        icon = status_icon.get(r.status, "?")
        name = r.test_name.replace("[chromium]", "")
        if not verbose:
            max_name = 52
        else:
            max_name = 47
        if len(name) > max_name:
            name = name[: max_name - 3] + "..."
        url = r.page_url or ""
        max_url = 60 if not verbose else 50
        if len(url) > max_url:
            url = url[: max_url - 3] + "..."

        ts = _format_timestamp(r.indexed_at)

        if verbose:
            print(f"{i:<4} {icon:<3} {r.condition_ref:<12} {name:<50} {r.story_ref:<8} {ts:<17} {url}")
        else:
            print(f"{i:<4} {icon:<3} {r.condition_ref:<12} {name:<55} {r.story_ref:<8} {url}")


# ---------------------------------------------------------------------------
# search
# ---------------------------------------------------------------------------


def _cmd_search(args: argparse.Namespace) -> None:
    """Search evidence sidecars and print results as a table."""
    index = _build_index()
    results = index.search(**_filter_kwargs(args))

    if not results:
        print("No evidence matches your search.")
        return

    _print_search_table(results, verbose=args.verbose)
    print(f"\n{len(results)} result(s).")

    # Save results to a temp file so 'detail' can reference them
    _save_last_results(results)

    if args.rerun:
        _rerun_tests(results)


def _save_last_results(results: list) -> None:
    """Save search results to a temp file for cross-command reference."""
    import tempfile

    data = [
        {
            "sidecar_path": r.sidecar_path,
            "test_name": r.test_name,
            "test_package": r.test_package,
        }
        for r in results
    ]
    path = Path(tempfile.gettempdir()) / "evidence_cli_last_results.json"
    path.write_text(json.dumps(data))


def _load_last_results() -> list[dict]:
    """Load the last search results from the temp file."""
    import tempfile

    path = Path(tempfile.gettempdir()) / "evidence_cli_last_results.json"
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text())  # type: ignore[no-any-return]
    except json.JSONDecodeError, OSError:
        return []


def _rerun_tests(results: list) -> None:
    """Rerun pytest on the test packages that produced the search results."""
    packages = sorted({r.test_package for r in results if r.test_package})
    if not packages:
        print("No test packages to rerun.")
        return

    from src.storage import get_storage

    gen_dir = get_storage().generated_tests_dir()
    test_files: list[str] = []
    for pkg_name in packages:
        pkg_dir = gen_dir / pkg_name
        if pkg_dir.exists():
            test_files.extend(str(f) for f in pkg_dir.glob("test_*.py") if f.name != "conftest.py")

    if not test_files:
        print(f"No test files found in packages: {', '.join(packages)}")
        return

    print(f"\nRerunning {len(test_files)} test file(s) from {len(packages)} package(s)...")
    cmd = [sys.executable, "-m", "pytest", *test_files, "-v", "--tb=short"]
    subprocess.run(cmd)


# ---------------------------------------------------------------------------
# detail
# ---------------------------------------------------------------------------


def _cmd_detail(args: argparse.Namespace) -> None:
    """Show detailed evidence for a result from the last search."""
    last = _load_last_results()
    if not last:
        print("No previous search results. Run 'search' first.")
        return

    idx = args.number - 1
    if idx < 0 or idx >= len(last):
        print(f"Result #{args.number} not found. Last search had {len(last)} results.")
        return

    entry = last[idx]
    index = _build_index()
    sidecar = index.get_sidecar_detail(entry["sidecar_path"])

    if sidecar is None:
        print(f"Could not load sidecar: {entry['sidecar_path']}")
        return

    test = sidecar.get("test", {})
    page = sidecar.get("page", {})
    steps = sidecar.get("steps", [])

    print(f"\n{'=' * 70}")
    print(f"  Test:     {test.get('name', '?')}")
    print(f"  Condition: {test.get('condition_ref', '?')}")
    print(f"  Story:    {test.get('story_ref', '?')}")
    print(f"  Status:   {test.get('status', '?')}")
    print(f"  Page URL: {page.get('url', '?')}")
    print(f"  Package:  {entry['test_package']}")
    print(f"{'=' * 70}")

    if steps:
        print(f"\nSteps ({len(steps)}):")
        for s in steps:
            step_num = s.get("step", "?")
            step_type = s.get("type", "?")
            label = s.get("label", "")
            result = s.get("result", {})
            step_status = result.get("status", "?")
            elapsed = result.get("elapsed_ms", 0)
            error = result.get("error") or result.get("failure_note")

            icon = "\u2705" if step_status == "passed" else "\u274c"
            print(f"  {icon} Step {step_num} [{step_type}]: {label}")
            if elapsed:
                print(f"       ({elapsed}ms)")
            if error:
                print(f"       \u26a0\ufe0f  {error}")
    else:
        print("\n  (no steps recorded)")

    # Also show locator info if available
    for s in steps:
        locator = s.get("locator")
        if locator:
            print(f"\n  Locator used: {locator}")
            break


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------


def _cmd_export(args: argparse.Namespace) -> None:
    """Export evidence to CSV, NDJSON, or JUnit XML."""
    fmt = args.format
    output = Path(args.output).resolve()
    index = _build_index()
    kwargs = _filter_kwargs(args)

    # Count matching results before export
    results = index.search(**{**kwargs, "limit": 100_000})
    result_count = len(results)

    if result_count == 0:
        print("No evidence matches your filters. Nothing exported.")
        return

    if fmt == "csv":
        export_csv(index, output=output, **kwargs)
    elif fmt == "ndjson":
        export_ndjson(index, output=output, **kwargs)
    elif fmt == "junit":
        export_junit_xml(index, output=output, **kwargs)
    else:
        print(f"Unknown format: {fmt}", file=sys.stderr)
        sys.exit(1)

    size_kb = output.stat().st_size / 1024 if output.exists() else 0

    # Build a human-readable filter summary
    filters: list[str] = []
    if kwargs.get("query"):
        filters.append(f'query="{kwargs["query"]}"')
    if kwargs.get("status"):
        filters.append(f"status={kwargs['status']}")
    if kwargs.get("url_domain"):
        filters.append(f"domain={kwargs['url_domain']}")
    if kwargs.get("condition_prefix"):
        filters.append(f"prefix={kwargs['condition_prefix']}")
    if kwargs.get("story_ref"):
        filters.append(f"story={kwargs['story_ref']}")
    filter_str = ", ".join(filters) if filters else "all evidence"

    print(f"Exported {result_count} sidecar(s) [{filter_str}] to {output} ({size_kb:.1f} KB)")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description="Search, inspect, rerun, and export Playwright test evidence.",
        prog="evidence-cli",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # ── search ────────────────────────────────────────────────────────────
    p_search = sub.add_parser("search", help="Search evidence sidecars")
    p_search.add_argument("--query", "-q", default="", help="Free-text search query")
    p_search.add_argument("--status", choices=["passed", "failed", "skipped", "error"])
    p_search.add_argument("--domain", help="URL domain filter (e.g. automationexercise.com)")
    p_search.add_argument("--condition-prefix", help="Condition ref prefix (e.g. TC01)")
    p_search.add_argument("--story-ref", help="Story reference (e.g. S06)")
    p_search.add_argument("--step-type", choices=["navigate", "click", "fill", "assertion", "select"])
    p_search.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Show recorded timestamps and full details",
    )
    p_search.add_argument(
        "--rerun",
        action="store_true",
        help="Rerun pytest on the test packages matching search results",
    )
    p_search.set_defaults(func=_cmd_search)

    # ── detail ────────────────────────────────────────────────────────────
    p_detail = sub.add_parser(
        "detail",
        help="Show step-by-step evidence for a result from the last search",
    )
    p_detail.add_argument(
        "number",
        type=int,
        help="Result number from the last search (e.g. 3)",
    )
    p_detail.set_defaults(func=_cmd_detail)

    # ── export ────────────────────────────────────────────────────────────
    p_export = sub.add_parser("export", help="Export evidence to file")
    p_export.add_argument(
        "--format",
        "-f",
        required=True,
        choices=["csv", "ndjson", "junit"],
        help="Export format",
    )
    p_export.add_argument(
        "--output",
        "-o",
        required=True,
        help="Output file path",
    )
    p_export.add_argument("--query", "-q", default="", help="Free-text search query")
    p_export.add_argument("--status", choices=["passed", "failed", "skipped", "error"])
    p_export.add_argument("--domain", help="URL domain filter")
    p_export.add_argument("--condition-prefix", help="Condition ref prefix")
    p_export.add_argument("--story-ref", help="Story reference")
    p_export.add_argument("--step-type", choices=["navigate", "click", "fill", "assertion", "select"])
    p_export.set_defaults(func=_cmd_export)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
