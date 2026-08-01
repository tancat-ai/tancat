"""UAT for AI-034 Phase 3 — one skeleton function per confirmed test row.

Runs the REAL pipeline path with the REAL LLM (LM Studio :8080):

  1. SpecAnalyzer derives conditions from a story (numbered ACs -> deterministic)
  2. TestTableExpander expands each condition into concrete test rows (LLM)
  3. table_to_conditions() converts confirmed rows into generation conditions
  4. TestOrchestrator generates ONE skeleton function per condition
  5. Verifies: function count == confirmed row count, skeleton valid, no skips

Usage:
    python scripts/uat/uat_test_table.py [--url https://www.saucedemo.com]
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.llm_client import LLMClient  # noqa: E402
from src.orchestrator import TestOrchestrator  # noqa: E402
from src.spec_analyzer import SpecAnalyzer  # noqa: E402
from src.test_generator import TestGenerator  # noqa: E402
from src.test_plan import TestPlan  # noqa: E402
from src.test_table import TestTableExpander, table_to_conditions  # noqa: E402

STORY = """As a customer, I want to sort the product catalogue and log in so I can find and buy items quickly.

Acceptance Criteria:
1. filters — A-Z, Z-A, price low-high, price high-low
2. login with valid credentials
"""

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"


def check(name: str, passed: bool, detail: str = "") -> None:
    marker = f"{GREEN}PASS{RESET}" if passed else f"{RED}FAIL{RESET}"
    print(f"  [{marker}] {name}" + (f" — {detail}" if detail else ""))
    return


async def main() -> int:
    parser = argparse.ArgumentParser(description="AI-034 Phase 3 UAT")
    parser.add_argument("--url", default="https://www.saucedemo.com", help="Target site URL")
    args = parser.parse_args()

    failures = 0

    # ── 1. Plan (deterministic numbered ACs) ──────────────────────────────
    print("\n[1] Build Living Test Plan (SpecAnalyzer)")
    analyzer = SpecAnalyzer()
    conditions = analyzer.analyze(STORY)
    plan = TestPlan.from_conditions(story_ref="story_test_table_uat", sprint="Backlog", conditions=conditions)
    check("conditions derived", len(plan.conditions) >= 2, f"{len(plan.conditions)} condition(s)")
    for condition in plan.conditions:
        print(f"      {condition.id}: {condition.text}")
    if len(plan.conditions) < 2:
        failures += 1

    # ── 2. Expand into Test Rows (LLM) ────────────────────────────────────
    print("\n[2] Expand conditions into Test Rows (TestTableExpander)")
    expander = TestTableExpander()
    table = expander.expand_conditions(plan.conditions)
    check("rows produced", len(table) > len(plan.conditions), f"{len(plan.conditions)} conditions -> {len(table)} rows")
    for row in table:
        print(f"      {row.id} [{row.condition_ref}] {row.expected_action}: {row.intent}")
    if len(table) <= len(plan.conditions):
        failures += 1

    # ── 3. Convert confirmed rows -> generation conditions ─────────────────
    print("\n[3] Rows -> generation conditions (table_to_conditions)")
    from src.test_table import TestTable

    test_table = TestTable(rows=table, confirmed_ids={row.id for row in table})
    row_conditions = table_to_conditions(test_table)
    check(
        "one condition per row",
        len(row_conditions) == len(test_table.rows),
        f"{len(test_table.rows)} rows -> {len(row_conditions)} conditions",
    )
    check(
        "condition ids match row ids",
        [c.id for c in row_conditions] == [r.id for r in table],
    )
    if len(row_conditions) != len(test_table.rows):
        failures += 1

    # ── 4. Skeleton generation — ONE function per condition (LLM) ─────────
    print(f"\n[4] Skeleton generation ({len(row_conditions)} functions expected)")
    LLMClient.set_session_provider("openai-local", base_url="http://localhost:8080")
    client = LLMClient()
    generator = TestGenerator(client=client)
    orchestrator = TestOrchestrator(generator, pom_mode=False)

    start = time.time()
    try:
        skeleton = await orchestrator._generate_combined_skeleton_for_conditions(
            user_story=STORY,
            conditions=row_conditions,
            target_urls=[args.url],
        )
    except Exception as exc:  # noqa: BLE001
        check("skeleton generation", False, f"{type(exc).__name__}: {exc}")
        return 1
    duration = time.time() - start

    function_names = re.findall(r"^\s*def\s+(test_\w+)", skeleton, re.MULTILINE)
    check(
        "one skeleton function per row",
        len(function_names) == len(row_conditions),
        f"{len(row_conditions)} rows -> {len(function_names)} functions ({duration:.1f}s)",
    )
    for name in function_names:
        print(f"      {name}")

    # ── 5. Skeleton quality ───────────────────────────────────────────────
    check("no pytest.skip in skeleton", "pytest.skip" not in skeleton)
    placeholder_count = len(re.findall(r"\{\{\{?(\w+):", skeleton))
    check("placeholders present", placeholder_count > 0, f"{placeholder_count} placeholder(s)")
    check("code substantive", len(skeleton) > 200, f"{len(skeleton)} chars")

    if len(function_names) != len(row_conditions):
        failures += 1
    if "pytest.skip" in skeleton:
        failures += 1

    print()
    if failures:
        print(f"{RED}UAT FAILED — {failures} check(s) failed{RESET}")
        return 1
    print(f"{GREEN}UAT PASSED — one skeleton per confirmed test row verified{RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
