"""Unit tests for scripts/uat.py — results aggregation (S6 follow-up).

Regression: ``--all-sites --save`` previously persisted only the LAST site's
``SiteResult`` because ``results.append(site_result)`` sat outside the
site loop in ``main()`` — the saved JSON and the OVERALL line both reflected
one site even though both ran. See ``docs/sessions/2026-08-23_ai052_session6_ship.md``.
"""

from __future__ import annotations

import importlib.util
from importlib.machinery import ModuleSpec
from pathlib import Path
from typing import Any

UAT_MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "uat.py"
_uat: Any = None


def _load_uat_module() -> Any:
    """Load scripts/uat.py by file path (mirrors tests/test_uat_script.py).

    Cached — each reload would fork the dataclasses and break cross-instance
    isinstance behaviour inside summarize_results().
    """
    global _uat
    if _uat is None:
        import sys

        spec: ModuleSpec | None = importlib.util.spec_from_file_location("uat_script", UAT_MODULE_PATH)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        # Register in sys.modules BEFORE exec_module: dataclasses resolves
        # string annotations (PEP 563) against sys.modules[cls.__module__],
        # which is None for unregistered spec-loaded modules.
        sys.modules["uat_script"] = module
        spec.loader.exec_module(module)
        _uat = module
    return _uat


def _site(site_id: str, passed: int, failed: int) -> Any:
    m = _load_uat_module()
    checks = [m.CheckResult(f"c{i}", i < passed) for i in range(passed + failed)]
    return m.SiteResult(site_id=site_id, site_name=site_id, pom_mode=True, checks=checks)


def test_summarize_results_aggregates_all_sites() -> None:
    m = _load_uat_module()
    # AE 12/13 + saucedemo 10/13 (the actual S6 UAT shape)
    results = [_site("automationexercise", 12, 1), _site("saucedemo", 10, 3)]
    assert m.summarize_results(results) == (22, 4, 26)


def test_summarize_results_single_site_unchanged() -> None:
    m = _load_uat_module()
    results = [_site("saucedemo", 10, 3)]
    assert m.summarize_results(results) == (10, 3, 13)


def test_summarize_results_empty() -> None:
    m = _load_uat_module()
    assert m.summarize_results([]) == (0, 0, 0)


def test_main_appends_every_site_not_just_last() -> None:
    """Static guard: results.append must sit INSIDE the site loop.

    Catches the exact regression shape (dedented append after the loop) that
    made --all-sites --save persist only the last site.
    """
    import ast

    source = UAT_MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    main_fn = next(n for n in ast.walk(tree) if isinstance(n, ast.AsyncFunctionDef) and n.name == "main")
    loop = next(n for n in ast.walk(main_fn) if isinstance(n, ast.For))
    appends_in_loop = [
        n
        for n in ast.walk(loop)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "append"
        and isinstance(n.func.value, ast.Name)
        and n.func.value.id == "results"
    ]
    assert appends_in_loop, "results.append(site_result) must be inside the site loop"
    # And nowhere else in main
    all_appends = [
        n
        for n in ast.walk(main_fn)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Attribute)
        and n.func.attr == "append"
        and isinstance(n.func.value, ast.Name)
        and n.func.value.id == "results"
    ]
    assert len(all_appends) == 1, "exactly one results.append in main, inside the loop"


def test_saved_output_contains_every_site() -> None:
    """The output_data shape written by --save carries one entry per site."""
    results = [_site("automationexercise", 12, 1), _site("saucedemo", 10, 3)]
    output_sites = [r.to_dict() for r in results]
    assert [s["site_id"] for s in output_sites] == ["automationexercise", "saucedemo"]
