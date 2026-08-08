"""One-off: re-run resolve-and-learn for the 3 mock sites with the fixed
MockServer + B-047 port-aware site_hash, regenerating clean fine-tuning rows
for banking_mock / ecommerce_mock / lv_insurance (contaminated rows were
purged — see playwright_resolved_alpaca.bak_* for the originals).

Run:  uv run python scripts/rerun_mock_resolve_learn.py
"""

from __future__ import annotations

import asyncio
import json
import sys

from scripts.synthesize_stories import TRAINING_DIR, resolve_and_learn

MOCK_SITES = ("banking_mock", "ecommerce_mock", "lv_insurance")


def main() -> None:
    stories = [
        json.loads(line)
        for line in (TRAINING_DIR / "synthetic_stories.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    mocks = [s for s in stories if s["site"] in MOCK_SITES]
    skel_path = TRAINING_DIR / "synthetic_skeletons_alpaca.jsonl"
    skeletons = [json.loads(line) for line in skel_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    print(f"resolve-learn: {len(mocks)} mock stories, {len(skeletons)} pre-generated skeletons")
    asyncio.run(resolve_and_learn(mocks, rag_modes=[True, False], skeleton_rows=skeletons))


if __name__ == "__main__":
    sys.exit(main())
