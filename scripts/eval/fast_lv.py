"""Fast LV Insurance eval — skeleton + simple resolve, no journey discovery."""
import asyncio, json, os, sys, time, re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ["RAG_ENABLED"] = "1"

from src.llm_client import LLMClient
from src.test_generator import TestGenerator
from src.scraper import PageScraper
from src.skeleton_parser import SkeletonParser
from src.prompt_utils import prepare_conditions_for_generation
from src.code_postprocessor import normalise_generated_code

async def main():
    golden_file = Path("scripts/eval/dataset/eval-005_lv_insurance_quote.json")
    golden = json.loads(golden_file.read_text())
    base_url = golden["base_url"]

    client = LLMClient(
        provider="openai-compatible", base_url="https://api.deepseek.com/v1",
        api_key="sk-d90378f27e0647f28d59eb762a388f38", model="deepseek-chat",
    )

    # --- Generate skeleton ---
    t0 = time.time()
    gen = TestGenerator(client=client)
    conditions = prepare_conditions_for_generation("\n".join(golden["conditions"]))
    skeleton = await gen.generate_skeleton(
        golden["user_story"], conditions, target_urls=[base_url], expected_count=10,
    )
    parser = SkeletonParser()
    skeleton = parser.normalise_placeholder_actions(skeleton)
    print(f"Skeleton: {time.time()-t0:.1f}s, {len(parser.parse_placeholders(skeleton))} placeholders", flush=True)

    # --- Scrape ---
    t0 = time.time()
    scraper = PageScraper()
    elements, error, _ = await scraper.scrape_url(base_url)
    print(f"Scrape: {time.time()-t0:.1f}s, {len(elements)} elements" + (f", error={error}" if error else ""), flush=True)

    # Build lookup maps
    by_id = {e.get("id","").lower(): e for e in elements if e.get("id")}
    by_name = {e.get("name","").lower(): e for e in elements if e.get("name")}
    by_text = {}
    for e in elements:
        t = (e.get("text") or "").strip().lower()
        if t: by_text[t] = e

    # --- Resolve ---
    t0 = time.time()
    placeholders = parser.parse_placeholders(skeleton)
    resolved = 0
    unresolved = []

    def find_element(desc, action):
        d = desc.lower().strip()
        # Direct ID match
        for eid, elem in by_id.items():
            if d in eid or eid in d:
                return elem.get("selector") or f"#{eid}"
        # Name match
        for nm, elem in by_name.items():
            if d in nm or nm in d:
                return elem.get("selector") or f"[name='{nm}']"
        # Text match
        for txt, elem in by_text.items():
            if d in txt:
                return elem.get("selector") or f"text='{txt}'"
        return None

    # Build resolved code
    lines = []
    skip_unresolved = set()
    for journey in parser.parse_test_journeys(skeleton):
        func_lines = skeleton.splitlines()[journey.start_line-1:journey.end_line]
        resolved_func = []
        has_unresolved = False
        for line in func_lines:
            indent = line[:len(line) - len(line.lstrip())]
            m = re.match(r'\s*\{\{(\w+):([^}]+)\}\}', line)
            if m:
                action, desc = m.group(1), m.group(2).strip()
                selector = find_element(desc, action)
                if selector:
                    indent = line[:len(line) - len(line.lstrip())]
                    if action == "GOTO":
                        resolved_func.append(f'{indent}evidence_tracker.navigate("{base_url}")')
                    elif action == "FILL":
                        val = desc.split(":")[-1].strip() if ":" in desc else "test"
                        resolved_func.append(f'{indent}evidence_tracker.fill("{selector}", "{val}", label="{desc}")')
                    elif action == "CLICK":
                        resolved_func.append(f'{indent}evidence_tracker.click("{selector}", label="{desc}")')
                    elif action == "ASSERT":
                        resolved_func.append(f'{indent}evidence_tracker.assert_visible("{selector}", label="{desc}")')
                    resolved += 1
                else:
                    resolved_func.append(f'{indent}pytest.skip("Unresolved: {desc}")')
                    has_unresolved = True
                    unresolved.append(desc)
            else:
                resolved_func.append(line)
        lines.extend(resolved_func)
        if has_unresolved:
            fn_line = func_lines[0] if func_lines else ""
            if "def test_" in fn_line:
                indent = fn_line[:len(fn_line) - len(fn_line.lstrip())]
                lines.insert(len(lines) - len(resolved_func), f'{indent}pytest.skip("Skipping: unresolved placeholders")')

    final_code = "\n".join(lines)
    final_code = normalise_generated_code(final_code)
    print(f"Resolve: {time.time()-t0:.1f}s, {resolved}/{len(placeholders)} resolved, {len(unresolved)} unresolved", flush=True)

    # --- Validate ---
    from scripts.eval.golden_validator import validate_dataset
    results = validate_dataset(Path("scripts/eval/dataset"), {"eval-005": final_code}, {})
    for s in results:
        if s.resolutions:
            correct = sum(1 for r in s.resolutions if r.matched)
            print(f"ACCURACY: {correct}/{len(s.resolutions)} = {correct/len(s.resolutions)*100:.1f}%", flush=True)
        else:
            print(f"ACCURACY: no resolutions matched", flush=True)

    out = Path("scripts/eval/captures/lv_insurance_fast.py")
    out.write_text(final_code)
    print(f"Saved: {out}", flush=True)

asyncio.run(main())
