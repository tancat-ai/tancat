"""Synthesize new user stories + skeletons to grow the fine-tuning dataset.

Pipeline (reuses the project's own machinery end-to-end):

    Stage 1 — Story synthesis
        For each eval site, prompt the local LLM (openai-local / llama.cpp on
        :8080) to write N new user stories + numbered acceptance criteria,
        anchored to the site's real element inventory. Validates that each
        story has numbered conditions and writes ``synthetic_stories.jsonl``.

    Stage 2 — Skeleton generation (offline, no browser)
        For each synthetic story, call ``TestGenerator.generate_skeleton()``
        (Phase 1 of the production pipeline — pure LLM, prompt built by
        ``src/prompt_builder.py``). The skeleton is the training output.

    Stage 3 — Validation
        Runs ``SkeletonParser.validate_skeleton()`` (same gate production
        uses) plus a criteria-count check. Only passing rows are written.

Outputs (Alpaca format, ready for Unsloth Studio):
    training_data/synthetic_stories.jsonl            (story + conditions)
    training_data/synthetic_skeletons_alpaca.jsonl   (instruction/input/output)

Usage:
    python scripts/synthesize_stories.py --count 10                  # stories only
    python scripts/synthesize_stories.py --count 10 --skeletons      # + skeleton gen (linear)
    python scripts/synthesize_stories.py --count 10 --skeletons --mode both
        # linear + LangGraph skeletons per story (graph is deterministic —
        # run once; linear is stochastic — rerun for diversity)
    python scripts/synthesize_stories.py --count 10 --skeletons --merge
        # --merge appends passing rows into training_data/playwright_skeleton_alpaca.jsonl
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any

from src.llm_client import LLMClient
from src.prompt_utils import count_conditions, prepare_conditions_for_generation
from src.skeleton_parser import SkeletonParser
from src.test_generator import TestGenerator

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TRAINING_DIR = PROJECT_ROOT / "training_data"
EVAL_DATASET_DIR = PROJECT_ROOT / "scripts" / "eval" / "dataset"
MAIN_SKELETON_FILE = TRAINING_DIR / "playwright_skeleton_alpaca.jsonl"

logger = logging.getLogger(__name__)

#: Element inventory per site — anchors generated stories to real elements so
#: the LLM cannot hallucinate pages. Extend this as sites grow.
SITE_INVENTORY: dict[str, str] = {
    "saucedemo": (
        "Pages: login, inventory, cart, checkout. "
        "Elements: #user-name, #password, #login-button, .inventory_item, "
        "#add-to-cart-sauce-labs-backpack, .shopping_cart_link, #checkout, "
        "#first-name, #last-name, #postal-code, #continue, #finish, #back-to-products"
    ),
    "automationexercise": (
        "Pages: home, products, product-details, cart, checkout, login. "
        "Elements: 'Products' link, 'Cart' link, 'Login' link, .add-to-cart, "
        "a[href=\"/view_cart\"], 'Place Order', 'Proceed To Checkout'"
    ),
    "demoqa": (
        "Pages: automation-practice-form. Elements: #firstName, #lastName, "
        "#userEmail, #userNumber, #dateOfBirthInput, #subjectsContainer, "
        "#currentAddress, #state, #city, #submit"
    ),
    "theinternet": (
        "Pages: /login, /add_remove_elements/, /checkboxes, /dropdown, /alerts. "
        "Elements: #username, #password, button.radius, .example a, #checkbox_1, "
        "#dropdown, button[onclick*='jsAlert'], #result"
    ),
    "lv_insurance": (
        "Local mock insurance quote site. Pages: home, vehicle, driver, coverage. "
        "Elements: 'Car Insurance' card, cover start date, vehicle registration, "
        "driving license number, years licensed, occupation select, quote summary"
    ),
    "ecommerce_mock": (
        "Local mock ecommerce (mock_sites/ecommerce). Pages: index, products, "
        "cart, checkout. Elements: 'Add to cart' buttons, 'Cart' link, "
        "'Checkout' link, #checkout-form, #name, #email, #address, #city, #zip, "
        "#card-name, #card-number, 'Place Order', #empty_cart"
    ),
    "banking_mock": (
        "Local mock banking (mock_sites/banking). Pages: index (login), "
        "dashboard, account, transfer, payments. Elements: #user-name, #password, "
        "#login-button, #login-error, #welcome-message, #accounts-list, "
        "#transfer-form, #from-account, #to-account, #amount, #transfer-submit, "
        "#payment-form, #payee, #pay-bill, #payment-amount, #payment-date"
    ),
}

STORY_PROMPT = """You are a QA scenario writer for automated web testing.

Write {count} DISTINCT, realistic user stories for the website "{site}" at {url}.

Each story must be a single sentence in the form:
"As a <role>, I want to <action>, <more actions> so that <benefit>."

The stories must ONLY exercise elements that exist on this site:

=== SITE ELEMENT INVENTORY ===
{inventory}

=== RULES ===
1. Every story must be executable against the inventory above — no imaginary pages.
2. Vary the flows: happy paths, edge cases (empty fields, max quantities, cancel),
   navigation sequences, and permission-denied scenarios.
3. For EVERY story, also write numbered acceptance criteria (4-10 criteria),
   each starting with "N. ".
4. Output format — STRICT, one story block after another, no prose:

STORY 1
Story: <the user story sentence>
Conditions:
1. <criterion>
2. <criterion>

STORY 2
...

=== EXAMPLE ===
STORY 1
Story: As a registered customer, I want to sign in, add the Sauce Labs Backpack to my cart, and complete checkout so that I can receive my order.
Conditions:
1. Sign in with username standard_user and password secret_sauce
2. Add the Sauce Labs Backpack to the cart
3. Open the shopping cart
4. Verify the backpack appears in the cart with the correct price
5. Proceed to checkout and fill shipping details
6. Finish the order and verify the confirmation message

Generate the {count} stories now."""


def extract_stories(completion: str) -> list[dict[str, str]]:
    """Parse the LLM's STORY n blocks into {story, conditions} dicts.

    Returns only blocks that have a Story line and at least 2 numbered
    conditions — malformed blocks are dropped (and logged).
    """
    stories: list[dict[str, str]] = []
    # Split on STORY <n> markers
    blocks = re.split(r"(?m)^STORY\s+\d+\s*$", completion)
    for block in blocks[1:]:  # first chunk is preamble
        lines = [ln.strip() for ln in block.splitlines() if ln.strip()]
        story_line = next((ln for ln in lines if ln.lower().startswith("story:")), "")
        story = story_line[len("story:") :].strip().strip('"')
        if not story:
            continue
        # Collect numbered conditions ("1. ...")
        cond_idx = next((i for i, ln in enumerate(lines) if ln.lower().startswith("conditions:")), -1)
        cond_lines = [ln for ln in lines[cond_idx + 1 :] if re.match(r"^\d+[.)]\s+", ln)]
        if len(cond_lines) >= 2:
            stories.append(
                {
                    "story": story,
                    "conditions": prepare_conditions_for_generation("\n".join(cond_lines)),
                }
            )
    return stories


def load_eval_sites() -> list[dict[str, str]]:
    """Load site metadata from the eval datasets."""
    sites: list[dict[str, str]] = []
    for f in sorted(EVAL_DATASET_DIR.glob("eval-*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        sites.append(
            {
                "site": d.get("site", f.stem),
                "url": d.get("base_url", ""),
                "inventory": SITE_INVENTORY.get(d.get("site", ""), ""),
            }
        )
    return [s for s in sites if s["inventory"]]


def validate_story(story: dict[str, str]) -> bool:
    """A story is valid if it has a plausible sentence + >=2 numbered conditions."""
    if not story.get("story") or len(story["story"]) < 20:
        return False
    if count_conditions(story.get("conditions", "")) < 2:
        return False
    return True


async def synthesize_stories_for_site(client: LLMClient, site: dict[str, str], count: int) -> list[dict[str, Any]]:
    """Ask the LLM for `count` stories on one site; return validated rows."""
    prompt = STORY_PROMPT.format(site=site["site"], url=site["url"], inventory=site["inventory"], count=count)
    completion = await client.generate(prompt, timeout=600)
    rows: list[dict[str, Any]] = []
    for story in extract_stories(completion):
        if not validate_story(story):
            logger.warning("Dropping malformed story for %s: %.60s", site["site"], story["story"])
            continue
        rows.append(
            {
                "site": site["site"],
                "url": site["url"],
                "story": story["story"],
                "conditions": story["conditions"],
            }
        )
    return rows


async def generate_skeleton_for_row(
    generator: TestGenerator, row: dict[str, Any], parser: SkeletonParser, *, use_graph: bool = False
) -> dict[str, str] | None:
    """Phase-1 skeleton for one story; returns an Alpaca row or None (invalid).

    ``use_graph=False`` → single-call linear pipeline (production default,
    stochastic). ``use_graph=True`` → LangGraph Planner→Generator→Validator
    (deterministic, has its own retry loop — 2-4 LLM calls per story).
    """
    expected_count = count_conditions(row["conditions"])
    try:
        skeleton = await generator.generate_skeleton(
            user_story=row["story"],
            conditions=row["conditions"],
            target_urls=[row["url"]] if row["url"] else None,
            expected_count=expected_count,
            use_graph=use_graph,
        )
    except Exception as exc:  # LLM failure / timeout — skip row
        logger.warning("Skeleton generation failed for %.60s: %s", row["story"], exc)
        return None

    # Same normalisation production applies before validation (the LLM often
    # emits single-brace {GOTO:...} and synonym actions like VERIFY/ADD).
    skeleton = parser.normalise_placeholder_actions(skeleton)

    error = parser.validate_skeleton(skeleton)
    if error:
        logger.warning("Skeleton validation failed for %.60s: %s", row["story"], error)
        return None

    # Criteria-count gate: the skeleton must contain exactly the expected
    # number of test functions.
    fn_names = parser.test_definition_pattern.findall(skeleton)
    if len(fn_names) != expected_count:
        logger.warning(
            "Count mismatch for %.60s: expected %d functions, got %d",
            row["story"],
            expected_count,
            len(fn_names),
        )
        return None

    instruction = (
        "You are a Playwright Python test engineer. Generate a complete pytest "
        f"test file for the following user story against the site '{row['site']}' "
        f"({row['url']}). Use the double-brace placeholder format "
        "{{GOTO:...}}, {{CLICK:...}}, {{FILL:...}}, {{ASSERT:...}} for every "
        "test step. One test function per acceptance criterion.\n\n"
        f"=== USER STORY ===\n{row['story']}\n\n"
        f"=== ACCEPTANCE CRITERIA ===\n{row['conditions']}\n\n"
        "Output ONLY the Python code."
    )
    return {"instruction": instruction, "input": "", "output": skeleton}


async def run(count: int, do_skeletons: bool, merge: bool, mode: str = "linear") -> None:
    sites = load_eval_sites()
    if not sites:
        raise SystemExit("No eval sites with element inventories found.")

    client = LLMClient(provider_name="openai-local")
    generator = TestGenerator(client=client)
    parser = SkeletonParser()

    story_rows: list[dict[str, Any]] = []
    for site in sites:
        print(f"  {site['site']}: synthesizing {count} stories...")
        rows = await synthesize_stories_for_site(client, site, count)
        story_rows.extend(rows)
        print(f"    -> {len(rows)} valid stories")

    stories_path = TRAINING_DIR / "synthetic_stories.jsonl"
    TRAINING_DIR.mkdir(parents=True, exist_ok=True)
    with stories_path.open("w", encoding="utf-8") as fh:
        for r in story_rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\nStories written: {len(story_rows)} -> {stories_path}")

    if not do_skeletons:
        return

    skeleton_path = TRAINING_DIR / "synthetic_skeletons_alpaca.jsonl"
    passing: list[dict[str, str]] = []
    for row in story_rows:
        if mode in ("linear", "both"):
            alpaca = await generate_skeleton_for_row(generator, row, parser, use_graph=False)
            if alpaca:
                passing.append(alpaca)
        if mode in ("graph", "both"):
            alpaca = await generate_skeleton_for_row(generator, row, parser, use_graph=True)
            if alpaca:
                passing.append(alpaca)

    # Dedupe exact duplicate rows (deterministic graph runs may repeat).
    seen: set[str] = set()
    unique: list[dict[str, str]] = []
    for r in passing:
        if r["output"] in seen:
            continue
        seen.add(r["output"])
        unique.append(r)
    passing = unique

    with skeleton_path.open("w", encoding="utf-8") as fh:
        for r in passing:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(
        f"Skeletons passing validation: {len(passing)}/{len(story_rows) * (1 if mode != 'both' else 2)} -> {skeleton_path}"
    )

    if merge and passing:
        # Append into the main Alpaca file (dedupe against existing rows).
        existing: set[str] = set()
        if MAIN_SKELETON_FILE.exists():
            for line in MAIN_SKELETON_FILE.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    existing.add(json.loads(line)["output"])
        added = 0
        with MAIN_SKELETON_FILE.open("a", encoding="utf-8") as fh:
            for r in passing:
                if r["output"] in existing:
                    continue
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
                existing.add(r["output"])
                added += 1
        print(f"Merged {added} new rows into {MAIN_SKELETON_FILE}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=5, help="Stories per site (default 5)")
    parser.add_argument("--skeletons", action="store_true", help="Generate + validate skeletons")
    parser.add_argument("--merge", action="store_true", help="Merge passing rows into main dataset")
    parser.add_argument(
        "--mode",
        choices=["linear", "graph", "both"],
        default="linear",
        help="Skeleton pipeline: linear (stochastic), graph (deterministic), or both (default linear)",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s %(message)s",
    )

    asyncio.run(run(args.count, args.skeletons, args.merge, args.mode))


if __name__ == "__main__":
    main()
