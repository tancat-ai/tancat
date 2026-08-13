#!/usr/bin/env python3
"""Headless test-generation driver for CI (Phase 7a).

Runs the SAME production pipeline the UI/CLI use (``ui_pipeline.run_pipeline``)
with zero interactive prompts. Contract for the CI integration:

- deterministic exit codes: 0 generated, 1 generation error, 2 config error
- ``--json`` machine-readable output on stdout
- workspace isolation (AI-029) so parallel jobs never collide
- danger-zone allow-list (Q3 grilling): non-staging URLs fail fast unless
  ``--danger-zone`` or an explicit ``--allowed-domains`` extension

Usage::

    python scripts/ci_generate.py --story story.md --url https://staging.example.com [--json]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from src.ci_ignore import load_ignore_spec
from src.journey_models import CredentialProfile
from src.provider_config import get_provider_defaults
from src.storage import init_storage
from src.ui_pipeline import PipelineSessionState, run_pipeline

EXIT_OK = 0
EXIT_GENERATION_ERROR = 1
EXIT_CONFIG_ERROR = 2

# Safe-by-default allow-list (Q3 grilling, 2026-08-13). Anything else requires
# --danger-zone or an --allowed-domains extension.
_SAFE_HOST_SUBSTRINGS = (".staging.", ".test.", "-dev.", "staging.", "test.")
_SAFE_HOST_SUFFIXES = ("-dev", ".local")


def _is_allowed_url(url: str, allowed_domains: Sequence[str]) -> bool:
    """Return True when *url* is on the safe allow-list (or explicitly allowed)."""
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host in {"localhost", "127.0.0.1", "::1"}:
        return True
    if any(host == d.lower() or host.endswith("." + d.lower()) for d in allowed_domains):
        return True
    if any(s in host for s in _SAFE_HOST_SUBSTRINGS):
        return True
    if any(host.endswith(s) for s in _SAFE_HOST_SUFFIXES):
        return True
    return False


def _check_danger_zone(url: str, danger_zone: bool, allowed_domains: Sequence[str]) -> None:
    """Raise ``ValueError`` when *url* is not allow-listed and not overridden."""
    if danger_zone or _is_allowed_url(url, allowed_domains):
        return
    raise ValueError(
        f"target URL '{url}' is not on the safe allow-list "
        "(localhost, *.staging.*, *-dev, *.test.*). Generated tests can fill forms, "
        "place orders, and mutate data — CI must run against staging, not production. "
        "Set --danger-zone explicitly (prod smoke/load testing only) or extend the list "
        "via --allowed-domains."
    )


def _resolve_story(story: str | Path) -> str:
    """Read *story* as a file path if it exists, otherwise treat as inline text."""
    text = str(story)
    if not text.strip():
        return text
    p = Path(text)
    if p.exists() and p.is_file():
        return p.read_text(encoding="utf-8")
    return text


def _parse_credential_profile(raw: str) -> CredentialProfile | None:
    """Parse a JSON credential profile: {"label", "username", "password"}."""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"--credential-profile is not valid JSON: {exc}") from exc
    try:
        return CredentialProfile(
            label=str(data["label"]),
            username=str(data["username"]),
            password=str(data["password"]),
        )
    except KeyError as exc:
        raise ValueError(f"credential profile must contain {exc} — got keys {sorted(data)}") from exc


def _count_test_functions(code: str) -> int:
    return sum(1 for line in code.splitlines() if line.startswith("def test_"))


def _count_skips(code: str) -> int:
    return sum(1 for line in code.splitlines() if "pytest.skip(" in line)


async def _run_pipeline_async(
    *,
    story: str,
    criteria: str,
    provider: str,
    model_name: str,
    base_url: str,
    target_urls: list[str],
    consent_mode: str,
    pom_mode: bool,
    credential_profile: CredentialProfile | None,
    session: PipelineSessionState,
) -> None:
    await run_pipeline(
        user_story=story,
        criteria=criteria,
        provider=provider,
        provider_base_url=base_url,
        model_name=model_name,
        target_urls=target_urls,
        consent_mode=consent_mode,
        credential_profile=credential_profile,
        pom_mode=pom_mode,
        session=session,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ci_generate",
        description="Headless AI test generation for CI (Phase 7a).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Exit codes: 0 generated, 1 generation error, 2 configuration error.\n"
            "Target URL safety: only localhost/127.0.0.1, *.staging.*, *-dev, *.test.*\n"
            "are allowed without --danger-zone."
        ),
    )
    parser.add_argument("--story", required=True, help="Story markdown file path, or inline story text")
    parser.add_argument("--url", required=True, help="Target site URL (staging only — see --danger-zone)")
    parser.add_argument(
        "--criteria", default="", help="Optional pre-written acceptance criteria; empty = derive from the story"
    )
    parser.add_argument("--workspace", default="ci-workspace", help="AI-029 workspace name (default: ci-workspace)")
    parser.add_argument("--pom", action="store_true", help="Page Object Model mode")
    parser.add_argument(
        "--provider", default="openai-local", help="LLM provider (openai-local, lm-studio, ollama, openai)"
    )
    parser.add_argument("--model", default="", help="Model name (defaults to the provider's default)")
    parser.add_argument(
        "--llm-base-url", default="", help="OpenAI-compatible base URL (defaults to the provider's default)"
    )
    parser.add_argument("--llm-api-key", default="", help="API key for cloud providers (use a CI secret)")
    parser.add_argument(
        "--credential-profile", default="", help='JSON: {"label","username","password"} for login-required sites'
    )
    parser.add_argument("--ignore-file", default="", help="Path to .ai-test-ignore.yml (validated; gating lands in 7b)")
    parser.add_argument(
        "--danger-zone", action="store_true", help="Allow a non-allow-listed URL (prod smoke/load testing only)"
    )
    parser.add_argument(
        "--allowed-domains", default="", help="Comma-separated extra safe domains (internal staging names)"
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON on stdout")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    # --- config validation -------------------------------------------------
    if not args.url:
        print("ERROR: --url is required", file=sys.stderr)
        return EXIT_CONFIG_ERROR
    try:
        urlparse(args.url)
    except ValueError as exc:
        print(f"ERROR: invalid --url: {exc}", file=sys.stderr)
        return EXIT_CONFIG_ERROR

    allowed_domains = [d.strip() for d in args.allowed_domains.split(",") if d.strip()]

    story_text = _resolve_story(args.story)

    try:
        if not story_text.strip():
            raise ValueError("--story resolved to empty text")
        _check_danger_zone(args.url, args.danger_zone, allowed_domains)
        ignore_spec = load_ignore_spec(args.ignore_file or None)
        if args.llm_api_key:
            os.environ["OPENAI_API_KEY"] = args.llm_api_key
        credential_profile = _parse_credential_profile(args.credential_profile) if args.credential_profile else None
    except ValueError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return EXIT_CONFIG_ERROR

    provider = args.provider
    base_url = args.llm_base_url or get_provider_defaults(provider)[0]
    model_name = args.model or get_provider_defaults(provider)[1]

    # --- workspace isolation (AI-029) --------------------------------------
    init_storage(workspace=args.workspace)

    # --- run the production pipeline ---------------------------------------
    session = PipelineSessionState()
    start = time.monotonic()
    try:
        asyncio.run(
            _run_pipeline_async(
                story=story_text,
                criteria=args.criteria,
                provider=provider,
                model_name=model_name,
                base_url=base_url,
                target_urls=[args.url],
                consent_mode="auto-dismiss",
                pom_mode=args.pom,
                credential_profile=credential_profile,
                session=session,
            )
        )
    except Exception as exc:  # generation failures are exit 1, not a crash
        duration_s = round(time.monotonic() - start, 2)
        if args.json:
            print(
                json.dumps(
                    {
                        "ok": False,
                        "exit_code": EXIT_GENERATION_ERROR,
                        "error": str(exc),
                        "duration_s": duration_s,
                    }
                )
            )
        else:
            print(f"GENERATION FAILED after {duration_s}s: {exc}", file=sys.stderr)
        return EXIT_GENERATION_ERROR

    duration_s = round(time.monotonic() - start, 2)
    saved_path = session.get("pipeline_saved_path", "") or ""
    manifest_path = session.get("pipeline_manifest_path", "") or ""
    code = session.get("pipeline_results", "") or ""
    unresolved = list(session.get("pipeline_unresolved", []) or [])
    conditions = session.get("pipeline_conditions", []) or []

    if not saved_path:
        if args.json:
            print(
                json.dumps(
                    {"ok": False, "exit_code": EXIT_GENERATION_ERROR, "error": "pipeline produced no saved test file"}
                )
            )
        else:
            print("ERROR: pipeline produced no saved test file", file=sys.stderr)
        return EXIT_GENERATION_ERROR

    result: dict[str, Any] = {
        "ok": True,
        "exit_code": EXIT_OK,
        "mode": "generate-only",
        "package": str(Path(saved_path).resolve()),
        "manifest": str(Path(manifest_path).resolve()) if manifest_path else "",
        "workspace": args.workspace,
        "test_count": _count_test_functions(code),
        "conditions": len(conditions),
        "unresolved": len(unresolved),
        "skipped_lines": _count_skips(code),
        "ignores": ignore_spec.count,
        "pom_mode": args.pom,
        "provider": provider,
        "model": model_name,
        "duration_s": duration_s,
    }

    if args.json:
        print(json.dumps(result))
    else:
        print(f"✅ Generated {result['test_count']} tests ({result['conditions']} conditions) in {duration_s}s")
        print(f"   package: {result['package']}")
        print(f"   unresolved placeholders: {result['unresolved']} ({result['skipped_lines']} skip lines)")
        print(
            f"   ignores loaded: {result['ignores']}  ·  mode: {result['mode']}  ·  provider: {provider}/{model_name}"
        )
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
