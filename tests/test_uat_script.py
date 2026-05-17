"""Unit tests for the UAT script site selection and configuration."""

import importlib.util
from importlib.machinery import ModuleSpec
from pathlib import Path
from typing import Any


def load_uat_module() -> Any:
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "uat" / "uat_automationexercise.py"
    spec: ModuleSpec | None = importlib.util.spec_from_file_location("uat_automationexercise", script_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert module is not None
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_uat_site_config_includes_saucedemo() -> None:
    module = load_uat_module()
    assert "saucedemo" in module.SITE_CONFIGS
    assert module.SITE_CONFIGS["saucedemo"]["target_urls"] == ["https://www.saucedemo.com"]
    assert "standard_user" in module.SITE_CONFIGS["saucedemo"]["conditions"]
    assert "secret_sauce" in module.SITE_CONFIGS["saucedemo"]["conditions"]


def test_parse_args_supports_site_option() -> None:
    module = load_uat_module()
    args = module.parse_args(["--site", "saucedemo"])
    assert args.site == "saucedemo"


def test_find_unresolved_placeholder_artifacts_detects_tokens_and_skips() -> None:
    module = load_uat_module()
    code = """
def test_example(page):
    pytest.skip("Skipping: unresolved placeholders for: 'checkout button'")
    pytest.skip("Unresolved placeholder: {{CLICK:checkout button}}")
"""

    placeholders, has_skip = module.find_unresolved_placeholder_artifacts(code)

    assert placeholders == ["{{CLICK:"]
    assert has_skip is True


def test_find_unresolved_placeholder_artifacts_accepts_resolved_code() -> None:
    module = load_uat_module()
    code = """
def test_example(page):
    evidence_tracker.click("#checkout", label="checkout button")
"""

    placeholders, has_skip = module.find_unresolved_placeholder_artifacts(code)

    assert placeholders == []
    assert has_skip is False
