#!/usr/bin/env python3
"""Cache-key computation for the Phase 7 CI action (spec §7).

Key = ``sha256(story + url + model + provider + prompt-fingerprint)``.

The prompt fingerprint is a constant bumped whenever the generation prompts
change (the AI-042-F4 lesson): prompt changes are regeneration-sensitive, and
a cache keyed only on the story would silently serve stale packages after a
prompt tweak. Bumping ``PROMPT_FINGERPRINT`` invalidates every cached package
in one move.

Pure stdlib (hashlib) on purpose — the same file runs under the runner's
``python3`` in workflow steps AND under the action image's venv python, so
the workflow's ``actions/cache`` key and the action's internal cache-dir
check can never drift apart (one source of truth).

Usage::

    python action/cache_key.py --story "..." --url https://... --model gpt-4 --provider openai
    # prints the hex digest on stdout (nothing else)

    # importable:
    from action.cache_key import compute_cache_key, PROMPT_FINGERPRINT
"""

from __future__ import annotations

import argparse
import hashlib
import sys

# Bump when generation prompts change — invalidates all cached packages
# (AI-042-F4: stale cache keyed only on the story would mask regressions).
PROMPT_FINGERPRINT = "phase7-7b-v1"


def compute_cache_key(story: str, url: str, model: str, provider: str) -> str:
    """Return the 64-char hex cache key for a generate-mode run."""
    material = "|".join(
        [
            story.strip(),
            url.strip(),
            model.strip(),
            provider.strip(),
            PROMPT_FINGERPRINT,
        ]
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cache_key",
        description="Compute the Phase 7 actions/cache key (spec §7).",
    )
    parser.add_argument("--story", default="", help="Story text or path (as given to the action)")
    parser.add_argument("--url", default="", help="Target site URL")
    parser.add_argument("--model", default="", help="Model name (empty = provider default)")
    parser.add_argument("--provider", default="", help="LLM provider")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    print(compute_cache_key(args.story, args.url, args.model, args.provider))
    return 0


if __name__ == "__main__":
    sys.exit(main())
