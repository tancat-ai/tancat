"""Deterministic step / expected-result alignment guard (emit time).

The generator prompt asks the model to match an ASSERT's specificity to the
criterion's openness: an OPEN criterion ("an item", "a radio option", "e.g. X")
should get a property check, a FIXED one should check the target it names.
That is a request to the model. This module is the deterministic half: where the
criterion's openness cue survives into the ASSERT description - the description
is copied from the criterion - the emitter enforces the shape itself.

Two directions:

- **OPEN criterion + DIRECT assertion** -> ``refuse``. The check pins one example
  instance, so it false-negatives when the run legitimately picks a different
  outcome. The emitter emits an honest skip instead of an unsound pass, which is
  the pattern B-069 already uses for a fallback-resolved assertion.
- **FIXED criterion + PROPERTY assertion** -> ``flag`` only. A global container
  ("#content", ".text") proves nothing, but the instance the criterion meant is
  not recoverable from the description, so guessing one would be worse than
  reporting it. Logged, never rewritten.

Softening an open check to a count (``assert_count_at_least``) was considered
and rejected: ``locator.count()`` ignores visibility, so it would trade a false
negative for a false pass - the opposite of what this guard is for.

The cue list mirrors ``scripts/eval/eval_alignment.py`` on purpose: the product
guard and the report-only eval metric must classify the same text the same way,
or the measured alignment rate stops describing the product.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = [
    "OPEN_CUES",
    "AlignmentDecision",
    "alignment_decision",
    "classify_assertion",
    "classify_openness",
    "locator_is_loose",
]

# Assertion methods that check a property of a set rather than one instance.
# Mirrors scripts/eval/eval_alignment.py::PROPERTY_METHODS.
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

# Single-element methods: DIRECT unless the locator is a loose/generic target.
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

# A URL assertion pins one specific page.
URL_METHOD = "to_have_url"

# Openness cues in the criterion wording (mirrors the eval metric).
OPEN_CUES: tuple[str, ...] = (
    r"e\.g\.",
    r"for example",
    r"\bat least one\b",
    r"\bat least 1\b",
    r"\ban? (?:item|product|radio|option|account|row|entry)s?\b",
    r"\bany\b",
    r"\bone of\b",
    r"\bsome\b",
)

_OPEN_RE = re.compile("|".join(OPEN_CUES), re.IGNORECASE)

_INSTANCEISH_RE = re.compile(r"[A-Za-z]+[-_][A-Za-z0-9]|[-_]\d|\d", re.ASCII)
_BARE_CLASS_RE = re.compile(r"^\.[A-Za-z][\w-]*$")
_BARE_ID_RE = re.compile(r"^#[A-Za-z][\w-]*$")
_TYPE_ONLY_RE = re.compile(r"^[a-z][\w]*$", re.IGNORECASE)


def classify_openness(text: str) -> str:
    """Return ``OPEN`` when the wording leaves the outcome open, else ``FIXED``."""
    return "OPEN" if _OPEN_RE.search(text or "") else "FIXED"


def locator_is_loose(locator: str) -> bool:
    """True when a single-element locator names a generic target, not an instance."""
    loc = (locator or "").strip().strip("'\"")
    if not loc:
        return True
    if _BARE_CLASS_RE.match(loc):
        return True
    if _TYPE_ONLY_RE.match(loc):
        return True
    if _BARE_ID_RE.match(loc):
        # A bare id is loose unless it carries instance-like tokens
        # (remove-sauce-labs-backpack, gender-radio-1).
        return not _INSTANCEISH_RE.search(loc[1:])
    return False


def classify_assertion(method: str, locator: str) -> str:
    """Return ``PROPERTY`` or ``DIRECT`` for one emitted assertion."""
    m = (method or "").strip()
    if m == URL_METHOD:
        return "DIRECT"
    if m in PROPERTY_METHODS:
        return "PROPERTY"
    if m in SINGLE_ELEMENT_METHODS:
        return "PROPERTY" if locator_is_loose(locator) else "DIRECT"
    # Unknown method: treat as DIRECT (it pins a target) rather than guess.
    return "DIRECT"


@dataclass(frozen=True)
class AlignmentDecision:
    """What the guard did (or would do) for one ASSERT.

    ``action`` is one of:

    - ``aligned``  - nothing to do; leave the emitted check alone.
    - ``refuse``   - OPEN criterion with an instance-pinned (DIRECT) check; the
      caller should emit an honest skip rather than the unsound assertion.
    - ``flag``     - FIXED criterion with a loose/property check; log it, the
      intended instance is not recoverable so nothing is rewritten.
    """

    action: str
    reason: str


def _safe(text: str) -> str:
    """Make text safe to embed inside a double-quoted emitted string."""
    return (text or "").replace("\\", "").replace('"', "'").replace("\n", " ").replace("\r", " ").strip()


def alignment_decision(description: str, method: str, locator: str) -> AlignmentDecision:
    """Decide how one emitted ASSERT relates to its criterion's openness.

    Acts only where the cue is actually available - an empty description carries
    no cue, so an empty description is FIXED and only the (non-destructive)
    flag direction can fire.
    """
    criterion = classify_openness(description)
    assertion = classify_assertion(method, locator)

    if criterion == "OPEN" and assertion == "DIRECT":
        return AlignmentDecision(
            action="refuse",
            reason=(
                "open-ended step resolved to one specific element "
                f"({_safe(locator)}); asserting it would fail when a different "
                "outcome is legitimately chosen"
            ),
        )

    if criterion == "FIXED" and assertion == "PROPERTY":
        return AlignmentDecision(
            action="flag",
            reason=(
                "step names a specific target but the check is generic "
                f"({_safe(method)} on {_safe(locator)}); it proves nothing about that target"
            ),
        )

    return AlignmentDecision(action="aligned", reason="")
