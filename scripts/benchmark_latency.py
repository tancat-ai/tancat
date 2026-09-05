#!/usr/bin/env python3
"""Per-model-tier LLM latency benchmark (Phase 6h, spec §5.10).

Produces the published per-model-tier table used as the honesty signal behind
the product's latency SLO: **target < 2–3 minutes per 6-criteria story on
consumer hardware**.

What it measures (all through the product's own machinery):

1. ``list_models``                             — endpoint connectivity latency
2. **skeleton generation** (``TestGenerator``) — the full single-call skeleton
   for a 6-criteria story (the dominant LLM cost)
3. **resolution** (``SemanticCandidateRanker``)— a realistic 8-candidate
   pick, cold and (cache-enabled) warm — the 45s→120s timeout class
4. **estimated story LLM time**                — skeleton + expected resolution
   calls per story, compared against the SLO (180s target)

Usage (uses the configured provider, mirroring ``ci_generate``)::

    python scripts/benchmark_latency.py --provider lm-studio --model qwen3.5:35b
    python scripts/benchmark_latency.py --json --save docs/benchmarks/latency.json
    python scripts/benchmark_latency.py --self-test   # hermetic, no LLM (CI)

Output: a human table + ``--json``; ``--save`` writes the published table
(schema version + date + SLO + per-call medians) so a regression over
model/config changes is visible in git.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

# A 6-criteria story the benchmark uses by default (consumer-ish e-commerce).
DEFAULT_STORY = (
    "As a shopper I can browse and check out on the demo store. "
    "1. Home page loads and shows products. "
    "2. I can log in with my credentials. "
    "3. I can search for a dress. "
    "4. I can add a dress to the cart. "
    "5. The cart shows my item with correct price. "
    "6. I can complete the checkout flow and see an order confirmation."
)
DEFAULT_CONDITIONS = (
    "1. Home page is visible and product grid loads. "
    "2. Login succeeds and inventory page is displayed. "
    "3. A dress product is found and opened. "
    "4. The dress is added to the cart. "
    "5. The cart displays the item and price. "
    "6. Checkout completes and confirmation shows."
)

SLO_TARGET_S = 180  # spec §5.10: < 2–3 min per 6-criteria story

RESOLUTION_CANDIDATES = [
    {"label": "Add to cart", "locator": "#add-to-cart", "role": "button", "text": "Add to Cart"},
    {"label": "Cart link", "locator": "a[href='/cart.html']", "role": "link", "text": "Cart"},
    {"label": "Checkout button", "locator": "#checkout", "role": "button", "text": "Proceed to Checkout"},
    {"label": "Fleece jacket add", "locator": "#add-to-cart-fleece", "role": "button", "text": "Add to cart"},
    {"label": "Product title", "locator": "#item-title", "role": "heading", "text": "Sauce Labs Fleece Jacket"},
    {"label": "Search box", "locator": "#search", "role": "textbox", "text": "Search products"},
    {"label": "Login button", "locator": "#login-button", "role": "button", "text": "LOGIN"},
    {"label": "Success banner", "locator": "#success", "role": "status", "text": "Order placed successfully!"},
]


class _NullAsyncGenerator:
    """No-LLM stub for --self-test: measures the benchmark machinery only."""

    async def generate(
        self,
        prompt: str,
        timeout: int = 300,
        system_prompt: str | None = None,
        *,
        enable_thinking: bool | None = None,
    ) -> str:
        # Simulate a fast local model (~1.2s) and return a real skeleton-shaped
        # / ranker-shaped payload so the pipeline-parsing paths are exercised.
        time.sleep(0.2)
        if "Rank the following" in prompt or "Choose only from the numbered" in (system_prompt or ""):
            return json.dumps({"selected_index": 1, "assertion_type": "toBeVisible"})
        return (
            "import pytest\n"
            "def test_01_home_visible(page):\n"
            "    expect(page.locator('#product-grid')).to_be_visible()\n"
        )


def _make_client(provider: str, model: str, base_url: str) -> Any:
    from src.llm_client import LLMClient

    return LLMClient(provider=provider, model=model, base_url=base_url or None)


def _median(values: list[float]) -> float:
    return round(statistics.median(values), 3) if values else 0.0


def _time_list_models(client: Any) -> float:
    start = time.monotonic()
    models = client.list_models(timeout=5)
    return round(time.monotonic() - start, 3), len(models)


async def _time_skeleton(client: Any, iterations: int, cache: bool) -> list[float]:
    # output_dir to a temp dir so the benchmark never touches generated_tests/.
    import tempfile

    from src.test_generator import TestGenerator

    with tempfile.TemporaryDirectory() as td:
        gen = TestGenerator(client=client, output_dir=td)
        latencies: list[float] = []
        for _ in range(iterations):
            start = time.monotonic()
            await gen.generate_skeleton(DEFAULT_STORY, DEFAULT_CONDITIONS)
            latencies.append(round(time.monotonic() - start, 3))
        return latencies


async def _time_resolution(
    ranker: Any,
    *,
    iterations: int,
    cold: bool,
    warm: bool,
) -> dict[str, float]:
    """Time single resolution picks against the canned candidate list.

    ``cold`` = first call (cache empty/stale); ``warm`` = a re-resolve of the
    same prompt (cache hit) — measures the cache benefit (0ms when enabled).
    """
    result: dict[str, float] = {}

    async def _one() -> float:
        start = time.monotonic()
        await ranker.choose_best_candidate(
            action="CLICK",
            description="add the fleece jacket to the cart",
            current_url="https://demo.example/products",
            candidates=RESOLUTION_CANDIDATES,
        )
        return round(time.monotonic() - start, 3)

    if cold:
        result["cold_median_s"] = _median([await _one() for _ in range(iterations)])
    if warm:
        # Same prompt again → cache hit when the cache is enabled (env default).
        result["warm_median_s"] = _median([await _one() for _ in range(iterations)])

    return result


def _report(measurements: dict[str, Any]) -> str:
    lines = [
        "Latency benchmark (per-model tier) — Phase 6h",
        f"  provider : {measurements['provider']}",
        f"  model    : {measurements['model']}",
        f"  base_url : {measurements['base_url'] or '(default)'}",
        f"  date     : {measurements['ran_at']}",
        f"  SLO      : < {SLO_TARGET_S}s per 6-criteria story",
    ]
    m = measurements
    lines.append(f"  list_models  : {m['list_models_s']}s ({m['models_listed']} models)")
    lines.append(f"  skeleton     : median {m['skeleton_median_s']}s over {m['iterations']} runs")
    if "resolution_cold_median_s" in m:
        lines.append(f"  resolution   : cold median {m['resolution_cold_median_s']}s")
    if "resolution_warm_median_s" in m:
        lines.append(f"                : warm median {m['resolution_warm_median_s']}s (cache hit → ~0ms)")
    est = m.get("estimated_story_llm_s")
    if est is not None:
        ok = "within SLO" if est <= SLO_TARGET_S else "OVER SLO"
        lines.append(f"  story (est)  : {est}s LLM time per 6-criteria story — {ok}")
    return "\n".join(lines)


async def _run(args: argparse.Namespace) -> dict[str, Any]:
    if args.self_test:
        client: Any = _NullAsyncGenerator()
        # --self-test drives the timing through the stub + a cache-disabled
        # ranker so the benchmark machinery is exercised with no LLM.
        from src.llm_cache import LLMCache

        lat = await _time_stub_skeleton(client, args.iterations)
        ranker_cold = _make_ranker(client, cache=LLMCache(enabled=False))
        rows: list[float] = []
        for _ in range(args.iterations):
            start = time.monotonic()
            await ranker_cold.choose_best_candidate(
                action="CLICK",
                description="add the fleece jacket to the cart",
                current_url="https://demo.example/products",
                candidates=RESOLUTION_CANDIDATES,
            )
            rows.append(round(time.monotonic() - start, 3))
        return {
            "provider": "self-test",
            "model": "null-async",
            "base_url": "",
            "ran_at": datetime.now(UTC).isoformat(),
            "iterations": args.iterations,
            "list_models_s": 0.0,
            "models_listed": 0,
            "skeleton_median_s": round(sum(lat) / len(lat), 3) if lat else 0.0,
            "resolution_cold_median_s": _median(rows),
            "estimated_story_llm_s": 0.0,
            "slo_target_s": SLO_TARGET_S,
            "self_test": True,
        }

    client = _make_client(args.provider, args.model, args.llm_base_url)
    provider = client.provider_name

    list_models_s, models_listed = _time_list_models(client)

    skeleton_lat = await _time_skeleton(client, args.iterations, cache=True)

    from src.llm_cache import LLMCache

    ranker = _make_ranker(client, cache=None)  # env default (AITEST_LLM_CACHE)
    resolution = await _time_resolution(ranker, iterations=args.iterations, cold=True, warm=True)

    skeleton_median = _median(skeleton_lat)
    # Rough per-story estimate: 1 skeleton + ~2 resolution picks per criterion
    # (a typical ASSERT + CLICK pair), so ~12 resolution calls for 6 criteria.
    resolution_median = resolution.get("resolution_cold_median_s", 0.0)
    estimated = round(skeleton_median + 12 * resolution_median, 1)

    return {
        "provider": provider,
        "model": args.model,
        "base_url": args.llm_base_url or "",
        "ran_at": datetime.now(UTC).isoformat(),
        "iterations": args.iterations,
        "list_models_s": list_models_s,
        "models_listed": models_listed,
        "skeleton_median_s": skeleton_median,
        "resolution_cold_median_s": resolution.get("resolution_cold_median_s", 0.0),
        "resolution_warm_median_s": resolution.get("resolution_warm_median_s", 0.0),
        "cache_hit_s": max(
            0.0, resolution.get("resolution_cold_median_s", 0.0) - resolution.get("resolution_warm_median_s", 0.0)
        ),
        "estimated_story_llm_s": estimated,
        "slo_target_s": SLO_TARGET_S,
    }


def _make_ranker(client: Any, cache: Any | None = None) -> Any:
    from src.semantic_candidate_ranker import SemanticCandidateRanker

    return SemanticCandidateRanker(generator=client, cache=cache)


async def _time_stub_skeleton(client: Any, iterations: int) -> list[float]:
    lat: list[float] = []
    for _ in range(iterations):
        start = time.monotonic()
        await client.generate(DEFAULT_STORY)
        lat.append(round(time.monotonic() - start, 3))
    return lat


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="LLM latency benchmark (Phase 6h).")
    parser.add_argument("--provider", default="", help="Provider key (default: env / auto-detect).")
    parser.add_argument("--model", default="", help="Model name (default: provider default).")
    parser.add_argument("--llm-base-url", default="", help="Provider base URL (default: provider default).")
    parser.add_argument("--iterations", type=int, default=3, help="Iterations per measurement (default 3).")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON on stdout.")
    parser.add_argument("--save", default="", help="Write the published table JSON to this path.")
    parser.add_argument("--self-test", action="store_true", help="Hermetic run with a null LLM (CI).")
    args = parser.parse_args(argv)

    measurements = asyncio.run(_run(args))

    if args.save:
        out = Path(args.save)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(measurements, indent=2), encoding="utf-8")
        print(f"Benchmark table written to {out}")

    if args.json:
        print(json.dumps(measurements))
    else:
        print(_report(measurements))
    return 0


if __name__ == "__main__":
    sys.exit(main())
