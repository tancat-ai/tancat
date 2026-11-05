"""Fail closed when an owner placeholder would be published (j-0289).

A placeholder in ``landing/`` is not a note to self: ``pages-deploy.yml`` builds
``landing/`` as the site root on every push to main, so a placeholder that
reaches main is a placeholder a customer reads. This module is the one rule, used
by the deploy workflow (which refuses to publish) and by
``tests/test_landing_no_placeholders.py`` (which refuses the commit).

The marker, not the sentence: the check keys on the house placeholder convention
rather than on today's wording, so the next placeholder fails too.

  * the CSS class ``placeholder-owner`` - use it on any visible placeholder span;
  * the phrase ``to be supplied by the owner``;
  * an UPPERCASE bracketed token of eight characters or more, e.g.
    ``[LEGAL ENTITY NAME - ...]``, which is how these read in a paragraph.

Usage::

    python scripts/maintenance/check_landing_placeholders.py [root]

Exit code 0 when the landing tree is clean, 1 when a placeholder is present.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LANDING = REPO_ROOT / "landing"

#: Literal markers: the house convention for "the owner must fill this in".
MARKERS: tuple[str, ...] = (
    "placeholder-owner",
    "to be supplied by the owner",
)

#: An uppercase bracketed placeholder, e.g. ``[LEGAL ENTITY NAME - to be ...]``.
BRACKET_PLACEHOLDER = re.compile(r"\[[A-Z][A-Z0-9 ,&/'’.\-]{6,}\]")

#: Only the published pages are scanned. Images, PDFs and fonts cannot carry a
#: marker a reader would see in the HTML.
SUFFIXES: tuple[str, ...] = (".html", ".htm")


def find_placeholders(root: Path = LANDING) -> list[str]:
    """Return one ``path:line: marker`` line per placeholder found under *root*.

    An empty list means the landing tree is safe to publish.
    """
    findings: list[str] = []
    if not root.exists():
        return [f"{root}: landing directory not found - refusing to call it clean"]
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:  # unreadable is not clean
            findings.append(f"{path}: could not be read ({exc}) - refusing to call it clean")
            continue
        for number, line in enumerate(text.splitlines(), start=1):
            lowered = line.lower()
            for marker in MARKERS:
                if marker in lowered:
                    findings.append(f"{path.relative_to(root.parent)}:{number}: {marker}")
            for match in BRACKET_PLACEHOLDER.findall(line):
                findings.append(f"{path.relative_to(root.parent)}:{number}: {match}")
    return findings


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    root = Path(args[0]) if args else LANDING
    findings = find_placeholders(root)
    if findings:
        print("REFUSING TO PUBLISH: owner placeholder(s) left in the landing tree:", file=sys.stderr)
        for finding in findings:
            print(f"  {finding}", file=sys.stderr)
        print(
            "\nFill the placeholders with the wording the owner approves, or remove the sentence. "
            "The marker convention is documented in scripts/maintenance/check_landing_placeholders.py.",
            file=sys.stderr,
        )
        return 1
    print(f"Landing tree clean: no owner placeholder in {root}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
