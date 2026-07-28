"""LV Insurance — local LLM test."""
import asyncio, json, os, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["RAG_ENABLED"] = "1"
os.environ["LANGGRAPH_ENABLED"] = "0"

from src.llm_client import LLMClient
from src.test_generator import TestGenerator
from src.scraper import PageScraper
from src.skeleton_parser import SkeletonParser
from src.placeholder_orchestrator import PlaceholderOrchestrator
from src.prompt_utils import prepare_conditions_for_generation, count_conditions
from src.code_postprocessor import normalise_generated_code
from src.pipeline_models import PageRequirement

async def main():
    golden = json.loads(Path("scripts/eval/dataset/eval-005_lv_insurance_quote.json").read_text())
    base_url = golden["base_url"]
    conditions_text = "\n".join(golden["conditions"])

    client = LLMClient()
    print(f"LLM: {client.provider_name} / {client.model}", flush=True)
    gen = TestGenerator(client=client)
    parser = SkeletonParser()

    t0 = time.time()
    conditions = prepare_conditions_for_generation(conditions_text)
    skeleton = await gen.generate_skeleton(golden["user_story"], conditions, target_urls=[base_url], expected_count=10)
    skeleton = parser.normalise_placeholder_actions(skeleton)
    journeys = parser.parse_test_journeys(skeleton)
    print(f"Skeleton: {time.time()-t0:.1f}s, {len(journeys)} journeys, {len(parser.parse_placeholders(skeleton))} ph", flush=True)

    t0 = time.time()
    scraper = PageScraper()
    elements, error, _ = await scraper.scrape_url(base_url)
    print(f"Scrape: {time.time()-t0:.1f}s, {len(elements)} elements", flush=True)

    t0 = time.time()
    resolver = PlaceholderOrchestrator(starting_url=base_url, credential_profile=None, pom_mode=False, generator=client)
    final_code = await resolver._replace_placeholders_sequentially(
        skeleton_code=skeleton, journeys=journeys,
        page_requirements=[PageRequirement(keyword="home", description="Landing page")],
        seed_urls=[base_url], scraped_data={base_url: elements}, scraped_errors={},
    )
    print(f"Resolve: {time.time()-t0:.1f}s", flush=True)

    final_code = normalise_generated_code(final_code)
    
    from scripts.eval.golden_validator import validate_dataset as vd
    results = vd(Path("scripts/eval/dataset"), {"eval-005": final_code}, {})
    for s in results:
        if s.resolutions:
            correct = sum(1 for r in s.resolutions if r.matched)
            print(f"ACCURACY: {correct}/{len(s.resolutions)} = {correct/len(s.resolutions)*100:.1f}%", flush=True)
    
    out = Path("scripts/eval/captures/local_lv_linear.py")
    out.write_text(final_code)
    print(f"Saved: {out}", flush=True)

asyncio.run(main())
