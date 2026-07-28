"""A/B test: linear vs graph pipeline, same LLM, same mode, RAG on.

Usage:
    LANGGRAPH_ENABLED=1 RAG_ENABLED=1 python scripts/eval/ab_test.py --story eval-001
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))


def _ensure_env(provider: str, base_url: str, api_key: str, model: str) -> None:
    """Ensure RAG is enabled and set the LLM provider."""
    os.environ.setdefault("RAG_ENABLED", "1")

    from src.llm_client import LLMClient

    LLMClient.set_session_provider(
        provider=provider,
        base_url=base_url,
        model=model,
    )
    # Also set the API key in env for the provider layer
    if provider == "openai-compatible":
        os.environ["OPENAI_COMPATIBLE_API_KEY"] = api_key
        os.environ["OPENAI_COMPATIBLE_BASE_URL"] = base_url
        os.environ["OPENAI_COMPATIBLE_MODEL"] = model


async def run_linear(story_data: dict) -> dict:
    """Run the LINEAR pipeline (LANGGRAPH_ENABLED=0)."""
    os.environ["LANGGRAPH_ENABLED"] = "0"

    from src.llm_client import LLMClient
    from src.orchestrator import TestOrchestrator
    from src.test_generator import TestGenerator

    client = LLMClient()
    generator = TestGenerator(client=client)
    orchestrator = TestOrchestrator(generator, pom_mode=True)

    start = time.time()
    code = await orchestrator.run_pipeline(
        user_story=story_data["user_story"],
        conditions="\n".join(story_data["conditions"]),
        target_urls=[story_data["base_url"]],
    )
    duration = time.time() - start

    return {"code": code, "duration_s": duration, "pipeline": "linear"}


async def run_graph(story_data: dict) -> dict:
    """Run the GRAPH pipeline (LANGGRAPH_ENABLED=1, default)."""
    os.environ.pop("LANGGRAPH_ENABLED", None)  # remove override, default is enabled

    from src.llm_client import LLMClient
    from src.orchestrator import TestOrchestrator
    from src.test_generator import TestGenerator

    client = LLMClient()
    generator = TestGenerator(client=client)
    orchestrator = TestOrchestrator(generator, pom_mode=True)

    start = time.time()

    # Step 1: Generate skeleton via graph
    state = await orchestrator.run_pipeline_via_graph(
        user_story=story_data["user_story"],
        conditions="\n".join(story_data["conditions"]),
        target_urls=[story_data["base_url"]],
        auto_confirm=True,
    )

    if state is None or not state.test_code:
        print("  WARNING: Graph returned no code, falling back to linear")
        os.environ["LANGGRAPH_ENABLED"] = "0"
        return await run_linear(story_data)

    # Step 2: Feed graph skeleton into standard pipeline (scrape + resolve)
    code = await orchestrator.run_pipeline(
        user_story=story_data["user_story"],
        conditions="\n".join(story_data["conditions"]),
        target_urls=[story_data["base_url"]],
        prebuilt_skeleton=state.test_code,
    )

    duration = time.time() - start
    return {"code": code, "duration_s": duration, "pipeline": "graph"}


def validate_code(code: str, golden: dict) -> dict:
    """Validate generated code against golden keys."""
    import re

    _METHODS = "navigate|fill|click|assert_visible|assert_text|assert_text_contains|assert_value|assert_checked|assert_disabled|assert_enabled|assert_count|assert_empty"

    _EVIDENCE_CALL_RE = re.compile(
        r"evidence_tracker\.(" + _METHODS + r")" r"\s*\(\s*" r"""(['"])(.*?)\2""",
    )

    # Extract locators from generated code
    generated: list[dict] = []
    for line in code.splitlines():
        m = _EVIDENCE_CALL_RE.search(line)
        if m:
            method = m.group(1)
            action = "GOTO" if method == "navigate" else "FILL" if method == "fill" else "CLICK" if method == "click" else "ASSERT"
            generated.append({"action": action, "locator": m.group(3), "method": method})

    # Compare against golden keys
    results = []
    for crit in golden.get("golden_resolutions", []):
        for ph in crit.get("placeholders", []):
            expected = ph.get("expected_locator", "")
            tolerances = ph.get("tolerance_selectors", [])
            matched = False
            matched_locator = None

            for g in generated:
                if g["locator"] == expected or g["locator"] in tolerances:
                    matched = True
                    matched_locator = g["locator"]
                    break

            results.append({
                "action": ph["action"],
                "description": ph["description"],
                "expected": expected,
                "matched": matched,
                "got": matched_locator,
            })

    total = len(results)
    correct = sum(1 for r in results if r["matched"])
    accuracy = correct / total * 100 if total else 0

    return {"total": total, "correct": correct, "accuracy": accuracy, "details": results}


async def main() -> None:
    parser = argparse.ArgumentParser(description="A/B test linear vs graph pipeline")
    parser.add_argument("--story", default="eval-001", help="Story ID to test")
    parser.add_argument("--dataset-dir", default=str(_PROJECT_ROOT / "scripts" / "eval" / "dataset"))
    parser.add_argument("--provider", default="openai-compatible")
    parser.add_argument("--base-url", default="https://api.deepseek.com/v1")
    parser.add_argument("--api-key", default=os.environ.get("DEEPSEEK_API_KEY", ""))
    parser.add_argument("--model", default="deepseek-chat")
    args = parser.parse_args()

    _ensure_env(args.provider, args.base_url, args.api_key, args.model)

    # Load story data
    dataset_dir = Path(args.dataset_dir)
    golden_file = dataset_dir / f"{args.story}_saucedemo_login_checkout.json" if args.story == "eval-001" else None
    if golden_file is None or not golden_file.exists():
        # Try to find any matching file
        matches = list(dataset_dir.glob(f"{args.story}*.json"))
        if not matches:
            print(f"ERROR: No dataset file found for {args.story}", file=sys.stderr)
            sys.exit(1)
        golden_file = matches[0]

    story_data = json.loads(golden_file.read_text())
    print(f"Story: {story_data['title']}")
    print(f"Site:  {story_data['base_url']}")
    print(f"Conditions: {len(story_data['conditions'])}")
    print(f"Golden placeholders: {sum(len(c['placeholders']) for c in story_data.get('golden_resolutions', []))}")
    print()

    # --- LINEAR ---
    print("=" * 60)
    print("LINEAR PIPELINE (LANGGRAPH_ENABLED=0)")
    print("=" * 60)
    linear_result = await run_linear(story_data)
    linear_validation = validate_code(linear_result["code"], story_data)
    print(f"  Duration: {linear_result['duration_s']:.1f}s")
    print(f"  Accuracy: {linear_validation['accuracy']:.1f}% ({linear_validation['correct']}/{linear_validation['total']})")

    # Save linear code
    linear_path = _PROJECT_ROOT / "scripts" / "eval" / "captures" / "linear" / f"{args.story}_linear.py"
    linear_path.parent.mkdir(parents=True, exist_ok=True)
    linear_path.write_text(linear_result["code"])
    print(f"  Saved to: {linear_path}")

    # --- GRAPH ---
    print()
    print("=" * 60)
    print("GRAPH PIPELINE (LANGGRAPH_ENABLED=1)")
    print("=" * 60)
    graph_result = await run_graph(story_data)
    graph_validation = validate_code(graph_result["code"], story_data)
    print(f"  Duration: {graph_result['duration_s']:.1f}s")
    print(f"  Accuracy: {graph_validation['accuracy']:.1f}% ({graph_validation['correct']}/{graph_validation['total']})")

    # Save graph code
    graph_path = _PROJECT_ROOT / "scripts" / "eval" / "captures" / "graph" / f"{args.story}_graph.py"
    graph_path.parent.mkdir(parents=True, exist_ok=True)
    graph_path.write_text(graph_result["code"])
    print(f"  Saved to: {graph_path}")

    # --- COMPARISON ---
    print()
    print("=" * 60)
    print("COMPARISON")
    print("=" * 60)
    print(f"  Linear: {linear_validation['accuracy']:.1f}% ({linear_validation['correct']}/{linear_validation['total']})")
    print(f"  Graph:  {graph_validation['accuracy']:.1f}% ({graph_validation['correct']}/{linear_validation['total']})")
    delta = graph_validation["accuracy"] - linear_validation["accuracy"]
    sign = "+" if delta >= 0 else ""
    print(f"  Delta:  {sign}{delta:.1f}pp")

    # Show mismatches side by side
    print()
    print("Placeholder-level comparison:")
    print(f"{'Action':8s} {'Description':40s} {'Expected':35s} {'Linear':35s} {'Graph':35s}")
    print("-" * 160)
    for i, (lr, gr) in enumerate(zip(linear_validation["details"], graph_validation["details"])):
        l_loc = lr["got"] or "(unresolved)"
        g_loc = gr["got"] or "(unresolved)"
        l_mark = "Y" if lr["matched"] else "N"
        g_mark = "Y" if gr["matched"] else "N"
        print(f"{lr['action']:8s} {lr['description'][:38]:40s} {lr['expected'][:33]:35s} {l_mark} {l_loc[:30]:35s} {g_mark} {g_loc[:30]:35s}")

    # Save comparison JSON
    comparison = {
        "story": args.story,
        "linear": {"accuracy": linear_validation["accuracy"], "duration_s": linear_result["duration_s"]},
        "graph": {"accuracy": graph_validation["accuracy"], "duration_s": graph_result["duration_s"]},
        "delta_pp": delta,
    }
    comp_path = _PROJECT_ROOT / "scripts" / "eval" / "captures" / f"{args.story}_comparison.json"
    comp_path.write_text(json.dumps(comparison, indent=2))
    print(f"\nComparison saved to: {comp_path}")


if __name__ == "__main__":
    asyncio.run(main())
