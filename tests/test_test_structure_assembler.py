"""Tests for src/test_structure_assembler.py — structural re-serialization.

The assembler rebuilds the generated test file from the parsed journey model
so the pipeline owns the structure: module-level statement leaks and dangling
decorators (LLM skeleton mistakes that crash pytest at COLLECTION time) become
structurally impossible.
"""

from __future__ import annotations

import ast

from src.test_structure_assembler import rebuild_test_structure

SAMPLE = """\
from playwright.sync_api import Page, expect
import pytest
from pages.home_page import HomePage

BASE_URL = 'https://example.com'

@pytest.mark.evidence(condition_ref="T01", story_ref="S01")
def test_01_home(page: Page, evidence_tracker):
    home_page = HomePage(page, evidence_tracker)
    evidence_tracker.navigate(BASE_URL)

@pytest.mark.evidence(condition_ref="T02", story_ref="S02")
def test_02_cart(page: Page, evidence_tracker):
    home_page = HomePage(page, evidence_tracker)
    home_page.click('Add to cart')
"""


def _module_calls(tree: ast.Module) -> list[ast.Expr]:
    return [node for node in tree.body if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call)]


def test_leaks_stripped_by_construction() -> None:
    code = (
        "from pages.home_page import HomePage\n"
        "\n"
        "home_page.click('Categories')\n"
        "evidence_tracker.assert_visible('h2', label='Category page')\n"
        "\n"
        '@pytest.mark.evidence(condition_ref="T01", story_ref="S01")\n'
        "def test_01(page, evidence_tracker):\n"
        "    home_page = HomePage(page, evidence_tracker)\n"
        "    home_page.click('Products')\n"
    )
    result = rebuild_test_structure(code)
    tree = ast.parse(result)
    assert _module_calls(tree) == []
    funcs = [n for n in tree.body if isinstance(n, ast.FunctionDef)]
    assert len(funcs) == 1
    assert funcs[0].name == "test_01"
    # Legitimate in-function call preserved.
    assert "home_page.click('Products')" in result
    # Leak text gone entirely.
    assert "home_page.click('Categories')" not in result


def test_dangling_decorator_removed() -> None:
    """A module-level decorator with no following def is a leak — dropped."""
    code = (
        "import pytest\n"
        "\n"
        '@pytest.mark.evidence(condition_ref="T01", story_ref="S01")\n'
        "\n"
        '@pytest.mark.evidence(condition_ref="T02", story_ref="S02")\n'
        "def test_01(page, evidence_tracker):\n"
        "    page.goto('https://example.com')\n"
    )
    result = rebuild_test_structure(code)
    tree = ast.parse(result)
    funcs = [n for n in tree.body if isinstance(n, ast.FunctionDef)]
    assert len(funcs) == 1
    # Exactly one decorator, attached to the function, ref T02.
    assert len(funcs[0].decorator_list) == 1
    assert "T02" in ast.unparse(funcs[0].decorator_list[0])


def test_constants_and_imports_preserved() -> None:
    result = rebuild_test_structure(SAMPLE)
    assert "BASE_URL = 'https://example.com'" in result
    assert "from pages.home_page import HomePage" in result
    assert "import pytest" in result


def test_multiple_functions_rebuilt_with_canonical_shells() -> None:
    result = rebuild_test_structure(SAMPLE)
    tree = ast.parse(result)
    funcs = [n for n in tree.body if isinstance(n, ast.FunctionDef)]
    assert [f.name for f in funcs] == ["test_01_home", "test_02_cart"]
    for f in funcs:
        assert len(f.decorator_list) == 1
    # Bodies preserved.
    assert "home_page.click('Add to cart')" in result


def test_body_setup_lines_preserved() -> None:
    """POM instantiation lines (no placeholders) must survive the rebuild."""
    code = (
        "import pytest\n"
        '@pytest.mark.evidence(condition_ref="T01", story_ref="S01")\n'
        "def test_01(page, evidence_tracker):\n"
        "    home_page = HomePage(page, evidence_tracker)\n"
        "    products_page = ProductsPage(page, evidence_tracker)\n"
        "    evidence_tracker.navigate('https://example.com')\n"
    )
    result = rebuild_test_structure(code)
    assert "home_page = HomePage(page, evidence_tracker)" in result
    assert "products_page = ProductsPage(page, evidence_tracker)" in result


def test_module_level_helper_function_preserved() -> None:
    code = (
        "import pytest\n"
        "\n"
        "def _helper(page):\n"
        "    return page\n"
        "\n"
        '@pytest.mark.evidence(condition_ref="T01", story_ref="S01")\n'
        "def test_01(page, evidence_tracker):\n"
        "    page.goto('https://example.com')\n"
    )
    result = rebuild_test_structure(code)
    assert "def _helper(page):" in result
    assert "def test_01(page: Page, evidence_tracker):" in result


def test_no_journeys_returns_input_unchanged() -> None:
    code = "import pytest\n\npytest.skip('nothing')\n"
    assert rebuild_test_structure(code) == code


def test_rebuilt_output_collects_safely() -> None:
    """The rebuilt file must parse with zero module-level calls."""
    result = rebuild_test_structure(SAMPLE)
    tree = ast.parse(result)
    assert _module_calls(tree) == []
    # Every function has exactly the canonical signature + one decorator.
    for f in [n for n in tree.body if isinstance(n, ast.FunctionDef)]:
        args = [a.arg for a in f.args.args]
        assert args == ["page", "evidence_tracker"], args
