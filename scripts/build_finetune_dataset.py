"""Build an instruction-tuning dataset from the project's generated tests.

Converts the tancat-ai/tancat pipeline's artifacts
(``generated_tests/<pkg>/scrape_manifest.json`` + ``package_manifest.json``)
into an **Alpaca-format JSONL** dataset suitable for direct upload into
Unsloth Studio (or any SFT trainer):

    {"instruction": "<skeleton prompt template>",
     "input":       "<user story + starting URL>",
     "output":      "<skeleton test code with {{PLACEHOLDER}} steps>"}

The output is the Phase-1 *skeleton* the pipeline asks its LLM to produce
(placeholder-based pytest functions). That is the task you want the
fine-tuned model to learn: given a user story, emit Playwright pytest
skeletons with ``{{GOTO:}}`` / ``{{CLICK:}}`` / ``{{FILL:}}`` / ``{{ASSERT:}}``
steps — exactly what ``src/prompt_builder.py`` prompts for.

The script also ingests the eval harness datasets (``scripts/eval/dataset/eval-*.json``)
which are *higher quality* than the generated packages:

* they persist the **numbered acceptance criteria** the pipeline feeds the LLM
  (generated packages drop them),
* they carry **golden resolutions** — ground-truth ``(action, description) →
  expected_locator`` pairs, human-validated — which feed a second dataset:
  placeholder-resolution (Phase 2 of the pipeline, the known weak spot).

Two dataset kinds are produced:

1. ``playwright_skeleton_alpaca.jsonl`` — story (+conditions) → skeleton code.
2. ``playwright_resolution_alpaca.jsonl`` — placeholder → expected locator.

Usage:
    python scripts/build_finetune_dataset.py [--out training_data/playwright_skeleton_alpaca.jsonl]
    python scripts/build_finetune_dataset.py --resolutions [--out training_data/playwright_resolution_alpaca.jsonl]
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
GENERATED_TESTS_DIR = PROJECT_ROOT / "generated_tests"
TRAINING_DIR = PROJECT_ROOT / "training_data"
EVAL_DATASET_DIR = PROJECT_ROOT / "scripts" / "eval" / "dataset"

#: Static prefix reused from the production skeleton prompt (Phase 1).
#: The pipeline's prompt builder interpolates story/conditions/urls at render
#: time; we reproduce the same static structure here so the fine-tuned model
#: sees an instruction that matches what the project sends in production.
SKELETON_INSTRUCTION_PREFIX = """You are a Playwright Python test engineer.

=== INSTRUCTIONS ===
Generate EXACTLY {count} test functions. One per criterion.
Use ONLY the double-brace placeholder format for test steps.
NO PROSE. NO EXPLANATIONS. START WITH IMPORTS.

=== ALLOWED STEP FORMATS ===
{{GOTO:page keyword}}
{{CLICK:button or link description}}
{{FILL:input field description:value to type}}
{{ASSERT:what should be visible or true (element, content, or page state; 'home page loaded' → URL check)}}

=== PLACEHOLDER DESCRIPTION RULES ===
1. Keep descriptions SHORT (2-5 words). Use the element's visible text or label.
2. For CLICK: use the button/link text, e.g. {{CLICK:Login}}, {{CLICK:Dress}}, {{CLICK:Add to cart}}
3. For FILL: use the field label, e.g. {{FILL:username:admin}}, {{FILL:password:secret}}
4. For ASSERT: describe what to see, e.g. {{ASSERT:product list}}, {{ASSERT:cart total}}, {{ASSERT:welcome message}}
5. For GOTO: use a keyword, e.g. {{GOTO:home}}, {{GOTO:cart}}, {{GOTO:checkout}}
6. DO NOT write long descriptions like 'the button that says Add to cart next to the Blue Top product'.
   Instead write: {{CLICK:Add to cart}}
7. DO NOT write vague descriptions like 'some element is visible on the page'.
   Instead write: {{ASSERT:product list}} or {{ASSERT:Cart Summary}}
8. For 'verify <page> loads/opens' conditions, use the page-state form
   {{ASSERT:<page> loaded}} (e.g. {{ASSERT:home page loaded}}) — it resolves to
   a URL assertion (expect(page).to_have_url). Do NOT write {{ASSERT:<page> title}}.
9. For disappearance checks ('popup closed', 'item removed'), describe the
   ABSENCE — they resolve to not-visible assertions (assert_hidden).

=== JOURNEY STRUCTURE (MANDATORY) ===
1. Every step must appear on the page it belongs to. Follow the story order:
   fill ALL fields on the current page BEFORE navigating (Next) to the next page.
2. Never place a step after the navigation that leaves its page.
3. Do NOT emit pytest.skip for steps you cannot place.
4. Use the exact labels from the story for fields and buttons.

=== EXAMPLE OUTPUT ===
import pytest
from playwright.sync_api import Page

@pytest.mark.evidence(condition_ref="TC-01", story_ref="S01")
def test_01_example(page, evidence_tracker):
    {{GOTO:home}}
    {{ASSERT:home page loaded}}
    {{FILL:username:admin}}
    {{CLICK:submit button}}
    {{ASSERT:welcome message}}

=== USER STORY ===
{story}

=== KNOWN URLS ===
{urls}

Generate the {count} test functions now."""


def build_instruction(story: str, urls: str, count: int) -> str:
    """Return the full instruction prompt for one training example."""
    return SKELETON_INSTRUCTION_PREFIX.format(story=story, urls=urls, count=count)


def load_json(path: Path) -> dict[str, Any]:
    """Load a JSON file, returning {} on any parse error."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError, json.JSONDecodeError:
        return {}


def journey_to_function(journey: dict[str, Any]) -> str:
    """Reconstruct one skeleton test function from a scrape-manifest journey."""
    test_name = journey.get("test_name", "test_unnamed")
    steps = journey.get("steps", [])
    lines = [
        f'@pytest.mark.evidence(condition_ref="{test_name.replace("test_", "T").upper()[:12]}", story_ref="S01")',
        f"def {test_name}(page: Page, evidence_tracker):",
    ]
    for step in steps:
        raw = str(step.get("raw_line", "")).rstrip()
        if raw.strip():
            lines.append(raw if raw.startswith("    ") else f"    {raw.strip()}")
    if len(steps) == 0:
        lines.append("    pass")
    return "\n".join(lines) + "\n"


def build_skeleton_output(journeys: list[dict[str, Any]]) -> str:
    """Assemble the full skeleton file body (imports + all journey functions)."""
    header = "import pytest\nfrom playwright.sync_api import Page\n\n"
    body = "\n".join(journey_to_function(j) for j in journeys)
    return header + body


def collect_packages() -> list[dict[str, Any]]:
    """Scan generated_tests/ for packages with a scrape manifest and story."""
    packages: list[dict[str, Any]] = []
    for manifest_path in sorted(GENERATED_TESTS_DIR.glob("*/package_manifest.json")):
        pkg_dir = manifest_path.parent
        manifest = load_json(manifest_path)
        story = manifest.get("source_story", "").strip()
        if not story:
            continue
        scrape = load_json(pkg_dir / "scrape_manifest.json")
        journeys = scrape.get("journeys", [])
        if not journeys:
            continue
        packages.append(
            {
                "package": pkg_dir.name,
                "story": story,
                "starting_url": manifest.get("starting_url", ""),
                "additional_urls": manifest.get("additional_urls", []),
                "journeys": [j for j in journeys if j.get("steps")],
                "provider": manifest.get("provider", ""),
                "model": manifest.get("model", ""),
            }
        )
    return packages


def build_alpaca_examples(packages: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Convert packages into Alpaca-format rows (instruction/input/output)."""
    examples: list[dict[str, str]] = []
    for pkg in packages:
        urls = ", ".join([pkg["starting_url"], *pkg["additional_urls"]]) or "home"
        count = len(pkg["journeys"])
        # input = the user story (what the operator types into the pipeline);
        # the instruction already embeds story+urls like production does, so
        # keep `input` empty to avoid duplication — Unsloth treats empty
        # `input` as "no extra context".
        instruction = build_instruction(pkg["story"], urls, count)
        output = build_skeleton_output(pkg["journeys"])
        examples.append(
            {
                "instruction": instruction,
                "input": "",
                "output": output,
            }
        )
    return examples


def dedupe(examples: list[dict[str, str]]) -> list[dict[str, str]]:
    """Drop exact duplicate (instruction, output) pairs."""
    seen: set[tuple[str, str]] = set()
    out: list[dict[str, str]] = []
    for ex in examples:
        key = (ex["instruction"], ex["output"])
        if key in seen:
            continue
        seen.add(key)
        out.append(ex)
    return out


#: Sites that genuinely have a login flow — used by the hallucinated-login
#: filter to keep auth steps only where they belong.
_LOGIN_SITES: set[str] = {"saucedemo", "automationexercise", "theinternet", "banking_mock"}
_LOGIN_MARKERS: tuple[str, ...] = (
    "standard_user",
    "secret_sauce",
    "{{FILL:username",
    "{{FILL:password",
    "{{CLICK:Login",
)


def _row_site(row: dict[str, str]) -> str:
    """Extract the site name from a row's instruction, or "" if unknown."""
    for marker in ("site '", 'site "'):
        if marker in row.get("instruction", ""):
            after = row["instruction"].split(marker, 1)[1]
            return after.split("'")[0] if marker.endswith("'") else after.split('"')[0]
    return ""


def is_hallucinated_login_row(row: dict[str, str]) -> bool:
    """True when a row contains login steps on a site that has no login page.

    The LLM frequently invents `standard_user`/`secret_sauce` login steps for
    guest-flow sites (ecommerce, lv_insurance, demoqa). Those rows can never
    resolve — they poison the training set with impossible steps.
    """
    site = _row_site(row)
    if site in _LOGIN_SITES:
        return False  # auth belongs here
    text = row.get("output", "")
    return any(marker in text for marker in _LOGIN_MARKERS)


def filter_file(path: Path, *, drop_hallucinated_login: bool, in_place: bool = False) -> tuple[int, int]:
    """Filter a JSONL dataset; returns (original, kept)."""
    if not path.exists():
        return 0, 0
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    kept = [r for r in rows if not (drop_hallucinated_login and is_hallucinated_login_row(r))]
    if in_place and len(kept) != len(rows):
        write_jsonl(kept, path)
    return len(rows), len(kept)


def write_jsonl(examples: list[dict[str, str]], out_path: Path) -> None:
    """Write examples to a JSONL file (one JSON object per line)."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as fh:
        for ex in examples:
            fh.write(json.dumps(ex, ensure_ascii=False) + "\n")


def collect_eval_datasets() -> list[dict[str, Any]]:
    """Load the eval harness dataset JSONs (story + conditions + golden keys)."""
    datasets: list[dict[str, Any]] = []
    for f in sorted(EVAL_DATASET_DIR.glob("eval-*.json")):
        d = load_json(f)
        if d.get("user_story") and d.get("conditions"):
            datasets.append(d)
    return datasets


def condition_label(idx: int, total: int) -> str:
    """Map a criterion index to the TC-xx label the pipeline uses."""
    return f"TC-{idx + 1:02d}" if total <= 99 else f"TC-{idx + 1:03d}"


def golden_to_skeleton(golden_resolutions: list[dict[str, Any]], conditions: list[str]) -> str:
    """Reconstruct a skeleton test file from golden resolutions.

    Each golden resolution block holds the placeholders for one criterion;
    each placeholder maps action+description to the expected locator. We emit
    the placeholder-only skeleton (what Phase 1 asks the LLM to produce).
    """
    lines = ["import pytest", "from playwright.sync_api import Page", ""]
    for i, block in enumerate(golden_resolutions):
        cond_text = conditions[i] if i < len(conditions) else f"criterion {i + 1}"
        # Strip leading numbering like "1. " or "1) " before slugifying
        cond_slug = re.sub(r"^\d+[.)]\s*", "", cond_text).lower()
        fn = f"test_{i + 1:02d}_" + re.sub(r"[^a-z0-9]+", "_", cond_slug).strip("_")[:60]
        lines.append(
            f'@pytest.mark.evidence(condition_ref="{condition_label(i, len(golden_resolutions))}", story_ref="S01")'
        )
        lines.append(f"def {fn}(page: Page, evidence_tracker):")
        for p in block.get("placeholders", []):
            action = p.get("action", "CLICK")
            desc = p.get("description", "")
            lines.append(f"    {{{{ACTION:{desc}}}}}".replace("ACTION", action))
        lines.append("")
    return "\n".join(lines)


def build_eval_skeleton_examples(datasets: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Story + conditions → skeleton code, from the eval datasets."""
    examples: list[dict[str, str]] = []
    for d in datasets:
        conditions_text = "\n".join(d["conditions"])
        count = len(d["conditions"])
        urls = d.get("base_url", "")
        instruction = (
            SKELETON_INSTRUCTION_PREFIX.format(story=d["user_story"], urls=urls, count=count)
            + f"\n\n=== ACCEPTANCE CRITERIA ===\n{conditions_text}"
        )
        output = golden_to_skeleton(d.get("golden_resolutions", []), d["conditions"])
        examples.append({"instruction": instruction, "input": "", "output": output})
    return examples


def build_resolution_examples(datasets: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Placeholder → expected locator pairs (Phase 2 ground truth).

    This targets the pipeline's known weak spot: resolving a placeholder like
    ``{{CLICK:login button}}`` to a concrete locator (e.g. ``#login-button``).
    """
    examples: list[dict[str, str]] = []
    for d in datasets:
        site = d.get("site", "")
        base_url = d.get("base_url", "")
        for block in d.get("golden_resolutions", []):
            for p in block.get("placeholders", []):
                action = p.get("action", "")
                desc = p.get("description", "")
                locator = p.get("expected_locator", "")
                if not (action and desc and locator):
                    continue
                instruction = (
                    "You are a Playwright Python test engineer resolving a test step "
                    f"placeholder on the site '{site}' ({base_url}).\n\n"
                    "Resolve the placeholder to a single concrete Playwright locator "
                    "(CSS selector preferred, else attribute-based). Output ONLY the locator string."
                )
                examples.append(
                    {
                        "instruction": instruction,
                        "input": f"Action: {action}\nElement description: {desc}",
                        "output": locator,
                    }
                )
    return examples


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        default=str(PROJECT_ROOT / "training_data" / "playwright_skeleton_alpaca.jsonl"),
        help="Output JSONL path",
    )
    parser.add_argument(
        "--resolutions",
        action="store_true",
        help="Build the placeholder-resolution dataset instead (Phase 2 ground truth)",
    )
    parser.add_argument("--no-eval", action="store_true", help="Skip eval datasets (generated_tests only)")
    parser.add_argument("--stats", action="store_true", help="Print dataset statistics")
    parser.add_argument(
        "--clean",
        action="store_true",
        help="Filter existing training JSONL files in-place: drop hallucinated-login "
        "rows (login steps on sites with no auth, e.g. standard_user on ecommerce). "
        "Safe to run anytime; prints a before/after summary.",
    )
    args = parser.parse_args()

    if args.clean:
        for fname in (
            "playwright_skeleton_alpaca.jsonl",
            "playwright_resolved_alpaca.jsonl",
            "synthetic_skeletons_alpaca.jsonl",
        ):
            before, after = filter_file(TRAINING_DIR / fname, drop_hallucinated_login=True, in_place=True)
            if before:
                print(f"{fname}: {before} -> {after} (dropped {before - after} hallucinated-login rows)")
        return

    if args.resolutions and args.out == str(PROJECT_ROOT / "training_data" / "playwright_skeleton_alpaca.jsonl"):
        args.out = str(PROJECT_ROOT / "training_data" / "playwright_resolution_alpaca.jsonl")

    datasets = collect_eval_datasets()

    if args.resolutions:
        examples = dedupe(build_resolution_examples(datasets))
        out_path = Path(args.out)
        write_jsonl(examples, out_path)
        print(f"Resolution pairs   : {len(examples)}")
        print(f"Output             : {out_path}")
        if args.stats:
            outs = [len(ex["output"]) for ex in examples]
            print(f"Output chars      : min={min(outs)} median={int(statistics.median(outs))} max={max(outs)}")
        return

    packages = collect_packages()
    examples = dedupe(build_alpaca_examples(packages))

    if not args.no_eval:
        eval_examples = dedupe(build_eval_skeleton_examples(datasets))
        print(f"Eval datasets       : {len(datasets)} (story+conditions -> skeleton)")
        print(f"  eval examples     : {len(eval_examples)}")
        examples.extend(eval_examples)

    examples = dedupe(examples)
    out_path = Path(args.out)
    write_jsonl(examples, out_path)

    print(f"Packages scanned   : {len(packages)}")
    print(f"Examples written   : {len(examples)}")
    print(f"Output             : {out_path}")

    if args.stats:
        outs = [len(ex["output"]) for ex in examples]
        ins = [len(ex["instruction"]) for ex in examples]
        if outs:
            print(f"Output chars     : min={min(outs)} median={int(statistics.median(outs))} max={max(outs)}")
            print(f"Instruction chars: min={min(ins)} median={int(statistics.median(ins))} max={max(ins)}")
        print(
            f"Total tokens     : ~{sum(len(ex['instruction'] + ex['output']) for ex in examples) // 4:,} (chars/4 estimate)"
        )


if __name__ == "__main__":
    main()
