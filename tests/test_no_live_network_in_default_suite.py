"""Guard: no live-network tests may run in the default (unmarked) suite.

``pytest.ini`` runs the suite with ``-m "not slow and not integration"``, so
tests carrying ``@pytest.mark.slow`` / ``@pytest.mark.integration`` (or a
module-level ``pytestmark``) are excluded from every default run — local and
CI. This guard statically scans the suite and FAILS when a test function
references a live-site URL in a navigation context without any exclusion
marker.

Why it exists: the 2026-08-03 CLI-review audit claimed
``tests/integration/test_pom_mode_end_to_end.py`` "hits live
automationexercise.com with NO slow/integration marker". That claim was
verified false — the file is pure offline string/JSON-schema checks (the
URLs live in a module-level sample constant, never executed). The genuinely
network-touching tests (LLM pipeline runs, real embedding-model downloads)
already carry markers. This guard makes the property durable: a network test
added without markers now fails here instead of silently slowing/flaking the
default suite.

Limitation: it is a static scan — URL indirection through variables is not
caught. It covers the common failure mode (a literal live URL inside a test
body).
"""

from __future__ import annotations

import ast
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent

# Live sites the pipeline targets / exercises. Localhost and file:// are NOT
# listed: the default suite may legitimately use local servers and fixtures.
LIVE_DOMAINS: tuple[str, ...] = (
    "automationexercise.com",
    "saucedemo.com",
    "demoqa.com",
    "the-internet.herokuapp.com",
    "restful-booker.herokuapp.com",
    "practice.cypress.io",
    "juice-shop.herokuapp.com",
)

# Call signatures that actually navigate/scrape/execute against a URL. The
# domain must co-occur with one of these to be flagged — merely asserting a
# config value like ``target_urls == ["https://www.saucedemo.com"]`` must not
# trip the guard.
EXCLUSION_MARKERS = ("slow", "integration")

AST_FN = ast.FunctionDef | ast.AsyncFunctionDef

# Executed-call signals that actually navigate / scrape / run against a URL.
# Detection is call-site-based: the live domain must appear as a literal
# argument of one of these calls. Sample-code strings passed to code
# transformers (normalise_generated_code, strip_evidence_from_test_code,
# inject_pom_*) contain the same text but never execute it — those are not
# flagged.
_EXEC_ATTRS: frozenset[str] = frozenset(
    {"goto", "navigate", "scrape_url", "scrape_all", "run_pipeline", "attempt_login"}
)
_EXEC_NAMES: frozenset[str] = frozenset({"scrape_url", "scrape_all", "run_pipeline"})

# A test that explicitly mocks the network layer (AsyncMock / MagicMock /
# monkeypatch / patch) is, by construction, not executing real I/O — even if
# live URLs appear as mock return data.
_MOCK_SIGNALS: tuple[str, ...] = ("AsyncMock", "MagicMock", "monkeypatch", "patch(")


def _call_has_live_url_arg(call: ast.Call) -> bool:
    """True when a literal string argument of the call references a live domain."""
    for arg in list(call.args) + [kw.value for kw in call.keywords]:
        # Unwrap list/tuple literals: target_urls=["https://..."]
        if isinstance(arg, (ast.List, ast.Tuple)):
            for item in arg.elts:
                if isinstance(item, ast.Constant) and isinstance(item.value, str):
                    if any(domain in item.value for domain in LIVE_DOMAINS):
                        return True
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            if any(domain in arg.value for domain in LIVE_DOMAINS):
                return True
    return False


def _function_executes_live_navigation(node: AST_FN) -> bool:
    """True when the test body executes a navigation call with a live URL."""
    for sub in ast.walk(node):
        if not isinstance(sub, ast.Call):
            continue
        if isinstance(sub.func, ast.Attribute):
            if sub.func.attr not in _EXEC_ATTRS:
                continue
        elif isinstance(sub.func, ast.Name):
            if sub.func.id not in _EXEC_NAMES:
                continue
        else:
            continue
        if _call_has_live_url_arg(sub):
            return True
    return False


def _module_has_exclusion_marker(tree: ast.Module, source: str) -> bool:
    """True when the module carries a pytestmark slow/integration marker."""
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "pytestmark":
                    src = ast.get_source_segment(source, node.value)
                    if src and any(marker in src for marker in EXCLUSION_MARKERS):
                        return True
    return False


def _function_has_exclusion_marker(node: AST_FN, source: str) -> bool:
    for decorator in node.decorator_list:
        src = ast.get_source_segment(source, decorator)
        if src and any(marker in src for marker in EXCLUSION_MARKERS):
            return True
    return False


def _scan_for_unmarked_live_tests() -> list[str]:
    """Return test identifiers that touch live sites without exclusion markers."""
    flagged: list[str] = []
    for test_file in sorted(TESTS_DIR.rglob("test_*.py")):
        if test_file.name == Path(__file__).name:
            continue  # don't scan the guard itself
        try:
            source = test_file.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except OSError, SyntaxError:
            continue
        module_marked = _module_has_exclusion_marker(tree, source)
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not node.name.startswith("test_"):
                continue
            if module_marked or _function_has_exclusion_marker(node, source):
                continue
            body = ast.get_source_segment(source, node)
            if body is None:
                continue
            if any(signal in body for signal in _MOCK_SIGNALS):
                continue  # network layer explicitly mocked — no real I/O
            if not _function_executes_live_navigation(node):
                continue
            flagged.append(f"{test_file.relative_to(TESTS_DIR)}::{node.name}")
    return flagged


def test_default_suite_has_no_unmarked_live_network_tests() -> None:
    """Any test navigating to a live site must be marked slow/integration.

    This is the contract behind ``addopts = -m "not slow and not integration"``
    in pytest.ini: the default run (local and CI) must be deterministic and
    offline. If this test flags new code, add ``@pytest.mark.slow`` +
    ``@pytest.mark.integration`` (or a module-level ``pytestmark``) to the
    offending test — do NOT delete or weaken this guard.
    """
    flagged = _scan_for_unmarked_live_tests()
    assert not flagged, (
        "Live-network tests found without slow/integration markers — they "
        "would run in every default pytest AND in CI:\n  " + "\n  ".join(flagged)
    )
