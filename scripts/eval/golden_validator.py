"""golden_validator.py — Validate generated code against golden answer keys.

Parses Python test code to extract locators used in evidence_tracker.* calls,
then compares each against the expected locators from golden JSON files.

Pure logic — no browser, no LLM, no I/O beyond reading the provided strings.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from eval_metrics import ResolutionResult, StoryResult

# ---------------------------------------------------------------------------
# Code parsing
# ---------------------------------------------------------------------------

_METHODS = "|".join(
    [
        "navigate",
        "fill",
        "click",
        "assert_visible",
        "assert_text",
        "assert_text_contains",
        "assert_value",
        "assert_checked",
        "assert_disabled",
        "assert_enabled",
        "assert_count",
        "assert_empty",
    ]
)

# Captures: group(1)=method, group(2)=locator
# Handles both single and double quoted arguments
_EVIDENCE_CALL_RE = re.compile(
    r"evidence_tracker\.(" + _METHODS + r")"
    r"\s*\(\s*"
    r"""(['"])(.*?)\2""",
)

_SKIP_RE = re.compile(
    r"""pytest\.skip\s*\(\s*['"]Skipping: unresolved placeholders for:\s*['"]([^'"]*?)['"]""",
)

_TEST_FUNC_RE = re.compile(r"^def\s+test_\d+_\w+", re.MULTILINE)


def _action_from_method(method: str) -> str:
    """Map evidence_tracker method name to placeholder action."""
    if method == "navigate":
        return "GOTO"
    if method == "fill":
        return "FILL"
    if method == "click":
        return "CLICK"
    return "ASSERT"


def extract_locators_from_code(code: str) -> list[dict[str, str]]:
    """Extract all evidence_tracker calls with their locators from generated code.

    Returns a list of dicts:
        [{"method": "fill", "action": "FILL", "locator": "#user-name"}, ...]
    """
    results: list[dict[str, str]] = []
    for match in _EVIDENCE_CALL_RE.finditer(code):
        method = match.group(1)
        locator = match.group(3)
        if method == "navigate":
            continue
        results.append(
            {
                "method": method,
                "action": _action_from_method(method),
                "locator": locator,
            }
        )
    return results


def extract_skipped_descriptions(code: str) -> list[str]:
    """Extract descriptions from pytest.skip() calls."""
    return _SKIP_RE.findall(code)


def extract_test_function_count(code: str) -> int:
    """Count test functions (def test_XX_...) in generated code."""
    return len(_TEST_FUNC_RE.findall(code))


# ---------------------------------------------------------------------------
# Golden key loading
# ---------------------------------------------------------------------------


def load_golden_key(path: Path) -> dict[str, Any]:
    """Load and validate a golden key JSON file."""
    data = json.loads(path.read_text(encoding="utf-8"))
    required_keys = {"id", "site", "base_url", "conditions", "golden_resolutions"}
    missing = required_keys - set(data.keys())
    if missing:
        raise ValueError(f"Golden key {path.name} missing keys: {missing}")
    return data


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _build_golden_lookup(golden: dict[str, Any]) -> list[dict[str, Any]]:
    """Flatten golden_resolutions into a flat list of placeholder dicts."""
    flat: list[dict[str, Any]] = []
    for crit in golden.get("golden_resolutions", []):
        for ph in crit.get("placeholders", []):
            flat.append(
                {
                    "criterion_index": crit.get("criterion_index", 0),
                    "action": ph["action"],
                    "description": ph["description"],
                    "expected_locator": ph["expected_locator"],
                    "tolerance_selectors": ph.get("tolerance_selectors", []),
                    "expected_page": ph.get("expected_page", ""),
                }
            )
    return flat


def _match_generated_to_golden(
    generated_locators: list[dict[str, str]],
    golden_placeholders: list[dict[str, Any]],
) -> list[ResolutionResult]:
    """Match each golden placeholder against generated locators.

    Strategy: for each golden placeholder, search generated locators for a
    matching action.  Prefer exact locator matches over non-matches.
    """
    results: list[ResolutionResult] = []
    used_indices: set[int] = set()

    for gp in golden_placeholders:
        best: ResolutionResult | None = None

        for i, gl in enumerate(generated_locators):
            if i in used_indices:
                continue
            if gl["action"] != gp["action"]:
                continue

            locator = gl["locator"]
            expected = gp["expected_locator"]
            tolerances = gp.get("tolerance_selectors", [])

            matched = locator == expected or locator in tolerances

            candidate = ResolutionResult(
                action=gp["action"],
                description=gp["description"],
                expected_locator=expected,
                tolerance_selectors=tolerances,
                generated_locator=locator,
                matched=matched,
            )

            if candidate.matched and (best is None or not best.matched):
                best = candidate
                used_indices.add(i)
                break
            elif best is None or not best.matched:
                best = candidate

        if best is None:
            results.append(
                ResolutionResult(
                    action=gp["action"],
                    description=gp["description"],
                    expected_locator=gp["expected_locator"],
                    tolerance_selectors=gp.get("tolerance_selectors", []),
                    generated_locator=None,
                    matched=False,
                )
            )
        else:
            results.append(best)

    return results


def validate_story(
    code: str,
    golden: dict[str, Any],
    generation_duration_s: float = 0.0,
) -> StoryResult:
    """Validate a single story's generated code against its golden key.

    Returns a StoryResult with all resolution outcomes.
    """
    generated = extract_locators_from_code(code)
    golden_ph = _build_golden_lookup(golden)
    test_count = extract_test_function_count(code)

    total_criteria = len(golden.get("conditions", []))
    criteria_with_skeletons = test_count

    resolutions = _match_generated_to_golden(generated, golden_ph)

    return StoryResult(
        story_id=golden["id"],
        site=golden["site"],
        total_criteria=total_criteria,
        criteria_with_skeletons=criteria_with_skeletons,
        resolutions=resolutions,
        generation_duration_s=generation_duration_s,
    )


def validate_dataset(
    dataset_dir: Path,
    code_map: dict[str, str],
    durations: dict[str, float] | None = None,
) -> list[StoryResult]:
    """Validate all stories in a dataset directory against captured code.

    Args:
        dataset_dir: Path to scripts/eval/dataset/
        code_map: dict mapping story_id (e.g. 'eval-001') to generated code string
        durations: optional dict mapping story_id to generation duration in seconds

    Returns:
        List of StoryResult, one per story.
    """
    results: list[StoryResult] = []
    durations = durations or {}

    for golden_file in sorted(dataset_dir.glob("*.json")):
        golden = load_golden_key(golden_file)
        story_id = golden["id"]
        code = code_map.get(story_id)
        if code is None:
            results.append(
                StoryResult(
                    story_id=story_id,
                    site=golden["site"],
                    total_criteria=len(golden.get("conditions", [])),
                    criteria_with_skeletons=0,
                )
            )
            continue

        results.append(
            validate_story(
                code=code,
                golden=golden,
                generation_duration_s=durations.get(story_id, 0.0),
            )
        )

    return results
