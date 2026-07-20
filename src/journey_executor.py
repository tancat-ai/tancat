"""Execute authenticated journeys with SSO/MFA/CAPTCHA detection.

This module provides the ``execute_journey`` public API — a subprocess-backed
entry point for running journey steps through authenticated pages. It is
distinct from ``JourneyScraper`` (in journey_scraper.py) which follows a
scrape-focused path; this module focuses on user interaction with auth guards.
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

from src.accessibility_enricher import AccessibilityEnricher
from src.journey_auth_detector import (
    detect_auth_redirect,
    detect_captcha,
    detect_mfa,
    detect_sso,
)
from src.journey_enrichment import capture_a11y_snapshot_sync
from src.journey_models import CredentialProfile, JourneyResult, JourneyStep, substitute_templates
from src.scraper import PageScraper

# ───────────────────────────────────────────────────────────────
# _execute_journey_sync  (runs inside a subprocess)
# ───────────────────────────────────────────────────────────────


def _execute_journey_sync(
    journey_steps: list[JourneyStep],
    credential_profile: CredentialProfile | None = None,
    timeout_ms: int = 30_000,
    starting_url: str | None = None,
) -> JourneyResult:
    """Execute journey steps in a single Playwright browser session.

    Checks for auth redirects, SSO, MFA, and CAPTCHA — returns explicit errors.
    """
    captured_pages: dict[str, list[dict[str, Any]]] = {}
    failed_steps: list[str] = []
    redirected_urls: list[str] = []
    error_message: str | None = None

    # Determine base domain for SSO detection
    base_domain: str = ""
    if starting_url:
        base_domain = urlparse(starting_url).netloc

    html_scraper = PageScraper(timeout_ms=timeout_ms)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()
        page.set_default_timeout(timeout_ms)

        try:
            # Navigate to starting URL if provided
            if starting_url:
                page.goto(starting_url, wait_until="networkidle", timeout=timeout_ms)
                _dismiss_consent_overlays(page)
                base_domain = urlparse(page.url).netloc

            current_url: str = page.url

            for step_index, step in enumerate(journey_steps):
                if error_message:
                    # Journey stopped by detection — record remaining as failed
                    failed_steps.append(f"Step {step_index + 1} ({step.action}): journey stopped — {error_message}")
                    continue

                try:
                    if step.action == "goto" or step.action == "navigate":
                        target_url = step.url or ""
                        if not target_url:
                            failed_steps.append(f"Step {step_index + 1}: goto/navigate without url")
                            continue

                        page.goto(target_url, wait_until="networkidle", timeout=step.timeout_ms)
                        _dismiss_consent_overlays(page)

                        current_url = page.url

                        # Update base_domain from first navigation
                        if not base_domain:
                            base_domain = urlparse(current_url).netloc

                        # Auth redirect detection
                        page_title = page.title()
                        h1_text = ""
                        try:
                            h1_el = page.locator("h1").first
                            if h1_el.count() > 0:
                                h1_text = h1_el.inner_text()
                        except Exception:
                            pass

                        if detect_auth_redirect(current_url, target_url, page_title, h1_text):
                            failed_steps.append(
                                f"Step {step_index + 1}: Page redirected to login — add a login step before this page"
                            )
                            if current_url not in redirected_urls:
                                redirected_urls.append(current_url)

                        # SSO detection
                        if base_domain and detect_sso(base_domain, current_url):
                            error_message = (
                                "SSO/OAuth redirect detected — automated login not supported for this provider"
                            )
                            failed_steps.append(f"Step {step_index + 1}: {error_message}")

                        # CAPTCHA detection
                        html = page.content()
                        if detect_captcha(html):
                            error_message = "CAPTCHA detected — automated login not supported"
                            failed_steps.append(f"Step {step_index + 1}: {error_message}")

                        # MFA detection
                        if detect_mfa(html):
                            error_message = "MFA prompt detected — automated login not supported"
                            failed_steps.append(f"Step {step_index + 1}: {error_message}")

                    elif step.action == "click":
                        selector = step.selector
                        text = step.text
                        if not selector and text:
                            # Try text-based click
                            try:
                                page.get_by_text(text, exact=False).first.click(timeout=step.timeout_ms)
                            except Exception:
                                failed_steps.append(f"Step {step_index + 1}: Could not click text '{text}'")
                            continue
                        if not selector:
                            failed_steps.append(f"Step {step_index + 1}: click without selector or text")
                            continue
                        try:
                            _click_with_locator(page, selector, step.timeout_ms)
                        except Exception as e:
                            failed_steps.append(f"Step {step_index + 1}: click '{selector}' failed — {e}")

                    elif step.action == "fill":
                        selector = step.selector
                        if not selector:
                            failed_steps.append(f"Step {step_index + 1}: fill without selector")
                            continue
                        fill_text = step.text or ""
                        fill_text = substitute_templates(fill_text, credential_profile)
                        try:
                            _fill_with_locator(page, selector, fill_text, step.timeout_ms)
                        except Exception as e:
                            failed_steps.append(f"Step {step_index + 1}: fill '{selector}' failed — {e}")

                    elif step.action == "submit":
                        # Submit — click submit button
                        submit_selectors = [
                            "input[type='submit']",
                            "button[type='submit']",
                            "button:has-text('Submit')",
                            "button:has-text('submit')",
                        ]
                        clicked = False
                        for sel in submit_selectors:
                            try:
                                loc = page.locator(sel).first
                                if loc.count() > 0:
                                    loc.click(timeout=step.timeout_ms)
                                    clicked = True
                                    break
                            except Exception:
                                continue
                        if not clicked:
                            failed_steps.append(f"Step {step_index + 1}: submit — no submit button found")

                    elif step.action == "capture":
                        html = page.content()
                        elements = html_scraper._extract_elements_from_html(html, base_url=page.url)  # noqa: SLF001
                        try:
                            a11y_snapshot = capture_a11y_snapshot_sync(context, page)
                            if a11y_snapshot is not None:
                                elements = AccessibilityEnricher.enrich(elements, a11y_snapshot)  # type: ignore[arg-type]
                        except Exception:
                            pass
                        captured_pages[current_url] = elements

                    elif step.action == "wait":
                        wait_desc = step.description or "1.0"
                        try:
                            wait_seconds = float(wait_desc)
                        except ValueError:
                            wait_seconds = 1.0
                        page.wait_for_timeout(int(wait_seconds * 1000))
                        # Also wait for selector if provided
                        if step.selector:
                            try:
                                page.wait_for_selector(step.selector, timeout=step.timeout_ms)
                            except Exception:
                                pass

                except Exception as e:
                    failed_steps.append(f"Step {step_index + 1} ({step.description or step.action}): {e}")

                current_url = page.url

        finally:
            context.close()
            browser.close()

    success = error_message is None and not failed_steps
    return JourneyResult(
        success=success,
        captured_pages=captured_pages,
        failed_steps=failed_steps,
        error_message=error_message,
        redirected_urls=redirected_urls,
    )


# ───────────────────────────────────────────────────────────────
# execute_journey  (public API — subprocess pattern)
# ───────────────────────────────────────────────────────────────


def execute_journey(
    journey_steps: list[JourneyStep],
    credential_profile: CredentialProfile | None = None,
    timeout_ms: int = 30_000,
    starting_url: str | None = None,
) -> JourneyResult:
    """Execute a journey in a subprocess (avoids ProactorEventLoop on Windows).

    Serialises steps to JSON, spawns subprocess, deserialises JourneyResult.
    """
    steps_data = [asdict(s) for s in journey_steps]
    credential_data = asdict(credential_profile) if credential_profile else None

    payload = {
        "journey_steps": steps_data,
        "credential_profile": credential_data,
        "timeout_ms": timeout_ms,
        "starting_url": starting_url,
    }

    subprocess_path = str(Path(__file__).resolve().with_name("journey_executor.py"))
    completed = subprocess_run(
        subprocess_path,
        "--execute-journey",
        payload,
        timeout_ms,
        len(journey_steps),
    )

    return _parse_execute_result(completed)


def _parse_execute_result(completed: Any) -> JourneyResult:
    """Parse the subprocess result for execute_journey."""
    if completed.stderr:
        print(completed.stderr, flush=True, file=sys.stderr)

    if completed.returncode != 0:
        return JourneyResult(
            success=False,
            captured_pages={},
            failed_steps=["Subprocess failed to execute journey"],
            error_message=completed.stderr.strip() if completed.stderr else "Subprocess error",
        )

    try:
        data = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError:
        return JourneyResult(
            success=False,
            captured_pages={},
            failed_steps=["Failed to parse subprocess output"],
            error_message="Invalid JSON from subprocess",
        )

    if not isinstance(data, dict):
        return JourneyResult(
            success=False,
            captured_pages={},
            failed_steps=["Subprocess returned unexpected output"],
        )

    return JourneyResult.from_dict(data)


def subprocess_run(subprocess_path: str, flag: str, payload: dict, timeout_ms: int, step_count: int) -> Any:
    """Helper to run a subprocess with JSON payload."""
    import subprocess as _subprocess

    return _subprocess.run(
        [sys.executable, subprocess_path, flag],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
        timeout=max(120, timeout_ms // 1000 * max(1, step_count)),
    )


# ────────────────────────────────────────────────────────────────
# Helpers extracted from JourneyScraper for executor use
# ────────────────────────────────────────────────────────────────


def _dismiss_consent_overlays(page: Any) -> None:
    """Dismiss cookie consent and ad overlays."""
    from src.browser_utils import dismiss_consent_overlays

    dismiss_consent_overlays(page)  # type: ignore[arg-type]


def _click_with_locator(page: Any, selector: str, timeout_ms: int) -> None:
    """Click an element by selector, with scroll-into-view."""
    locator = page.locator(selector).first
    if locator.count() == 0:
        return
    try:
        locator.scroll_into_view_if_needed(timeout=min(2000, timeout_ms))
    except Exception:
        pass
    locator.click(timeout=min(5000, timeout_ms))
    page.wait_for_timeout(500)


def _fill_with_locator(page: Any, selector: str, text: str, timeout_ms: int) -> None:
    """Fill an input element by selector."""
    locator = page.locator(selector).first
    if locator.count() == 0:
        return
    locator.fill(text)


# ─── Legacy alias (deduplicated — see journey_enrichment.py) ───
_capture_a11y_snapshot_sync = capture_a11y_snapshot_sync  # noqa: PLW1508


# ────────────────────────────────────────────────────────────────
# Subprocess entry points
# ────────────────────────────────────────────────────────────────


def _run_execute_journey_entry() -> int:
    """Entry point for the subprocess-backed execute_journey."""
    payload = json.loads(sys.stdin.read() or "{}")
    if not isinstance(payload, dict):
        print(
            json.dumps(
                JourneyResult(
                    success=False,
                    captured_pages={},
                    failed_steps=["Invalid payload"],
                    error_message="Invalid JSON payload",
                ).to_dict()
            )
        )
        return 1

    # Reconstruct journey steps
    steps_data = payload.get("journey_steps", [])
    steps: list[JourneyStep] = []
    for s in steps_data:
        if not isinstance(s, dict):
            continue
        steps.append(
            JourneyStep(
                action=str(s.get("action", "")),
                url=str(s["url"]) if s.get("url") else None,
                selector=str(s["selector"]) if s.get("selector") else None,
                text=str(s["text"]) if s.get("text") else None,
                description=str(s.get("description", "")),
                timeout_ms=int(s.get("timeout_ms", 30_000)),
            )
        )

    # Reconstruct credential profile
    credential_data = payload.get("credential_profile")
    credential_profile: CredentialProfile | None = None
    if credential_data and isinstance(credential_data, dict):
        credential_profile = CredentialProfile(
            label=str(credential_data.get("label", "")),
            username=str(credential_data.get("username", "")),
            password=str(credential_data.get("password", "")),
        )

    timeout_ms = int(payload.get("timeout_ms", 30_000))
    starting_url = payload.get("starting_url")

    result = _execute_journey_sync(
        journey_steps=steps,
        credential_profile=credential_profile,
        timeout_ms=timeout_ms,
        starting_url=starting_url,
    )
    print(json.dumps(result.to_dict()))
    return 0


if __name__ == "__main__":
    if "--execute-journey" in sys.argv:
        raise SystemExit(_run_execute_journey_entry())
