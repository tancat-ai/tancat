"""Unit tests for the CI ignore-list parser (Phase 7, `src/ci_ignore.py`)."""

from __future__ import annotations

import pytest

from src.ci_ignore import load_ignore_spec


def test_none_path_returns_empty_spec() -> None:
    spec = load_ignore_spec(None)
    assert spec.count == 0
    assert not spec.matches("test_01_x")


def test_missing_file_raises(tmp_path: object) -> None:
    with pytest.raises(ValueError, match="not found"):
        load_ignore_spec(f"{tmp_path}/nope.yml")  # type: ignore[arg-type]


def test_invalid_yaml_raises(tmp_path: object) -> None:
    p = f"{tmp_path}/bad.yml"
    with open(p, "w", encoding="utf-8") as fh:
        fh.write("ignores: [unclosed\n")
    with pytest.raises(ValueError, match="invalid YAML"):
        load_ignore_spec(p)  # type: ignore[arg-type]


def test_missing_ignores_key_raises(tmp_path: object) -> None:
    p = f"{tmp_path}/empty.yml"
    with open(p, "w", encoding="utf-8") as fh:
        fh.write("other: true\n")
    with pytest.raises(ValueError, match="'ignores' list"):
        load_ignore_spec(p)  # type: ignore[arg-type]


def test_ignores_not_a_list_raises(tmp_path: object) -> None:
    p = f"{tmp_path}/badlist.yml"
    with open(p, "w", encoding="utf-8") as fh:
        fh.write("ignores: nope\n")
    with pytest.raises(ValueError, match="must be a list"):
        load_ignore_spec(p)  # type: ignore[arg-type]


def test_rule_missing_test_raises(tmp_path: object) -> None:
    p = f"{tmp_path}/notest.yml"
    with open(p, "w", encoding="utf-8") as fh:
        fh.write("ignores:\n  - reason: no test here\n")
    with pytest.raises(ValueError, match="non-empty 'test' glob"):
        load_ignore_spec(p)  # type: ignore[arg-type]


def test_rule_invalid_regex_raises(tmp_path: object) -> None:
    p = f"{tmp_path}/badre.yml"
    with open(p, "w", encoding="utf-8") as fh:
        fh.write("ignores:\n  - test: 't*'\n    reason: 'known flaky'\n    match: '([unclosed'\n")
    with pytest.raises(ValueError, match="invalid 'match' regex"):
        load_ignore_spec(p)  # type: ignore[arg-type]


def test_rule_unknown_key_raises(tmp_path: object) -> None:
    p = f"{tmp_path}/unk.yml"
    with open(p, "w", encoding="utf-8") as fh:
        fh.write("ignores:\n  - test: 't*'\n    typo: 'x'\n")
    with pytest.raises(ValueError, match="unknown keys"):
        load_ignore_spec(p)  # type: ignore[arg-type]


def test_glob_match_without_message(tmp_path: object) -> None:
    p = f"{tmp_path}/ok.yml"
    with open(p, "w", encoding="utf-8") as fh:
        fh.write("ignores:\n  - test: 'test_08*'\n    reason: 'known flaky in mock'\n")
    spec = load_ignore_spec(p)  # type: ignore[arg-type]
    assert spec.count == 1
    assert spec.matches("test_08_checkout[chromium]")
    assert not spec.matches("test_07_fill")
    assert spec.describe("test_08_checkout[chromium]") == "known flaky in mock"
    assert spec.describe("test_07_fill") is None


def test_rule_missing_reason_raises(tmp_path: object) -> None:
    """The anti-rug rule: an ignore without a reason is rejected."""
    p = f"{tmp_path}/noreason.yml"
    with open(p, "w", encoding="utf-8") as fh:
        fh.write("ignores:\n  - test: 'test_09*'\n")
    with pytest.raises(ValueError, match="non-empty 'reason'"):
        load_ignore_spec(p)  # type: ignore[arg-type]


def test_match_regex_constrains_failure_message(tmp_path: object) -> None:
    p = f"{tmp_path}/re.yml"
    with open(p, "w", encoding="utf-8") as fh:
        fh.write(
            "ignores:\n  - test: 'test_09*'\n    reason: 'known flaky in mock'\n    match: \"Locator '.*' not found\"\n"
        )
    spec = load_ignore_spec(p)  # type: ignore[arg-type]
    assert spec.matches("test_09_x[chromium]", "Locator 'a[href=/x]' not found")
    assert not spec.matches("test_09_x[chromium]", "AssertionError: expected 5 to equal 3")


def test_empty_ignores_yields_zero_rules(tmp_path: object) -> None:
    p = f"{tmp_path}/empty.yml"
    with open(p, "w", encoding="utf-8") as fh:
        fh.write("ignores: []\n")
    spec = load_ignore_spec(p)  # type: ignore[arg-type]
    assert spec.count == 0
