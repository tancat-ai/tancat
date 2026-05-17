"""CLI menu rendering and input helpers.

Provides coloured menus, input prompts, and the LLM configuration flow.
"""

from __future__ import annotations

import os
from pathlib import Path

from .color import bold, green, red, yellow

# ── Print helpers ───────────────────────────────────────────────────────────


def print_header(title: str) -> None:
    width = 60
    print()
    print("=" * width)
    print(bold(f"  {title}"))
    print("=" * width)
    print()


def print_menu(options: list[str], prompt: str = "Choose an option") -> int:
    """Print a numbered menu and return the selected index (0-based)."""
    for i, opt in enumerate(options, 1):
        print(f"  {i}. {opt}")
    while True:
        try:
            choice = input(f"\n{prompt} [1-{len(options)}]: ").strip()
            idx = int(choice) - 1
            if 0 <= idx < len(options):
                return idx
        except ValueError, KeyboardInterrupt:
            pass
        print(yellow("  Invalid choice. Please try again."))


def read_non_empty(prompt: str) -> str:
    """Read a non-empty line from the user."""
    while True:
        value = input(prompt).strip()
        if value:
            return value
        print(yellow("  Input cannot be empty. Please try again."))


def read_optional(prompt: str, default: str = "") -> str:
    """Read a line, returning *default* on empty input."""
    value = input(prompt).strip()
    return value if value else default


# ── LLM configuration ─────────────────────────────────────────────────────


def _get_available_models(provider_name: str, provider_url: str) -> list[str]:
    """Try to list available models for the given provider."""
    try:
        import httpx

        if provider_name == "ollama":
            response = httpx.get(f"{provider_url}/api/tags", timeout=5.0)
            response.raise_for_status()
            return [m["name"] for m in response.json().get("models", [])]
        elif provider_name == "lm-studio":
            response = httpx.get(f"{provider_url}/v1/models", timeout=5.0)
            response.raise_for_status()
            return [m["id"] for m in response.json().get("data", [])]
        elif provider_name == "openai":
            return ["gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo"]
    except Exception:
        pass
    return []


def configure_llm(provider: str, base_url: str, model_name: str) -> tuple[str, str, str]:
    """Let the user pick LLM provider and model. Returns (provider, base_url, model)."""
    print_header("LLM Configuration")

    providers: list[tuple[str, str, str]] = [
        ("Ollama (local)", "ollama", "http://localhost:11434"),
        ("LM Studio (local)", "lm-studio", "http://localhost:1234"),
        ("OpenAI (cloud)", "openai", "https://api.openai.com"),
    ]

    idx = print_menu([p[0] for p in providers], "Select LLM provider")
    display_name, provider_key, default_url = providers[idx]

    url = read_optional(f"  Base URL (default: {default_url}):", default_url)

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
        selected_model = read_optional(f"  Model name (default: {fallback}):", fallback)

    print(green(f"  ✓ Provider: {provider_key} | URL: {url} | Model: {selected_model}"))
    return provider_key, url, selected_model


def _default_model(provider: str) -> str:
    if provider == "ollama":
        return "qwen3.5:35b"
    if provider == "lm-studio":
        return "lmstudio-community/Qwen2.5-7B-Instruct-GGUF"
    return "gpt-4o"


# ── User story collection ─────────────────────────────────────────────────


def collect_user_story() -> str:
    """Let user paste or upload a user story. Returns raw text."""
    print_header("User Story Input")

    mode = print_menu(
        ["Paste Text", "Upload File", "Load baseline (automationexercise.com)"],
        "Input method",
    )

    baseline_text = _get_baseline_text()

    if mode == 2:
        print(green("  Baseline loaded."))
        return baseline_text

    if mode == 0:
        print("\n  Paste your user story and acceptance criteria below.")
        print("  (End with an empty line or Ctrl+D / Ctrl+Z on Windows)")
        print("  ---")
        lines: list[str] = []
        try:
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
        return collect_user_story()
    try:
        content = Path(filepath).read_text(encoding="utf-8")
        print(green(f"  Read {len(content)} characters from {filepath}"))
        return content
    except FileNotFoundError:
        print(red(f"  File not found: {filepath}"))
        return collect_user_story()  # type: ignore[name-defined]
    except Exception as exc:
        print(red(f"  Error reading file: {exc}"))
        return collect_user_story()  # type: ignore[name-defined]


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
        # "scrape" steps capture page context — no extra fields needed

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
