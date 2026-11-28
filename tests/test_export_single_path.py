"""t-1488: one function owns an export, and no caller can skip the cap.

The audit's shape of failure was a check that lived on one path (file writes) and
was missing on another (the UI's in-memory bytes). This test refuses that shape:

- ``src/evidence_export.py`` exposes ONE export function. The per-format builders are
  private, so nothing outside the module can ask for bytes directly.
- No module except ``scripts/parity_check.py`` may pass ``enforce_cap=False`` (the
  named tooling bypass), and none except ``src/ui/ui_evidence.py`` may pass
  ``charge_meter=False`` (the UI charges on the click; Streamlit re-runs every
  interaction).
- Every call site of the export function is named, so a new surface is a visible edit
  here rather than a silent bypass.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXPORT_MODULE = ROOT / "src" / "evidence_export.py"

#: The only public name that produces export bytes.
PUBLIC_EXPORT = "export_evidence"

#: The private builders. Calling one outside the module is a bypass.
PRIVATE_BUILDERS = {"_csv_text", "_ndjson_text", "_junit_text"}

#: file: the only place allowed to switch the cap off, and why.
CAP_BYPASS_ALLOWED = {"scripts/parity_check.py": "our own CI tooling, throwaway index"}

#: file: the only place allowed to defer the meter charge, and why.
CHARGE_DEFERRED_ALLOWED = {
    "src/ui/ui_evidence.py": "Streamlit re-runs; charged on the click",
    "scripts/parity_check.py": "same named bypass - a throwaway index must not charge",
}

#: Every caller of the one export path, with the surface it serves.
CALLERS = {
    "cli/evidence_cli.py": "the CLI export command, writing a file",
    "src/cli/pipeline_runner.py": "the run's report files",
    "src/ui/ui_evidence.py": "the three download buttons",
    "action/export_evidence_junit.py": "the Action's enriched JUnit",
    "scripts/parity_check.py": "the parity gate (named bypass)",
}

#: Not product surfaces: tests drive the one path, and fixtures are inputs.
SKIP_DIRS = {
    ".venv",
    "__pycache__",
    ".git",
    "graphify-out",
    "site",
    "node_modules",
    "fixtures",
    "tests",
}


def _python_files() -> list[Path]:
    return sorted(
        path for path in ROOT.rglob("*.py") if not any(part in SKIP_DIRS for part in path.relative_to(ROOT).parts)
    )


def _tree(path: Path) -> ast.Module | None:
    """The parsed module, or None for a file that is not valid Python.

    A deliberately broken fixture is not an export caller; parsing failures must not
    turn this guard into a crash.
    """
    try:
        return ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError, UnicodeDecodeError:
        return None


def _public_functions(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_")
    }


def _calls(tree: ast.Module) -> list[tuple[str, ast.Call]]:
    found: list[tuple[str, ast.Call]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
            found.append((name, node))
    return found


def test_the_export_module_has_one_public_way_to_get_bytes() -> None:
    public = _public_functions(EXPORT_MODULE)
    assert PUBLIC_EXPORT in public, "the one export function is gone"
    # Everything else is a helper (private by name) or a constant.
    export_like = {name for name in public if "export" in name.lower() or name.endswith("_text")}
    assert export_like == {PUBLIC_EXPORT}, f"a second public export path exists: {sorted(export_like)}"


def test_no_module_outside_the_export_module_calls_a_private_builder() -> None:
    offenders: list[str] = []
    for path in _python_files():
        if path == EXPORT_MODULE:
            continue
        tree = _tree(path)
        if tree is None:
            continue
        for name, _node in _calls(tree):
            if name in PRIVATE_BUILDERS:
                offenders.append(f"{path.relative_to(ROOT).as_posix()}: {name}")
    assert offenders == [], f"a caller builds export bytes directly: {offenders}"


def test_only_the_named_tooling_bypass_switches_the_cap_off() -> None:
    offenders: list[str] = []
    for path in _python_files():
        tree = _tree(path)
        if tree is None:
            continue
        for name, node in _calls(tree):
            if name != PUBLIC_EXPORT:
                continue
            for keyword in node.keywords:
                if keyword.arg == "enforce_cap" and getattr(keyword.value, "value", True) is False:
                    rel = path.relative_to(ROOT).as_posix()
                    if rel not in CAP_BYPASS_ALLOWED:
                        offenders.append(f"{rel}:{node.lineno}")
    assert offenders == [], f"a caller switches the export cap off outside the allow-list: {offenders}"


def test_only_the_ui_defers_the_meter_charge() -> None:
    offenders: list[str] = []
    for path in _python_files():
        tree = _tree(path)
        if tree is None:
            continue
        for name, node in _calls(tree):
            if name != PUBLIC_EXPORT:
                continue
            for keyword in node.keywords:
                if keyword.arg == "charge_meter" and getattr(keyword.value, "value", True) is False:
                    rel = path.relative_to(ROOT).as_posix()
                    if rel not in CHARGE_DEFERRED_ALLOWED:
                        offenders.append(f"{rel}:{node.lineno}")
    assert offenders == [], f"a caller defers the meter charge outside the UI: {offenders}"


def test_every_caller_is_named() -> None:
    callers: dict[str, str] = {}
    for path in _python_files():
        if path == EXPORT_MODULE:
            continue
        tree = _tree(path)
        if tree is None:
            continue
        for name, _node in _calls(tree):
            if name == PUBLIC_EXPORT:
                callers[path.relative_to(ROOT).as_posix()] = ""
                break
    assert set(callers) == set(CALLERS), (
        "the set of export call sites changed - name the new surface here: "
        f"added {sorted(set(callers) - set(CALLERS))}, removed {sorted(set(CALLERS) - set(callers))}"
    )


def test_the_export_function_checks_the_cap_before_building() -> None:
    """Order matters: the cap is asked before any bytes are made."""
    tree = ast.parse(EXPORT_MODULE.read_text(encoding="utf-8"))
    func = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == PUBLIC_EXPORT)
    body = ast.get_source_segment(EXPORT_MODULE.read_text(encoding="utf-8"), func) or ""
    assert body.index("_meter_check(") < body.index("builders[format_name]("), (
        "the cap must be checked before the bytes are built"
    )
    assert body.index("_meter_record(") < body.index("Path(output).write_text"), (
        "the meter must be charged before the file is written"
    )
