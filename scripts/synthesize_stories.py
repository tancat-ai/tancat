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

    Stage 4 — Resolve & Learn (optional, --resolve-and-learn)
        For each skeleton, run the production Phase-2 resolver
        (``Orchestrator.run_pipeline(prebuilt_skeleton=...)``) which scrapes
        the site and resolves placeholders to real locators, then execute the
        resolved test against the live site. Passing steps are automatically
        written into the RAG store as verified ``LearnedPattern`` entries
        (via ``generated_tests/conftest.py``'s ``learn_from_evidence`` hook)
        — growing retrieval memory for future runs, exactly like a real
        pipeline run. Run with ``RAG_ENABLED=0`` for cold-start (no golden
        pattern bonus) resolutions — the resolver's known weak spot.

Outputs (Alpaca format, ready for Unsloth Studio):
    training_data/synthetic_stories.jsonl            (story + conditions)
    training_data/synthetic_skeletons_alpaca.jsonl   (instruction/input/output)
    training_data/resolved_tests/<site>/test_*.py    (resolved, executable tests)

Usage:
    python scripts/synthesize_stories.py --count 10                  # stories only
    python scripts/synthesize_stories.py --count 10 --skeletons      # + skeleton gen (linear)
    python scripts/synthesize_stories.py --count 10 --skeletons --mode both
        # linear + LangGraph skeletons per story (graph is deterministic —
        # run once; linear is stochastic — rerun for diversity)
    python scripts/synthesize_stories.py --count 10 --skeletons --merge
        # --merge appends passing rows into training_data/playwright_skeleton_alpaca.jsonl
    python scripts/synthesize_stories.py --count 5 --resolve-and-learn --mode both
        # resolve skeletons against live sites, execute, and learn passing
        # steps into the RAG store. RAG_ENABLED=0 disables golden-pattern
        # retrieval for cold-start resolution data.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import subprocess
import sys
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

#: Sites with a login/authentication flow. The story synthesizer uses this to
#: reject stories that invent login steps for sites without auth (ecommerce,
#: lv_insurance, demoqa have no login page — a `standard_user` login step there
#: can never resolve and produces poisoned training rows).
HAS_LOGIN: dict[str, bool] = {
    "saucedemo": True,
    "automationexercise": True,
    "demoqa": False,
    "theinternet": True,
    "lv_insurance": False,
    "ecommerce_mock": False,
    "banking_mock": True,
}


STORY_PROMPT = """You are a QA scenario writer for automated web testing.

Write {count} DISTINCT, realistic user stories for the website "{site}" at {url}.

Each story must be a single sentence in the form:
"As a <role>, I want to <action>, <more actions> so that <benefit>."

The stories must ONLY exercise elements that exist on this site:

=== SITE ELEMENT INVENTORY ===
{inventory}

=== AUTHENTICATION RULE (STRICT) ===
This site has login: {has_login}.
{auth_rule}

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
    has_login = HAS_LOGIN.get(site["site"], False)
    auth_rule = (
        "ONLY include sign-in/login steps in a story when this site HAS a login page "
        "AND the inventory above lists login/username/password elements."
        if has_login
        else "NEVER write stories or criteria that require signing in, a username, a password, "
        "or a login page — this site has no authentication. Checkout/shopping flows are guest flows."
    )
    prompt = STORY_PROMPT.format(
        site=site["site"],
        url=site["url"],
        inventory=site["inventory"],
        count=count,
        has_login=has_login,
        auth_rule=auth_rule,
    )
    completion = await client.generate(prompt, timeout=600)
    rows: list[dict[str, Any]] = []
    for story in extract_stories(completion):
        if not validate_story(story):
            logger.warning("Dropping malformed story for %s: %.60s", site["site"], story["story"])
            continue
        # Auth guard: a story on a login-less site must not invent login steps.
        if not has_login and _story_mentions_login(story):
            logger.warning(
                "Dropping story that invents login on login-less site %s: %.60s",
                site["site"],
                story["story"],
            )
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


def _story_mentions_login(story: dict[str, str]) -> bool:
    """True when a story or its conditions reference authentication."""
    text = (story.get("story", "") + " " + story.get("conditions", "")).lower()
    return any(
        term in text
        for term in (
            "log in",
            "login",
            "sign in",
            "sign-in",
            "signin",
            "username",
            "password",
            "credentials",
            "authenticate",
        )
    )


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


async def resolve_and_learn(
    story_rows: list[dict[str, Any]],
    *,
    rag_modes: list[bool] | None = None,
    max_sites: int = 0,
    skeleton_rows: list[dict[str, str]] | None = None,
) -> None:
    """Stage 4 — resolve skeletons against live sites, execute, and learn.

    For each (story, conditions) row this:

    1. Runs the production Phase-2 resolver via
       ``Orchestrator.run_pipeline(prebuilt_skeleton=...)`` — this scrapes the
       site, resolves ``{{PLACEHOLDER}}`` steps to real locators, and returns
       executable test code.
    2. Writes the resolved test into ``generated_tests/resolved/<site>/`` and
       executes it with pytest against the live site.
    3. Passing steps are written into the RAG store automatically by the
       ``generated_tests/conftest.py`` ``learn_from_evidence`` hook — the same
       learning path production runs use.

    ``rag_modes`` controls how many resolution passes to run per story:
    ``[True]`` = RAG-assisted only, ``[False]`` = cold-start only (no golden
    pattern bonus — the resolver's known weak spot), ``[True, False]`` = both
    (2 resolved outputs per story → 2× resolution fine-tuning data).

    ``skeleton_rows`` optionally supplies pre-generated skeletons (Alpaca
    rows from Stage 2). When provided, each story uses the matching skeleton
    instead of regenerating one (1 skeleton per story; use ``--mode both``
    at Stage 2 and pass all rows here to also cycle linear/graph variants).
    """
    from src.orchestrator import TestOrchestrator

    if rag_modes is None:
        rag_modes = [True]

    # Auto-start the mock HTTP server (port 8781) if any story targets a
    # localhost mock site. Each mock site is served with its own directory
    # as root, matching the eval datasets' ``mock_dir`` contract: eval-006
    # (ecommerce) serves ``mock_sites/ecommerce``, eval-007 (banking) serves
    # ``mock_sites/banking``, eval-005 (lv_insurance) serves the repo root
    # (its URL includes ``generated_tests/mock_insurance_site.html``).
    mock_dirs: dict[str, Path] = {
        "banking_mock": PROJECT_ROOT / "mock_sites" / "banking",
        "ecommerce_mock": PROJECT_ROOT / "mock_sites" / "ecommerce",
    }
    mock_needed = [s for s in story_rows if "localhost:8781" in (s.get("url") or "")]
    if mock_needed:
        from scripts.mock_server import MockServer

        sites_used = {s["site"] for s in mock_needed}
        dirs = {mock_dirs[s] for s in sites_used if s in mock_dirs}
        if "lv_insurance" in sites_used or not dirs:
            dirs.add(PROJECT_ROOT)  # lv_insurance serves repo root
        # One server per distinct directory — mock sites share port 8781, so
        # serve them on different ports; update the story URLs accordingly.
        port = 8781
        for d in sorted(dirs):
            MockServer.start(port=port, directory=str(d))
            print(f"[resolve-learn] mock server on :{port} (dir={d.name})")
            port += 1

        # Rewrite story URLs: banking/ecommerce stories point at
        # ``localhost:8781/index.html`` but their server may be on another
        # port. Rebase every mock story URL onto the assigned port.
        for row in story_rows:
            if "localhost:8781" in (row.get("url") or ""):
                site = row["site"]
                base = (
                    "8781"
                    if site in ("lv_insurance",) or site not in mock_dirs
                    else str(8781 + sorted(dirs).index(mock_dirs[site]))
                )
                row["url"] = row["url"].replace("localhost:8781", f"localhost:{base}")

    out_root = PROJECT_ROOT / "generated_tests" / "resolved"
    out_root.mkdir(parents=True, exist_ok=True)

    # Map stories to pre-generated skeletons (Alpaca rows carry the story in
    # their instruction). When absent, fall back to regenerating one.
    skeletons_by_story: dict[str, list[str]] = {}
    if skeleton_rows:
        for sr in skeleton_rows:
            inst = sr.get("instruction", "")
            # Match by the story snippet embedded in the instruction.
            for row in story_rows:
                story_head = row["story"][:40]
                if story_head in inst:
                    skeletons_by_story.setdefault(row["story"], []).append(sr["output"])
                    break

    sites = sorted({row["site"] for row in story_rows})
    if max_sites:
        sites = sites[:max_sites]

    summary: dict[str, Any] = {"site": {}, "passed": 0, "failed": 0}
    resolved_rows: list[dict[str, str]] = []  # fine-tuning rows (story → resolved code)
    for site in sites:
        site_rows = [r for r in story_rows if r["site"] == site]
        site_dir = out_root / site
        site_dir.mkdir(parents=True, exist_ok=True)
        print(f"\n[resolve-learn] {site}: {len(site_rows)} stories")

        for i, row in enumerate(site_rows, 1):
            story = row["story"]
            conditions = row["conditions"]
            url = row.get("url", "")
            print(f"  [{i}/{len(site_rows)}] {story[:60]}...")

            # Skeleton candidates: pre-generated (linear/graph variants) or fresh.
            candidates = skeletons_by_story.get(story)
            if not candidates:
                orchestrator0 = TestOrchestrator(test_generator=TestGenerator())
                try:
                    candidates = [await _skeleton_for_story(orchestrator0, story, conditions, url)]
                except Exception as exc:
                    print(f"    !! skeleton failed: {exc}")
                    summary["failed"] += 1
                    continue

            for rag_on in rag_modes:
                for skel_idx, skeleton in enumerate(candidates):
                    tag = f"rag{'on' if rag_on else 'off'}_sk{skel_idx + 1}"
                    # Set/clear RAG for this pass.
                    if rag_on:
                        os.environ.pop("RAG_ENABLED", None)
                    else:
                        os.environ["RAG_ENABLED"] = "0"

                    orchestrator = TestOrchestrator(test_generator=TestGenerator())
                    try:
                        final_code = await orchestrator.run_pipeline(
                            user_story=story,
                            conditions=conditions,
                            target_urls=[url] if url else None,
                            prebuilt_skeleton=skeleton,
                        )
                    except Exception as exc:
                        print(f"    !! [{tag}] pipeline failed: {exc}")
                        summary["failed"] += 1
                        continue

                    test_file = site_dir / f"test_{i:02d}_{tag}_{_slug(story)}.py"
                    test_file.write_text(final_code, encoding="utf-8")

                    result = _run_pytest(test_file)
                    summary["site"].setdefault(site, {"passed": 0, "failed": 0})
                    if result:
                        summary["passed"] += 1
                        summary["site"][site]["passed"] += 1
                    else:
                        summary["failed"] += 1
                        summary["site"][site]["failed"] += 1

                    # Capture resolved code as a fine-tuning row regardless of
                    # pass/fail — the resolution itself is the training signal.
                    resolved_rows.append(
                        {
                            "instruction": (
                                "You are a Playwright Python test engineer. Convert the following "
                                f"placeholder skeleton into a complete resolved pytest test file for the site "
                                f"'{site}' ({url}). Replace every {{GOTO:...}}/{{CLICK:...}}/{{FILL:...}}/"
                                "{{ASSERT:...}} placeholder with a concrete Playwright locator and "
                                "evidence_tracker call. Keep one test function per criterion.\n\n"
                                f"=== USER STORY ===\n{story}\n\n"
                                f"=== ACCEPTANCE CRITERIA ===\n{conditions}\n\n"
                                "Output ONLY the Python code."
                            ),
                            "input": "",
                            "output": final_code,
                        }
                    )

    # Persist resolved fine-tuning rows — APPEND so multiple resolve_and_learn
    # calls (e.g. mocks phase + live phase) accumulate in one file instead of
    # the later call clobbering the earlier one.
    resolved_path = TRAINING_DIR / "playwright_resolved_alpaca.jsonl"
    existing: set[str] = set()
    if resolved_path.exists():
        for line in resolved_path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                existing.add(json.loads(line)["output"])
    added = 0
    with resolved_path.open("a", encoding="utf-8") as fh:
        for r in resolved_rows:
            if r["output"] in existing:
                continue
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
            existing.add(r["output"])
            added += 1
    print(f"\nResolved-code fine-tuning rows: {added} added (file now has {len(existing)}) -> {resolved_path}")

    print("\n=== resolve-and-learn summary ===")
    for site, counts in summary["site"].items():
        print(f"  {site}: {counts['passed']} passed, {counts['failed']} failed")
    print(f"  TOTAL: {summary['passed']} passed, {summary['failed']} failed")
    print(f"  Output: {out_root}")


async def _skeleton_for_story(orchestrator: Any, story: str, conditions: str, url: str) -> str:
    """Generate a skeleton via the orchestrator's test generator (offline)."""
    count = count_conditions(conditions)
    skeleton = await orchestrator.test_generator.generate_skeleton(
        user_story=story,
        conditions=conditions,
        target_urls=[url] if url else None,
        expected_count=count,
    )
    return orchestrator.parser.normalise_placeholder_actions(skeleton)


def _slug(text: str, maxlen: int = 40) -> str:
    """Filesystem-safe slug from a story sentence."""
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:maxlen]
    return slug or "story"


def _run_pytest(test_file: Path) -> bool:
    """Execute a resolved test file against the live site.

    The file lives under ``generated_tests/resolved/<site>/`` so pytest picks
    up ``generated_tests/conftest.py`` — which carries the
    ``learn_from_evidence`` RAG hook — via rootdir discovery. Passing steps
    are written into the RAG store automatically, exactly like a production
    run.
    """
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        str(test_file),
        "-o",
        "addopts=",
        "-o",
        f"pythonpath={PROJECT_ROOT}",
        "--browser=chromium",
        "--screenshot=only-on-failure",
        "--timeout=120",
        "-q",
        "--tb=line",
        "--no-header",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=300, cwd=str(PROJECT_ROOT))
    except subprocess.TimeoutExpired:
        print("    !! test timeout")
        return False
    if proc.returncode == 0:
        return True
    # Show a compact failure summary (last few lines of pytest output)
    tail = (proc.stdout or "").strip().splitlines()[-3:]
    for line in tail:
        print(f"    !! {line}")
    return False


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
    parser.add_argument(
        "--resolve-and-learn",
        action="store_true",
        help="Stage 4: resolve skeletons against live sites, execute, and learn passing steps into the RAG store.",
    )
    parser.add_argument(
        "--rag-both",
        action="store_true",
        help="With --resolve-and-learn: run BOTH RAG-assisted and cold-start "
        "(RAG_ENABLED=0) resolution passes per story (2x resolution data)",
    )
    parser.add_argument(
        "--max-sites",
        type=int,
        default=0,
        help="Limit Stage 4 to the first N sites (default: all)",
    )
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s %(message)s",
    )

    asyncio.run(run(args.count, args.skeletons, args.merge, args.mode))

    if args.resolve_and_learn:
        rag_modes = [True, False] if args.rag_both else [True]
        print(
            f"\nStage 4 (resolve-and-learn): RAG passes = "
            f"{'RAG-on + cold-start (RAG off)' if args.rag_both else 'RAG-on only'}"
        )
        stories = [
            json.loads(line)
            for line in (TRAINING_DIR / "synthetic_stories.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        # Reuse skeletons from the skeleton stage when present (linear+graph).
        sk_path = TRAINING_DIR / "synthetic_skeletons_alpaca.jsonl"
        skeleton_rows: list[dict[str, str]] = []
        if sk_path.exists():
            skeleton_rows = [
                json.loads(line) for line in sk_path.read_text(encoding="utf-8").splitlines() if line.strip()
            ]
            print(f"Reusing {len(skeleton_rows)} pre-generated skeletons")
        asyncio.run(
            resolve_and_learn(
                stories,
                rag_modes=rag_modes,
                max_sites=args.max_sites,
                skeleton_rows=skeleton_rows or None,
            )
        )


if __name__ == "__main__":
    main()
