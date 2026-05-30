"""CLI menu rendering and input helpers.

Renders a CHOICE-inspired retro terminal UI: green-on-black phosphor
aesthetic with box-drawing borders and a ``>`` selection indicator.

All input logic (LLM config, user story, URLs, auth, journey) is
preserved from the previous implementation — only rendering changed.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

from . import terminal_adapter
from .color import green, red, yellow
from .retro_ui import (
    clear_screen,
    prompt_input,
    prompt_non_empty,
    render_header,
    render_menu,
    render_shortcut_bar,
)

# ── Default selected index (persist across screen redraws) ─────────────────

_default_selected: list[int] = [0]


def _next_selected() -> int:
    """Return and increment the default selected index for the next menu."""
    idx = _default_selected[0]
    _default_selected[0] = 0  # reset after use
    return idx


# ── Header ─────────────────────────────────────────────────────────────────


def print_header(title: str, subtitle: str = "") -> None:
    """Print a CHOICE-style section header with box-drawing borders."""
    if title == "AI Playwright Test Generator":
        subtitle = subtitle or "Generate Playwright tests from user stories with AI"
    clear_screen()
    render_header(title, subtitle)
    print()  # blank line after header


# ── Menu ───────────────────────────────────────────────────────────────────


def _running_in_git_bash() -> bool:
    """Detect whether the process is running inside Git Bash (MINGW64).

    msvcrt functions (kbhit / getwch) do NOT work reliably in Git Bash —
    they silently fail or interfere with the PTY that Git Bash uses for
    input.  When running there we must skip all msvcrt-based draining.
    """
    return terminal_adapter.terminal.running_in_git_bash()


def _drain_stdin_immediate() -> int:
    """Drain immediately-available data from stdin using select (non-blocking).

    Returns the number of lines consumed (for diagnostic logging).
    Uses select.select with 0 timeout so it never blocks.
    Works in Git Bash (MINGW64) where msvcrt is unavailable.
    """
    import select

    lines_consumed = 0
    try:
        readable, _, _ = select.select([sys.stdin], [], [], 0.0)
        if readable:
            while True:
                readable2, _, _ = select.select([sys.stdin], [], [], 0.0)
                if not readable2:
                    break
                data = sys.stdin.readline()
                if not data:
                    break
                lines_consumed += 1
    except Exception:
        pass
    return lines_consumed


def _flush_msvcrt_buffer() -> None:
    """Quick-flush residual keystrokes from msvcrt input buffer.

    In Git Bash (MINGW64), do NOT drain stdin — pasted text goes through
    the PTY's stdin pipe, so draining it would consume the user's input.
    """
    terminal_adapter.terminal.flush()


def _drain_msvcrt_buffer_aggressive() -> None:
    """Aggressive drain for multi-line paste — wait until buffer stays empty.

    In Git Bash (MINGW64), do NOT drain stdin — pasted text goes through
    the PTY's stdin pipe, so draining it would consume the user's input.
    """
    # Best-effort aggressive flush using the standard flush implementation.
    terminal_adapter.terminal.flush()


def _read_key() -> str:
    """Read a single keypress using msvcrt (Windows) or non-blocking fallback.

    In Git Bash (MINGW64), msvcrt does not work and termios/tty are
    unavailable.  Instead we use a background thread + select to read
    stdin without blocking indefinitely.  The thread yields after data
    arrives (or after a short timeout), so the menu stays responsive.

    Returns:
    - '^' for Up arrow
    - 'v' for Down arrow
    - the character typed for regular keys
    """
    return terminal_adapter.terminal.read_key()


def _read_key_git_bash() -> str:
    """Non-blocking key reader for Git Bash (MINGW64).

    Uses a background thread that calls ``select.select`` on stdin with a
    short timeout so the menu never hangs when no input is available.
    Falls back to line-based input (Enter to confirm) when arrow-key
    escape sequences are not supported by the terminal.
    """
    # Delegated to terminal adapter for consistency and testability.
    return terminal_adapter.terminal.read_key()


def set_terminal_adapter(adapter: terminal_adapter.TerminalAdapter) -> None:
    """Replace the active terminal adapter (used for testing/injection)."""
    terminal_adapter.terminal = adapter


def print_menu(
    options: list[str],
    prompt: str = "Choose an option",
    shortcuts: list[tuple[str, str]] | None = None,
) -> int:
    """Print a numbered retro menu and return the selected index (0-based).

    Supports:
    - Arrow keys: Up/Down to navigate, Enter to select
    - Numbered input: type ``1``, ``2``, etc. and press Enter
    - Shortcut keys: single-letter keys defined in *shortcuts*
    """
    first_render = True
    selected = 0
    while True:
        if not first_render:
            clear_screen()
        first_render = False

        render_menu(options, selected=selected)
        print()
        sys.stdout.flush()

        def _format_shortcuts(entries: list[tuple[str, str]]) -> str:
            return "  ".join(f"[{key}]{label}" for key, label in entries)

        bar: list[tuple[str, str]] = []
        for i, opt in enumerate(options):
            label = opt.split(" (", 1)[0]
            bar.append((str(i + 1), label))

        if shortcuts:
            existing_labels = {v.lower() for _, v in bar}
            for s in shortcuts:
                if s[1].lower() not in existing_labels:
                    bar.append(s)
                    existing_labels.add(s[1].lower())

        existing_keys = {k for k, _ in bar}
        existing_labels = {v.lower() for _, v in bar}
        if "Q" not in existing_keys and "quit" not in existing_labels:
            bar.append(("Q", "Quit"))

        try:
            inner = max(40, os.get_terminal_size().columns - 2)
        except OSError:
            inner = 78
        if len(_format_shortcuts(bar)) > inner and shortcuts:
            bar = bar[: len(options)] + [(key, key) for key, _ in shortcuts]
            existing_keys = {k for k, _ in bar}
            existing_labels = {v.lower() for _, v in bar}
            if "Q" not in existing_keys and "quit" not in existing_labels:
                bar.append(("Q", "Quit"))
        if len(_format_shortcuts(bar)) > inner:
            bar = bar[: len(options)]
            existing_keys = {k for k, _ in bar}
            existing_labels = {v.lower() for _, v in bar}
            if "Q" not in existing_keys and "quit" not in existing_labels:
                bar.append(("Q", "Quit"))

        render_shortcut_bar(bar)
        print()

        if _running_in_git_bash():
            try:
                choice = input("   Enter selection: ").strip()
            except KeyboardInterrupt, EOFError:
                print("\n  Interrupted.")
                return -1
        else:
            try:
                key = _read_key()
                if not key:
                    try:
                        choice = input("   Enter selection: ").strip()
                    except KeyboardInterrupt, EOFError:
                        print("\n  Interrupted.")
                        return -1
                else:
                    if key == "^":
                        selected = max(0, selected - 1)
                        continue
                    if key == "v":
                        selected = min(len(options) - 1, selected + 1)
                        continue
                    if key == "\r":
                        _flush_msvcrt_buffer()
                        return selected

                    if key in ("\x08", "\x7f"):
                        continue

                    choice = key.strip()
            except KeyboardInterrupt, EOFError:
                print("\n  Interrupted.")
                return -1

        if not choice:
            continue

        if len(choice) == 1 and not choice.isdigit():
            upper = choice.upper()
            # Always handle Q (Quit) immediately — do not trap it in shortcut loops
            if upper == "Q":
                _flush_msvcrt_buffer()
                print("\n  Quitting.")
                return -1
            # Check registered shortcuts (non-Quit)
            if shortcuts:
                for key, _label in shortcuts:
                    if key.upper() == upper:
                        print(yellow(f"  Shortcut '{key}' is not available on this screen."))
                        return -1  # Return to caller; caller handles routing
            print(yellow("  Invalid shortcut. Please try again."))
            continue

        try:
            idx = int(choice) - 1
            if 0 <= idx < len(options):
                _flush_msvcrt_buffer()
                return idx
        except ValueError:
            pass

        print(yellow("  Invalid choice. Please try again."))


# ── Text input ─────────────────────────────────────────────────────────────


def read_non_empty(prompt_text: str) -> str:
    """Read a non-empty line from the user (retro-styled)."""
    return prompt_non_empty(prompt_text)


def read_optional(prompt_text: str, default: str = "") -> str:
    """Read a line, returning *default* on empty input (retro-styled)."""
    return prompt_input(prompt_text, default)


# ── LLM configuration ─────────────────────────────────────────────────────


def _get_available_models(provider_name: str, provider_url: str) -> list[str]:
    """Try to list available models for the given provider."""
    import httpx

    try:
        if provider_name == "ollama":
            response = httpx.get(f"{provider_url}/api/tags", timeout=2.0)
            response.raise_for_status()
            return [m["name"] for m in response.json().get("models", [])]
        elif provider_name == "lm-studio":
            response = httpx.get(f"{provider_url}/v1/models", timeout=2.0)
            response.raise_for_status()
            return [m["id"] for m in response.json().get("data", [])]
        elif provider_name == "openai-local":
            response = httpx.get(f"{provider_url}/v1/models", timeout=2.0)
            if response.status_code in (200, 401):
                return [m["id"] for m in response.json().get("data", [])]
            return []
        elif provider_name == "openai":
            return ["gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo"]
    except httpx.ConnectError as e:
        print(yellow(f"  ⚠ Cannot connect to {provider_url}: {e}"))
    except httpx.TimeoutException as e:
        print(yellow(f"  ⚠ Connection to {provider_url} timed out: {e}"))
    except httpx.HTTPStatusError as e:
        print(yellow(f"  ⚠ HTTP error from {provider_url}: {e.response.status_code}"))
    except Exception as e:
        print(yellow(f"  ⚠ Failed to list models: {e}"))
    return []


def configure_llm(provider: str, base_url: str, model_name: str) -> tuple[str, str, str]:
    """Let the user pick LLM provider and model. Returns (provider, base_url, model)."""
    print_header("LLM Configuration")

    providers: list[tuple[str, str, str]] = [
        ("Ollama (local)", "ollama", "http://localhost:11434"),
        ("LM Studio (local)", "lm-studio", "http://localhost:1234"),
        ("OpenAI-Compatible (local)", "openai-local", "http://localhost:8080"),
        ("OpenAI (cloud)", "openai", "https://api.openai.com"),
    ]

    idx = print_menu(
        [p[0] for p in providers],
        "Select LLM provider",
        shortcuts=[("O", "Ollama"), ("L", "LM Studio"), ("C", "OpenAI-Local"), ("A", "OpenAI")],
    )
    if idx < 0:
        return provider, base_url, model_name

    display_name, provider_key, default_url = providers[idx]

    url = read_optional("  Base URL", default_url)

    models = _get_available_models(provider_key, url)
    if models:
        print(f"\n  Available models ({len(models)}):")
        for i, model in enumerate(models[:15], 1):
            print(f"    {i}. {model}")
        if len(models) > 15:
            print(f"    ... and {len(models) - 15} more")
        model_choice = read_optional(
            f"\n  Select model [1-{len(models)}] (default: 1):",
            "1",
        )
        if model_choice.strip().isdigit() and 0 < int(model_choice) <= len(models):
            selected_model = models[int(model_choice) - 1]
        else:
            selected_model = models[0]
    else:
        print(f"\n  Could not auto-detect models for {provider_key}.")
        fallback = model_name or _default_model(provider_key)
        selected_model = read_optional("  Model name", fallback)

    print(green(f"  ✓ Provider: {provider_key} | URL: {url} | Model: {selected_model}"))
    return provider_key, url, selected_model


def _default_model(provider: str) -> str:
    if provider == "ollama":
        return "qwen3.5:35b"
    if provider == "lm-studio":
        return "lmstudio-community/Qwen2.5-7B-Instruct-GGUF"
    if provider == "openai-local":
        return "llama"
    return "gpt-4o"


# ── User story collection ─────────────────────────────────────────────────


def collect_user_story() -> str:
    """Let user paste or upload a user story. Returns raw text."""
    print_header("User Story Input")

    mode = print_menu(
        ["Paste Text", "Upload File", "Load baseline (automationexercise.com)"],
        "Input method",
        shortcuts=[("P", "Paste"), ("U", "Upload"), ("B", "Baseline")],
    )

    baseline_text = _get_baseline_text()

    if mode == 2:
        print(green("  Baseline loaded."))
        return baseline_text

    if mode == 0:
        _drain_msvcrt_buffer_aggressive()
        print("\n  Paste your user story and acceptance criteria below.")
        print("  (End with an empty line or Ctrl+D / Ctrl+Z on Windows)")
        print("  ---")
        lines: list[str] = []
        try:
            import sys

            sys.stdout.flush()
            time.sleep(0.1)
            while True:
                line = input()
                if not line and lines:
                    break
                lines.append(line)
        except EOFError:
            pass
        return "\n".join(lines)

    # mode == 1: Upload File
    filepath = read_optional("  Enter file path:", "")
    if not filepath:
        print(yellow("  No file provided. Please paste text instead."))
        return collect_user_story()  # type: ignore[return-value]
    try:
        content = Path(filepath).read_text(encoding="utf-8")
        print(green(f"  Read {len(content)} characters from {filepath}"))
        return content
    except FileNotFoundError:
        print(red(f"  File not found: {filepath}"))
        return collect_user_story()  # type: ignore[return-value]
    except Exception as exc:
        print(red(f"  Error reading file: {exc}"))
        return collect_user_story()  # type: ignore[return-value]


def _get_baseline_text() -> str:
    return """## User Story
As a customer I want to browse products, add them to my cart, and proceed to checkout

## Acceptance Criteria
1. [navigate] From the home page, click on a product category link (e.g. a link that says "Dress")
2. [navigate] On the category page, click the "Add to cart" button next to a product
3. [assert] A confirmation popup appears with text "Product added to cart!" and a "Continue Shopping" button
4. [click] Click the "Continue Shopping" button to close the confirmation popup
5. [navigate] Click the "Cart" link or cart icon in the page header
6. [assert] The cart page displays a table showing the products I added, with product names, prices, and quantities
7. [navigate] From the cart page, click the "Check Out" button
8. [assert] The checkout page loads, showing a form to enter my details and an order summary

(Total: 8 criteria)
"""


# ── URL collection ─────────────────────────────────────────────────────────


def collect_urls() -> tuple[str, str]:
    """Let user enter target URLs. Returns (starting_url, additional_urls)."""
    print_header("Target URLs")

    choice = print_menu(
        ["Enter manually", "Load baseline (automationexercise.com)"],
        "URL source",
        shortcuts=[("M", "Manual"), ("B", "Baseline")],
    )

    if choice == 1:
        print(green("  Baseline loaded."))
        return "https://automationexercise.com/", ""

    starting = read_optional("  Starting URL (e.g. https://your-site.example/):")
    print("  Additional URLs (one per line, empty line to finish):")
    urls: list[str] = []
    try:
        while True:
            line = input()
            if not line and urls:
                break
            if line.strip():
                urls.append(line.strip())
    except EOFError:
        pass
    return starting, "\n".join(urls)


def parse_target_urls(base_url: str, urls_input: str) -> list[str]:
    """Merge base_url and additional URLs into a deduplicated list."""
    urls = [u.strip() for u in urls_input.splitlines() if u.strip()]
    if base_url.strip() and base_url.strip() not in urls:
        urls.insert(0, base_url.strip())
    return urls


# ── Consent mode ──────────────────────────────────────────────────────────


def collect_consent_mode() -> str:
    idx = print_menu(
        ["auto-dismiss", "leave-as-is", "test-consent-flow"],
        "Consent handling",
    )
    return ["auto-dismiss", "leave-as-is", "test-consent-flow"][idx]


# ── Authentication / Journey (AI-009 Phase B) ────────────────────────────


def collect_authentication() -> dict[str, str] | None:
    """Let user define a credential profile. Returns dict or None to skip."""
    print_header("Authentication (optional)")

    choice = print_menu(
        ["Configure credentials", "Skip (no authentication needed)"],
        "Authentication",
        shortcuts=[("C", "Configure"), ("S", "Skip")],
    )
    if choice == 1:
        print(yellow("  Skipping authentication setup."))
        return None

    label = read_non_empty("  Profile label (e.g. Standard user):")
    username = read_non_empty("  Username:")
    password = read_non_empty("  Password:")
    print(green(f"  ✓ Credential profile '{label}' saved (session only — never persisted to disk)."))
    return {"label": label, "username": username, "password": password}


JOURNEY_STEP_ACTIONS = ["navigate", "click", "fill", "wait", "scrape"]


def collect_journey_steps() -> list[dict[str, str]]:
    """Interactive journey builder. Returns list of step dicts."""
    print_header("Journey Builder (optional)")

    choice = print_menu(
        ["Build journey steps", "Skip (use static URL scraping)"],
        "Journey scraping",
        shortcuts=[("B", "Build"), ("S", "Skip")],
    )
    if choice == 1:
        print(yellow("  Skipping journey builder — using static URL scraping."))
        return []

    steps: list[dict[str, str]] = []
    print("  Define the steps the scraper will follow.")
    print("  Add a 'scrape' step wherever you want page context collected.\n")

    while True:
        if steps:
            print("  Current journey:")
            for i, step in enumerate(steps, 1):
                desc = step.get("description", "")
                action = step.get("action", "?")
                extra = ""
                if action == "navigate" and step.get("url"):
                    extra = f" -> {step['url']}"
                elif action == "click" and step.get("selector"):
                    extra = f" [{step['selector']}]"
                elif action == "fill" and step.get("selector"):
                    val = step.get("text", "")
                    if val in ("{{username}}", "{{password}}"):
                        extra = f" [{step['selector']} = {val}]"
                    else:
                        extra = f" [{step['selector']} = <redacted>]"
                print(f"    {i}. {action}{extra} ({desc})")
            print()

        add_choice = print_menu(
            ["Add step", "Done building"],
            "Journey builder",
            shortcuts=[("A", "Add"), ("D", "Done")],
        )
        if add_choice == 1:
            break

        action_idx = print_menu(JOURNEY_STEP_ACTIONS, "Step type")
        action = JOURNEY_STEP_ACTIONS[action_idx]

        new_step: dict[str, str] = {"action": action}
        desc = read_optional(f"  Description for this {action} step:")
        if desc:
            new_step["description"] = desc

        if action == "navigate":
            new_step["url"] = read_non_empty("  URL to navigate to:")
        elif action == "click":
            new_step["selector"] = read_non_empty("  CSS selector or button text:")
        elif action == "fill":
            new_step["selector"] = read_non_empty("  Input field selector:")
            raw_value = read_optional("  Value (or {{username}} / {{password}} for credential template):")
            new_step["text"] = raw_value
        elif action == "wait":
            new_step["selector"] = read_non_empty("  Selector to wait for:")

        steps.append(new_step)
        print(green(f"  ✓ Added {action} step.\n"))

    return steps


# ── File opener ───────────────────────────────────────────────────────────


def open_file(path: str) -> None:
    """Open a file using the system's default application."""
    import subprocess
    import sys

    try:
        if sys.platform == "win32":
            os.startfile(path)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["open", path], check=True)
        else:
            subprocess.run(["xdg-open", path], check=True)
    except Exception:
        pass
