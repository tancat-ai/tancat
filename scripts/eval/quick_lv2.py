"""Quick flat-mode eval-005 test - NO journey discovery, NO stateful upgrade."""
import asyncio, json, os, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ["RAG_ENABLED"] = "1"
os.environ["LANGGRAPH_ENABLED"] = "0"

from src.llm_client import LLMClient
from src.test_generator import TestGenerator
from src.scraper import PageScraper
from src.placeholder_resolver import PlaceholderResolver
from src.skeleton_parser import SkeletonParser
from src.skeleton_validator import SkeletonValidator
from src.prompt_utils import prepare_conditions_for_generation
from src.code_postprocessor import normalise_generated_code

async def main():
    golden_file = Path("scripts/eval/dataset/eval-005_lv_insurance_quote.json")
    golden = json.loads(golden_file.read_text())
    base_url = golden["base_url"]

    client = LLMClient(
        provider="openai-compatible",
        base_url="https://api.deepseek.com/v1",
        api_key="sk-d90378f27e0647f28d59eb762a388f38",
        model="deepseek-chat",
    )
    gen = TestGenerator(client=client)

    # --- Phase 1: Skeleton ---
    t0 = time.time()
    conditions = prepare_conditions_for_generation("\n".join(golden["conditions"]))
    skeleton = await gen.generate_skeleton(
        golden["user_story"], conditions,
        target_urls=[base_url], expected_count=10,
    )
    print(f"SKELETON: {time.time()-t0:.1f}s", flush=True)

    parser = SkeletonParser()
    skeleton = parser.normalise_placeholder_actions(skeleton)

    # --- Phase 2: Simple scrape (no journey discovery) ---
    t0 = time.time()
    scraper = PageScraper()
    elements, error, final_url = await scraper.scrape_url(base_url)
    print(f"SCRAPE: {time.time()-t0:.1f}s, {len(elements)} elements", flush=True)

    # --- Phase 3: Resolve placeholders ---
    t0 = time.time()
    resolver = PlaceholderResolver()
    placeholders = parser.parse_placeholders(skeleton)
    print(f"Placeholders to resolve: {len(placeholders)}", flush=True)
    
    # Simple direct resolution - try each placeholder against scraped elements
    resolved_count = 0
    for ph in placeholders:
        action = ph.get("action", "")
        desc = ph.get("description", "")
        # Try to find matching element
        for elem in elements:
            eid = elem.get("id", "")
            ename = elem.get("name", "")
            etext = elem.get("text", "").lower()
            elabel = elem.get("aria_label", "").lower()
            desc_lower = desc.lower()
            if desc_lower in eid or desc_lower in ename or desc_lower in etext or desc_lower in elabel:
                resolved_count += 1
                break
    print(f"RESOLVE (simple): {time.time()-t0:.1f}s, {resolved_count}/{len(placeholders)} matched", flush=True)

    # Build final code  
    code = skeleton  # placeholder - would need full resolution
    out = Path("scripts/eval/captures/lv_insurance_flat.py")
    out.write_text(code)
    print(f"DONE: {len(code)} chars", flush=True)

asyncio.run(main())
