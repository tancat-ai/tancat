"""Structured run results display for the CLI.

Provides ANSI-formatted rendering of pytest run results including:
- Metrics summary line with colored counts
- Per-test results table with status, duration, error messages
- Failure classification and diagnostics
- Re-run suggestions

Uses ``cli.color`` for ANSI colour codes that auto-disable when stdout
is not a terminal.
"""

from __future__ import annotations

from src.failure_classifier import FailureCategory, classify_failure
from src.pytest_output_parser import RunResult

from .color import bold, dim_green, green, phosphor_green, red, yellow

# ── Status badges ──────────────────────────────────────────────────────────


def _status_badge(status: str) -> str:
    """Return a coloured emoji-free status badge."""
    mapping = {
        "passed": green("[PASS]"),
        "failed": red("[FAIL]"),
        "error": red("[ERROR]"),
        "skipped": yellow("[SKIP]"),
    }
    return mapping.get(status, f"[{status.upper()}]")


# ── Metrics line ───────────────────────────────────────────────────────────


def render_run_metrics(run: RunResult) -> None:
    """Print a single-line coloured summary of the run.

    Example output::

      Run Results: ✅ 5 passed, 1 failed, 0 errors, 2 skipped in 12.34s
    """
    parts: list[str] = []

    if run.failed == 0 and run.errors == 0:
        parts.append(phosphor_green(f"✅ {run.passed} passed"))
    else:
        parts.append(green(f"{run.passed} passed"))

    if run.failed > 0:
        parts.append(red(f"{run.failed} failed"))
    if run.errors > 0:
        parts.append(red(f"{run.errors} errors"))
    if run.skipped > 0:
        parts.append(yellow(f"{run.skipped} skipped"))

    summary = ", ".join(parts)
    duration = f" in {run.duration:.2f}s" if run.duration > 0 else ""
    overall = green("✅") if run.failed == 0 and run.errors == 0 else red("❌")
    print(f"  {overall} Run Results: {summary}{duration}")
    print()


# ── Results table ──────────────────────────────────────────────────────────


def render_results_table(run: RunResult) -> None:
    """Print an ASCII table of per-test results.

    Columns: status badge, test name, duration, error message (if failed).
    Failed tests show a truncated error message on a sub-line.
    """
    if not run.results:
        print(dim_green("  (no test results)"))
        return

    # Calculate column widths
    name_width = max(len(r.name) for r in run.results)
    name_width = min(max(name_width, 40), 80)  # clamp between 40 and 80

    # Header
    header = f"  {'STATUS':<8} {'TEST NAME':<{name_width}} {'DUR':>7}"
    print(bold(header))
    print("  " + "─" * len(header))

    for result in run.results:
        badge = _status_badge(result.status)
        dur = f"{result.duration:6.2f}s"
        name = result.name
        if len(name) > name_width:
            name = "…" + name[-(name_width - 1) :]

        print(f"  {badge} {name:<{name_width}} {dur}")

        # Error message for failed/error tests
        if result.error_message:
            error_text = result.error_message
            max_error_len = name_width + 50
            if len(error_text) > max_error_len:
                error_text = error_text[:max_error_len] + "..."
            # Indent to align under test name
            for line in error_text.splitlines()[:3]:
                print(f"  {'':>8} {'':>{name_width}}   {red(line)}")
            if len(result.error_message.splitlines()) > 3:
                print(f"  {'':>8} {'':>{name_width}}   {red('...')}")

    print()


# ── Failure details ────────────────────────────────────────────────────────


def render_failure_details(run: RunResult) -> None:
    """Print classified failure details for each failed test.

    Shows the failure category, raw locator (if available), and a
    human-readable suggestion for remediation.
    """
    failed = [r for r in run.results if r.status in ("failed", "error") and r.error_message]
    if not failed:
        return

    print(bold("  Failure Classification:"))
    print("  " + "─" * 40)

    for idx, result in enumerate(failed, start=1):
        detail = classify_failure(result.error_message)

        print()
        print(red(f"  [{idx}] {result.name}"))
        print(f"      Category:  {detail.category.value}")

        if detail.raw_locator:
            print(f"      Locator:   `{detail.raw_locator}`")
        if detail.failure_url:
            print(f"      Page:      {detail.failure_url}")

        # Suggestion
        suggestion = _suggestion_for_category(detail.category)
        if suggestion:
            print(yellow(f"      Suggestion: {suggestion}"))

    print()


def _suggestion_for_category(category: FailureCategory) -> str:
    """Return a human-readable suggestion for a failure category."""
    suggestions = {
        FailureCategory.LOCATOR_TIMEOUT: "Check that the element exists on the page; consider increasing timeout or using a fallback locator.",
        FailureCategory.STRICT_VIOLATION: "The locator matched multiple elements — make it more specific (e.g. add an ID or data-testid).",
        FailureCategory.NAVIGATION_ERROR: "Verify the URL is correct and the page is reachable. Check for redirects or authentication requirements.",
        FailureCategory.ASSERTION_FAILURE: "The element was found but content did not match — check for page state changes or dynamic content.",
        FailureCategory.OTHER: "Review the error message for clues.",
    }
    return suggestions.get(category, "")


# ── Raw pytest output (optional) ───────────────────────────────────────────


def render_raw_output(run: RunResult, *, expanded: bool = False) -> None:
    """Print the raw pytest output, optionally behind a toggle prompt."""
    if not run.raw_output:
        return

    if not expanded:
        show = input("  Show raw pytest output? [y/N]: ").strip().lower()
        if show not in ("y", "yes"):
            return

    print()
    print(bold("  --- Pytest Output ---"))
    for line in run.raw_output.splitlines():
        print(f"  {line}")
    print("  --- End Output ---")
    print()


# ── Combined display ───────────────────────────────────────────────────────


def render_run_results(run: RunResult, *, show_raw: bool = False) -> None:
    """Render the full structured run results view.

    Args:
        run: Parsed pytest run result.
        show_raw: If True, append raw pytest output without prompting.
    """
    render_run_metrics(run)
    render_results_table(run)
    render_failure_details(run)

    if show_raw:
        render_raw_output(run, expanded=True)
    elif run.raw_output:
        render_raw_output(run, expanded=False)


# ── Run History Summary ────────────────────────────────────────────────────


def render_run_history_summary() -> None:
    """Display the run history summary using ASCII tables.

    Shows recent run history, flaky tests, and comparison between
    the last two runs.
    """
    from src.run_history_cli import format_full_history_summary

    summary = format_full_history_summary()
    print(summary)
