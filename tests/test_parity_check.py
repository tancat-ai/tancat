"""Tests for the offline parity check (scripts/parity_check.py).

The script is the gate; these tests pin the two things that make it a gate at
all: the normaliser that decides what "the same step" means, and the fact that
one fixed input really does agree - so a regression in either mode's export or
in a report format fails here first, not in CI only.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = PROJECT_ROOT / "scripts" / "parity_check.py"


def _load() -> Any:
    spec = importlib.util.spec_from_file_location("parity_check", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # dataclasses resolve their class by module name, so register before exec
    sys.modules.setdefault(spec.name, module)
    spec.loader.exec_module(module)
    return module


POM_SNIPPET = """
def test_t02_navigate_to_cart(page):
    home_page = HomePage(page)
    page.goto('http://127.0.0.1:8123/index.html')
    home_page.click('go to cart', selector='#go-cart')
    expect(page.locator('#cart-title')).to_be_visible()
"""

FLAT_SNIPPET = """
def test_t02_navigate_to_cart(page):
    page.goto('http://127.0.0.1:8123/index.html')
    page.locator('#go-cart').click()
    expect(page.locator('#cart-title')).to_be_visible()
"""


def test_same_steps_from_pom_and_flat_source() -> None:
    mod = _load()
    assert mod.actions_from_source(POM_SNIPPET) == mod.actions_from_source(FLAT_SNIPPET)
    assert mod.actions_from_source(FLAT_SNIPPET) == [
        ("navigate", "http://127.0.0.1:8123/index.html"),
        ("click", "#go-cart"),
        ("assert_visible", "#cart-title"),
    ]


def test_label_difference_does_not_make_a_difference() -> None:
    """A page object carries its label; the flat export cannot. Not a diff."""
    mod = _load()
    pom = "    home_page.fill('username', 'standard_user', selector='#user-name')\n"
    flat = "    page.locator('#user-name').fill('standard_user')\n"
    assert mod.actions_from_source(pom) == mod.actions_from_source(flat) == [("fill", "#user-name")]


def test_test_names_are_read_in_file_order() -> None:
    mod = _load()
    source = "def test_b(page):\n    pass\n\n\ndef test_a(page):\n    pass\n"
    assert mod.test_names(source) == ["test_b", "test_a"]


def test_table_marks_a_difference() -> None:
    mod = _load()
    report = mod.Report()
    report.add("mode", "test count", 2, 3)
    report.allowed("mode", "file layout", "pages/", "one file")
    table = mod.render_table(report.rows)
    assert "DIFF" in table
    assert "allowed" in table
    assert len(report.failures) == 1


def test_fixed_fixture_agrees_end_to_end() -> None:
    """The whole check on the committed fixture: offline, fast, zero diffs."""
    mod = _load()
    assert mod.main([]) == 0


def test_gate_fails_when_one_mode_drops_a_step(tmp_path: Path, monkeypatch: Any) -> None:
    """The gate must bite: a flat export that loses an assertion is a DIFF.

    This is the d-0043 shape - a strip that ate part of a step - at the level the
    check actually looks at.
    """
    mod = _load()
    package = PROJECT_ROOT / "fixtures" / "golden_package"
    source = (package / "test_golden_flow.py").read_text(encoding="utf-8")

    class FakeMode:
        POM = "pom"
        FLAT = "flat"

    class FakeResult:
        def __init__(self, export_dir: Path) -> None:
            self.export_dir = export_dir

    def fake_export(*, source_package_dir: Any, export_mode: Any, output_base_dir: str) -> Any:
        out = Path(output_base_dir) / "out"
        out.mkdir(parents=True, exist_ok=True)
        body = source
        if export_mode == FakeMode.FLAT:
            body = "\n".join(line for line in body.splitlines() if "#cart-title" not in line)
        (out / "test_golden_flow.py").write_text(body, encoding="utf-8")
        return FakeResult(out)

    monkeypatch.setattr(mod, "_load_export_service", lambda: (FakeMode, fake_export))
    report = mod.Report()
    mod.check_mode(package, report, tmp_path)
    assert any(r.artefact == "step sequence (action + target)" for r in report.failures)
