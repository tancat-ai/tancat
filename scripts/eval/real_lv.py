"""LV Insurance eval — full PlaceholderOrchestrator resolution, no journey discovery."""
import asyncio, json, os, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["RAG_ENABLED"] = "1"

from src.llm_client import LLMClient
from src.test_generator import TestGenerator
from src.scraper import PageScraper
from src.skeleton_parser import SkeletonParser
from src.placeholder_orchestrator import PlaceholderOrchestrator
from src.prompt_utils import prepare_conditions_for_generation, count_conditions
from src.code_postprocessor import normalise_generated_code
from src.pipeline_models import PageRequirement

DEEPSEEK = dict(provider="openai-compatible", base_url="https://api.deepseek.com/v1",
                api_key="sk-d90378f27e0647f28d59eb762a388f38", model="deepseek-chat")

async def run_pipeline(label, use_graph):
    if use_graph:
        os.environ.pop("LANGGRAPH_ENABLED", None)
    else:
        os.environ["LANGGRAPH_ENABLED"] = "0"

    golden = json.loads(Path("scripts/eval/dataset/eval-005_lv_insurance_quote.json").read_text())
    base_url = golden["base_url"]
    conditions_text = "\n".join(golden["conditions"])

    client = LLMClient(**DEEPSEEK)
    gen = TestGenerator(client=client)
    parser = SkeletonParser()

    # --- Skeleton ---
    t0 = time.time()
    conditions = prepare_conditions_for_generation(conditions_text)
    expected_count = count_conditions(conditions_text)

    if use_graph:
        from src.orchestrator import TestOrchestrator
        orch = TestOrchestrator(gen, pom_mode=False)
        state = await orch.run_pipeline_via_graph(
            user_story=golden["user_story"], conditions=conditions_text,
            target_urls=[base_url], auto_confirm=True,
        )
        skeleton = state.test_code if (state and state.test_code) else await gen.generate_skeleton(
            golden["user_story"], conditions, target_urls=[base_url], expected_count=expected_count)
        if state and state.errors:
            print(f"  [{label}] Graph errors: {state.errors[:3]}", flush=True)
    else:
        skeleton = await gen.generate_skeleton(
            golden["user_story"], conditions, target_urls=[base_url], expected_count=expected_count)

    skeleton = parser.normalise_placeholder_actions(skeleton)
    n_ph = len(parser.parse_placeholders(skeleton))
    journeys = parser.parse_test_journeys(skeleton)
    skel_time = time.time() - t0
    print(f"  [{label}] Skeleton: {skel_time:.1f}s, {len(journeys)} journeys, {n_ph} placeholders", flush=True)

    # --- Scrape (initial only, skip journey discovery) ---
    t0 = time.time()
    scraper = PageScraper()
    elements, error, _ = await scraper.scrape_url(base_url)
    if error:
        print(f"  [{label}] Scrape error: {error}", flush=True)
    scrape_time = time.time() - t0
    print(f"  [{label}] Scrape: {scrape_time:.1f}s, {len(elements)} elements", flush=True)

    # --- Resolve with REAL PlaceholderOrchestrator ---
    t0 = time.time()
    resolver = PlaceholderOrchestrator(
        starting_url=base_url, credential_profile=None,
        pom_mode=False, generator=client,
    )
    page_reqs = [PageRequirement(keyword="home", description="Landing page")]

    final_code = await resolver._replace_placeholders_sequentially(
        skeleton_code=skeleton,
        journeys=journeys,
        page_requirements=page_reqs,
        seed_urls=[base_url],
        scraped_data={base_url: elements},
        scraped_errors={},
    )
    resolve_time = time.time() - t0
    print(f"  [{label}] Resolve: {resolve_time:.1f}s", flush=True)

    # --- Validate ---
    final_code = normalise_generated_code(final_code)
    from scripts.eval.golden_validator import validate_dataset
    results = validate_dataset(Path("scripts/eval/dataset"), {"eval-005": final_code}, {})
    acc = 0.0
    for s in results:
        if s.resolutions:
            correct = sum(1 for r in s.resolutions if r.matched)
            acc = correct / len(s.resolutions) * 100
            print(f"  [{label}] Golden: {correct}/{len(s.resolutions)} matched", flush=True)
        else:
            n_res = len(s.resolutions)
            print(f"  [{label}] Golden: {n_res} resolutions, 0 matched", flush=True)
    print(f"  [{label}] ACCURACY: {acc:.1f}%", flush=True)

    out = Path(f"scripts/eval/captures/lv_insurance_{label}.py")
    out.write_text(final_code, encoding="utf-8")
    print(f"  [{label}] Total: {skel_time+scrape_time+resolve_time:.1f}s", flush=True)
    return acc

async def main():
    print("=== LV INSURANCE (real resolver, no journey disc) ===")
    lin_acc = await run_pipeline("linear", use_graph=False)
    print()
    grp_acc = await run_pipeline("graph", use_graph=True)
    print()
    print(f"Linear: {lin_acc:.1f}%  |  Graph: {grp_acc:.1f}%  |  Delta: {grp_acc-lin_acc:+.1f}pp")

asyncio.run(main())
