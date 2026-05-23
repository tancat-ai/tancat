"""Unit tests for src/locator_repair.py"""

from __future__ import annotations

import tempfile
from pathlib import Path
from textwrap import dedent

from src.locator_repair import (
    LocatorPatch,
    LocatorRepairError,
    apply_patch,
    apply_patch_to_file,
    extract_locator_from_line,
)

# -- extract_locator_from_line --


def test_extract_locator_simple() -> None:
    line = 'page.locator("#product-name").click()'
    result = extract_locator_from_line(line)
    assert result == "#product-name"


def test_extract_locator_single_quotes() -> None:
    line = "page.locator('#product-name').click()"
    result = extract_locator_from_line(line)
    assert result == "#product-name"


def test_extract_locator_complex() -> None:
    line = "page.locator('get_by_role('link', name='Products')').click()"
    result = extract_locator_from_line(line)
    assert result == "get_by_role('link', name='Products')"


def test_extract_locator_no_match() -> None:
    line = "page.goto('https://example.com')"
    result = extract_locator_from_line(line)
    assert result is None


def test_extract_locator_get_by_shorthand() -> None:
    # get_by_* methods don't use .locator() so won't match
    line = 'page.get_by_role("button").click()'
    result = extract_locator_from_line(line)
    assert result is None


# -- apply_patch --


def _make_temp_test(source: str) -> Path:
    """Write *source* to a temporary .py file and return the path."""
    tmp = Path(tempfile.mkdtemp()) / "test_example.py"
    tmp.write_text(source, encoding="utf-8")
    return tmp


def test_apply_patch_replaces_locator_keeps_action() -> None:
    source = dedent("""\
        def test_example(page):
            page.goto("https://example.com")
            page.locator("#old-locator").click()
            page.locator("#other").fill("hello")
        """)
    tmp = _make_temp_test(source)
    try:
        patch = LocatorPatch(
            original_locator="#old-locator",
            repaired_locator="#new-locator",
            line_number=3,
            test_file=tmp,
        )
        result = apply_patch(patch)
        assert "#new-locator" in result
        assert "#old-locator" not in result
        assert "#other" in result  # other line untouched
        assert ".click()" in result  # action preserved
    finally:
        tmp.unlink()


def test_apply_patch_preserves_double_quotes() -> None:
    source = 'page.locator("#broken").fill("text")'
    tmp = _make_temp_test(source)
    try:
        patch = LocatorPatch(
            original_locator="#broken",
            repaired_locator="[data-testid='input']",
            line_number=1,
            test_file=tmp,
        )
        result = apply_patch(patch)
        assert "[data-testid='input']" in result
    finally:
        tmp.unlink()


def test_apply_patch_preserves_single_quotes() -> None:
    source = "page.locator('#broken').click()"
    tmp = _make_temp_test(source)
    try:
        patch = LocatorPatch(
            original_locator="#broken",
            repaired_locator=".correct-class",
            line_number=1,
            test_file=tmp,
        )
        result = apply_patch(patch)
        assert "'.correct-class'" in result
    finally:
        tmp.unlink()


def test_apply_patch_searches_window_when_line_off() -> None:
    source = dedent("""\
        def test_example(page):
            page.goto("https://example.com")
            # comment line
            # another comment
            page.locator("#target").click()
        """)
    tmp = _make_temp_test(source)
    try:
        # Report line_number=2 (the goto line), locator is actually on line 5
        patch = LocatorPatch(
            original_locator="#target",
            repaired_locator="#fixed",
            line_number=2,
            test_file=tmp,
        )
        result = apply_patch(patch)
        assert "#fixed" in result
        assert "#target" not in result
    finally:
        tmp.unlink()


def test_apply_patch_raises_when_locator_not_found() -> None:
    source = dedent("""\
        def test_example(page):
            page.goto("https://example.com")
            page.locator("#something-else").click()
        """)
    tmp = _make_temp_test(source)
    try:
        patch = LocatorPatch(
            original_locator="#nonexistent",
            repaired_locator="#fixed",
            line_number=1,
            test_file=tmp,
        )
        try:
            apply_patch(patch)
            raise AssertionError("Expected LocatorRepairError")
        except LocatorRepairError as e:
            assert e.expected_locator == "#nonexistent"
    finally:
        tmp.unlink()


def test_apply_patch_to_file_writes_disk() -> None:
    source = 'page.locator("#old").click()'
    tmp = _make_temp_test(source)
    try:
        patch = LocatorPatch(
            original_locator="#old",
            repaired_locator="#new",
            line_number=1,
            test_file=tmp,
        )
        apply_patch_to_file(patch)
        assert tmp.read_text(encoding="utf-8") == 'page.locator("#new").click()'
    finally:
        tmp.unlink()


def test_apply_patch_fallback_simple_replace() -> None:
    """When .locator() pattern doesn't match, fall back to string replace."""
    source = "result = some_func('#old-selector')"
    tmp = _make_temp_test(source)
    try:
        patch = LocatorPatch(
            original_locator="#old-selector",
            repaired_locator="#new-selector",
            line_number=1,
            test_file=tmp,
        )
        result = apply_patch(patch)
        assert "#new-selector" in result
        assert "#old-selector" not in result
    finally:
        tmp.unlink()


def test_apply_patch_multiline_test() -> None:
    """Patch correct line in a multi-line test without touching siblings."""
    source = dedent("""\
        def test_multi(page):
            page.goto("https://example.com")
            page.locator("#first").click()
            page.locator("#second").fill("value")
            page.locator("#third").press("Enter")
        """)
    tmp = _make_temp_test(source)
    try:
        patch = LocatorPatch(
            original_locator="#second",
            repaired_locator="[name='input']",
            line_number=4,
            test_file=tmp,
        )
        result = apply_patch(patch)
        lines = result.splitlines()
        assert "#first" in lines[2]
        assert "[name='input']" in lines[3]
        assert "#third" in lines[4]
    finally:
        tmp.unlink()
