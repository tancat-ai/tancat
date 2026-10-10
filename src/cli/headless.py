#!/usr/bin/env python3
"""Headless test-generation driver for the product CLI (``tancat run``).

Promoted from the old ``scripts/ci_generate.py`` (Phase 7a) so a person, a
script and the CI Action share one entry point. The GitHub Action and the
GitLab template call ``tancat run``; the old script was removed (t-0576).

Runs the SAME production pipeline the UI/CLI use (``ui_pipeline.run_pipeline``)
with zero interactive prompts. Contract:

- deterministic exit codes: 0 generated, 1 generation error, 2 config error
- ``--json`` machine-readable output on stdout
- workspace isolation (AI-029) so parallel jobs never collide
- danger-zone allow-list (Q3 grilling): non-staging URLs fail fast unless
  ``--danger-zone`` or an explicit ``--allowed-domains`` extension

Usage::

    tancat run --story story.md --url https://staging.example.com [--json]
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
from src.url_guard import UrlGuard

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


def _license_usage_section() -> dict[str, Any]:
    """License + usage visibility for ``--json`` (Phase 6e).

    Offline and best-effort: a failure to read the meter never fails the
    generate (the meter already degrades to zeros internally).
    """
    try:
        from src.usage_meter import UsageMeter

        meter = UsageMeter()
        return {
            "license": {
                "status": meter.summary().license_status,
                "tier": meter.summary().tier,
                "token_present": _license_token_present(),
            },
            "usage": meter.summary().to_dict(),
        }
    except Exception as exc:  # pragma: no cover - defensive
        return {"license": {"status": "unknown", "tier": "free", "error": str(exc)}, "usage": {}}


def _license_token_present() -> bool:
    try:
        from src.licensing.license import load_license

        return bool(load_license())
    except Exception:  # pragma: no cover - defensive
        return False


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


_RUN_EPILOG = (
    "Exit codes: 0 generated, 1 generation error, 2 configuration error.\n"
    "Target URL safety: only localhost/127.0.0.1, *.staging.*, *-dev, *.test.*\n"
    "are allowed without --danger-zone."
)


def _add_run_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--story", required=True, help="Story markdown file path, or inline story text")
    parser.add_argument("--url", required=True, help="Target site URL (staging only — see --danger-zone)")
    parser.add_argument(
        "--criteria", default="", help="Optional pre-written acceptance criteria; empty = derive from the story"
    )
    parser.add_argument(
        "--workspace",
        default="",
        help=(
            "AI-029 workspace name (default: $AITEST_WORKSPACE, else ci-workspace). "
            "Set the env var to share a project's learned answers with the UI/CLI."
        ),
    )
    parser.add_argument(
        "--storage-root",
        default="",
        help="Base directory for the workspace (default: repo root). The CI action passes "
        "$GITHUB_WORKSPACE so generated artifacts persist to the runner.",
    )
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
    parser.add_argument(
        "--allow-private-networks",
        action="store_true",
        help="Permit target URLs on private/RFC1918 networks (internal staging behind a "
        "corporate network). Never unblocks link-local/metadata addresses. "
        "Equivalent env: AITEST_ALLOW_PRIVATE_NETWORKS=1.",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON on stdout")


def add_run_parser(subparsers: Any) -> argparse.ArgumentParser:
    """Attach the ``tancat run`` subcommand to the product CLI parser."""
    parser = subparsers.add_parser(
        "run",
        help="Generate tests headlessly from a story and a target URL (CI/script friendly)",
        description="Headless AI test generation (the same pipeline the UI and menu use).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_RUN_EPILOG,
    )
    _add_run_arguments(parser)
    return parser


def build_parser() -> argparse.ArgumentParser:
    """Standalone parser for ``tancat run`` (used by the shim and tests)."""
    parser = argparse.ArgumentParser(
        prog="tancat run",
        description="Headless AI test generation (the same pipeline the UI and menu use).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_RUN_EPILOG,
    )
    _add_run_arguments(parser)
    return parser


def run(args: argparse.Namespace) -> int:
    """Execute a parsed ``tancat run`` invocation. Returns the exit code."""
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
        # SSRF guard (Phase 6 6a): composes UNDER the danger-zone allow-list —
        # --danger-zone may promote a public host, it never unblocks a
        # link-local/metadata/private address. Private networks are opt-in.
        UrlGuard(allow_private_networks=args.allow_private_networks).validate(args.url)
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

    # --- license validation (Phase 6e, spec §5.4) ---------------------------
    # Report-only by default (open-core adoption on-ramp — §9 Q1). Paid
    # deployments set AITEST_ENFORCE_LICENSING=1 for a hard gate: generation is
    # refused only when a license token is present but unusable (expired beyond
    # grace / invalid signature) — the free tier always remains legitimate.
    license_section = _license_usage_section()
    if os.environ.get("AITEST_ENFORCE_LICENSING", "0") == "1":
        lstat = license_section.get("license", {})
        if lstat.get("status") in ("expired_blocked", "invalid") and lstat.get("token_present"):
            print(
                f"ERROR: license '{lstat.get('status')}' — set a valid AITEST_LICENSE_KEY "
                "(or AITEST_LICENSE_FILE) or clear AITEST_ENFORCE_LICENSING.",
                file=sys.stderr,
            )
            return EXIT_CONFIG_ERROR

    # --- workspace isolation (AI-029) --------------------------------------
    # t-0591: an explicit --workspace wins; otherwise honour $AITEST_WORKSPACE
    # (the documented UI/CLI share route) before the CI default. Without this
    # the default overrode the env var, so the docs' env line did not work for
    # `tancat run` (the RAG scope half did).
    workspace = args.workspace or os.environ.get("AITEST_WORKSPACE", "").strip() or "ci-workspace"
    init_storage(root=Path(args.storage_root) if args.storage_root else None, workspace=workspace)

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
        "workspace": workspace,
        "test_count": _count_test_functions(code),
        "conditions": len(conditions),
        "unresolved": len(unresolved),
        "skipped_lines": _count_skips(code),
        "ignores": ignore_spec.count,
        "pom_mode": args.pom,
        "provider": provider,
        "model": model_name,
        "duration_s": duration_s,
        **license_section,
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


# ── check-llm ─────────────────────────────────────────────────────────────


def add_check_llm_parser(subparsers: Any) -> argparse.ArgumentParser:
    """Attach the ``tancat check-llm`` subcommand to the product CLI parser."""
    parser = subparsers.add_parser(
        "check-llm",
        help="Probe the configured LLM endpoint (reachability, key, model, response)",
        description="Run the same BYO-LLM health probe as the UI/CLI 'Check LLM' action.",
    )
    parser.add_argument(
        "--provider", default="", help="Provider (default: persisted setting, then $LLM_PROVIDER, then openai-local)"
    )
    parser.add_argument(
        "--model", default="", help="Model name (default: persisted/env setting, then the provider default)"
    )
    parser.add_argument(
        "--llm-base-url", default="", help="Base URL (default: persisted/env setting, then the provider default)"
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON on stdout")
    return parser


def check_llm_main(args: argparse.Namespace) -> int:
    """Run the health probe. Exit 0 when healthy, 1 otherwise."""
    from src.cli.session import create_session
    from src.llm_health import build_client, check_llm, render_report

    session = create_session()
    provider = args.provider or session.provider
    base_url = args.llm_base_url or session.provider_base_url
    model = args.model or session.model_name
    result = check_llm(
        build_client(provider, base_url=base_url or None, model=model or None), requested_model=model or None
    )

    if args.json:
        print(
            json.dumps(
                {
                    "ok": result.ok,
                    "exit_code": EXIT_OK if result.ok else EXIT_GENERATION_ERROR,
                    "headline": result.headline,
                    "provider": result.provider,
                    "base_url": result.base_url,
                    "model": result.requested_model,
                    "reachable": result.reachable,
                    "key_ok": result.key_ok,
                    "model_available": result.model_available,
                    "capability_ok": result.capability_ok,
                    "elapsed_s": result.elapsed_s,
                    "sample_output": result.sample_output,
                    "warnings": result.warnings,
                    "errors": result.errors,
                }
            )
        )
    else:
        print(render_report(result))
        if not result.ok:
            print("\nFix: start your LLM server or correct the provider settings, then run 'tancat check-llm' again.")
    return EXIT_OK if result.ok else EXIT_GENERATION_ERROR


def main(argv: Sequence[str] | None = None) -> int:
    """Standalone entry point (``python -m src.cli.headless`` and tests)."""
    return run(build_parser().parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
