"""Fast A/B for LV Insurance — improved resolver with space-normalized matching."""
import asyncio, json, os, sys, time, re
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["RAG_ENABLED"] = "1"

from src.llm_client import LLMClient
from src.test_generator import TestGenerator
from src.scraper import PageScraper
from src.skeleton_parser import SkeletonParser
from src.prompt_utils import prepare_conditions_for_generation

DEEPSEEK = dict(provider="openai-compatible", base_url="https://api.deepseek.com/v1",
                api_key="sk-d90378f27e0647f28d59eb762a388f38", model="deepseek-chat")

async def run_pipeline(label, use_graph):
    if use_graph:
        os.environ.pop("LANGGRAPH_ENABLED", None)
    else:
        os.environ["LANGGRAPH_ENABLED"] = "0"

    golden_file = Path("scripts/eval/dataset/eval-005_lv_insurance_quote.json")
    golden = json.loads(golden_file.read_text())
    base_url = golden["base_url"]
    conditions_text = "\n".join(golden["conditions"])

    client = LLMClient(**DEEPSEEK)
    gen = TestGenerator(client=client)
    parser = SkeletonParser()

    # --- Skeleton ---
    t0 = time.time()
    conditions = prepare_conditions_for_generation(conditions_text)

    if use_graph:
        from src.orchestrator import TestOrchestrator
        orch = TestOrchestrator(gen, pom_mode=False)
        state = await orch.run_pipeline_via_graph(
            user_story=golden["user_story"], conditions=conditions_text,
            target_urls=[base_url], auto_confirm=True,
        )
        if state and state.test_code:
            skeleton = state.test_code
        else:
            skeleton = await gen.generate_skeleton(golden["user_story"], conditions, target_urls=[base_url], expected_count=10)
    else:
        skeleton = await gen.generate_skeleton(golden["user_story"], conditions, target_urls=[base_url], expected_count=10)

    skeleton = parser.normalise_placeholder_actions(skeleton)
    n_ph = len(parser.parse_placeholders(skeleton))
    skel_time = time.time() - t0
    print(f"  [{label}] Skeleton: {skel_time:.1f}s, {n_ph} placeholders", flush=True)

    # --- Scrape ---
    t0 = time.time()
    scraper = PageScraper()
    elements, error, _ = await scraper.scrape_url(base_url)
    scrape_time = time.time() - t0
    print(f"  [{label}] Scrape: {scrape_time:.1f}s, {len(elements)} elements", flush=True)

    # Build lookup - normalize by removing spaces/dashes
    def _norm(s):
        return (s or "").lower().replace(" ", "").replace("-", "").replace("_", "")

    by_id = {}
    for e in elements:
        eid = e.get("id") or ""
        if eid:
            by_id[_norm(eid)] = e
    by_name = {}
    for e in elements:
        nm = e.get("name") or ""
        if nm:
            by_name[_norm(nm)] = e
    by_label = {}
    for e in elements:
        lbl = e.get("aria_label") or e.get("placeholder") or ""
        if lbl:
            by_label[_norm(lbl)] = e
    by_text = {}
    for e in elements:
        txt = (e.get("text") or "").strip()
        if txt and len(txt) < 50:
            by_text[_norm(txt)] = e

    def find_selector(desc):
        d = _norm(desc)
        # ID match
        if d in by_id: return f"#{d}"
        for eid in by_id:
            if d in eid or eid in d: return f"#{eid}"
        # Name match
        if d in by_name: return f"[name='{d}']"
        for nm in by_name:
            if d in nm or nm in d: return f"[name='{nm}']"
        # Label match
        if d in by_label: return f"[aria-label='{d}']"
        for lbl in by_label:
            if d in lbl or lbl in d: return f"[aria-label='{lbl}']"
        # Text match
        for txt in by_text:
            if d in txt: return f"text='{txt}'"
        return None

    # --- Resolve ---
    t0 = time.time()
    placeholders = parser.parse_placeholders(skeleton)

    lines = []
    resolved = 0
    for journey in parser.parse_test_journeys(skeleton):
        func_lines = skeleton.splitlines()[journey.start_line - 1:journey.end_line]
        has_unresolved = False
        for line in func_lines:
            indent = line[:len(line) - len(line.lstrip())]
            m = re.match(r'\s*\{\{(\w+):([^}]+)\}\}', line)
            if m:
                action, desc = m.group(1), m.group(2).strip()
                sel = find_selector(desc)
                if sel:
                    if action == "GOTO":
                        lines.append(f'{indent}evidence_tracker.navigate("{base_url}")')
                    elif action == "FILL":
                        val = "test"
                        if ":" in desc:
                            val = desc.split(":")[-1].strip()
                        lines.append(f'{indent}evidence_tracker.fill("{sel}", "{val}", label="{desc}")')
                    elif action == "CLICK":
                        lines.append(f'{indent}evidence_tracker.click("{sel}", label="{desc}")')
                    elif action == "ASSERT":
                        lines.append(f'{indent}evidence_tracker.assert_visible("{sel}", label="{desc}")')
                    resolved += 1
                else:
                    lines.append(f'{indent}pytest.skip("Unresolved: {desc}")')
                    has_unresolved = True
            else:
                lines.append(line)

    from src.code_postprocessor import normalise_generated_code
    final_code = normalise_generated_code("\n".join(lines))
    resolve_time = time.time() - t0
    print(f"  [{label}] Resolve: {resolve_time:.1f}s, {resolved}/{len(placeholders)}", flush=True)

    # --- Validate ---
    from scripts.eval.golden_validator import validate_dataset
    results = validate_dataset(Path("scripts/eval/dataset"), {"eval-005": final_code}, {})
    acc = 0.0
    for s in results:
        if s.resolutions:
            correct = sum(1 for r in s.resolutions if r.matched)
            acc = correct / len(s.resolutions) * 100
            print(f"  [{label}] Golden matches: {correct}/{len(s.resolutions)}", flush=True)
    print(f"  [{label}] ACCURACY: {acc:.1f}%", flush=True)
    print(f"  [{label}] Total: {skel_time+scrape_time+resolve_time:.1f}s", flush=True)

    out = Path(f"scripts/eval/captures/lv_insurance_{label}.py")
    out.write_text(final_code)
    return acc, final_code

async def main():
    print("=== LV INSURANCE FAST A/B (improved resolver) ===")
    lin_acc, _ = await run_pipeline("linear", use_graph=False)
    print()
    grp_acc, _ = await run_pipeline("graph", use_graph=True)
    print()
    print(f"Linear: {lin_acc:.1f}%  |  Graph: {grp_acc:.1f}%  |  Delta: {grp_acc-lin_acc:+.1f}pp")

asyncio.run(main())
