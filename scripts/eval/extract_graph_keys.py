"""Graph golden key extraction tool.

Extracts expected locators from graph-generated capture files and
saves them as golden keys for graph-specific evaluation.

Usage:
    # Extract all graph golden keys from captures
    python scripts/eval/extract_graph_keys.py

    # Then run eval against graph keys
    python scripts/eval/eval_harness.py run --mode static --dataset scripts/eval/dataset/graph
"""

from __future__ import annotations

import json
import re
from pathlib import Path

DATASET = Path("scripts/eval/dataset")
CAPTURES = Path("scripts/eval/captures")
GRAPH_KEYS = DATASET / "graph"

SITE_MAP = {
    "saucedemo": "eval-001",
    "automationexercise": "eval-002",
    "demoqa": "eval-003",
    "theinternet": "eval-004",
    "lv_insurance": "eval-005",
}


def extract_locators_from_code(code: str) -> list[dict]:
    """Extract (action, description, locator) from generated test code."""
    results = []
    for line in code.splitlines():
        # Direct: evidence_tracker.ACTION('locator', ..., label='desc')
        m = re.search(r"evidence_tracker\.(\w+)\(['\"]([^'\"]+)['\"]", line)
        if m:
            action_raw = m.group(1)
            locator = m.group(2)
            label_m = re.search(r"label=['\"]([^'\"]+)['\"]", line)
            desc = label_m.group(1) if label_m else action_raw
        else:
            # POM: xxx_page.ACTION('description')
            m = re.search(r"(\w+_page)\.(\w+)\(['\"]([^'\"]+)['\"]", line)
            if m:
                action_raw = m.group(2)
                desc = m.group(3)
                locator = desc
            else:
                continue

        action_map = {
            "navigate": "GOTO",
            "click": "CLICK",
            "fill": "FILL",
            "assert_visible": "ASSERT",
            "assert_text": "ASSERT",
            "assert_text_contains": "ASSERT",
            "select": "SELECT",
            "get_text": "ASSERT",
            "assert_value": "ASSERT",
            "assert_disabled": "ASSERT",
            "assert_enabled": "ASSERT",
        }
        action = action_map.get(action_raw, action_raw.upper())

        results.append(
            {
                "action": action,
                "description": desc,
                "expected_locator": locator,
                "tolerance_selectors": [],
            }
        )
    return results


def main():
    GRAPH_KEYS.mkdir(exist_ok=True)

    for capture_file in sorted(CAPTURES.glob("*_code.py")):
        site = capture_file.stem.replace("_code", "")
        story_id = SITE_MAP.get(site)
        if not story_id:
            continue

        # Load original for story/criteria/URL
        orig_files = list(DATASET.glob(f"{story_id}_*.json"))
        if not orig_files:
            continue
        orig = json.loads(orig_files[0].read_text())

        code = capture_file.read_text()
        locators = extract_locators_from_code(code)

        key = {
            "id": story_id,
            "site": site,
            "user_story": orig["user_story"],
            "conditions": orig["conditions"],
            "base_url": orig["base_url"],
            "golden_resolutions": [
                {"criterion": f"Graph criterion {i + 1}", "placeholders": [gl]} for i, gl in enumerate(locators)
            ],
        }

        out = GRAPH_KEYS / f"{story_id}_{site}_graph.json"
        out.write_text(json.dumps(key, indent=2))
        print(f"  {out.name}: {len(locators)} placeholders")

    print(f"\nGraph golden keys saved to {GRAPH_KEYS}/")
    print("Run: python scripts/eval/eval_harness.py run --mode static --dataset scripts/eval/dataset/graph")


if __name__ == "__main__":
    main()
