"""Product CLI surface (t-0405 / t-0565): help, version, exit codes, run, check-llm.

The interactive menu stays the default; these tests pin the headless surface a
script, an agent or the CI Action consumes:

- ``--help`` / ``--version`` print and exit 0
- an unknown flag or command errors (exit 2)
- ``run`` is the product's headless driver (same code the Action calls) and a
  failed run exits non-zero
- ``--json`` is parseable
"""

from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest

from src.cli import main as cli_main
from src.llm_health import HealthCheckResult

REPO_ROOT = Path(__file__).resolve().parent.parent
MOCK_DIR = REPO_ROOT / "mock_sites" / "ecommerce"

ECOMMERCE_STORY = (
    "As a customer, I want to browse products on the store, add them to my cart, "
    "proceed to checkout, and place an order."
)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


# ---------------------------------------------------------------------------
# Help / version / unknown flags (offline, in-process)
# ---------------------------------------------------------------------------


def test_help_exits_zero_with_usage(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli_main.main(["--help"]) == 0
    out = capsys.readouterr().out
    assert "Usage:" in out
    assert "Playwright" in out
    assert "tancat run" in out


def test_version_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli_main.main(["--version"]) == 0
    out = capsys.readouterr().out.strip()
    assert out.startswith("tancat ")
    assert out.split()[-1][0].isdigit()


def test_unknown_flag_exits_two(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli_main.main(["--definitely-not-a-flag"]) == 2
    assert "unrecognized arguments" in capsys.readouterr().err


def test_unknown_command_exits_two(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli_main.main(["frobnicate"]) == 2
    assert "invalid choice" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# check-llm (offline: the probe is patched, no network)
# ---------------------------------------------------------------------------


def _healthy() -> HealthCheckResult:
    return HealthCheckResult(
        provider="openai-local",
        base_url="http://127.0.0.1:8080/v1",
        requested_model="llama",
        reachable=True,
        key_ok=True,
        model_available=True,
        capability_ok=True,
        elapsed_s=0.1,
        sample_output="ready",
    )


def test_check_llm_json_is_parseable(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    import src.llm_health as health

    monkeypatch.setattr(health, "build_client", lambda *a, **k: object())
    monkeypatch.setattr(health, "check_llm", lambda *a, **k: _healthy())

    assert cli_main.main(["check-llm", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert payload["ok"] is True
    assert payload["exit_code"] == 0
    assert payload["provider"] == "openai-local"


def test_check_llm_unreachable_exits_one(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    import src.llm_health as health

    broken = HealthCheckResult(
        provider="openai-local",
        base_url="http://127.0.0.1:1/v1",
        requested_model="llama",
        reachable=False,
        key_ok=True,
        model_available=True,
        capability_ok=False,
        errors=["connection refused"],
    )
    monkeypatch.setattr(health, "build_client", lambda *a, **k: object())
    monkeypatch.setattr(health, "check_llm", lambda *a, **k: broken)

    assert cli_main.main(["check-llm", "--json"]) == 1
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert payload["ok"] is False
    assert payload["exit_code"] == 1


# ---------------------------------------------------------------------------
# run (config errors offline; one hermetic E2E through the product CLI)
# ---------------------------------------------------------------------------


def test_run_config_error_exits_two(capsys: pytest.CaptureFixture[str]) -> None:
    """A failed run is a non-zero exit a CI script can branch on."""
    rc = cli_main.main(["run", "--story", "s", "--url", "https://prod.example.com/"])
    assert rc == 2
    assert "not on the safe allow-list" in capsys.readouterr().err


@pytest.mark.slow
@pytest.mark.integration
def test_run_e2e_through_product_cli_matches_action_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """`tancat run` runs the same pipeline the Action calls, and --json parses."""
    from scripts.fake_llm import FakeLLMServer
    from scripts.mock_server import MockServer

    monkeypatch.setenv("RAG_ENABLED", "0")
    monkeypatch.setenv("FLOW_MEMORY_ENABLED", "0")

    mock_port = _free_port()
    workspace = tmp_path / "ws"

    try:
        with MockServer.start(port=mock_port, directory=str(MOCK_DIR)):
            with FakeLLMServer() as fake:
                rc = cli_main.main(
                    [
                        "run",
                        "--story",
                        ECOMMERCE_STORY,
                        "--url",
                        f"http://localhost:{mock_port}/index.html",
                        "--workspace",
                        str(workspace),
                        "--provider",
                        "openai-local",
                        "--llm-base-url",
                        fake.url,
                        "--model",
                        "fake-model",
                        "--json",
                    ]
                )
    finally:
        from src.storage import reset_storage

        reset_storage()

    assert rc == 0, capsys.readouterr().err
    payload = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert payload["ok"] is True
    assert payload["mode"] == "generate-only"
    assert payload["test_count"] >= 1
    package = Path(payload["package"])
    assert package.exists()
    assert workspace in package.parents
