"""Time just the journey scraper for LV Insurance."""
import asyncio, time, logging, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s", datefmt="%H:%M:%S")

from src.llm_client import LLMClient
from src.test_generator import TestGenerator
from src.orchestrator import TestOrchestrator
from src.skeleton_parser import SkeletonParser

async def test():
    client = LLMClient(
        provider="openai-compatible",
        base_url="https://api.deepseek.com/v1",
        api_key="sk-d90378f27e0647f28d59eb762a388f38",
        model="deepseek-chat",
    )
    gen = TestGenerator(client=client)

    import json
    golden = json.loads(Path("scripts/eval/dataset/eval-005_lv_insurance_quote.json").read_text())
    story = golden["user_story"]
    conditions = "\n".join(golden["conditions"])

    orch = TestOrchestrator(gen, pom_mode=False)

    start = time.time()
    skeleton = await gen.generate_skeleton(
        story, conditions,
        target_urls=["http://127.0.0.1:8781/generated_tests/mock_insurance_site.html"],
        expected_count=10,
    )
    print(f"Skeleton gen: {time.time()-start:.1f}s")

    parser = SkeletonParser()
    journeys = parser.parse_test_journeys(skeleton)
    print(f"Journeys: {len(journeys)}, steps: {sum(len(j.steps) for j in journeys)}")

    start = time.time()
    discovery_data, pages = await orch._scrape_journeys_statefully(
        journeys,
        "http://127.0.0.1:8781/generated_tests/mock_insurance_site.html",
        None,
    )
    elapsed = time.time() - start
    print(f"Journey scrape: {elapsed:.1f}s, pages={len(pages)}, urls={len(discovery_data)}")
    for url, elems in discovery_data.items():
        print(f"  {url}: {len(elems)} elements")

asyncio.run(test())
