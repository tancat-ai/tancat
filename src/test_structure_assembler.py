"""Structural re-serializer for generated test files.

The pipeline owns the file structure; the LLM's raw text only contributes
test-function body lines.

Why this exists
---------------
LLM skeletons occasionally leak bare executable statements (``home_page.click(...)``,
dangling decorators) OUTSIDE any test function. They reference fixtures that
don't exist at module scope and crash pytest at COLLECTION time, before any
test runs. Patching each leak pattern after the fact (sanitizers) is
whack-a-mole — instead, this module rebuilds the file from the parsed journey
model, so module-level statements are structurally impossible: they are never
re-emitted.

What the pipeline owns
----------------------
- the header (imports, module constants, module-level helper def/class blocks)
- per-test: the ``@pytest.mark.evidence`` decorator + the ``def`` shell
  (built with a PEP 750 t-string — no escape/quote juggling)

What comes from the LLM text
----------------------------
- test names, ``condition_ref`` / ``story_ref`` values
- the function body lines (already resolved upstream)

Call this AFTER placeholder resolution, evidence-marker injection and
normalisation — as the final structural safety pass.
"""

from __future__ import annotations

import re
from typing import Any

from src.skeleton_parser import SkeletonParser

__all__ = ["rebuild_test_structure"]


def _render(tpl: Any) -> str:
    """Interleave ``Template.strings`` + ``Template.interpolations`` into plain text.

    PEP 750 t-strings produce a ``Template`` whose ``values`` only contains the
    evaluated interpolations; the literal text lives in ``strings``. This helper
    reassembles the full string in order.
    """
    out: list[str] = []
    for i, text in enumerate(tpl.strings):
        out.append(text)
        if i < len(tpl.interpolations):
            out.append(str(tpl.interpolations[i].value))
    return "".join(out)


def _build_shell(condition_ref: str, story_ref: str, test_name: str) -> str:
    """Return the pipeline-owned decorator + ``def`` shell for one test.

    Built with a t-string: the literal text (decorator + signature) is plain,
    and the interpolated values are structured parts — no ``\\n`` escapes, no
    quote juggling.
    """
    tpl = t"""\
@pytest.mark.evidence(condition_ref="{condition_ref}", story_ref="{story_ref}")
def {test_name}(page: Page, evidence_tracker):
"""
    return _render(tpl)


def _is_module_constant(line: str) -> bool:
    """True when the module-level line is a constant assignment (no call)."""
    stripped = line.strip()
    if "=" not in stripped:
        return False
    lhs = stripped.split("=")[0].strip()
    return "(" not in lhs


def rebuild_test_structure(code: str) -> str:
    """Rebuild the test file from the parsed journey model.

    - The header (everything before the first test function) is preserved
      verbatim except module-level executable statements and dangling
      decorators, which are dropped by construction.
    - Each test function is re-emitted with a canonical t-string shell
      (decorator + ``def`` signature); body lines are taken verbatim from the
      resolved code.

    Returns the input unchanged when no test functions are found (safe
    fallback — nothing to rebuild).
    """
    parser = SkeletonParser()
    journeys = parser.parse_test_journeys(code)
    lines = code.splitlines()
    if not journeys:
        return code

    first_start = journeys[0].start_line - 1
    header: list[str] = []
    for line in lines[:first_start]:
        stripped = line.strip()
        if not stripped:
            header.append(line)
        elif line[:1] in (" ", "\t"):
            header.append(line)
        elif stripped.startswith(("#", "from ", "import ", "def ", "class ")):
            header.append(line)
        elif stripped.startswith("@"):
            # Decorators are re-emitted per-test by the assembler; a dangling
            # decorator (no following def) at module level is a leak.
            continue
        elif _is_module_constant(line):
            header.append(line)
        else:
            # Module-level call leak (e.g. ``home_page.click('Categories')``).
            continue

    out: list[str] = []
    for journey in journeys:
        def_start = journey.start_line - 1
        end = journey.end_line
        # Walk up from the def to collect its own decorator lines (the def
        # pattern matches ``def`` only, so decorators sit just above the def).
        decorator_start = def_start
        while decorator_start > 0 and lines[decorator_start - 1].strip().startswith("@"):
            decorator_start -= 1
        # Ref extraction uses ONLY the decorator region. The journey block can
        # extend into the NEXT test's decorator, so scanning the whole block
        # would attribute the next test's ref to this one.
        condition_ref, story_ref = "unknown", "S01"
        for line in reversed(lines[decorator_start:def_start]):
            m = re.search(r'condition_ref\s*=\s*["\']([^"\']+)', line)
            if m:
                condition_ref = m.group(1)
            m2 = re.search(r'story_ref\s*=\s*["\']([^"\']+)', line)
            if m2:
                story_ref = m2.group(1)
            if condition_ref != "unknown" and story_ref != "S01":
                break

        block = lines[decorator_start:end]

        # Body: drop the LLM's own decorator + def line; keep everything else
        # (POM instantiations, resolved steps, skips, comments).
        body = "\n".join(
            line
            for line in block
            if not (line.strip().startswith("@pytest.mark") or line.strip().startswith("def test_"))
        )
        out.append(_build_shell(condition_ref, story_ref, journey.test_name) + body)

    return "\n".join(header) + "\n\n" + "\n\n".join(out)
