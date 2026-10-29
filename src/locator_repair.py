"""Locator repair — surgical replacement of a broken locator in a generated test line.

Provides file-level surgery that replaces only the locator string while
preserving the surrounding action (`.click()`, `.fill()`, etc).
Also launches headed Playwright codegen for interactive locator capture.

Design-time only — not used at test runtime.
"""

from __future__ import annotations

import ast
import os
import re
import signal
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal


@dataclass
class LocatorPatch:
    """Describes a single locator replacement.

    Attributes:
        original_locator: The broken locator string extracted from the error.
        repaired_locator: The corrected locator string (e.g., from codegen).
        line_number: 1-based line in the generated test to patch.
        test_file: Path to the generated test file.
    """

    original_locator: str
    repaired_locator: str
    line_number: int
    test_file: str | Path


@dataclass
class SetupScriptResult:
    """Result of running prerequisite steps before a codegen session."""

    state_file: str | None
    page_url: str | None


CodegenStatus = Literal["captured", "no_click", "failed", "cannot_replay"]


@dataclass(frozen=True)
class CodegenOutcome:
    """What a headed codegen session actually produced.

    The old API returned ``str | None``, so a timeout and a human who changed
    their mind were indistinguishable. The status is the distinction the UI
    needs:

    - ``captured``: a locator was recorded (``locator`` holds it);
    - ``no_click``: the browser closed or the recording held no action;
    - ``failed``: the session crashed, timed out, or could not be read;
    - ``cannot_replay``: a state file was required but is missing, so the
      step cannot be replayed from the journey's real state.
    """

    status: CodegenStatus
    locator: str | None = None
    reason: str = ""

    @property
    def captured(self) -> bool:
        """True when a locator was captured."""
        return self.status == "captured" and bool(self.locator)


def translate_setup_step_to_python(step: str) -> list[str]:
    """Translate a generated test step line into Playwright setup script lines.

    Handles POM method calls, evidence_tracker actions, and raw Playwright locators.
    Each translation is wrapped in try/except but logs failures so silent breakage
    is visible in the terminal output.
    """
    stripped = step.strip()
    lines: list[str] = []

    # ── POM click: home_page.click('Label') ──────────────────────
    pom_click = re.match(
        r"(?:home_page|category_product_page|cart_page|products_page|generated_page|"
        r"checkout_page|login_page|account_page|contact_page|"
        r"[a-z_]+_page)\.click\(['\"]([^'\"]+)['\"]\)",
        stripped,
    )
    if pom_click:
        text = pom_click.group(1).replace("'", "\\'")
        lines.extend(
            [
                "        try:",
                "            # Try link first, then button, then any clickable",
                f"            el = page.get_by_role('link', name='{text}').first",
                "            if el.count() > 0 and el.is_visible(timeout=1000):",
                "                href = el.get_attribute('href')",
                "                if href:",
                "                    page.goto(urljoin(page.url, href))",
                "                else:",
                "                    el.click(timeout=5000)",
                "            else:",
                f"                page.get_by_role('button', name='{text}').first.click(timeout=5000)",
                "        except Exception:",
                "            try:",
                f"                page.get_by_text('{text}', exact=False).first.click(timeout=5000)",
                "            except Exception:",
                "                try:",
                f"                    el = page.locator('a, button, [role=\"button\"], [role=\"link\"]').filter(has_text='{text}').first",
                "                    if el.count() > 0:",
                "                        href = el.get_attribute('href')",
                "                        if href:",
                "                            page.goto(urljoin(page.url, href))",
                "                        else:",
                "                            el.click(force=True, timeout=5000)",
                "                except Exception as _e:",
                f"                    print(f'[setup] WARNING: click(\"{text}\") failed: {{_e}}')",
            ]
        )
        return lines

    # ── POM fill: home_page.fill('Field', 'value') ───────────────
    pom_fill = re.match(
        r"(?:home_page|category_product_page|cart_page|products_page|generated_page|"
        r"checkout_page|login_page|account_page|contact_page|"
        r"[a-z_]+_page)"
        r"\.fill\(['\"]([^'\"]+)['\"],\s*['\"]([^'\"]+)['\"]\)",
        stripped,
    )
    if pom_fill:
        field = pom_fill.group(1).replace("'", "\\'")
        value = pom_fill.group(2).replace("'", "\\'")
        lines.extend(
            [
                "        try:",
                f"            page.get_by_label('{field}').fill('{value}', timeout=5000)",
                "        except Exception:",
                "            try:",
                f"                page.get_by_placeholder('{field}').fill('{value}', timeout=5000)",
                "            except Exception:",
                "                try:",
                f"                    page.get_by_role('textbox', name='{field}').first.fill('{value}', timeout=5000)",
                "                except Exception as _e:",
                f"                    print(f'[setup] WARNING: fill(\"{field}\") failed: {{_e}}')",
            ]
        )
        return lines

    # ── POM select / check / uncheck ────────────────────────────
    pom_select = re.match(
        r"(?:[a-z_]+_page)\.select_option\(['\"]([^'\"]+)['\"],\s*['\"]([^'\"]+)['\"]\)",
        stripped,
    )
    if pom_select:
        field = pom_select.group(1).replace("'", "\\'")
        value = pom_select.group(2).replace("'", "\\'")
        lines.extend(
            [
                "        try:",
                f"            page.get_by_label('{field}').select_option('{value}', timeout=5000)",
                "        except Exception as _e:",
                f"            print(f'[setup] WARNING: select_option(\"{field}\") failed: {{_e}}')",
            ]
        )
        return lines

    pom_check = re.match(
        r"(?:[a-z_]+_page)\.(check|uncheck)\(['\"]([^'\"]+)['\"]\)",
        stripped,
    )
    if pom_check:
        action = pom_check.group(1)
        label = pom_check.group(2).replace("'", "\\'")
        lines.extend(
            [
                "        try:",
                f"            cb = page.get_by_label('{label}')",
                f"            if cb.count() > 0: cb.{action}(timeout=5000)",
                "        except Exception as _e:",
                f"            print(f'[setup] WARNING: {action}(\"{label}\") failed: {{_e}}')",
            ]
        )
        return lines

    # ── evidence_tracker.click(label='...') ─────────────────────
    ev_click = re.match(
        r"evidence_tracker\.click\(['\"]([^'\"]+)['\"](?:,\s*label=\s*['\"]([^'\"]+)['\"])?\)",
        stripped,
    )
    if ev_click:
        selector = ev_click.group(1).replace("'", "\\'")
        label = ev_click.group(2)
        if label:
            text = label.replace("'", "\\'")
        else:
            text = selector
        lines.extend(
            [
                "        try:",
                f"            page.get_by_text('{text}').first.click(timeout=5000)",
                "        except Exception as _e:",
                f"            print(f'[setup] WARNING: evidence_tracker.click(\"{text}\") failed: {{_e}}')",
            ]
        )
        return lines

    # ── evidence_tracker.fill(selector, 'value', label='...') ───
    ev_fill = re.match(
        r"evidence_tracker\.fill\(['\"]([^'\"]+)['\"],\s*['\"]([^'\"]+)['\"](?:,\s*label=\s*['\"]([^'\"]+)['\"])?\)",
        stripped,
    )
    if ev_fill:
        field = (ev_fill.group(3) or ev_fill.group(1)).replace("'", "\\'")
        value = ev_fill.group(2).replace("'", "\\'")
        lines.extend(
            [
                "        try:",
                f"            page.get_by_label('{field}').fill('{value}', timeout=5000)",
                "        except Exception:",
                "            try:",
                f"                page.get_by_placeholder('{field}').fill('{value}', timeout=5000)",
                "            except Exception as _e:",
                f"                print(f'[setup] WARNING: evidence_tracker.fill(\"{field}\") failed: {{_e}}')",
            ]
        )
        return lines

    # ── evidence_tracker.navigate('url') or page.goto('url') ─────
    navigate_match = re.match(
        r"(?:evidence_tracker\.navigate|page\.goto)\s*\(\s*['\"]([^'\"]+)['\"]\s*\)",
        stripped,
    )
    if navigate_match:
        url = navigate_match.group(1).replace("'", "\\'")
        lines.append(f"        page.goto('{url}')")
        lines.append("        page.wait_for_load_state('networkidle')")
        lines.append("        page.wait_for_timeout(500)")
        return lines

    # ── evidence_tracker.assert_visible(...) — no-op, just wait ──
    if "evidence_tracker.assert_" in stripped:
        lines.append("        page.wait_for_timeout(300)")
        return lines

    # ── dismiss_consent_overlays(page) — call our banner dismiss ─
    if "dismiss_consent_overlays" in stripped or "dismiss_banners" in stripped:
        lines.append("        _dismiss_banners(page)")
        return lines

    # ── Raw locator calls: page.locator('...').click() / fill() ──
    loc_match = re.search(r"locator\(['\"]([^'\"]+)['\"]", stripped)
    if loc_match:
        val = loc_match.group(1).replace("'", "\\'")
        if ".fill(" in stripped:
            fill_val_match = re.search(r"\.fill\(['\"]([^'\"]+)['\"]", stripped)
            fill_val = fill_val_match.group(1).replace("'", "\\'") if fill_val_match else "test"
            lines.append(f"        try: page.locator('{val}').fill('{fill_val}', timeout=5000)")
        else:
            lines.append(f"        try: page.locator('{val}').click(timeout=5000)")
        lines.append("        except Exception as _e: print(f'[setup] WARNING: locator action failed: {_e}')")
        return lines

    # ── Fallback: label-based ────────────────────────────────────
    label_match = re.search(r"label=['\"]([^'\"]+)['\"]", stripped)
    if label_match and "evidence_tracker" in stripped:
        lbl = label_match.group(1).replace("'", "\\'")
        lines.append(f"        try: page.get_by_text('{lbl}').click(timeout=5000)")
        lines.append("        except Exception as _e: print(f'[setup] WARNING: label click failed: {_e}')")
        return lines

    # ── Fallback: get_by_role ────────────────────────────────────
    role_match = re.search(
        r"\.get_by_role\(\s*['\"]([^'\"]+)['\"].*?name=\s*['\"]([^'\"]+)['\"]",
        stripped,
    )
    if role_match:
        role = role_match.group(1)
        name = role_match.group(2).replace("'", "\\'")
        if ".fill(" in stripped:
            val_match = re.search(r"\.fill\(['\"]([^'\"]+)['\"]", stripped)
            val = val_match.group(1).replace("'", "\\'") if val_match else "test"
            lines.append(f"        page.get_by_role('{role}', name='{name}').fill('{val}', timeout=5000)")
        else:
            lines.append(f"        page.get_by_role('{role}', name='{name}').click(timeout=5000)")
        return lines

    return lines


@dataclass
class LocatorRepairError(Exception):
    """Raised when the target locator could not be found on the expected line."""

    line_number: int
    expected_locator: str
    actual_line: str


# Regex that splits a playwright chained call into the locator part and the
# action part.  It captures the argument inside .locator("...") — supporting
# both single and double quotes, and escaped quotes inside.
_LOCATOR_ACTION_SPLIT = re.compile(
    r'(.+\.locator\()(["\'])(.*?)\2(\)\.(.+))',
    re.DOTALL,
)


def _find_locator_action_line(
    source: str,
    line_number: int,
    original_locator: str,
) -> tuple[int, str]:
    """Return (0-based index, raw_line) for the line containing *original_locator*.

    Searches a window around *line_number* (reported error line) because
    Playwright error line numbers don't always match the locator call line.

    Raises:
        LocatorRepairError: if the locator string is not found nearby.
    """
    lines = source.splitlines()
    # Search +/- 10 lines around the reported line
    start = max(0, line_number - 11)
    end = min(len(lines), line_number + 9)

    for offset in range(start, end):
        # Check the locator string appears in this line
        if original_locator in lines[offset]:
            return (offset, lines[offset])

    # Fallback: search entire file
    for offset, line in enumerate(lines):
        if original_locator in line:
            return (offset, line)

    raise LocatorRepairError(
        line_number=line_number,
        expected_locator=original_locator,
        actual_line="(not found in file)",
    )


def apply_patch(patch: LocatorPatch) -> str:
    """Apply a locator patch to the test source and return the patched source.

    The function finds the line containing *original_locator*, replaces only the
    locator string inside `.locator("...")`, and preserves the action (`.click()`,
    `.fill()`, etc.).

    Args:
        patch: The locator patch to apply.

    Returns:
        The full source with the locator replaced.

    Raises:
        LocatorRepairError: if the original locator cannot be found.
    """
    test_path = Path(patch.test_file)
    source = test_path.read_text(encoding="utf-8")

    # B-042: an empty original_locator would match *every* line in the search
    # window and then .replace("", ...) would mangle the whole line — reject it.
    if not patch.original_locator:
        raise LocatorRepairError(
            line_number=patch.line_number,
            expected_locator="",
            actual_line="(empty original_locator — nothing to patch)",
        )

    (line_idx, raw_line) = _find_locator_action_line(
        source,
        patch.line_number,
        patch.original_locator,
    )

    # B-042: carry the original line's leading indentation into the
    # reconstruction. The regex groups below only cover the statement itself;
    # writing it back without the indent dedents a patched line inside a test
    # function to module scope, breaking collection (NameError / 1 error, 0
    # tests). The fallback replace path preserves the rest of the line, but the
    # regex path rebuilds from groups — so re-apply the indent explicitly.
    indent = raw_line[: len(raw_line) - len(raw_line.lstrip())]

    # Try to match the .locator(...) pattern and replace only the locator string
    match = _LOCATOR_ACTION_SPLIT.search(raw_line)
    if match:
        before_quote = match.group(1).lstrip()  # e.g. 'page.locator(' (indent stripped)
        quote_char = match.group(2)  # '"' or "'"
        _old_locator = match.group(3)  # discarded — we trust the patch
        after_quote = match.group(4)  # e.g. ').click()'
        # Reconstruct with the repaired locator, preserving the line's indent
        new_line = f"{indent}{before_quote}{quote_char}{patch.repaired_locator}{quote_char}{after_quote}"
    else:
        # Fallback: simple string replace for the original_locator on this line
        new_line = raw_line.replace(patch.original_locator, patch.repaired_locator)

    lines = source.splitlines()
    lines[line_idx] = new_line
    return "\n".join(lines)


def apply_patch_to_file(patch: LocatorPatch) -> None:
    """Apply a locator patch and write the result back to disk."""
    patched_source = apply_patch(patch)
    test_path = Path(patch.test_file)
    test_path.write_text(patched_source, encoding="utf-8")


_CODEGEN_CALL = re.compile(
    r"(?m)^[ \t]*page[.](locator|get_by_test_id|get_by_label|get_by_text|get_by_title|get_by_placeholder|get_by_role)[(]",
)
_CODEGEN_LOCATOR_METHODS = {
    "locator",
    "get_by_test_id",
    "get_by_label",
    "get_by_text",
    "get_by_title",
    "get_by_placeholder",
}


def _call_argument_source(source: str, open_paren: int) -> str | None:
    """Return the text inside the balanced call whose ``(`` ends at *open_paren*.

    Scans quotes and nested brackets so a wrapped codegen call (the common case
    for a long role name) and a ``)`` inside a quoted name are both read
    correctly. Returns ``None`` for an unbalanced call.
    """
    depth = 1
    index = open_paren
    quote: str | None = None
    escaped = False
    while index < len(source):
        char = source[index]
        if quote is not None:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
        else:
            if char in ("'", '"'):
                quote = char
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
                if depth == 0:
                    return source[open_paren:index]
        index += 1
    return None


def _parse_call_arguments(argument_source: str) -> tuple[list[str | None], dict[str, str]]:
    """Parse Python call arguments without executing them.

    Returns positional string arguments (``None`` for non-literals) and keyword
    string arguments. Uses the AST so escaped quotes and an apostrophe inside a
    name are read exactly as Python writes them, not by a fragile character
    class.
    """
    try:
        call = ast.parse(f"_f({argument_source})", mode="eval").body
    except SyntaxError:
        return [], {}
    if not isinstance(call, ast.Call):
        return [], {}

    positional: list[str | None] = []
    for arg in call.args:
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            positional.append(arg.value)
        else:
            positional.append(None)

    keywords: dict[str, str] = {}
    for keyword in call.keywords:
        if keyword.arg and isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, str):
            keywords[keyword.arg] = keyword.value.value
    return positional, keywords


def _single_quote(value: str) -> str:
    """Return *value* as a single-quoted Python string literal."""
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def _extract_locator(content: str) -> str | None:
    """Extract the first real locator from a codegen recording.

    The call must start a line with the ``page`` receiver, so a locator-looking
    string inside a ``print`` or a comment is not a match. Calls are read one at
    a time and balanced-scanned, so a first call without a name cannot cross
    into a second call on a later line.
    """
    for match in _CODEGEN_CALL.finditer(content):
        method = match.group(1)
        argument_source = _call_argument_source(content, match.end())
        if argument_source is None:
            continue
        positional, keywords = _parse_call_arguments(argument_source)

        if method == "get_by_role":
            role = positional[0] if positional else None
            if not role:
                continue
            name = keywords.get("name")
            if name:
                return f"get_by_role({_single_quote(role)}, name={_single_quote(name)})"
            return f"get_by_role({_single_quote(role)})"

        if method in _CODEGEN_LOCATOR_METHODS:
            value = positional[0] if positional else None
            if value is None:
                value = keywords.get("name") or keywords.get("text") or keywords.get("label")
            if value is not None:
                return value
    return None


def _kill_process_tree(proc: subprocess.Popen[Any]) -> None:
    """Kill the codegen process and every child it spawned.

    ``proc.kill()`` only kills the Playwright shim. On Windows the browser is a
    child of that shim, so it survives and keeps the profile locked; taskkill
    /T walks the tree. On POSIX the session was started in its own process
    group, so the whole group is killed.
    """
    if sys.platform == "win32":
        try:
            subprocess.run(
                ["taskkill", "/T", "/F", "/PID", str(proc.pid)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=10,
            )
        except OSError, subprocess.TimeoutExpired:
            pass
        try:
            proc.kill()
        except OSError:
            pass
        return

    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except OSError, ProcessLookupError, PermissionError:
        try:
            proc.kill()
        except OSError:
            pass


def _wait_quietly(proc: subprocess.Popen[Any], timeout: float = 5.0) -> None:
    """Wait for exit, but never let a second TimeoutExpired escape to the UI."""
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            proc.kill()
        except OSError:
            pass


def _remove_codegen_workdir(work_dir: Path) -> None:
    """Remove the recording and its private directory, always."""
    try:
        for child in work_dir.iterdir():
            try:
                child.unlink()
            except OSError:
                pass
        work_dir.rmdir()
    except OSError:
        pass


def run_codegen_session(url: str, timeout_seconds: int = 120, state_file: str | None = None) -> CodegenOutcome:
    """Launch headed Playwright codegen and capture the first recorded locator.

    When a state_file is provided, the codegen session loads saved cookies and
    localStorage so cart contents, consent preferences, and login state are
    preserved. A state file that was requested but does not exist is REFUSED:
    replaying from the wrong state would make the human blame the page for a
    failure the tool caused.

    The recording is written inside a private directory and removed in a
    ``finally``. Codegen records every value the human typed (``fill`` calls),
    so a leaked script is a secret on disk.

    Args:
        url: URL to navigate to.
        timeout_seconds: Maximum time to wait for a click.
        state_file: Optional path to a storage state JSON file to load.

    Returns:
        A :class:`CodegenOutcome` naming the distinct result.
    """
    import logging

    _log = logging.getLogger(__name__)

    if state_file and not Path(state_file).exists():
        reason = f"the saved state '{state_file}' is missing, so this step cannot be replayed"
        _log.warning("Refusing codegen session: %s", reason)
        return CodegenOutcome("cannot_replay", reason=reason)

    if state_file:
        _log.info("Loading saved state from %s (%d bytes)", state_file, Path(state_file).stat().st_size)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    work_dir = Path(tempfile.mkdtemp(prefix="tancat_codegen_"))
    output_file = work_dir / f"repair_locator_{timestamp}.py"
    try:
        try:
            os.chmod(work_dir, 0o700)
        except OSError:
            pass

        cmd = ["playwright", "codegen", "--output", str(output_file)]
        if state_file:
            cmd.extend(["--load-storage", state_file])
        cmd.append(url)

        _log.info("Launching codegen: %s", " ".join(cmd))

        popen_kwargs: dict[str, Any] = {}
        if os.name != "nt":
            # Own process group so a timeout can kill the browser too.
            popen_kwargs["start_new_session"] = True

        # Use DEVNULL to avoid pipe deadlocks with headed browser GUI process on Windows.
        # The browser writes to output_file directly, we do not need its stdout/stderr.
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                **popen_kwargs,
            )
        except OSError as exc:
            return CodegenOutcome("failed", reason=f"could not start Playwright codegen: {exc}")

        try:
            proc.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            _kill_process_tree(proc)
            _wait_quietly(proc)
            return CodegenOutcome("failed", reason=f"codegen timed out after {timeout_seconds}s")

        if not output_file.exists():
            if proc.returncode not in (0, None):
                return CodegenOutcome(
                    "failed", reason=f"codegen exited with status {proc.returncode} without a recording"
                )
            return CodegenOutcome("no_click", reason="the browser was closed without recording an action")

        try:
            os.chmod(output_file, 0o600)
        except OSError:
            pass

        try:
            content = output_file.read_text(encoding="utf-8")
        except OSError as exc:
            return CodegenOutcome("failed", reason=f"could not read the codegen recording: {exc}")

        locator = _extract_locator(content)
        if locator is None:
            return CodegenOutcome("no_click", reason="the recording contains no locator")
        return CodegenOutcome("captured", locator=locator)
    finally:
        _remove_codegen_workdir(work_dir)


def extract_locator_from_line(line: str) -> str | None:
    """Extract the locator string from a single line of test code.

    Looks for `.locator("...")` and returns the locator string.

    Args:
        line: A single line of Python/test code.

    Returns:
        The locator string (e.g., ``"get_by_role('heading', name='Products')")``)
        or ``None`` if no locator pattern is found.
    """
    match = _LOCATOR_ACTION_SPLIT.search(line)
    if not match:
        return None
    quote = match.group(2)
    raw = match.group(3)
    try:
        # The regex keeps the source escape (for example Women's shoes). Read
        # it as the Python string the generated line actually runs.
        return str(ast.literal_eval(f"{quote}{raw}{quote}"))
    except SyntaxError, ValueError:
        return raw
