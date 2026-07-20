"""Run results display, failure classification, and locator repair panel."""

from __future__ import annotations

import re
from pathlib import Path

import streamlit as st

from src.coverage_utils import build_coverage_analysis, build_coverage_display_rows
from src.failure_classifier import classify_failure
from src.locator_repair import SetupScriptResult, run_codegen_session, translate_setup_step_to_python
from src.pytest_output_parser import RunResult, TestResult
from src.self_healing import HealingReport, SelfHealingRunner
from src.ui.ui_results import _handle_run_tests
from src.url_utils import normalize_url_path


def _parse_condition_refs_from_source(source: str) -> dict[str, str]:
    """Extract condition_ref mappings from @pytest.mark.evidence decorators.

    Returns a dict mapping test function name → condition_ref (e.g. 'TC01.05').
    """
    mapping: dict[str, str] = {}
    pattern = re.compile(
        r"@pytest\.mark\.evidence\(condition_ref=[\"']([^\"']+)[\"'].*?\)\s*\n\s*def (test_\w+)",
        re.MULTILINE,
    )
    for match in pattern.finditer(source):
        condition_ref = match.group(1)
        test_name = match.group(2)
        mapping[test_name] = condition_ref
    return mapping


def _extract_error_from_raw_output(raw_output: str, test_name: str) -> str:
    """Extract the error message for a specific test from raw pytest output.

    Searches the FAILURES block for the test's error details when the
    TestResult.error_message is empty (common for timeout/locator failures).
    """
    if not raw_output or not test_name:
        return ""
    failures_start = raw_output.find("FAILURES")
    if failures_start == -1:
        short_pattern = re.compile(rf"FAILED\s+\S+::{re.escape(test_name)}\s*-\s*(.+)")
        short_match = short_pattern.search(raw_output)
        return short_match.group(1).strip() if short_match else ""
    failures_section = raw_output[failures_start:]
    name_pattern = re.compile(rf"_+\s*{re.escape(test_name)}\s*_+")
    name_match = name_pattern.search(failures_section)
    if not name_match:
        short_pattern = re.compile(rf"FAILED\s+\S+::{re.escape(test_name)}\s*-\s*(.+)")
        short_match = short_pattern.search(raw_output)
        return short_match.group(1).strip() if short_match else ""
    pos = name_match.end()
    next_boundary = re.search(r"_+\s+test_\w+\s*_+|^=+", failures_section[pos:], re.MULTILINE)
    if next_boundary:
        error_block = failures_section[pos : pos + next_boundary.start()]
    else:
        error_block = failures_section[pos:]
    lines = error_block.strip().split("\n")
    meaningful: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("E   ") or "Error" in stripped:
            meaningful.append(stripped)
        elif meaningful:
            meaningful.append(stripped)
    return "\n".join(meaningful) if meaningful else error_block.strip()


def _extract_last_steps_before_failure(source: str, test_name: str) -> list[str]:
    """Extract the last completed action steps before a test failure.

    Parses the test source to find evidence_tracker / page object method calls
    showing what completed before the failure point.
    """
    if not source or not test_name:
        return []
    escaped = re.escape(test_name)
    func_pattern = re.compile(rf"def {escaped}\(.*?\):\s*\n", re.MULTILINE)
    func_match = func_pattern.search(source)
    if not func_match:
        return []
    body_start = func_match.end()
    next_def = re.search(r"^def \w+", source[body_start:], re.MULTILINE)
    body_end = body_start + next_def.start() if next_def else len(source)
    body = source[body_start:body_end]
    step_pattern = re.compile(
        r"(?:evidence_tracker|\w+_page|\w+Page)\.(\w+)\((.+?)\)",
        re.MULTILINE,
    )
    steps: list[str] = []
    for sm in step_pattern.finditer(body):
        method = sm.group(1)
        args_raw = sm.group(2).strip()
        first_arg = args_raw.split(",")[0].strip().strip("'\"")
        if len(first_arg) > 50:
            first_arg = first_arg[:47] + "..."
        if method in ("navigate", "goto"):
            steps.append(f"Navigate to {first_arg}")
        elif method == "click":
            steps.append(f"Click '{first_arg}'")
        elif method in ("fill", "type"):
            steps.append(f"Fill '{first_arg}'")
        elif method in ("assert_visible", "assert_text", "assert_text_contains"):
            steps.append(f"Assert '{first_arg}'")
        elif method == "select_option":
            steps.append(f"Select '{first_arg}'")
    return steps[-6:]


def _get_generated_code_for_coverage() -> str:
    """Get generated test code for coverage analysis.

    Prefers reading the actual saved test file(s) over session state,
    because pipeline_results may be stale (e.g., from a previous run
    or empty when loading a saved package).
    """
    # First try session state (normal flow — just generated)
    code = st.session_state.get("pipeline_results") or ""
    if code.strip():
        return code
    # Fallback: read from the saved test file(s)
    saved_path = st.session_state.get("pipeline_saved_path", "")
    if saved_path:
        return _read_test_code_from_path(saved_path)
    return ""


def _read_test_code_from_path(saved_path: str) -> str:
    """Read test code from a saved test file or package directory.

    Handles both flat mode (single .py file) and POM mode (directory with
    multiple test files).
    """
    path = Path(saved_path)
    if path.is_file():
        return path.read_text(encoding="utf-8")
    if path.is_dir():
        # POM mode: concatenate all .py test files (skip __init__.py, conftest.py)
        parts: list[str] = []
        for py_file in sorted(path.rglob("*.py")):
            if py_file.name in ("__init__.py", "conftest.py"):
                continue
            parts.append(py_file.read_text(encoding="utf-8"))
        return "\n".join(parts)
    return ""


def _find_skip_line_number(source: str, test_name: str) -> int | None:
    """Find the line number (1-based) of the pytest.skip() in a test function."""
    lines = source.splitlines()
    in_test = False
    test_def_pattern = re.compile(rf"^def\s+{re.escape(test_name)}\b")

    for i, line in enumerate(lines):
        stripped = line.strip()
        if test_def_pattern.match(stripped):
            in_test = True
            continue
        if in_test:
            if stripped.startswith("def ") and not test_def_pattern.match(stripped):
                break
            if "pytest.skip(" in stripped:
                return i + 1  # 1-based
    return None


def _find_url_before_skip(source: str, test_name: str, skip_line: int) -> str | None:
    """Find the URL the test navigates to before the pytest.skip() line.

    Looks for evidence_tracker.navigate('url') or page.goto('url') calls
    before the skip line within the test function. Returns the *last*
    navigation URL before the skip (a test may navigate multiple times).
    """
    lines = source.splitlines()
    in_test = False
    last_url: str | None = None
    navigate_pattern = re.compile(r"(?:evidence_tracker\.navigate\(|page\.goto\()\s*['\"]([^'\"]+)['\"]")
    test_def_pattern = re.compile(rf"^def\s+{re.escape(test_name)}\b")

    for line in lines:
        stripped = line.strip()
        if test_def_pattern.match(stripped):
            in_test = True
            continue
        if in_test:
            if stripped.startswith("def ") and not test_def_pattern.match(stripped):
                break
            # Check if we've reached the skip line
            if "pytest.skip(" in stripped:
                break
            # Look for navigate calls before the skip — keep the *last* one
            match = navigate_pattern.search(line)
            if match:
                last_url = match.group(1)

    return last_url


def _extract_steps_before_skip(source: str, test_name: str, skip_line: int) -> list[str]:
    """Extract the action steps (clicks, fills, etc.) before the pytest.skip() line.

    Returns a list of raw python code lines that the user needs to
    execute manually before capturing the missing locator.
    """
    lines = source.splitlines()
    in_test = False
    steps: list[str] = []
    action_pattern = re.compile(
        r"(?:evidence_tracker\.(?:navigate|click|fill|select|check|uncheck)\(|"
        r"page\.goto\(|"
        r"(?:home_page|category_product_page|cart_page|products_page|generated_page)\.(?:click|fill|select)\(|"
        r"page\.locator\([^)]+\)\.(?:click|fill|select)\()"
    )
    test_def_pattern = re.compile(rf"^def\s+{re.escape(test_name)}\b")

    for line in lines:
        stripped = line.strip()
        if test_def_pattern.match(stripped):
            in_test = True
            continue
        if in_test:
            if stripped.startswith("def ") and not test_def_pattern.match(stripped):
                break
            # Check if we've reached the skip line
            if "pytest.skip(" in stripped:
                break
            # Look for action calls before the skip
            if action_pattern.search(line):
                steps.append(stripped)

    return steps


def _extract_code_lines_before_skip(source: str, test_name: str, skip_line: int) -> list[str]:
    """Extract the actual code lines before the pytest.skip() line for display.

    Unlike _extract_steps_before_skip (which only returns action lines that
    can be automated), this returns ALL code lines so the user can see the
    full context of what the test does before the skip point.

    Returns a list of code lines (empty lines and comments excluded).
    """
    lines = source.splitlines()
    in_test = False
    code_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith(f"def {test_name}("):
            in_test = True
            continue
        if in_test:
            if stripped.startswith("def ") and not stripped.startswith(f"def {test_name}("):
                break
            # Check if we've reached the skip line
            if "pytest.skip(" in stripped:
                break
            # Collect code lines (skip empty lines and comments)
            if stripped and not stripped.startswith("#"):
                code_lines.append(stripped)

    return code_lines


def _extract_all_steps_before_test(source: str, test_name: str) -> list[str]:
    """Extract all action steps from all tests before the given test.

    This is used to set up the page state for a test that depends on
    previous tests (e.g., adding items to cart before checkout).
    Includes navigation calls (page.goto, evidence_tracker.navigate) so
    the prerequisite script actually navigates to the right pages.

    Returns a list of raw python code lines.
    """
    lines = source.splitlines()
    in_test = False
    steps: list[str] = []
    action_pattern = re.compile(
        r"(?:evidence_tracker\.(?:navigate|click|fill|select|check|uncheck)\(|"
        r"page\.goto\(|"
        r"(?:home_page|category_product_page|cart_page|products_page|generated_page)\.(?:click|fill|select)\(|"
        r"page\.locator\([^)]+\)\.(?:click|fill|select)\()"
    )
    test_def_pattern = re.compile(rf"^def\s+{re.escape(test_name)}\b")

    for line in lines:
        stripped = line.strip()
        if test_def_pattern.match(stripped):
            break

        if stripped.startswith("def test_"):
            in_test = True
            continue

        if in_test:
            if stripped.startswith("def "):
                in_test = False
                continue

            if action_pattern.search(line):
                steps.append(stripped)

    return steps


def _render_skipped_tests_info(results: list[TestResult]) -> None:
    """Render information about skipped tests, showing why they were skipped."""
    skipped = [r for r in results if r.status == "skipped"]
    if not skipped:
        return

    st.divider()
    st.subheader("⏭️ Skipped Tests")

    # Try to extract skip reasons from the test file source
    saved_path = st.session_state.get("pipeline_saved_path", "")
    skip_reasons: dict[str, str] = {}
    skip_lines: dict[str, int] = {}
    skip_urls: dict[str, str] = {}
    if saved_path:
        try:
            source = _read_test_code_from_path(saved_path)
            for test in skipped:
                # Find pytest.skip() inside this test function
                pattern = re.compile(
                    rf"def {re.escape(test.name)}\(.*?\).*?pytest\.skip\((.*?)\)",
                    re.DOTALL,
                )
                match = pattern.search(source)
                if match:
                    reason = match.group(1).strip().strip("'\"")
                    skip_reasons[test.name] = reason
                # Track line number too
                ln = _find_skip_line_number(source, test.name)
                if ln:
                    skip_lines[test.name] = ln
                    # Find the URL before the skip
                    url = _find_url_before_skip(source, test.name, ln)
                    if url:
                        skip_urls[test.name] = normalize_url_path(url)
        except Exception:
            pass

    for test in skipped:
        reason = skip_reasons.get(test.name, "Unresolved placeholder — element could not be located on the page")
        is_unresolved = "unresolved" in reason.lower()
        with st.expander(f"⏭️ {test.name}", expanded=False):
            st.write(f"**Reason:** {reason}")
            if is_unresolved:
                st.info(
                    "This test contains steps that could not be mapped to elements on the page. "
                    "To fix this, you can:\n"
                    "1. Check that the target website matches the requirement description\n"
                    "2. Ensure the site is loaded correctly (check the base URL)\n"
                    "3. Re-run the pipeline with a more specific description for the unresolved steps"
                )
            if is_unresolved and saved_path:
                # Extract steps before the skip point AND all steps from previous tests
                source = _read_test_code_from_path(saved_path)
                line_num = skip_lines.get(test.name, 1)
                steps_before = _extract_steps_before_skip(source, test.name, line_num)
                # Also get steps from all previous tests to set up state
                all_previous_steps = _extract_all_steps_before_test(source, test.name)
                # Combine: previous test steps + current test steps before skip
                setup_steps = all_previous_steps + steps_before
                # Display ONLY the current test's steps as context
                if steps_before:
                    st.write("**Steps in this test before the skip point:**")
                    for step in steps_before:
                        st.write(f"  - {step}")
                else:
                    # Fallback: show the full code context so the user can see what the test does
                    code_context = _extract_code_lines_before_skip(source, test.name, line_num)
                    if code_context:
                        st.write("**Test code before the skip point (for reference):**")
                        st.code("\n".join(code_context), language="python")
                # Show the unresolved step explicitly so the user knows what to record
                if "unresolved placeholders for:" in reason:
                    unresolved_match = re.search(r"unresolved placeholders for: (.+)", reason)
                    if unresolved_match:
                        unresolved_text = unresolved_match.group(1)
                        st.write("**🔴 Unresolved step — record this action:**")
                        st.markdown(unresolved_text)
                if all_previous_steps:
                    st.caption("Prior test steps will be replayed automatically to set up page state.")
                if st.button("🖱️ Capture Locator", key=f"fix_skip_{test.name}", type="primary"):
                    st.session_state.skip_repair_test_name = test.name
                    st.session_state.skip_repair_line = line_num
                    st.session_state.skip_repair_file = saved_path
                    st.session_state.skip_repair_url = skip_urls.get(test.name, "")
                    st.session_state.skip_repair_steps = setup_steps
                    st.session_state.skip_repair_status = "browser_opening"
                    st.rerun()


def _render_skip_repair_panel() -> None:
    """Render the skip repair panel — opens codegen and replaces pytest.skip() with a real action."""
    repair_status = st.session_state.get("skip_repair_status")
    if repair_status is None:
        return

    if repair_status == "waiting":
        _render_skip_repair_waiting()
    elif repair_status == "browser_opening":
        _render_skip_repair_capture()
    elif repair_status in ("patched", "error"):
        _render_skip_repair_result()


def _render_skip_repair_waiting() -> None:
    """Show explanation before opening the browser for skipped test fix."""
    test_name = st.session_state.get("skip_repair_test_name", "unknown")
    target_url = (
        st.session_state.get("skip_repair_url", "")
        or st.session_state.get("starting_url", "")
        or st.session_state.get("last_starting_url", "")
    )
    steps_before = st.session_state.get("skip_repair_steps", [])
    st.divider()
    st.subheader("🖱️ Capture Locator for Skipped Test")

    st.write(f"**Test:** {test_name}")

    if steps_before:
        st.info(
            "The browser will open and automatically execute the prerequisite steps to set up the page state. "
            "Then you can click the element that was missing from the page. "
            "The `pytest.skip()` line will be replaced with the captured locator.\n\n"
            f"**Target URL:** {target_url}\n\n"
            "**Steps to be executed:**"
        )
        st.code("\n".join(steps_before), language="python")
    else:
        st.info(
            "The browser will open at the page where this test got stuck. "
            "Click the element that was missing from the page. "
            "The `pytest.skip()` line will be replaced with the captured locator.\n\n"
            f"**Target URL:** {target_url}"
        )

    fix_col, cancel_col = st.columns([1, 1])
    with fix_col:
        if st.button("🌐 Open browser and click element", type="primary"):
            st.session_state.skip_repair_status = "browser_opening"
            st.rerun()
    with cancel_col:
        if st.button("Cancel"):
            st.session_state.skip_repair_status = None
            st.rerun()


def _render_skip_repair_capture() -> None:
    """Run codegen and capture the locator, then replace pytest.skip() in the test file."""
    raw_target_url = (
        st.session_state.get("skip_repair_url", "")
        or st.session_state.get("starting_url", "")
        or st.session_state.get("last_starting_url", "")
    )
    target_url = normalize_url_path(raw_target_url)
    test_file = st.session_state.get("skip_repair_file", "")
    test_name = st.session_state.get("skip_repair_test_name", "")
    line_number = st.session_state.get("skip_repair_line", 1)
    steps_before = st.session_state.get("skip_repair_steps", [])

    if not target_url or not test_file or not test_name:
        st.session_state.skip_repair_status = "error"
        st.session_state.skip_repair_message = "❌ Missing target URL or test file path."
        st.rerun()

    state_file = None
    codegen_url = target_url
    setup_warnings: list[str] = []
    if steps_before:
        base_url = st.session_state.get("starting_url", "") or st.session_state.get("last_starting_url", "")
        with st.spinner("⏳ Running prerequisite steps to set up page state..."):
            setup_result = _run_setup_script(base_url, target_url, steps_before)
        state_file = setup_result.state_file
        if setup_result.page_url:
            codegen_url = setup_result.page_url
        if not state_file:
            setup_warnings.append(
                "⚠️ Could not save browser state — the cart may be empty. "
                "You may need to manually add an item to the cart before capturing the locator."
            )
        elif state_file and Path(state_file).exists():
            import os

            state_size = os.path.getsize(state_file)
            if state_size < 100:
                setup_warnings.append(
                    f"⚠️ Saved state file is very small ({state_size} bytes) — cart state may not have been captured."
                )

    if setup_warnings:
        for warning in setup_warnings:
            st.warning(warning)

    spinner_text = (
        f"⏳ Browser is opening at `{codegen_url}` — "
        "close the browser window after clicking the element you want to use..."
    )
    with st.spinner(spinner_text):
        replacement = run_codegen_session(codegen_url, timeout_seconds=180, state_file=state_file)

    if replacement:
        try:
            # Read the current source
            path = Path(test_file)
            source = path.read_text(encoding="utf-8")
            lines = source.splitlines()
            line_idx = line_number - 1  # 0-based

            if line_idx >= len(lines):
                st.session_state.skip_repair_status = "error"
                st.session_state.skip_repair_message = f"❌ Line {line_number} does not exist in the test file."
                st.rerun()

            old_line = lines[line_idx]
            if "pytest.skip" not in old_line:
                raise ValueError(f"Line {line_number} does not contain `pytest.skip`: {old_line.strip()}")
            indent = " " * (len(old_line) - len(old_line.lstrip()))
            # Replace the pytest.skip() line with a capture locator click
            new_line = f"{indent}page.locator({replacement!r}).click()"
            lines[line_idx] = new_line
            patched_source = "\n".join(lines)
            path.write_text(patched_source, encoding="utf-8")

            if (
                st.session_state.get("pipeline_results")
                and not Path(st.session_state.get("pipeline_saved_path", "")).is_dir()
            ):
                st.session_state.pipeline_results = patched_source

            st.session_state.skip_repair_status = "patched"
            st.session_state.skip_repair_message = (
                f"✅ `pytest.skip()` replaced with `page.locator({replacement!r}).click()` "
                f"on line {line_number} of `{test_file}`.\n\n"
                "You may need to edit the action type (e.g. `.click()` → `.fill('value')`).\n"
                "Click **▶️ Run Generated Tests** to verify the fix."
            )
        except Exception as exc:
            st.session_state.skip_repair_status = "error"
            st.session_state.skip_repair_message = f"❌ Could not apply fix: {exc}"
    else:
        st.session_state.skip_repair_status = "error"
        st.session_state.skip_repair_message = "❌ No locator captured. The browser may have timed out or been closed."

    st.rerun()


def _run_setup_script(base_url: str, target_url: str, steps: list[str]) -> SetupScriptResult:
    """Run a setup script to execute prerequisite steps, and save the browser state.

    This creates a temporary script that navigates to the base URL, executes the
    given steps (from all previous tests), and saves the context storage state
    (cookies, localStorage) to a temporary JSON file.

    Returns:
        SetupScriptResult with the saved state file path and final page URL.
    """
    import os
    import subprocess
    import sys
    import tempfile
    from urllib.parse import urljoin, urlparse

    normalized_base = normalize_url_path(base_url)
    normalized_target = normalize_url_path(target_url)

    state_file = os.path.join(tempfile.gettempdir(), f"repair_state_{os.urandom(4).hex()}.json")
    page_url_file = f"{state_file}.url"

    # Detect if we need cart seeding — when we navigate to a cart/checkout page
    # but no prior steps add items, the cart will be empty.
    _target_path = urlparse(normalized_target).path.rstrip("/")
    _needs_cart_seeding = _target_path in ("/view_cart", "/checkout")

    script_lines = [
        "from playwright.sync_api import sync_playwright",
        "import re as _re",
        "from urllib.parse import urljoin",
        "",
        "def _dismiss_banners(page, timeout=2000):",
        "    '''Best-effort dismissal of cookie/consent banners.'''",
        "    try: page.keyboard.press('Escape'); page.wait_for_timeout(300)",
        "    except Exception: pass",
        "    # Common consent button patterns",
        "    _btn_texts = [",
        "        'Consent', 'Accept', 'Accept All', 'OK', 'Got it',",
        "        'Got It', 'I Agree', 'Agree', 'Allow', 'Allow All',",
        "    ]",
        "    for btn_text in _btn_texts:",
        "        try:",
        "            btn = page.locator(f'button:has-text(\"{btn_text}\")').first",
        "            if btn.count() > 0 and btn.is_visible(timeout=500):",
        "                btn.click(timeout=2000)",
        "                page.wait_for_timeout(500)",
        "                break",
        "        except Exception: continue",
        "    # Remove Google Consent TVM via JS",
        "    try:",
        "        page.evaluate('''",
        "            () => {",
        "                const el = document.querySelector('.fc-consent-root');",
        "                if (el) el.remove();",
        "                const overlay = document.querySelector('.fc-dialog-overlay');",
        "                if (overlay) overlay.remove();",
        "            }''');",
        "        page.wait_for_timeout(300)",
        "    except Exception: pass",
        "",
        "try:",
        "    with sync_playwright() as p:",
        "        browser = p.chromium.launch(headless=True)",
        "        context = browser.new_context()",
        "        page = context.new_page()",
        f"        page.goto({normalized_base!r})",
        "        page.wait_for_timeout(1500)",
        "        _dismiss_banners(page)",
    ]

    # Cart-seeding: add an item to the cart before navigating to a cart/checkout page.
    # Without this, the cart page will be empty and "Proceed to checkout" etc. won't exist.
    if _needs_cart_seeding:
        _products_url = urljoin(normalized_base, "/products")
        script_lines.extend(
            [
                f"        print('[setup] Cart seeding: navigating to {_products_url}')",
                f"        page.goto({_products_url!r})",
                "        page.wait_for_load_state('networkidle')",
                "        page.wait_for_timeout(1000)",
                "        _dismiss_banners(page)",
                "        page.wait_for_timeout(500)",
                # Try two strategies: (A) hover to reveal overlay Add-to-cart, (B) click into product detail
                "        added_to_cart = False",
                "        # Strategy A: hover over a product card to reveal the overlay Add to cart button",
                "        _card_sel = '.product-image-wrapper, .single-products, .productinfo, .product-overlay'",
                "        product_cards = page.locator(_card_sel)",
                "        print(f'[setup] Found {product_cards.count()} product cards')",
                "        for i in range(min(product_cards.count(), 4)):",
                "            try:",
                "                card = product_cards.nth(i)",
                "                if not card.is_visible(timeout=500):",
                "                    continue",
                "                card.hover()",
                "                page.wait_for_timeout(800)",
                "                # Try multiple selector patterns for Add to cart",
                '                _add_sel = \'a:has-text("Add to cart"), button:has-text("Add to cart"), a.add-to-cart, .overlay-content a\'',
                "                add_btn = card.locator(_add_sel).first",
                "                if add_btn.count() > 0 and add_btn.is_visible(timeout=500):",
                "                    print(f'[setup] Clicking Add to cart via hover on card {i}')",
                "                    add_btn.click(force=True)",
                "                    page.wait_for_timeout(1500)",
                "                    added_to_cart = True",
                "                    break",
                "            except Exception as e:",
                "                print(f'[setup] Strategy A card {i} failed: {{e}}')",
                "                continue",
                "        # Strategy B: fallback — click first product link, then Add to cart on detail page",
                "        if not added_to_cart:",
                "            print('[setup] Strategy A failed, trying Strategy B')",
                "            product_link = page.locator(\"a[href*='/product_details/']\").first",
                "            if product_link.count() > 0:",
                "                product_link.click()",
                "                page.wait_for_load_state('networkidle')",
                "                page.wait_for_timeout(1000)",
                "                _dismiss_banners(page)",
                "                page.wait_for_timeout(500)",
                '                add_btn = page.locator(\'button:has-text("Add to cart"), a:has-text("Add to cart")\').first',
                "                if add_btn.count() > 0 and add_btn.is_visible(timeout=1000):",
                "                    print('[setup] Clicking Add to cart on product detail page')",
                "                    add_btn.click()",
                "                    page.wait_for_timeout(1500)",
                "                    added_to_cart = True",
                "        # Dismiss the confirmation modal / added-to-cart popup",
                "        if added_to_cart:",
                "            print('[setup] Product added to cart, dismissing modal')",
                "            # Wait for confirmation modal",
                "            page.wait_for_timeout(1000)",
                "            continue_btn = page.locator('button:has-text(\"Continue Shopping\"), .close-modal, .modal-footer button').first",
                "            if continue_btn.count() > 0 and continue_btn.is_visible(timeout=2000):",
                "                continue_btn.click()",
                "                page.wait_for_timeout(1000)",
                "            else:",
                "                # Modal might have auto-dismissed or used a different pattern",
                "                page.wait_for_timeout(1500)",
                "        else:",
                "            print('[setup] WARNING: Could not add any product to cart!')",
                "        # Navigate to the TARGET page (view_cart/checkout) to verify cart has items",
                "        # and to establish the correct page context for codegen.",
                f'        print("[setup] Navigating to target: {normalized_target!r}")',
                f"        page.goto({normalized_target!r})",
                "        page.wait_for_load_state('networkidle')",
                "        page.wait_for_timeout(1500)",
                "        _dismiss_banners(page)",
                "        page.wait_for_timeout(500)",
                "        # Verify cart is not empty — log a warning if it appears empty",
                "        _empty_cart_el = page.locator('#empty_cart, .cart_empty, [id*=\"empty\"]').first",
                "        if _empty_cart_el.count() > 0 and _empty_cart_el.is_visible(timeout=1000):",
                "            print('[setup] WARNING: Cart appears to be empty — Proceed to checkout may not be visible')",
                "        else:",
                "            print('[setup] Cart has items — ready for checkout')",
                "        # Now navigate BACK to base URL so replay steps have a clean starting point",
                f'        print("[setup] Returning to base URL for step replay: {normalized_base!r}")',
                f"        page.goto({normalized_base!r})",
                "        page.wait_for_timeout(1000)",
                "        _dismiss_banners(page)",
                "        page.wait_for_timeout(500)",
            ]
        )

    for step in steps:
        # Short wait between replay steps for page stability
        script_lines.append("        page.wait_for_timeout(300)")
        translated = translate_setup_step_to_python(step)
        if translated:
            script_lines.extend(translated)
            continue

        label_match = re.search(r"label=['\"]([^'\"]+)['\"]", step)
        if label_match:
            label = label_match.group(1).replace("'", "\\'")
            script_lines.append(f"        try: page.get_by_text('{label}').first.click(timeout=3000)")
            script_lines.append(
                f"        except Exception as _e: print(f'[setup] WARNING: label click \"{label}\" failed: {{_e}}')"
            )
            continue

        # Unrecognised step patterns — log and skip rather than silently ignoring
        if step and not step.startswith(("def ", "import ", "from ", "@", "#", "class ")):
            script_lines.append(f"        print(f'[setup] WARNING: skipping unrecognised step: {step[:120]}')")

    if not steps and normalized_target and normalized_target != normalized_base:
        script_lines.append(f"        page.goto({normalized_target!r})")
        script_lines.append("        page.wait_for_timeout(1000)")

    # Ensure we end on the target URL by navigating to it after all replay steps.
    # This guarantees the codegen session opens on the correct page with state intact.
    if steps:
        script_lines.extend(
            [
                f'        print("[setup] All steps replayed. Navigating to target: {normalized_target!r}")',
                f"        page.goto({normalized_target!r})",
                "        page.wait_for_load_state('networkidle')",
                "        page.wait_for_timeout(1500)",
                "        _dismiss_banners(page)",
                "        page.wait_for_timeout(500)",
            ]
        )

    script_lines.extend(
        [
            "        page.wait_for_timeout(1000)",
            "        print(f'[setup] Saving page URL: {page.url}')",
            f"        open(r'{page_url_file}', 'w', encoding='utf-8').write(page.url)",
            f"        print('[setup] Saving storage state to: {state_file}')",
            f"        context.storage_state(path=r'{state_file}')",
            "        print('[setup] Storage state saved, closing browser')",
            "        browser.close()",
            "except Exception as e:",
            "    import traceback",
            "    print(f'[setup] ERROR: {e}')",
            "    traceback.print_exc()",
        ]
    )

    script_content = "\n".join(script_lines)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(script_content)
        temp_path = f.name

    try:
        result = subprocess.run(
            [sys.executable, temp_path],
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0 or result.stderr.strip():
            import logging

            _log = logging.getLogger(__name__)
            _log.warning("Setup script errors: rc=%s stderr=%s", result.returncode, result.stderr.strip()[:500])
        page_url = None
        if os.path.exists(page_url_file):
            page_url = Path(page_url_file).read_text(encoding="utf-8").strip()
            try:
                os.unlink(page_url_file)
            except OSError:
                pass
        if os.path.exists(state_file):
            return SetupScriptResult(state_file=state_file, page_url=page_url)
        return SetupScriptResult(state_file=None, page_url=page_url)
    except Exception:
        return SetupScriptResult(state_file=None, page_url=None)
    finally:
        try:
            os.unlink(temp_path)
        except OSError:
            pass


def _render_skip_repair_result() -> None:
    """Show the skip repair result."""
    st.divider()
    st.subheader("🖱️ Capture Locator Result")

    message = st.session_state.get("skip_repair_message", "")
    status = st.session_state.get("skip_repair_status")

    if status == "patched":
        st.success(message)
        re_run_col, reset_col = st.columns([1, 1])
        with re_run_col:
            if st.button("▶️ Run Generated Tests", type="primary"):
                st.session_state.skip_repair_status = None
                _handle_run_tests()
        with reset_col:
            if st.button("Done"):
                st.session_state.skip_repair_status = None
                st.rerun()
    else:
        st.error(message)
        if st.button("Done"):
            st.session_state.skip_repair_status = None
            st.rerun()


class RunResultsDisplay:
    """Renders the test run results with failure classification and repair buttons."""

    @staticmethod
    def render(run_result: RunResult) -> None:
        """Display run metrics, coverage, results table with repair buttons, and downloads."""
        if st.session_state.get("pipeline_run_command"):
            st.caption(f"Command: {st.session_state.pipeline_run_command}")

        if run_result.errors > 0:
            st.error("Pytest hit a collection or import error before the generated tests could run.")

        metric_cols = st.columns(5)
        metric_cols[0].metric("Total", run_result.total)
        metric_cols[1].metric("Passed", run_result.passed)
        metric_cols[2].metric("Failed", run_result.failed)
        metric_cols[3].metric("Skipped", run_result.skipped)
        metric_cols[4].metric("Errors", run_result.errors)

        # ── Coverage traceability table (requirement → tests mapping) ──
        criteria_lines = [line.strip() for line in st.session_state.pipeline_criteria.splitlines() if line.strip()]
        generated_code = _get_generated_code_for_coverage()
        coverage_analysis = build_coverage_analysis(criteria_lines, generated_code)
        coverage_rows = build_coverage_display_rows(coverage_analysis["requirements"], run_result.results)
        if coverage_rows:
            st.subheader("📋 Coverage Traceability")
            coverage_dicts: list[dict[str, str]] = []
            for row in coverage_rows:
                coverage_dicts.append(
                    {
                        "ID": row.id_cell,
                        "Requirement": row.requirement,
                        "Coverage": row.status,
                        "Tests": row.tests,
                    }
                )
            st.dataframe(coverage_dicts, width="stretch", hide_index=True)

        # ── Test run results table (one row per test) ──
        if run_result.results:
            st.subheader("🧪 Test Results")

            # Parse condition_ref mapping from generated test source
            saved_path = st.session_state.get("pipeline_saved_path", "")
            condition_refs: dict[str, str] = {}
            if saved_path:
                try:
                    source = _read_test_code_from_path(saved_path)
                    condition_refs = _parse_condition_refs_from_source(source)
                except Exception:
                    pass

            test_rows: list[dict[str, str]] = []
            for tr in run_result.results:
                if tr.status == "passed":
                    icon = "✅"
                elif tr.status == "failed":
                    icon = "❌"
                elif tr.status == "skipped":
                    icon = "⏭️"
                else:
                    icon = "⏳"
                runtime = f"{tr.duration:.2f}s" if tr.duration > 0 else ""
                ref = condition_refs.get(tr.name, "")
                test_rows.append(
                    {
                        "": icon,
                        "Ref": ref,
                        "Test": tr.name,
                        "Runtime": runtime,
                        "Evidence": "📸",
                    }
                )
            st.dataframe(test_rows, width="stretch", hide_index=True)

        # Failed tests repair section
        _render_failed_tests_repair(run_result.results, run_result)

        # Skipped tests info section
        _render_skipped_tests_info(run_result.results)

        # Repair panel (shown after user clicks repair button)
        _render_repair_panel()

        # Skip repair panel (shown after user clicks capture locator for skipped test)
        _render_skip_repair_panel()

        # Pytest output
        if st.session_state.get("pipeline_run_output"):
            with st.expander("Pytest Output", expanded=run_result.errors > 0 or run_result.failed > 0):
                st.code(st.session_state.pipeline_run_output, language="text")

        # Download buttons
        from src.ui.ui_downloads import RenderDownloads

        RenderDownloads.render()


def _render_inline_evidence(run_result: RunResult) -> None:
    """Render evidence inline + link to the main Evidence Viewer tab."""
    from src.gantt_utils import safe_read_sidecar
    from src.report_utils import generate_annotated_journey

    st.divider()
    st.subheader("📸 Test Evidence")

    saved_path = st.session_state.get("pipeline_saved_path", "")
    if not saved_path:
        st.info("No test file path available.")
        return

    package_dir = Path(saved_path).parent
    evidence_dir = package_dir / "evidence"

    if not evidence_dir.exists():
        st.info(f"No evidence found at {evidence_dir}. Run tests to generate evidence.")
        return

    sidecars = sorted(evidence_dir.glob("*.evidence.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not sidecars:
        st.info("No evidence sidecars found for this test run.")
        return

    # Filter sidecars to only those for tests that just ran
    test_names = {result.name for result in run_result.results}

    def extract_test_name(s: Path) -> str:
        name = s.name
        if name.endswith(".evidence.json"):
            name = name[:-14]
        return name.split("[")[0]

    relevant_sidecars = [s for s in sidecars if extract_test_name(s) in test_names]

    if not relevant_sidecars:
        st.info("No evidence found for the tests that just ran.")
        return

    # Sort sidecars to match run result order (using base test name — strip [param] suffix)
    sorted_sidecars: list[Path] = []
    for result in run_result.results:
        base_name = result.name.split("[")[0] if "[" in result.name else result.name
        for s in relevant_sidecars:
            sidecar_base = extract_test_name(s)
            if sidecar_base == base_name or sidecar_base.startswith(base_name) or base_name.startswith(sidecar_base):
                if s not in sorted_sidecars:
                    sorted_sidecars.append(s)

    # Also add any remaining sidecars not matched
    for s in relevant_sidecars:
        if s not in sorted_sidecars:
            sorted_sidecars.append(s)

    # Check if user clicked the 📸 button in the results table
    pre_selected = st.session_state.pop("_select_evidence_test", None)
    default_idx = 0
    if pre_selected:
        for i, s in enumerate(sorted_sidecars):
            if extract_test_name(s) == pre_selected:
                default_idx = i
                break

    # Build friendly labels for the selector
    sidecar_labels: list[str] = []
    for s in sorted_sidecars:
        data = safe_read_sidecar(s)
        if data is None:
            sidecar_labels.append(s.stem.replace("[chromium]", ""))
            continue
        test_info = data.get("test", {})
        if not isinstance(test_info, dict):
            test_info = {}
        status = str(test_info.get("status", "unknown"))
        label = s.stem.replace("[chromium]", "")
        condition_ref = str(test_info.get("condition_ref", ""))
        if condition_ref:
            label = f"{condition_ref} — {label}"
        icon = "✅" if status == "passed" else ("⏭️" if status == "skipped" else "❌")
        sidecar_labels.append(f"{icon} {label}")

    selected_idx = st.selectbox(
        "Select test to inspect",
        options=range(len(sorted_sidecars)),
        format_func=lambda i: sidecar_labels[i] if i < len(sidecar_labels) else "[unknown]",
        index=default_idx,
        key="inline_evidence_selector",
    )
    selected = sorted_sidecars[selected_idx]

    try:
        html = generate_annotated_journey(
            sidecar_path=selected,
            title=selected.stem,
            bug_report_mode=False,
        )
        st.html(html)

        # Download button for plain-text bug report
        text_report = generate_annotated_journey(
            sidecar_path=selected,
            title=selected.stem,
            bug_report_mode=True,
        )
        filename = selected.stem.replace("[chromium]", "").strip()
        st.download_button(
            label="📥 Download Bug Report",
            data=text_report,
            file_name=f"{filename}_bug_report.txt",
            mime="text/plain",
            key="inline_download_bug_report",
        )
    except Exception as e:
        st.error(f"Failed to render evidence: {e}")


def _render_self_healing_results(report: HealingReport) -> None:
    """Render the self-healing report — what was fixed and what remains."""
    st.divider()
    st.subheader("🩹 Self-Healing Results")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Failures", report.total_failures)
    col2.metric("Fixed", report.fixed, delta=f"+{report.fixed}" if report.fixed > 0 else None)
    col3.metric(
        "Remaining",
        report.remaining,
        delta=f"-{report.remaining}" if report.remaining > 0 else "0",
        delta_color="inverse",
    )
    col4.metric("Iterations", report.iterations)

    if report.unfixable > 0:
        st.caption(f"{report.unfixable} failure(s) could not be automatically fixed.")

    if report.patches:
        st.write("**Applied patches:**")
        for p in report.patches:
            with st.expander(f"🔧 {p.test_name} — {p.strategy}"):
                st.caption(f"**Diagnosis:** {p.diagnosis}")
                st.code(f"- {p.old_text}\n+ {p.new_text}", language="diff")

    if report.total_failures == 0:
        st.success("✅ All tests pass — no failures to heal.")
        if st.button("🧹 Clear", key="heal_clear_zero"):
            st.session_state.self_healing_report = None
            st.rerun()
    elif report.all_fixed:
        st.success("🎉 All failures fixed! Re-run tests to verify.")
        if st.button("🔄 Re-run Tests Now", key="heal_rerun"):
            _handle_run_tests()
            st.rerun()
    elif report.remaining > 0:
        st.warning(
            f"{report.remaining} test(s) still failing. "
            "Re-run tests to see current state, then use '🔧 Fix Locator' "
            "for any remaining locator failures."
        )
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔄 Re-run Tests", key="heal_rerun_remaining", type="primary"):
                _handle_run_tests()
                st.rerun()
        with col2:
            if st.button("🧹 Clear Healing Results", key="heal_clear"):
                st.session_state.self_healing_report = None
                st.rerun()


def _render_failed_tests_repair(results: list[TestResult], run_result: RunResult | None = None) -> None:
    """Render repair buttons for failed tests with locator issues.

    Also shows failure details for tests that failed for non-locator reasons
    (assertion failures, timeouts, etc.) so the user can see what went wrong.
    Shows the last completed step before failure to help pinpoint the failure point.
    """
    failed = [r for r in results if r.status == "failed"]
    if not failed:
        return

    st.divider()
    st.subheader("❌ Failed Tests")

    # Parse test source for step extraction
    saved_path = st.session_state.get("pipeline_saved_path", "")

    # Self-healing button — runs automated repair on all failed tests
    if saved_path and st.button(
        "🩹 Self-Heal Failed Tests", type="secondary", help="Automatically analyze and fix failures using AI"
    ):
        with st.spinner("Running tests to identify failures..."):
            try:
                status_container = st.empty()

                def _update_status(msg: str) -> None:
                    status_container.caption(f"🩹 {msg}")

                runner = SelfHealingRunner(max_iterations=3)
                report = runner.heal(saved_path, on_progress=_update_status)
                st.session_state.self_healing_report = report
                if report.total_failures == 0:
                    st.toast("✅ All tests already pass — nothing to heal!", icon="✅")
                elif report.fixed > 0:
                    st.toast(f"🩹 Fixed {report.fixed}/{report.total_failures} failures!", icon="🩹")
                else:
                    st.toast(f"⚠️ Could not auto-fix {report.total_failures} failure(s)", icon="⚠️")
            except Exception as e:
                st.error(f"Self-healing failed: {e}")
                st.session_state.self_healing_report = None
        st.rerun()

    # Show healing results if available
    healing_report: HealingReport | None = st.session_state.get("self_healing_report")
    if healing_report is not None:
        _render_self_healing_results(healing_report)

    test_source = ""
    if saved_path:
        try:
            test_source = _read_test_code_from_path(saved_path)
        except Exception:
            pass

    for result in failed:
        detail = classify_failure(result.error_message) if result.error_message else None
        has_locator_repair = detail is not None and detail.raw_locator

        # Extract error from multiple sources
        error_preview = ""
        full_error = result.error_message or ""
        if not full_error and run_result:
            full_error = _extract_error_from_raw_output(run_result.raw_output, result.name)

        if full_error:
            lines = full_error.strip().split("\n")
            for line in lines:
                stripped = line.strip()
                if stripped and not stripped.startswith("File ") and not stripped.startswith("E   "):
                    error_preview = stripped[:300]
                    break
            if not error_preview and lines:
                error_preview = lines[-1].strip()[:300]

        # Extract the last completed step before the failure
        last_steps = _extract_last_steps_before_failure(test_source, result.name)

        with st.expander(f"❌ {result.name}", expanded=True):
            runtime = f"{result.duration:.2f}s" if result.duration > 0 else "unknown"
            st.caption(f"Runtime: {runtime}")

            if error_preview:
                st.error(error_preview)
            else:
                st.warning("No error details captured. Check Pytest Output expander below for the full traceback.")

            # Show completed steps before failure
            if last_steps:
                st.write("**Steps completed before failure:**")
                for step in last_steps:
                    st.write(f"  ✅ {step}")
                st.info(
                    "The test failed AFTER completing these steps. "
                    "Investigate the next expected action — common causes include: "
                    "element not found (wrong page state after navigation), "
                    "timeout waiting for element, or assertion on incorrect element."
                )

            if full_error:
                with st.expander("Full error output"):
                    st.code(full_error, language="text")

            if has_locator_repair and detail is not None:
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.write(f"**Locator:** `{detail.raw_locator}`")
                with col2:
                    if st.button("🔧 Fix Locator", key=f"repair_{result.name}", type="primary"):
                        st.session_state.repair_target = detail
                        st.session_state.repair_status = "waiting"
                        st.session_state.repair_test_name = result.name
                        st.session_state.repair_test_file = result.file_path
                        st.rerun()


def _render_repair_panel() -> None:
    """Render the locator repair panel when in repair mode."""
    repair_status = st.session_state.get("repair_status")

    if repair_status == "waiting":
        _render_repair_waiting_panel()
    elif repair_status == "browser_requested":
        _render_repair_browser_session()
    elif repair_status in ("patched", "error"):
        _render_repair_result_panel()


def _render_repair_waiting_panel() -> None:
    """Show the 'waiting' repair panel with explanation and action buttons."""
    detail = st.session_state.get("repair_target")
    test_file = st.session_state.get("repair_test_file", "unknown")

    st.divider()
    st.subheader("🔧 Locator Repair Mode")

    locator_label = detail.raw_locator if detail and detail.raw_locator else "unknown"
    st.write(f"**Failed locator:** `{locator_label}`")
    st.write(f"**Test file:** `{test_file}`")
    st.write(f"**Error:** {detail.error_message[:300] if detail else 'Unknown'}")

    st.info(
        "The browser will open at the page where this test got stuck. "
        "Click the element you want to use as the locator. "
        "The test file will be updated automatically."
    )

    fix_col, cancel_col = st.columns([1, 1])
    with fix_col:
        if st.button("🌐 Open browser and fix locator", type="primary"):
            st.session_state.repair_status = "browser_requested"
            st.rerun()
    with cancel_col:
        if st.button("Cancel"):
            st.session_state.repair_status = None
            st.session_state.repair_target = None
            st.rerun()


def _render_repair_browser_session() -> None:
    """Run the headed browser codegen session and apply the patch."""
    from src.locator_repair import LocatorPatch, apply_patch_to_file

    detail = st.session_state.get("repair_target")
    base_url = st.session_state.get("starting_url", "") or st.session_state.get("last_starting_url", "")
    failure_url = detail.failure_url if detail and detail.failure_url else base_url

    if not failure_url:
        st.session_state.repair_status = "error"
        st.session_state.repair_message = "❌ No URL available for browser session."
        st.rerun()

    with st.spinner(f"⏳ Browser is opening at `{failure_url}` — click the element you want to use..."):
        replacement = run_codegen_session(failure_url, timeout_seconds=120)

    if replacement:
        patch = LocatorPatch(
            original_locator=detail.raw_locator if detail and detail.raw_locator else "",
            repaired_locator=replacement,
            line_number=detail.line_number if detail and detail.line_number else 1,
            test_file=st.session_state.get("repair_test_file", st.session_state.get("pipeline_saved_path", "")),
        )
        try:
            apply_patch_to_file(patch)

            if (
                st.session_state.get("pipeline_results")
                and not Path(st.session_state.get("pipeline_saved_path", "")).is_dir()
            ):
                st.session_state.pipeline_results = Path(patch.test_file).read_text(encoding="utf-8")

            st.session_state.repair_status = "patched"
            st.session_state.repair_message = (
                f"✅ Locator patched: `{replacement}`\n"
                f"Changed line(s) in `{patch.test_file}`\n"
                "Click **▶️ Run Generated Tests** to verify the fix."
            )
        except Exception as exc:
            st.session_state.repair_status = "error"
            st.session_state.repair_message = f"❌ Could not patch: {exc}"
    else:
        st.session_state.repair_status = "error"
        st.session_state.repair_message = "❌ No locator captured. The browser may have timed out or been closed."

    st.rerun()


def _render_repair_result_panel() -> None:
    """Show the repair result (success or error) with actions."""
    st.divider()
    st.subheader("🔧 Locator Repair Result")

    message = st.session_state.get("repair_message", "")
    status = st.session_state.get("repair_status")

    if status == "patched":
        st.success(message)
    else:
        st.error(message)

    # Show updated test code if patched
    if status == "patched":
        test_file = st.session_state.get("repair_test_file", "")
        if test_file and Path(test_file).exists():
            with st.expander("Updated test file", expanded=True):
                st.code(Path(test_file).read_text(encoding="utf-8"), language="python")

    re_run_col, reset_col = st.columns([1, 1])
    with re_run_col:
        if st.button("▶️ Run Generated Tests", disabled=(status != "patched"), type="primary"):
            st.session_state.repair_status = None
            st.session_state.repair_target = None
            _handle_run_tests()
    with reset_col:
        if st.button("Done"):
            st.session_state.repair_status = None
            st.session_state.repair_target = None
            st.session_state.repair_message = None
            st.rerun()
