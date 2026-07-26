"""Quick flat-mode eval-005 test."""
import asyncio, json, os, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ["RAG_ENABLED"] = "1"
os.environ["LANGGRAPH_ENABLED"] = "0"

from src.llm_client import LLMClient
from src.test_generator import TestGenerator
from src.orchestrator import TestOrchestrator

async def main():
    golden_file = Path("scripts/eval/dataset/eval-005_lv_insurance_quote.json")
    golden = json.loads(golden_file.read_text())

    client = LLMClient(
        provider="openai-compatible",
        base_url="https://api.deepseek.com/v1",
        api_key="sk-d90378f27e0647f28d59eb762a388f38",
        model="deepseek-chat",
    )
    generator = TestGenerator(client=client)
    orch = TestOrchestrator(generator, pom_mode=False)  # FLAT mode

    import logging
    logging.basicConfig(level=logging.DEBUG, format='%(asctime)s [%(name)s] %(message)s', datefmt='%H:%M:%S')
    
    print("=== STARTING PIPELINE ===", flush=True)
    start = time.time()
    code = await orch.run_pipeline(
        user_story=golden["user_story"],
        conditions="\n".join(golden["conditions"]),
        target_urls=[golden["base_url"]],
    )
    elapsed = time.time() - start
    print(f"=== PIPELINE DONE: {elapsed:.1f}s ===", flush=True)

    out = Path("scripts/eval/captures/lv_insurance_flat.py")
    out.write_text(code)
    print(f"FLAT DONE: {elapsed:.1f}s, {len(code)} chars")
    
    # Quick validate
    from scripts.eval.golden_validator import validate_dataset
    results = validate_dataset(
        Path("scripts/eval/dataset"),
        {"eval-005": code},
        {},
    )
    for s in results:
        correct = sum(1 for r in s.resolutions if r.matched)
        print(f"Accuracy: {correct}/{len(s.resolutions)} ({correct/len(s.resolutions)*100:.1f}%)")

asyncio.run(main())
