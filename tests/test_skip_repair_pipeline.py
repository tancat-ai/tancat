"""Tests for the skip-repair extraction functions in src/ui/ui_run_results.py.

These functions extract steps before pytest.skip() calls and find URLs
for the skip-repair "Capture Locator" feature. They had zero test coverage
and contained multiple real bugs.
"""

from __future__ import annotations

from textwrap import dedent

from src.locator_repair import translate_setup_step_to_python

# Direct test of the extraction functions (they are pure logic, no Streamlit dependency)
from src.ui.ui_run_results import (
    _extract_all_steps_before_test,
    _extract_code_lines_before_skip,
    _extract_steps_before_skip,
    _find_skip_line_number,
    _find_url_before_skip,
)

# ---------------------------------------------------------------------------
# _find_skip_line_number
# ---------------------------------------------------------------------------


def test_find_skip_line_number_simple() -> None:
    source = dedent("""\
        def test_add_to_cart(page):
            evidence_tracker.navigate('https://example.com')
            page.locator("#add").click()
            pytest.skip("unresolved placeholder")
        """)
    result = _find_skip_line_number(source, "test_add_to_cart")
    assert result == 4  # 1-based


def test_find_skip_line_number_not_found() -> None:
    source = dedent("""\
        def test_add_to_cart(page):
            evidence_tracker.navigate('https://example.com')
            page.locator("#add").click()
        """)
    result = _find_skip_line_number(source, "test_add_to_cart")
    assert result is None


def test_find_skip_line_number_after_multiple_tests() -> None:
    source = dedent("""\
        def test_01_login(page):
            page.goto("https://example.com/login")
            page.locator("#login").click()

        def test_02_cart(page):
            pytest.skip("unresolved placeholder")

        def test_03_checkout(page):
            page.goto("https://example.com/checkout")
        """)
    result = _find_skip_line_number(source, "test_02_cart")
    assert result == 6


def test_find_skip_line_number_with_indent() -> None:
    source = dedent("""\
        def test_example(page):
            page.goto("https://example.com")
                pytest.skip("no element")
        """)
    result = _find_skip_line_number(source, "test_example")
    assert result == 3


# ---------------------------------------------------------------------------
# _find_url_before_skip
# ---------------------------------------------------------------------------


def test_find_url_before_skip_navigate() -> None:
    source = dedent("""\
        def test_add_to_cart(page):
            evidence_tracker.navigate('https://example.com/products')
            page.locator("#add").click()
            pytest.skip("unresolved placeholder")
        """)
    result = _find_url_before_skip(source, "test_add_to_cart", 4)
    assert result == "https://example.com/products"


def test_find_url_before_skip_page_goto() -> None:
    source = dedent("""\
        def test_add_to_cart(page):
            page.goto("https://example.com/products")
            page.locator("#add").click()
            pytest.skip("unresolved placeholder")
        """)
    result = _find_url_before_skip(source, "test_add_to_cart", 4)
    assert result == "https://example.com/products"


def test_find_url_before_skip_no_navigate() -> None:
    source = dedent("""\
        def test_add_to_cart(page):
            page.locator("#add").click()
            pytest.skip("unresolved placeholder")
        """)
    result = _find_url_before_skip(source, "test_add_to_cart", 3)
    assert result is None


def test_find_url_before_skip_uses_last_navigate() -> None:
    """Should return the last navigate/goto before the skip."""
    source = dedent("""\
        def test_add_to_cart(page):
            evidence_tracker.navigate('https://example.com')
            page.locator("#cat").click()
            evidence_tracker.navigate('https://example.com/products')
            pytest.skip("unresolved placeholder")
        """)
    result = _find_url_before_skip(source, "test_add_to_cart", 5)
    assert result == "https://example.com/products"


def test_find_url_before_skip_other_test_navigate_not_picked_up() -> None:
    """Should not return navigate calls from other tests before this one."""
    source = dedent("""\
        def test_01_login(page):
            evidence_tracker.navigate('https://example.com/login')

        def test_02_cart(page):
            page.locator("#cart").click()
            pytest.skip("unresolved placeholder")
        """)
    result = _find_url_before_skip(source, "test_02_cart", 5)
    assert result is None


# ---------------------------------------------------------------------------
# _extract_steps_before_skip — returns raw code lines in the target test
# ---------------------------------------------------------------------------


def test_extract_steps_before_skip_includes_navigate() -> None:
    """BUG FIX: the old regex missed evidence_tracker.navigate() calls."""
    source = dedent("""\
        def test_add_to_cart(page):
            evidence_tracker.navigate('https://example.com')
            page.locator("#add").click()
            pytest.skip("unresolved placeholder")
        """)
    result = _extract_steps_before_skip(source, "test_add_to_cart", 4)
    assert len(result) == 2
    assert "evidence_tracker.navigate('https://example.com')" in result[0]
    assert 'page.locator("#add").click()' in result[1]


def test_extract_steps_before_skip_includes_page_goto() -> None:
    """BUG FIX: the old regex missed page.goto() calls."""
    source = dedent("""\
        def test_add_to_cart(page):
            page.goto("https://example.com/products")
            page.locator("#add").click()
            pytest.skip("unresolved placeholder")
        """)
    result = _extract_steps_before_skip(source, "test_add_to_cart", 4)
    assert len(result) == 2
    assert 'page.goto("https://example.com/products")' in result[0]


def test_extract_steps_before_skip_does_not_include_other_test() -> None:
    """Should only extract steps within the target test function."""
    source = dedent("""\
        def test_01_login(page):
            page.goto("https://example.com/login")
            page.locator("#login").click()

        def test_02_cart(page):
            page.locator("#cart").click()
            pytest.skip("unresolved placeholder")
        """)
    result = _extract_steps_before_skip(source, "test_02_cart", 6)
    # Should NOT include login steps
    assert all("login" not in step for step in result)
    assert len(result) == 1
    assert "cart" in result[0]


def test_extract_steps_before_skip_no_steps() -> None:
    source = dedent("""\
        def test_add_to_cart(page):
            pytest.skip("immediate skip")
        """)
    result = _extract_steps_before_skip(source, "test_add_to_cart", 2)
    assert result == []


def test_extract_steps_before_skip_evidence_tracker_actions_only() -> None:
    """Should not include assert_visible or other non-action lines."""
    source = dedent("""\
        def test_add_to_cart(page):
            evidence_tracker.navigate('https://example.com')
            page.locator("#add").click()
            evidence_tracker.assert_visible('#popup', label='confirmation')
            pytest.skip("unresolved placeholder")
        """)
    result = _extract_steps_before_skip(source, "test_add_to_cart", 5)
    # Should include navigate and click, NOT assert_visible
    step_texts = " ".join(result)
    assert "navigate" in step_texts
    assert "click()" in step_texts
    assert "assert_visible" not in step_texts


# ---------------------------------------------------------------------------
# _extract_all_steps_before_test — returns steps from ALL tests before target
# ---------------------------------------------------------------------------


def test_extract_all_steps_before_test_single_prior_test() -> None:
    source = dedent("""\
        def test_01_login(page):
            evidence_tracker.navigate('https://example.com/login')
            page.locator("#login").click()

        def test_02_cart(page):
            pytest.skip("unresolved placeholder")
        """)
    result = _extract_all_steps_before_test(source, "test_02_cart")
    assert len(result) == 2
    assert any("navigate" in s for s in result)
    assert any("login" in s for s in result)


def test_extract_all_steps_before_test_includes_navigate() -> None:
    """BUG FIX: the old regex missed navigate/goto calls in prior tests."""
    source = dedent("""\
        def test_01_login(page):
            evidence_tracker.navigate('https://example.com/login')
            page.locator("#login").click()

        def test_02_cart(page):
            page.goto("https://example.com/cart")
            page.locator("#checkout").click()

        def test_03_checkout(page):
            pytest.skip("unresolved placeholder")
        """)
    result = _extract_all_steps_before_test(source, "test_03_checkout")
    combined = " ".join(result)
    # Should include navigate and goto
    assert "evidence_tracker.navigate" in combined
    assert "page.goto" in combined


def test_extract_all_steps_before_test_target_is_first() -> None:
    """If target is the first test, no steps should be returned."""
    source = dedent("""\
        def test_01_home(page):
            pytest.skip("unresolved placeholder")

        def test_02_login(page):
            page.goto("https://example.com/login")
        """)
    result = _extract_all_steps_before_test(source, "test_01_home")
    assert result == []


def test_extract_all_steps_before_test_ignores_assert_visible() -> None:
    """assert_visible and other non-action lines should not appear."""
    source = dedent("""\
        def test_01_login(page):
            evidence_tracker.navigate('https://example.com/login')
            page.locator("#login").click()
            evidence_tracker.assert_visible('#welcome', label='welcome')

        def test_02_cart(page):
            pytest.skip("unresolved placeholder")
        """)
    result = _extract_all_steps_before_test(source, "test_02_cart")
    combined = " ".join(result)
    assert "navigate" in combined
    assert "click()" in combined
    assert "assert_visible" not in combined


def test_extract_all_steps_before_test_multiple_prior_tests() -> None:
    source = dedent("""\
        def test_01_login(page):
            evidence_tracker.navigate('https://example.com/login')
            page.locator("#user").fill("user")

        def test_02_cart(page):
            evidence_tracker.navigate('https://example.com/cart')
            page.locator("#add").click()

        def test_03_checkout(page):
            pytest.skip("unresolved placeholder")
        """)
    result = _extract_all_steps_before_test(source, "test_03_checkout")
    combined = " ".join(result)
    assert "navigate('https://example.com/login')" in combined
    assert "navigate('https://example.com/cart')" in combined
    assert "#user" in combined
    assert "#add" in combined


# ---------------------------------------------------------------------------
# translate_setup_step_to_python — test the new navigate handling
# ---------------------------------------------------------------------------


def test_translate_evidence_tracker_navigate() -> None:
    """BUG FIX: navigate() calls were silently dropped."""
    lines = translate_setup_step_to_python("evidence_tracker.navigate('https://example.com/products')")
    joined = "\n".join(lines)
    assert "page.goto('https://example.com/products')" in joined


def test_translate_page_goto() -> None:
    """BUG FIX: page.goto() calls were silently dropped."""
    lines = translate_setup_step_to_python("page.goto('https://example.com/products')")
    joined = "\n".join(lines)
    assert "page.goto('https://example.com/products')" in joined


def test_translate_evidence_tracker_navigate_double_quotes() -> None:
    lines = translate_setup_step_to_python('evidence_tracker.navigate("https://example.com/products")')
    joined = "\n".join(lines)
    assert "page.goto('https://example.com/products')" in joined


def test_translate_pom_click_still_works_alongside_navigate() -> None:
    """Existing pom_click should still work after adding navigate handling."""
    lines = translate_setup_step_to_python("home_page.click('Dress')")
    joined = "\n".join(lines)
    assert "get_by_role('link', name='Dress')" in joined


def test_translate_evidence_tracker_fill_with_label_still_works() -> None:
    """Existing evidence_tracker fill handling should still work."""
    lines = translate_setup_step_to_python("evidence_tracker.click('.add-to-cart.btn', label='Add to cart')")
    joined = "\n".join(lines)
    assert "get_by_text('Add to cart')" in joined


# ---------------------------------------------------------------------------
# _extract_code_lines_before_skip — fallback display when no actionable steps
# ---------------------------------------------------------------------------


def test_extract_code_lines_before_skip_includes_all_lines() -> None:
    """Should return ALL code lines before the skip, not just action lines."""
    source = dedent("""\
        def test_add_to_cart(page):
            evidence_tracker.navigate('https://example.com')
            page.locator("#add").click()
            evidence_tracker.assert_visible('#popup', label='popup')
            pytest.skip("unresolved placeholder")
        """)
    result = _extract_code_lines_before_skip(source, "test_add_to_cart", 5)
    assert len(result) == 3  # all 3 non-empty, non-comment lines before skip
    assert any("navigate" in s for s in result)
    assert any("click()" in s for s in result)
    assert any("assert_visible" in s for s in result)


def test_extract_code_lines_before_skip_skips_comments_and_blanks() -> None:
    """Pure comment lines (starting with #) should be excluded, even if
    other lines contain # inside a string like '#add'."""
    source = dedent("""\
        def test_add_to_cart(page):
            # comment line
            evidence_tracker.navigate('https://example.com')
            page.locator("#add").click()
            pytest.skip("unresolved placeholder")
        """)
    result = _extract_code_lines_before_skip(source, "test_add_to_cart", 5)
    # Should contain 2 code lines (not the comment or skip)
    assert len(result) == 2
    # Check that no line IS a comment (starts with # after strip)
    assert not any(s.strip().startswith("#") for s in result)


def test_extract_code_lines_before_skip_empty_test() -> None:
    source = dedent("""\
        def test_add_to_cart(page):
            pytest.skip("immediate skip")
        """)
    result = _extract_code_lines_before_skip(source, "test_add_to_cart", 2)
    assert result == []


def test_extract_code_lines_before_skip_stops_at_next_def() -> None:
    """Should not include lines from the next test."""
    source = dedent("""\
        def test_01_login(page):
            page.goto("https://example.com/login")
            pytest.skip("unresolved placeholder")

        def test_02_cart(page):
            page.locator("#cart").click()
            pytest.skip("unresolved placeholder")
        """)
    result = _extract_code_lines_before_skip(source, "test_01_login", 3)
    assert len(result) == 1
    assert "login" in result[0]
    assert "cart" not in " ".join(result)


# ---------------------------------------------------------------------------
# _find_url_before_skip doesn't pick navigate from prior test (regression)
# ---------------------------------------------------------------------------


def test_find_url_before_skip_from_prior_test_not_picked() -> None:
    """Regression check: navigate in prior test ≠ navigate in target test."""
    source = dedent("""\
        def test_01_login(page):
            evidence_tracker.navigate('https://example.com/login')
            page.locator("#login").click()

        def test_02_cart(page):
            page.locator("#cart").click()
            pytest.skip("unresolved placeholder")
        """)
    result = _find_url_before_skip(source, "test_02_cart", 6)
    assert result is None
