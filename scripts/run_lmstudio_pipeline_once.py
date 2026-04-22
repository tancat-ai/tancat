from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path

# Ensure the repo root is on sys.path so imports work when run as script.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.llm_client import LLMClient  # noqa: E402
from src.orchestrator import TestOrchestrator  # noqa: E402
from src.spec_analyzer import SpecAnalyzer  # noqa: E402
from src.test_generator import TestGenerator  # noqa: E402


@dataclass(frozen=True)
class Args:
    provider_base_url: str
    model_name: str
    starting_url: str
    additional_urls: list[str]
    consent_mode: str


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run intelligent pipeline once (LM Studio).")
    parser.add_argument("--provider-base-url", default="http://localhost:1234")
    parser.add_argument("--model-name", default="google/gemma-4-26b-a4b")
    parser.add_argument("--starting-url", default="https://automationexercise.com/")
    parser.add_argument(
        "--additional-url",
        action="append",
        default=None,
        help="May be passed multiple times.",
    )
    parser.add_argument(
        "--consent-mode",
        default="auto-dismiss",
        choices=["auto-dismiss", "leave-as-is", "test-consent-flow"],
    )
    return parser


def _parse_args() -> Args:
    ns = _build_arg_parser().parse_args()
    default_additional = [
        "https://automationexercise.com/products",
        "https://automationexercise.com/view_cart",
        "https://automationexercise.com/checkout",
    ]
    additional_raw = ns.additional_url if ns.additional_url is not None else default_additional
    return Args(
        provider_base_url=str(ns.provider_base_url),
        model_name=str(ns.model_name),
        starting_url=str(ns.starting_url),
        additional_urls=[str(u) for u in additional_raw],
        consent_mode=str(ns.consent_mode),
    )


def main() -> int:
    args = _parse_args()

    user_story = "As a customer I want to add items to cart"
    criteria = "\n".join(
        [
            "1. Add items to cart",
            "2. Go to cart",
            "3. Check the items have been added correctly",
            "4. Go to check out",
            "5. Check out",
            "(Total: 5 criteria)",
        ]
    )

    print("STEP=init_client", flush=True)
    client = LLMClient(provider="lm-studio", model=args.model_name, base_url=args.provider_base_url)

    print("STEP=spec_analyze", flush=True)
    conditions = SpecAnalyzer(llm_client=client).analyze(
        f"User Story:\n{user_story}\n\nAcceptance Criteria:\n{criteria}"
    )
    if conditions:
        conditions_text = "\n".join(
            f"{i}. [{c.id}] {c.text} -> Expected: {c.expected}" for i, c in enumerate(conditions, 1)
        )
    else:
        conditions_text = criteria

    target_urls = [args.starting_url, *args.additional_urls]
    print(f"STEP=run_pipeline target_urls={len(target_urls)}", flush=True)
    orchestrator = TestOrchestrator(TestGenerator(client=client, model_name=args.model_name))
    asyncio.run(
        orchestrator.run_pipeline(
            user_story=user_story,
            conditions=conditions_text,
            target_urls=target_urls,
            consent_mode=args.consent_mode,
        )
    )

    print("PIPELINE_OK", flush=True)
    if orchestrator.last_result is not None:
        print(f"FINAL_CODE_LENGTH={len(orchestrator.last_result.final_code)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
