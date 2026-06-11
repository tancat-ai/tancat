"""Tests for POM injection in TestOrchestrator (AI-010 Phase 3 fix).

Validates that the orchestrator correctly injects POM imports and
instantiations into generated test code when pom_mode=True.
"""

from __future__ import annotations

from src.orchestrator import TestOrchestrator


def test_inject_pom_imports_after_existing_imports() -> None:
    """POM imports should be injected after existing import lines."""
    code = "from playwright.sync_api import Page, expect\nimport pytest\n\ndef test_foo(page):\n    pass\n"
    pom_imports = [
        "from pages.home_page import HomePage",
        "from pages.cart_page import CartPage",
    ]
    result = TestOrchestrator._inject_pom_imports(code, pom_imports)

    # POM imports appear after existing imports
    assert "from pages.home_page import HomePage" in result
    assert "from pages.cart_page import CartPage" in result
    # Existing imports still present
    assert "from playwright.sync_api import Page, expect" in result
    assert "import pytest" in result


def test_inject_pom_imports_empty_code() -> None:
    """POM imports should be prepended when no existing imports."""
    code = "def test_foo(page):\n    pass\n"
    pom_imports = ["from pages.home_page import HomePage"]
    result = TestOrchestrator._inject_pom_imports(code, pom_imports)

    assert "from pages.home_page import HomePage" in result
    # Import comes before function definition
    import_pos = result.index("from pages.home_page")
    func_pos = result.index("def test_foo")
    assert import_pos < func_pos


def test_inject_pom_instantiation_at_test_functions() -> None:
    """POM instantiation should be injected at the start of each test function."""
    code = (
        "from playwright.sync_api import Page\n"
        "\n"
        "def test_foo(page):\n"
        "    page.goto('http://example.com')\n"
        "\n"
        "def test_bar(page):\n"
        "    page.goto('http://example.com/other')\n"
    )
    pom_instantiation = [
        "    home_page = HomePage(page, evidence_tracker)",
    ]
    result = TestOrchestrator._inject_pom_instantiation(code, pom_instantiation)

    # Instantiation appears after each test function definition
    lines = result.splitlines()
    foo_instantiated = False
    bar_instantiated = False
    for i, line in enumerate(lines):
        if "def test_foo" in line:
            assert "home_page = HomePage(page, evidence_tracker)" in lines[i + 1]
            foo_instantiated = True
        if "def test_bar" in line:
            assert "home_page = HomePage(page, evidence_tracker)" in lines[i + 1]
            bar_instantiated = True

    assert foo_instantiated
    assert bar_instantiated


def test_inject_pom_instantiation_multiple_instances() -> None:
    """Multiple POM instances should all be injected."""
    code = "def test_foo(page):\n    pass\n"
    pom_instantiation = [
        "    home_page = HomePage(page, evidence_tracker)",
        "    cart_page = CartPage(page, evidence_tracker)",
    ]
    result = TestOrchestrator._inject_pom_instantiation(code, pom_instantiation)

    assert "    home_page = HomePage(page, evidence_tracker)" in result
    assert "    cart_page = CartPage(page, evidence_tracker)" in result


def test_inject_pom_instantiation_preserves_non_test_functions() -> None:
    """Non-test functions should not get POM instantiation injected."""
    code = "def helper_function():\n    return 42\n\ndef test_foo(page):\n    pass\n"
    pom_instantiation = ["    home_page = HomePage(page, evidence_tracker)"]
    result = TestOrchestrator._inject_pom_instantiation(code, pom_instantiation)

    lines = result.splitlines()
    # helper_function should NOT have instantiation after it
    for i, line in enumerate(lines):
        if "def helper_function" in line:
            assert "home_page" not in lines[i + 1]


def test_full_injection_pipeline() -> None:
    """End-to-end: imports and instantiations both injected correctly."""
    code = (
        "from playwright.sync_api import Page, expect\n"
        "import pytest\n"
        "\n"
        "def test_checkout(page):\n"
        "    evidence_tracker.click('#submit')\n"
        "\n"
        "def test_login(page):\n"
        "    evidence_tracker.fill('#username', 'user')\n"
    )

    pom_imports = [
        "from pages.home_page import HomePage",
        "from pages.login_page import LoginPage",
    ]
    pom_instantiation = [
        "    home_page = HomePage(page, evidence_tracker)",
        "    login_page = LoginPage(page, evidence_tracker)",
    ]

    # First inject imports
    result = TestOrchestrator._inject_pom_imports(code, pom_imports)
    # Then inject instantiations
    result = TestOrchestrator._inject_pom_instantiation(result, pom_instantiation)

    # Verify imports are present
    assert "from pages.home_page import HomePage" in result
    assert "from pages.login_page import LoginPage" in result

    # Verify instantiations appear after each test function
    lines = result.splitlines()
    for i, line in enumerate(lines):
        if "def test_checkout" in line:
            assert "home_page = HomePage(page, evidence_tracker)" in lines[i + 1]
            assert "login_page = LoginPage(page, evidence_tracker)" in lines[i + 2]
        if "def test_login" in line:
            assert "home_page = HomePage(page, evidence_tracker)" in lines[i + 1]
            assert "login_page = LoginPage(page, evidence_tracker)" in lines[i + 2]

    # Verify original code is preserved
    assert "evidence_tracker.click('#submit')" in result
    assert "evidence_tracker.fill('#username', 'user')" in result
