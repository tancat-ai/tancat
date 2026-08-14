"""Tests for the headless CI generation driver (Phase 7a).

- Unit: exit-code contract, danger-zone allow-list, config errors (offline).
- E2E: full generation against the ecommerce mock with the fake LLM — the
  hermetic proof that the headless path works with zero external services.
"""

from __future__ import annotations

import json
import socket
from pathlib import Path

import pytest

import scripts.ci_generate as ci_generate
from scripts.fake_llm import FakeLLMServer
from scripts.mock_server import MockServer
from src.ci_ignore import load_ignore_spec

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
# Danger-zone allow-list (Q3 grilling)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:8781/index.html",
        "http://127.0.0.1:9000/",
        "https://app.staging.example.com/",
        "https://shop.test.example.com/",
        "https://checkout-uat-dev.example.com/",
        "https://internal-staging.example.com/",
    ],
)
def test_allow_list_accepts_safe_urls(url: str) -> None:
    assert ci_generate._is_allowed_url(url, allowed_domains=())


@pytest.mark.parametrize(
    "url",
    [
        "https://shop.example.com/",
        "https://www.production.example.com/",
        "https://app.example.com/",
    ],
)
def test_allow_list_blocks_production_looking_urls(url: str) -> None:
    assert not ci_generate._is_allowed_url(url, allowed_domains=())


def test_allowed_domains_extension() -> None:
    url = "https://app.internal.company.com/"
    assert not ci_generate._is_allowed_url(url, allowed_domains=())
    assert ci_generate._is_allowed_url(url, allowed_domains=("internal.company.com",))
    assert ci_generate._is_allowed_url(url, allowed_domains=("internal.company.com", "other.com"))


# ---------------------------------------------------------------------------
# Config errors (exit 2) — no LLM, no browser, no network
# ---------------------------------------------------------------------------


def test_production_url_blocked_exits_2(capsys: pytest.CaptureFixture[str]) -> None:
    rc = ci_generate.main(["--story", "test story", "--url", "https://shop.example.com/"])
    assert rc == ci_generate.EXIT_CONFIG_ERROR
    assert "not on the safe allow-list" in capsys.readouterr().err


def test_empty_story_exits_2() -> None:
    rc = ci_generate.main(["--story", "", "--url", "http://localhost:8781/"])
    assert rc == ci_generate.EXIT_CONFIG_ERROR


def test_bad_ignore_file_exits_2(tmp_path: object, capsys: pytest.CaptureFixture[str]) -> None:
    bad = f"{tmp_path}/bad.yml"
    with open(bad, "w", encoding="utf-8") as fh:
        fh.write("ignores: [unclosed\n")
    rc = ci_generate.main(
        [
            "--story",
            "s",
            "--url",
            "http://localhost:8781/",
            "--ignore-file",
            bad,
        ]
    )
    assert rc == ci_generate.EXIT_CONFIG_ERROR
    assert "invalid YAML" in capsys.readouterr().err


def test_bad_credential_profile_exits_2(capsys: pytest.CaptureFixture[str]) -> None:
    rc = ci_generate.main(
        [
            "--story",
            "s",
            "--url",
            "http://localhost:8781/",
            "--credential-profile",
            "{not json",
        ]
    )
    assert rc == ci_generate.EXIT_CONFIG_ERROR
    assert "not valid JSON" in capsys.readouterr().err


def test_missing_story_argument_raises_argparse_error() -> None:
    with pytest.raises(SystemExit):
        ci_generate.main(["--url", "http://localhost:8781/"])


def test_valid_ignore_file_loads(tmp_path: object) -> None:
    ok = f"{tmp_path}/ok.yml"
    with open(ok, "w", encoding="utf-8") as fh:
        fh.write("ignores:\n  - test: 'test_08*'\n    reason: 'known flaky in mock'\n")
    spec = load_ignore_spec(ok)  # type: ignore[arg-type]
    assert spec.count == 1


# ---------------------------------------------------------------------------
# --storage-root (CI action: artifacts must persist under $GITHUB_WORKSPACE)
# ---------------------------------------------------------------------------


def test_storage_root_passed_to_init_storage(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The action passes $GITHUB_WORKSPACE as --storage-root so generated
    artifacts land in the runner's mounted workspace, not the container."""
    captured: dict[str, object] = {}

    def fake_init_storage(root: object = None, workspace: str = "default") -> object:
        captured["root"] = root
        captured["workspace"] = workspace
        return object()

    async def fake_run(**kwargs: object) -> None:  # noqa: ANN003
        return None

    monkeypatch.setattr(ci_generate, "init_storage", fake_init_storage)
    monkeypatch.setattr(ci_generate, "_run_pipeline_async", fake_run)

    rc = ci_generate.main(
        [
            "--story",
            "s",
            "--url",
            "http://localhost:8781/",
            "--workspace",
            "ws-name",
            "--storage-root",
            str(tmp_path),
        ]
    )
    # fake pipeline writes nothing -> generation error contract (exit 1)
    assert rc == ci_generate.EXIT_GENERATION_ERROR
    assert captured["root"] == tmp_path
    assert captured["workspace"] == "ws-name"


def test_default_storage_root_is_none(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    """Without --storage-root the driver keeps the repo-root default (backwards
    compatible with the shipped 7a-core behaviour and the E2E test)."""
    captured: dict[str, object] = {}

    def fake_init_storage(root: object = None, workspace: str = "default") -> object:
        captured["root"] = root
        captured["workspace"] = workspace
        return object()

    async def fake_run(**kwargs: object) -> None:  # noqa: ANN003
        return None

    monkeypatch.setattr(ci_generate, "init_storage", fake_init_storage)
    monkeypatch.setattr(ci_generate, "_run_pipeline_async", fake_run)

    ci_generate.main(["--story", "s", "--url", "http://localhost:8781/", "--workspace", "ws-name"])
    assert captured["root"] is None
    assert captured["workspace"] == "ws-name"


# ---------------------------------------------------------------------------
# E2E — full generation against the mock with the fake LLM (hermetic)
# ---------------------------------------------------------------------------


@pytest.mark.slow
@pytest.mark.integration
def test_e2e_generate_against_mock_with_fake_llm(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Hermetic: no RAG store writes / embedder downloads, no flow-memory writes.
    monkeypatch.setenv("RAG_ENABLED", "0")
    monkeypatch.setenv("FLOW_MEMORY_ENABLED", "0")

    mock_port = _free_port()
    workspace = tmp_path / "ws"
    ignore = tmp_path / ".ai-test-ignore.yml"
    ignore.write_text(
        "ignores:\n  - test: 'test_08*'\n    reason: 'known flaky in mock'\n",
        encoding="utf-8",
    )

    try:
        with MockServer.start(port=mock_port, directory=str(MOCK_DIR)):
            with FakeLLMServer() as fake:
                rc = ci_generate.main(
                    [
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
                        "--ignore-file",
                        str(ignore),
                        "--json",
                    ]
                )
    finally:
        from src.storage import reset_storage

        reset_storage()

    assert rc == ci_generate.EXIT_OK, capsys.readouterr().err

    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert out["ok"] is True
    assert out["exit_code"] == 0
    assert out["mode"] == "generate-only"
    assert out["test_count"] >= 1
    assert out["conditions"] >= 1
    assert out["ignores"] == 1
    assert out["pom_mode"] is False
    assert out["duration_s"] >= 0

    package = Path(out["package"])
    assert package.exists(), f"package not written: {package}"
    assert package.suffix == ".py"
    assert workspace in package.parents, f"package not under workspace: {package}"
