"""Step / expected-result ALIGNMENT metric (B-101 scout t-0316).

Does the product's emitted assertion match the *openness* of the step the
criterion describes? Two mismatch classes:

- **OPEN + DIRECT** - the step leaves the choice open ("add at least one
  item (e.g. Sauce Labs Backpack)") but the emitted check pins one
  instance (``.add-to-cart#remove-sauce-labs-backpack``). A correct test
  that made a *different* valid choice fails. This is the false-negative
  trap.
- **FIXED + PROPERTY** - the step names a specific target but the emitted
  check is a loose property (a page-wide wrapper, a generic class) that
  would pass for something else. This is the false-positive risk.

This is a **report/warn figure, not a pass/fail gate**. It is computed from
the run's own data (the dataset conditions and the emitted code), it needs
no browser and no model, and the owner accepts that free text is
input-dependent - so it reports a *rate*, not a verdict.

Classification
--------------
Criterion class (OPEN vs FIXED) is read from the criterion wording:
``OPEN`` when it carries an openness cue ("at least one", "an item",
"a product", "a radio option", "e.g.", "any", "one of", "some"); otherwise
``FIXED``.

Assertion class (PROPERTY vs DIRECT) is read from the emitted check:
``PROPERTY`` when the emitted method is one of the property emitters (the
``count_assertion_from_description`` / ``page_fact_from_description`` path,
e.g. ``assert_count_at_least``, ``assert_no_broken_images``), or the locator
is a loose/generic form (a bare class ``.x``, a bare id without instance
tokens, a type-only selector). ``DIRECT`` when the method pins one target
(a URL assertion, or a single-element check whose locator names a concrete
instance id/attribute).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Assertion methods that are property emitters (the code_postprocessor /
# evidence_tracker "count / page-fact / section" path). A property emitter
# checks a property of a set, not one named instance.
PROPERTY_METHODS: frozenset[str] = frozenset(
    {
        "assert_count",
        "assert_count_at_least",
        "assert_empty",
        "assert_contains",
        "assert_no_forbidden",
        "assert_no_broken_images",
        "assert_anchor_targets_exist",
        "assert_section_has_price",
        "assert_no_horizontal_scroll",
        "assert_text_contains",
    }
)

# Single-element methods that pin one target unless the locator is loose.
SINGLE_ELEMENT_METHODS: frozenset[str] = frozenset(
    {
        "assert_visible",
        "assert_hidden",
        "assert_text",
        "assert_value",
        "assert_checked",
        "assert_disabled",
        "assert_enabled",
        "assert_attribute",
        "assert_natural_width",
    }
)

# A URL assertion pins one specific page -> DIRECT.
URL_METHOD = "to_have_url"

# Openness cues in the criterion wording.
_OPEN_CUES: tuple[str, ...] = (
    r"e\.g\.",
    r"for example",
    r"\bat least one\b",
    r"\bat least 1\b",
    r"\ban? (?:item|product|radio|option|account|row|entry)s?\b",
    r"\bany\b",
    r"\bone of\b",
    r"\bsome\b",
)

_OPEN_RE = re.compile("|".join(_OPEN_CUES), re.IGNORECASE)

# A bare id / class locator with no instance-like token ("content", "text")
# is loose. An instance id carries a hyphen or a digit or a specific value.
_INSTANCEISH_RE = re.compile(r"[A-Za-z]+[-_][A-Za-z0-9]|[-_]\d|\d", re.ASCII)
_BARE_CLASS_RE = re.compile(r"^\.[A-Za-z][\w-]*$")
_BARE_ID_RE = re.compile(r"^#[A-Za-z][\w-]*$")
_TYPE_ONLY_RE = re.compile(r"^[a-z][\w]*$", re.IGNORECASE)


def classify_criterion(text: str) -> str:
    """Return ``OPEN`` or ``FIXED`` for one criterion's wording."""
    return "OPEN" if _OPEN_RE.search(text or "") else "FIXED"


def _locator_is_loose(locator: str) -> bool:
    """True when a single-element locator is a loose/generic target."""
    loc = (locator or "").strip()
    if not loc:
        return True
    if _BARE_CLASS_RE.match(loc):
        return True
    if _TYPE_ONLY_RE.match(loc):
        return True
    if _BARE_ID_RE.match(loc):
        # A bare id is loose unless it carries instance-like tokens
        # (remove-sauce-labs-backpack, gender-radio-1). "content" / "cart"
        # stay loose; a hyphenated or numbered id is a specific instance.
        return not _INSTANCEISH_RE.search(loc[1:])
    return False


def classify_assertion(method: str, locator: str) -> str:
    """Return ``PROPERTY`` or ``DIRECT`` for one emitted assertion step."""
    m = (method or "").strip()
    if m == URL_METHOD:
        return "DIRECT"
    if m in PROPERTY_METHODS:
        return "PROPERTY"
    if m in SINGLE_ELEMENT_METHODS:
        return "PROPERTY" if _locator_is_loose(locator) else "DIRECT"
    # Unknown method: treat as DIRECT (pins a target) rather than guess.
    return "DIRECT"


@dataclass
class AlignmentReport:
    """Aggregate step/expected-result alignment for one run.

    ``assert_steps`` is every emitted ASSERT step; ``mismatched`` counts the
    OPEN+DIRECT and FIXED+PROPERTY steps. ``per_story`` holds the same two
    counts for each story so a drift can be traced.
    """

    assert_steps: int = 0
    mismatched: int = 0
    open_direct: int = 0
    fixed_property: int = 0
    per_story: dict[str, dict[str, int]] = field(default_factory=dict)

    @property
    def rate_pct(self) -> float:
        """% of ASSERT steps that are specificity-misaligned."""
        if not self.assert_steps:
            return 0.0
        return self.mismatched / self.assert_steps * 100

    def rate_line(self) -> str:
        """The one-line report figure, e.g. 'N of M ASSERT steps ...'."""
        return f"{self.mismatched} of {self.assert_steps} ASSERT steps are specificity-misaligned"

    def to_dict(self) -> dict[str, Any]:
        return {
            "assert_steps": self.assert_steps,
            "mismatched": self.mismatched,
            "open_direct": self.open_direct,
            "fixed_property": self.fixed_property,
            "rate_pct": round(self.rate_pct, 1),
            "per_story": self.per_story,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AlignmentReport:
        return cls(
            assert_steps=data.get("assert_steps", 0),
            mismatched=data.get("mismatched", 0),
            open_direct=data.get("open_direct", 0),
            fixed_property=data.get("fixed_property", 0),
            per_story=data.get("per_story", {}) or {},
        )


def _criterion_text(dataset_dir: Path, story_id: str) -> list[str]:
    """Return the condition strings for *story_id* (empty if not found)."""
    for path in sorted(dataset_dir.glob("*.json")):
        try:
            import json

            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # pragma: no cover - a malformed file is skipped
            continue
        if data.get("id") == story_id:
            return [str(c) for c in data.get("conditions", [])]
    return []


def _assert_steps_in_test(test_code: str) -> list[dict[str, str]]:
    """Return the emitted ASSERT steps (method + locator) in one test."""
    steps: list[dict[str, str]] = []
    for m in re.finditer(r"evidence_tracker\.(assert_[a-z_]+)\s*\(\s*(['\"])(.*?)\2", test_code):
        steps.append({"method": m.group(1), "locator": m.group(3)})
    for m in re.finditer(r"""expect\(page\)\.to_have_url\(\s*['"]([^'"]*)['"]\s*\)""", test_code):
        steps.append({"method": URL_METHOD, "locator": f'expect(page).to_have_url("{m.group(1)}")'})
    return steps


def compute_alignment(dataset_dir: Path, code_map: dict[str, str]) -> AlignmentReport:
    """Compute the alignment report for one run's own data.

    ``dataset_dir`` holds the golden JSONs (criterion wording); ``code_map``
    maps story id -> emitted test code. One test function per criterion, in
    criterion order (the skeleton's contract, the same one the gate-2
    attribution relies on), so test index *i* pairs with condition *i*.
    """
    from golden_validator import extract_locators_per_test

    report = AlignmentReport()
    for story_id, code in code_map.items():
        if not code:
            continue
        conditions = _criterion_text(dataset_dir, story_id)
        per_test = extract_locators_per_test(code)
        story_steps = 0
        story_mismatch = 0
        story_open_direct = 0
        story_fixed_property = 0
        for idx, (test_name, _locators) in enumerate(per_test):
            if idx >= len(conditions):
                break
            criterion_class = classify_criterion(conditions[idx])
            test_code = _slice_test(code, test_name)
            for step in _assert_steps_in_test(test_code):
                assertion_class = classify_assertion(step["method"], step["locator"])
                story_steps += 1
                if criterion_class == "OPEN" and assertion_class == "DIRECT":
                    story_mismatch += 1
                    story_open_direct += 1
                elif criterion_class == "FIXED" and assertion_class == "PROPERTY":
                    story_mismatch += 1
                    story_fixed_property += 1
        if story_steps:
            report.per_story[story_id] = {
                "assert_steps": story_steps,
                "mismatched": story_mismatch,
                "open_direct": story_open_direct,
                "fixed_property": story_fixed_property,
            }
        report.assert_steps += story_steps
        report.mismatched += story_mismatch
        report.open_direct += story_open_direct
        report.fixed_property += story_fixed_property
    return report


def _slice_test(code: str, test_name: str) -> str:
    """Return the body of one ``test_name`` function."""
    parts = re.split(r"(?m)^(?=def\s+test_\d+_\w+)", code)
    for part in parts:
        first_line = part.split("\n", 1)[0]
        if first_line.startswith(f"def {test_name}") or first_line.strip().startswith(f"def {test_name}"):
            return part
    return ""


__all__ = [
    "AlignmentReport",
    "PROPERTY_METHODS",
    "SINGLE_ELEMENT_METHODS",
    "classify_assertion",
    "classify_criterion",
    "compute_alignment",
]
