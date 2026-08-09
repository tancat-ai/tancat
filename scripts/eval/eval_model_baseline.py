"""Measure LLM skeleton-generation quality on a fixed story set (before/after).

Runs the live LLM (whatever is on :8080 / configured in .env) through Phase-1
skeleton generation on a fixed set of stories, then scores the output with the
same gates production uses. Run this BEFORE fine-tuning to capture a baseline,
then again AFTER pointing .env at the fine-tuned model — the delta shows whether
training improved the model's actual job (writing valid Playwright skeletons).

Metrics (per story + aggregate):
  - valid_skeleton : passed SkeletonParser.validate_skeleton()
  - criteria_cover : # test functions == # acceptance criteria
  - hallucinated_login : contains standard_user/secret_sauce on a login-less site
  - skip_lines : count of pytest.skip(...) in the skeleton
  - placeholders : total placeholder steps

Usage:
    python scripts/eval/eval_model_baseline.py [--stories N] [--save training_data/model_baseline.json]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.llm_client import LLMClient  # noqa: E402
from src.prompt_utils import count_conditions  # noqa: E402
from src.skeleton_parser import SkeletonParser  # noqa: E402
from src.test_generator import TestGenerator  # noqa: E402

LOGIN_LESS = {"demoqa", "lv_insurance", "ecommerce_mock"}
LOGIN_MARKERS = ("standard_user", "secret_sauce")


def site_of(instruction: str) -> str:
    m = re.search(r"site '([^']+)'", instruction)
    return m.group(1) if m else "?"


async def evaluate_story(
    generator: TestGenerator,
    parser: SkeletonParser,
    row: dict,
) -> dict:
    """Generate a skeleton for one story and score it."""
    story = row["story"]
    conditions = row["conditions"]
    site = row["site"]
    url = row.get("url", "")
    expected = count_conditions(conditions)
    started = time.time()

    result: dict = {
        "site": site,
        "story_head": story[:60],
        "expected_criteria": expected,
        "valid_skeleton": False,
        "criteria_cover": False,
        "hallucinated_login": False,
        "skip_lines": 0,
        "placeholders": 0,
        "duration_s": 0.0,
        "error": None,
    }
    try:
        skeleton = await generator.generate_skeleton(
            user_story=story,
            conditions=conditions,
            target_urls=[url] if url else None,
            expected_count=expected,
        )
    except Exception as exc:  # LLM failure / timeout
        result["error"] = str(exc)[:200]
        result["duration_s"] = round(time.time() - started, 1)
        return result

    skeleton = parser.normalise_placeholder_actions(skeleton)
    result["valid_skeleton"] = parser.validate_skeleton(skeleton) is None
    fn_names = parser.test_definition_pattern.findall(skeleton)
    result["criteria_cover"] = len(fn_names) == expected
    result["skip_lines"] = skeleton.count("pytest.skip(")
    result["placeholders"] = len(re.findall(r"\{\{[A-Z_]+:", skeleton))
    if site in LOGIN_LESS:
        result["hallucinated_login"] = any(m in skeleton for m in LOGIN_MARKERS)
    result["duration_s"] = round(time.time() - started, 1)
    return result


async def run(stories_file: Path, limit: int, save: Path) -> None:
    rows = [json.loads(line) for line in stories_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    if limit:
        rows = rows[:limit]  # 0 (default) = all stories
    print(f"Evaluating {len(rows)} stories via live LLM...")

    client = LLMClient(provider_name="openai-local")
    generator = TestGenerator(client=client)
    parser = SkeletonParser()

    results = []
    for i, row in enumerate(rows, 1):
        print(f"  [{i}/{len(rows)}] {row['site']}: {row['story'][:50]}...", flush=True)
        results.append(await evaluate_story(generator, parser, row))

    # Aggregate
    n = len(results)
    valid = sum(1 for r in results if r["valid_skeleton"])
    cover = sum(1 for r in results if r["criteria_cover"])
    login = sum(1 for r in results if r["hallucinated_login"])
    skips = sum(r["skip_lines"] for r in results)
    phs = sum(r["placeholders"] for r in results)
    errors = sum(1 for r in results if r["error"])

    summary = {
        "model": _current_model(),
        "stories_evaluated": n,
        "valid_skeleton_rate": round(valid / n, 3) if n else 0,
        "criteria_cover_rate": round(cover / n, 3) if n else 0,
        "hallucinated_login_rate": round(login / n, 3) if n else 0,
        "total_skip_lines": skips,
        "total_placeholders": phs,
        "errors": errors,
        "per_story": results,
    }

    save.parent.mkdir(parents=True, exist_ok=True)
    save.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\n=== MODEL BASELINE ===")
    print(f"  model              : {summary['model']}")
    print(f"  stories            : {n}")
    print(f"  valid skeleton rate: {summary['valid_skeleton_rate']:.1%}")
    print(f"  criteria cover rate: {summary['criteria_cover_rate']:.1%}")
    print(f"  hallucinated login : {summary['hallucinated_login_rate']:.1%}")
    print(f"  skip lines         : {skips}")
    print(f"  placeholders       : {phs}")
    print(f"  errors             : {errors}")
    print(f"  saved              : {save}")


def _current_model() -> str:
    import os

    return os.environ.get("OPENAI_MODEL", "") or "auto-detect (see server /v1/models)"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--stories",
        type=int,
        default=0,
        help="Limit to first N stories (default: all)",
    )
    parser.add_argument(
        "--save",
        default=str(PROJECT_ROOT / "training_data" / "model_baseline.json"),
        help="Output JSON path",
    )
    args = parser.parse_args()

    stories_file = PROJECT_ROOT / "training_data" / "synthetic_stories.jsonl"
    asyncio.run(run(stories_file, args.stories, Path(args.save)))


if __name__ == "__main__":
    main()
