"""Step-through debugger for generated Playwright test packages.

Runs the REAL test functions (imported from a generated package) in a HEADED
browser, pausing after every tracker step so you can watch the page and the
add-to-cart modal / consent / ad-overlay behavior live.

The auto-dismissal logic lives inside EvidenceTracker.click() and is invisible
in the test file — this tool surfaces it by printing, before and after each
step:

  * current URL
  * add-to-cart modal (.modal-content) visibility
  * FreeCmp consent root (.fc-consent-root) presence
  * Google vignette (#google_vignette) presence
  * cart link count (header vs modal "View Cart")
  * the step result the tracker recorded (elapsed / status / no-op notes)

Usage:
    python scripts/debug_step_through.py <path/to/test_package/test_file.py>
    python scripts/debug_step_through.py <test_file.py> --test test_t10
    python scripts/debug_step_through.py <test_file.py> --auto   # no Enter prompts
    python scripts/debug_step_through.py <test_file.py> --headless

Examples:
    python scripts/debug_step_through.py generated_tests/test_20260803_101815_.../test_....py --test test_t10
    python scripts/debug_step_through.py generated_tests/verify_automationexercise_20260803_032242/test_automationexercise.py
"""

from __future__ import annotations

import argparse
import importlib.util
import inspect
import sys
import tempfile
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from playwright.sync_api import sync_playwright  # noqa: E402

from src.evidence_tracker import EvidenceTracker  # noqa: E402

# ── State inspection helpers ──────────────────────────────────────────────


def _state(page: Any) -> dict[str, Any]:
    """Snapshot of the signals that matter: modal, consent, ad, cart links."""

    def vis(sel: str) -> str:
        loc = page.locator(sel)
        if loc.count() == 0:
            return "absent"
        try:
            return "visible" if loc.first.is_visible() else "hidden"
        except Exception:
            return "?"

    cart_links = page.locator('a[href="/view_cart"]')
    return {
        "url": page.url,
        "modal(.modal-content)": vis(".modal-content"),
        "fc-consent-root": vis(".fc-consent-root"),
        "google_vignette": vis("#google_vignette"),
        "cart-links": cart_links.count(),
        "checkout-btn(.btn.check_out)": vis(".btn.check_out"),
        "do_action": vis("#do_action"),
    }


def _fmt_state(s: dict[str, Any]) -> str:
    return (
        f"  url={s['url']}\n"
        f"  modal={s['modal(.modal-content)']}  fc-consent={s['fc-consent-root']}  "
        f"vignette={s['google_vignette']}\n"
        f"  cart-links={s['cart-links']}  checkout-btn={s['checkout-btn(.btn.check_out)']}  "
        f"do_action={s['do_action']}"
    )


# ── Pausing tracker wrapper ───────────────────────────────────────────────


class StepTracker(EvidenceTracker):
    """EvidenceTracker that pauses after every public action and prints state."""

    auto: bool = False

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._step_no = 0

    def _pause(self, msg: str) -> None:
        print("\n" + msg)
        print(_fmt_state(_state(self.page)))
        if self.auto:
            return
        try:
            input("    [Enter] continue... ")
        except EOFError:
            pass

    def _after(self, action: str, label: str) -> None:
        self._step_no += 1
        last = self.steps[-1] if self.steps else {}
        result = last.get("result", {})
        note = (last.get("element") or {}).get("note", "")
        print(
            f"  -- step {self._step_no}: {action} [{label}] -> {result.get('status')} "
            f"({result.get('elapsed_ms')}ms){'  NOTE: ' + note if note else ''}"
        )
        print(_fmt_state(_state(self.page)))

    # Public actions the generated tests call — all route through the tracker.
    def navigate(self, url: str, label: str = "") -> None:
        label = label or f"Navigate to {url}"
        self._pause(f">> BEFORE {label}")
        super().navigate(url, label)
        self._after("navigate", label)

    def click(self, locator: str, label: str = "") -> None:
        label = label or f"Click {locator}"
        self._pause(f">> BEFORE {label}  (tracker auto-dismisses overlays + modals before this)")
        super().click(locator, label)
        self._after("click", label)

    def fill(self, locator: str, value: str, label: str = "") -> None:
        label = label or f"Fill {locator}"
        self._pause(f">> BEFORE {label}")
        super().fill(locator, value, label)
        self._after("fill", label)

    def assert_visible(self, locator: str, label: str = "") -> None:
        label = label or f"Assert visible: {locator}"
        self._pause(f">> BEFORE {label}")
        super().assert_visible(locator, label)
        self._after("assert_visible", label)

    def assert_hidden(self, locator: str, label: str = "") -> None:
        label = label or f"Assert hidden: {locator}"
        self._pause(f">> BEFORE {label}")
        super().assert_hidden(locator, label)
        self._after("assert_hidden", label)

    def assert_text(self, locator: str, expected: str, label: str = "") -> None:
        label = label or f"Assert text: {expected}"
        self._pause(f">> BEFORE {label}")
        super().assert_text(locator, expected, label)
        self._after("assert_text", label)


# ── Test loader + runner ──────────────────────────────────────────────────


def load_tests(test_file: Path) -> list[tuple[str, Any]]:
    """Import the test module and return (name, fn) for each test_* function."""
    sys.path.insert(0, str(test_file.parent))  # so `from pages.x import Y` resolves
    spec = importlib.util.spec_from_file_location("generated_test_module", test_file)
    assert spec and spec.loader, f"cannot load {test_file}"
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    tests = [(name, fn) for name, fn in inspect.getmembers(mod, inspect.isfunction) if name.startswith("test_")]
    return tests


def run_test(test_file: Path, name: str, fn: Any, headless: bool) -> None:
    print(f"\n{'=' * 70}\nTEST: {name}  (headed={not headless})\n{'=' * 70}")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        page = context.new_page()
        with tempfile.TemporaryDirectory(prefix="step_through_") as tmp:
            tracker = StepTracker(
                page,
                test_name=name,
                condition_ref="DBG",
                story_ref="DBG",
                test_package_dir=Path(tmp),
            )
            tracker.auto = auto_mode
            try:
                fn(page=page, evidence_tracker=tracker)
                print(f"\n[OK] {name} FINISHED")
            except Exception as exc:  # noqa: BLE001 - debug tool
                print(f"\n[FAIL] {name} raised: {type(exc).__name__}: {exc}")
            finally:
                browser.close()


def main() -> None:
    global auto_mode
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("test_file", type=Path, help="Path to the generated test .py file")
    parser.add_argument("--test", default="", help="Only run tests whose name contains this substring")
    parser.add_argument("--auto", action="store_true", help="Do not wait for Enter between steps")
    parser.add_argument("--headless", action="store_true", help="Run headless (default is headed)")
    args = parser.parse_args()
    auto_mode = args.auto

    if not args.test_file.exists():
        sys.exit(f"test file not found: {args.test_file}")

    tests = load_tests(args.test_file)
    if args.test:
        tests = [(n, f) for n, f in tests if args.test in n]
    if not tests:
        sys.exit(f"no tests found in {args.test_file} (filter={args.test!r})")

    print(f"Loaded {len(tests)} test(s) from {args.test_file}")
    for name, fn in tests:
        run_test(args.test_file, name, fn, headless=args.headless)


if __name__ == "__main__":
    main()
