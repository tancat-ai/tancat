"""t-1509: a fresh install draws its whole page, licence panel included, in 5s.

Run in a real browser, because that is where the stall showed: under AppTest the page
looked complete, while Chromium sat on a half-drawn sidebar with Streamlit's Stop
button still spinning and never reached the licence block.

The server is started with no LLM reachable (an endpoint on a closed port), exactly
like a fresh install. The test then asserts, within five seconds of opening the page,
that the licence field, the Activate button and the "no model" warning are all there.
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path

import pytest

playwright_api = pytest.importorskip("playwright.sync_api", reason="playwright is a dev dependency")

REPO_ROOT = Path(__file__).resolve().parent.parent
WAIT_SECONDS = 5.0


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _dead_endpoint() -> str:
    """A port nothing listens on: the fresh-install case."""
    return f"http://127.0.0.1:{_free_port()}/v1"


@pytest.fixture(scope="module")
def app_server() -> Iterator[tuple[str, subprocess.Popen[bytes]]]:
    port = _free_port()
    env = {
        **os.environ,
        # Point the product at an endpoint that cannot answer, with no provider key.
        "OPENAI_BASE_URL": _dead_endpoint(),
        "OPENAI_API_KEY": "not-a-key",
        "LLM_PROVIDER": "openai-local",
        "PYTHONIOENCODING": "utf-8",
        # Keep the probe path honest: no saved settings from this machine.
        "STREAMLIT_SERVER_HEADLESS": "true",
        "STREAMLIT_BROWSER_GATHER_USAGE_STATS": "false",
    }
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "streamlit",
            "run",
            str(REPO_ROOT / "streamlit_app.py"),
            "--server.port",
            str(port),
            "--server.headless",
            "true",
        ],
        cwd=str(REPO_ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    url = f"http://127.0.0.1:{port}"
    deadline = time.time() + 60
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=1):
                break
        except OSError:
            if proc.poll() is not None:
                pytest.fail("the Streamlit server exited before it could be tested")
            time.sleep(0.25)
    else:
        proc.terminate()
        pytest.fail("the Streamlit server did not open its port within 60s")
    yield url, proc
    proc.terminate()
    try:
        proc.wait(timeout=20)
    except subprocess.TimeoutExpired:  # pragma: no cover - a wedged server
        proc.kill()


def test_a_fresh_install_draws_the_licence_panel_within_five_seconds(
    app_server: tuple[str, subprocess.Popen[bytes]],
) -> None:
    url, _proc = app_server
    with playwright_api.sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page()
            started = time.perf_counter()
            page.goto(url, wait_until="domcontentloaded", timeout=30_000)

            # The licence field and its button: the last thing a stalled render reaches.
            page.get_by_label("Licence key").first.wait_for(timeout=int(WAIT_SECONDS * 1000))
            page.get_by_role("button", name="Activate").first.wait_for(timeout=1_000)

            # And the visible "no model" state, not silence.
            warning = page.get_by_text("No model is configured yet").or_(page.get_by_text("No answer from"))
            warning.first.wait_for(timeout=int(WAIT_SECONDS * 1000))

            elapsed = time.perf_counter() - started
            assert elapsed <= WAIT_SECONDS, f"the page took {elapsed:.1f}s to draw its licence panel"

            # The free-tier line the licence panel prints when nothing is stored.
            body = page.inner_text("body")
            assert "free tier" in body.lower(), "the licence panel did not report the free tier"
        finally:
            browser.close()
