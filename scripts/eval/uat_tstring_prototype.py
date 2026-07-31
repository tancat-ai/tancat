"""UAT: t-string PromptBuilder prototype vs legacy prompt (LV Insurance).

Runs the REAL pipeline (orchestrator.run_pipeline) twice against eval-005:

  * LEGACY path  — TestGenerator uses get_skeleton_prompt_template().format()
  * TSTRING path — TestGenerator uses build_skeleton_prompt() + PromptBuilder

The only difference is the prompt-construction seam (monkeypatched at
``TestGenerator.generate_skeleton``). Everything else — parser normalisation,
journey scraping, placeholder resolution, post-processing — is untouched.

Reports: skeleton stats, resolved locators, pytest.skip count, golden-key
matches for each path.

Usage:
    uv run python scripts/eval/uat_tstring_prototype.py
    (requires LM Studio / LLM on :8080 — see .env LLM_PROVIDER=openai-local)

One-off UAT script — archive to scripts/archive/ after the prototype decision.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))
sys.path.insert(0, str(_PROJECT_ROOT / "scripts" / "eval"))

from golden_validator import extract_locators_from_code, validate_story  # noqa: E402

from src.llm_client import LLMClient  # noqa: E402
from src.orchestrator import TestOrchestrator  # noqa: E402
from src.prompt_builder import PromptBuilder, build_skeleton_prompt  # noqa: E402
from src.prompt_utils import get_skeleton_prompt_template  # noqa: E402
from src.test_generator import TestGenerator  # noqa: E402

GOLDEN = _PROJECT_ROOT / "scripts" / "eval" / "dataset" / "eval-005_lv_insurance_quote.json"

TEST_FN_RE = re.compile(r"^\s*def\s+(test_\w+)\s*\(", re.M)
PLACEHOLDER_RE = re.compile(r"\{\{?(CLICK|FILL|GOTO|ASSERT|URL):[^}]+\}?\}")


def load_story() -> dict:
    return json.loads(GOLDEN.read_text(encoding="utf-8"))


def build_known_urls_block(golden: dict) -> str:
    return f"- {golden['base_url']}"


async def generate_skeleton_legacy(
    generator: TestGenerator,
    golden: dict,
) -> str:
    """Replicate the legacy skeleton prompt path exactly."""
    known_urls_block = build_known_urls_block(golden)
    expected_count = len(golden["conditions"])
    prompt = get_skeleton_prompt_template(expected_count=expected_count).format(
        user_story=golden["user_story"],
        conditions="\n".join(golden["conditions"]),
        known_urls_block=known_urls_block,
    )
    return await generator.client.generate(prompt)


async def generate_skeleton_tstring(
    generator: TestGenerator,
    golden: dict,
) -> str:
    """Skeleton via the PEP 750 t-string PromptBuilder."""
    known_urls_block = build_known_urls_block(golden)
    expected_count = len(golden["conditions"])
    template = build_skeleton_prompt(
        user_story=golden["user_story"],
        conditions="\n".join(golden["conditions"]),
        known_urls_block=known_urls_block,
        expected_count=expected_count,
    )
    prompt = PromptBuilder(template).render().text
    return await generator.client.generate(prompt)


def skeleton_stats(skeleton: str) -> dict:
    try:
        compile(skeleton, "<skeleton>", "exec")
        parseable = True
    except SyntaxError:
        parseable = False
    return {
        "test_functions": len(TEST_FN_RE.findall(skeleton)),
        "placeholders": len(PLACEHOLDER_RE.findall(skeleton)),
        "parseable": parseable,
    }


def report_resolution(final_code: str, golden: dict) -> dict:
    """Score with the OFFICIAL eval-harness matcher (action + normalized locator)."""
    result = validate_story(final_code, golden)
    matches = sum(1 for r in result.resolutions if r.matched)
    total = len(result.resolutions)
    return {
        "locators": len(extract_locators_from_code(final_code)),
        "skips": final_code.count("pytest.skip"),
        "golden_matches": f"{matches}/{total}",
        "unresolved": [r.description for r in result.resolutions if not r.matched],
    }


async def run_path(path_name: str, skeleton_fn: object, golden: dict, client: LLMClient) -> dict:
    print(f"\n{'=' * 70}\n--- {path_name} path: full pipeline ---\n{'=' * 70}")
    generator = TestGenerator(client=client)

    # Monkeypatch the real seam the orchestrator calls
    async def _patched_generate_skeleton(user_story, conditions, target_urls=None, expected_count=None):  # type: ignore[no-untyped-def]
        return await skeleton_fn(generator, golden)  # type: ignore[misc]

    generator.generate_skeleton = _patched_generate_skeleton  # type: ignore[method-assign]

    orchestrator = TestOrchestrator(generator, pom_mode=False)
    final_code = await orchestrator.run_pipeline(
        user_story=golden["user_story"],
        conditions="\n".join(golden["conditions"]),
        target_urls=[golden["base_url"]],
    )

    report = report_resolution(final_code, golden)
    report["final_code"] = final_code
    return report


async def main() -> int:
    golden = load_story()

    print("=" * 70)
    print("UAT — t-string PromptBuilder prototype (eval-005 LV Insurance)")
    print("=" * 70)

    # Prompt identity check first (no LLM needed)
    legacy_prompt = get_skeleton_prompt_template(expected_count=len(golden["conditions"])).format(
        user_story=golden["user_story"],
        conditions="\n".join(golden["conditions"]),
        known_urls_block=build_known_urls_block(golden),
    )
    tstring_prompt = (
        PromptBuilder(
            build_skeleton_prompt(
                user_story=golden["user_story"],
                conditions="\n".join(golden["conditions"]),
                known_urls_block=build_known_urls_block(golden),
                expected_count=len(golden["conditions"]),
            )
        )
        .render()
        .text
    )
    print(f"prompt byte-identical: {legacy_prompt == tstring_prompt} ({len(legacy_prompt)} chars)")

    client = LLMClient()

    results = {}
    for path_name, fn in (("LEGACY", generate_skeleton_legacy), ("TSTRING", generate_skeleton_tstring)):
        results[path_name] = await run_path(path_name, fn, golden, client)

    # ---- Summary ----
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"{'metric':<28}{'LEGACY':<20}{'TSTRING':<20}")
    for metric in ("locators", "skips", "golden_matches"):
        print(f"{metric:<28}{results['LEGACY'][metric]:<20}{results['TSTRING'][metric]:<20}")
    for path_name in ("LEGACY", "TSTRING"):
        if results[path_name]["unresolved"]:
            print(f"\n{path_name} unresolved ({len(results[path_name]['unresolved'])}):")
            for d in results[path_name]["unresolved"]:
                print(f"  - {d}")

    # Save artefacts
    out_dir = _PROJECT_ROOT / "scripts" / "eval" / "generated_tests"
    out_dir.mkdir(exist_ok=True)
    for path_name in ("LEGACY", "TSTRING"):
        (out_dir / f"uat_tstring_final_{path_name.lower()}.py").write_text(
            results[path_name]["final_code"], encoding="utf-8"
        )
    print(f"\nartefacts saved to {out_dir}")
    print("\n" + "=" * 70)
    return 0


if __name__ == "__main__":
    import asyncio

    sys.exit(asyncio.run(main()))
