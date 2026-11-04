"""d-0132: make the CLI help true, and let the next drift fail a test.

Three claims the help makes are pinned here, each against the code that owns
the fact - not against a second hand-typed copy:

- the provider names printed by ``tancat run --help`` are the ones
  ``provider_config.SUPPORTED_PROVIDERS`` holds;
- the safe-host list printed by ``--help`` (and in the refusal message) is
  built from the allow rule's own tokens, so ``*.local`` cannot go missing
  again;
- an unknown ``--provider`` is refused with exit code 2 instead of silently
  inheriting the Ollama defaults.

Plus the version line: commit, Python, platform and provider/model, and
``--help`` mentions ``-V``.
"""

from __future__ import annotations

import sys

import pytest

from src.cli.headless import (
    _RUN_EPILOG,
    _SAFE_HOST_EXACT,
    _SAFE_HOST_SUBSTRINGS,
    _SAFE_HOST_SUFFIXES,
    _is_allowed_url,
    _safe_host_help,
)
from src.cli.headless import (
    build_parser as build_run_parser,
)
from src.cli.main import _USAGE, _version_info
from src.cli.main import build_parser as build_product_parser
from src.provider_config import SUPPORTED_PROVIDERS, get_provider_defaults


def _provider_help() -> str:
    """The --provider help string as argparse will print it."""
    parser = build_run_parser()
    action = next(a for a in parser._actions if getattr(a, "dest", "") == "provider")
    assert action.help is not None
    return " ".join(action.help.split())


class TestProviderListIsTheCodesList:
    def test_printed_names_are_the_supported_providers(self) -> None:
        help_text = _provider_help()
        assert f"({', '.join(SUPPORTED_PROVIDERS)})" in help_text

    def test_no_provider_is_missing_from_the_printed_list(self) -> None:
        """The old text listed 4 of 7; azure/compatible/openrouter were invisible."""
        help_text = _provider_help()
        for provider in SUPPORTED_PROVIDERS:
            assert provider in help_text

    def test_check_llm_lists_the_same_names(self, capsys: pytest.CaptureFixture[str]) -> None:
        with pytest.raises(SystemExit):
            build_product_parser().parse_args(["check-llm", "--help"])
        printed = " ".join(capsys.readouterr().out.split())
        assert ", ".join(SUPPORTED_PROVIDERS) in printed


class TestSafeHostListIsTheAllowRule:
    def test_every_rule_token_is_printed(self) -> None:
        """The text is generated from the three tuples, so no token can be left out."""
        text = _safe_host_help()
        for host in _SAFE_HOST_EXACT:
            assert host in text
        for token in _SAFE_HOST_SUBSTRINGS:
            assert f"*{token}*" in text
        for token in _SAFE_HOST_SUFFIXES:
            assert f"*{token}" in text

    @pytest.mark.parametrize(
        "host",
        [
            "localhost",
            "127.0.0.1",
            "app.staging.example.com",
            "app.test.example.com",
            "shop-dev.example.com",
            "app.internal.local",
            "staging.example.com",
        ],
    )
    def test_a_host_from_the_printed_list_is_allowed(self, host: str) -> None:
        assert _is_allowed_url(f"http://{host}/page", ())

    def test_dot_local_is_allowed_and_printed(self) -> None:
        """headless.py:48-49 allowed *.local while :173-177 and :71-77 did not say so."""
        assert _is_allowed_url("http://intranet.local/", ())
        assert "*.local" in _safe_host_help()

    def test_a_public_site_is_still_refused(self) -> None:
        assert not _is_allowed_url("https://www.saucedemo.com/", ())

    def test_the_printed_help_carries_the_generated_rule(self) -> None:
        """The run epilog prints the same text the rule generates."""
        assert _safe_host_help() in _RUN_EPILOG
        assert _safe_host_help() in " ".join((build_run_parser().epilog or "").split())


class TestUnknownProviderIsRefused:
    def test_get_provider_defaults_refuses(self) -> None:
        with pytest.raises(ValueError, match="unknown LLM provider"):
            get_provider_defaults("bogus")

    def test_run_refuses_with_exit_2(self, capsys: pytest.CaptureFixture[str]) -> None:
        args = build_run_parser().parse_args(
            ["--story", "Add one item to the cart", "--url", "http://localhost:8080", "--provider", "bogus"]
        )
        from src.cli.headless import run

        assert run(args) == 2
        err = capsys.readouterr().err
        assert "unknown LLM provider 'bogus'" in err
        assert "openai-compatible" in err  # the refusal names the real choices

    def test_known_provider_still_defaults(self) -> None:
        assert get_provider_defaults("openai-local") == ("http://localhost:8080", "llama")


class TestVersionAndDiscoverability:
    def test_version_line_carries_the_build_facts(self) -> None:
        text = _version_info()
        assert text.startswith("tancat ")
        assert "(commit " in text
        assert f"Python {sys.version_info.major}.{sys.version_info.minor}" in text
        assert " on " in text  # platform
        assert "Provider " in text and "model " in text

    def test_help_mentions_the_short_version_flag(self) -> None:
        assert "-V" in _USAGE

    def test_help_shows_one_pasteable_first_run(self) -> None:
        assert "First run" in _USAGE
        assert "tancat run --story" in _USAGE
        assert "--url" in _USAGE

    def test_help_names_the_target_url_walkthrough_step(self) -> None:
        """main.py:609-613 skipped the 'Enter Target URLs' step the menu really has."""
        assert "Enter Target URLs" in _USAGE

    def test_help_makes_the_evidence_cli_discoverable(self) -> None:
        assert "python -m cli.evidence_cli search" in _USAGE
        assert "python -m cli.evidence_cli detail" in _USAGE
        assert "python -m cli.evidence_cli export" in _USAGE

    def test_help_says_pom_is_off_by_default(self) -> None:
        parser = build_run_parser()
        action = next(a for a in parser._actions if getattr(a, "dest", "") == "pom")
        assert "off by default" in (action.help or "")

    def test_ignore_file_help_says_what_run_does_today(self) -> None:
        """headless.py counted ignores; the help promised gating 'in 7b'."""
        parser = build_run_parser()
        action = next(a for a in parser._actions if getattr(a, "dest", "") == "ignore_file")
        help_text = " ".join((action.help or "").split())
        assert "counts" in help_text
        assert "7b" not in help_text
