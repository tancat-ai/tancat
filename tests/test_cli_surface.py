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
    lines = capsys.readouterr().out.strip().splitlines()
    # d-0132: the version block is now three lines - version+commit, the Python
    # build, and the provider/model - so a bug report carries the build facts.
    assert lines[0].startswith("tancat ")
    assert lines[0].split()[1][0].isdigit()
    assert "(commit " in lines[0]
    assert lines[1].startswith("Python ")
    assert lines[2].startswith("Provider ")


def test_short_version_flag_matches_long(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli_main.main(["-V"]) == 0
    out = capsys.readouterr().out
    assert out.startswith("tancat ")
    assert "-V" in cli_main._USAGE


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
# provider refusal (d-0132 blocker at 7660ab8)
#
# A stale LLM_PROVIDER used to raise out of create_session as a raw traceback
# with exit 1 - even when a valid --provider was passed on the command line.
# The provider is now resolved and validated at the session boundary, and the
# precedence is flag > saved setting (B-036) > environment > openai-local, so a
# stale env var cannot hijack the choice the user saved in the tool.
# ---------------------------------------------------------------------------


def _nothing_saved(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clear the settings store for this test, so the environment is the source."""
    import src.cli.session as session_mod

    monkeypatch.setattr(session_mod, "load_setting", lambda key, default=None: default)


def _save_provider(monkeypatch: pytest.MonkeyPatch, provider: str) -> None:
    """Make the settings store hold *provider* (and nothing else that matters)."""
    import src.cli.session as session_mod

    monkeypatch.setattr(
        session_mod,
        "load_setting",
        lambda key, default=None: provider if key == "provider" else default,
    )


def _record_provider(monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Patch the health probe and record which provider the CLI actually used."""
    import src.llm_health as health

    used: dict[str, str] = {}

    def fake_build(provider: str, base_url: str | None = None, model: str | None = None) -> object:
        used["provider"] = provider
        return object()

    monkeypatch.setattr(health, "build_client", fake_build)
    monkeypatch.setattr(health, "check_llm", lambda *a, **k: _healthy())
    return used


def test_check_llm_refuses_unknown_env_provider(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _nothing_saved(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "bogus")
    assert cli_main.main(["check-llm"]) == 2
    captured = capsys.readouterr()
    assert "unknown LLM provider 'bogus'" in captured.err
    assert "Traceback" not in captured.err + captured.out


def test_valid_flag_wins_over_unknown_env_provider(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _nothing_saved(monkeypatch)
    used = _record_provider(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "bogus")

    assert cli_main.main(["check-llm", "--provider", "openai-local", "--json"]) == 0
    assert used["provider"] == "openai-local"
    assert "Traceback" not in capsys.readouterr().err


def test_saved_provider_wins_over_the_environment(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """B-036: a stale env var must never hijack the provider saved in the tool."""
    _save_provider(monkeypatch, "lm-studio")
    used = _record_provider(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "openai")

    assert cli_main.main(["check-llm", "--json"]) == 0
    assert used["provider"] == "lm-studio"
    assert "Traceback" not in capsys.readouterr().err


def test_check_llm_refuses_unknown_persisted_provider(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _save_provider(monkeypatch, "bogus")
    assert cli_main.main(["check-llm"]) == 2
    captured = capsys.readouterr()
    assert "unknown LLM provider 'bogus'" in captured.err
    assert "Traceback" not in captured.err + captured.out


def test_valid_flag_wins_over_unknown_persisted_provider(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _save_provider(monkeypatch, "bogus")
    used = _record_provider(monkeypatch)

    assert cli_main.main(["check-llm", "--provider", "lm-studio", "--json"]) == 0
    assert used["provider"] == "lm-studio"


def test_interactive_start_refuses_unknown_env_provider(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _nothing_saved(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "bogus")
    assert cli_main.main([]) == 2
    captured = capsys.readouterr()
    assert "unknown LLM provider 'bogus'" in captured.err
    assert "Traceback" not in captured.err + captured.out


def test_interactive_start_refuses_unknown_persisted_provider(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _save_provider(monkeypatch, "bogus")
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    assert cli_main.main([]) == 2
    captured = capsys.readouterr()
    assert "unknown LLM provider 'bogus'" in captured.err
    assert "Traceback" not in captured.err + captured.out


# ---------------------------------------------------------------------------
# run (config errors offline; one hermetic E2E through the product CLI)
# ---------------------------------------------------------------------------


def test_run_config_error_exits_two(capsys: pytest.CaptureFixture[str]) -> None:
    """A failed run is a non-zero exit a CI script can branch on."""
    rc = cli_main.main(["run", "--story", "s", "--url", "https://prod.example.com/"])
    assert rc == 2
    assert "not on the safe allow-list" in capsys.readouterr().err


def test_interactive_exit_code_reflects_the_latest_run(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A failed run followed by a successful run must exit 0 (t-0569).

    The interactive session used to keep the first failure's flag, so a session
    that failed once and then succeeded still exited 1.
    """
    import asyncio

    from src.cli.session import Session

    session = Session(
        raw_requirements="As a user I want to log in so that I can access my account.",
        starting_url="https://example.com/",
        plan_confirmed=True,
    )
    monkeypatch.setattr(cli_main, "create_session", lambda: session)
    monkeypatch.setattr(cli_main, "_apply_session_llm_config", lambda _session: None)

    runs = {"count": 0}

    async def fake_run_pipeline(target: Session) -> None:
        runs["count"] += 1
        if runs["count"] == 1:
            target.pipeline_error = "boom (first run)"

    monkeypatch.setattr(cli_main, "run_pipeline", fake_run_pipeline)

    choices = iter(["Run Intelligent Pipeline", "Run Intelligent Pipeline", "Exit"])

    def fake_print_menu(options: list[str], *args: object, **kwargs: object) -> int:
        return options.index(next(choices))

    monkeypatch.setattr(cli_main, "print_menu", fake_print_menu)

    rc = asyncio.run(cli_main.interactive_session())

    assert runs["count"] == 2, "the test did not drive two runs"
    assert rc == 0, "a successful latest run must exit 0 despite the earlier failure"


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
