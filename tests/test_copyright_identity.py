"""The copyright owner and the footer are one fact, checked by marker (j-0299).

A name search cannot catch a footer that carries no name at all, and a phrase list
rots as soon as the wording moves. So this test finds the **marker** - ``&copy;``,
``(c)``, ``(c) 2026``, ``Copyright 2026``, ``All rights reserved`` - and the
**footer element**, and requires the company in the same block. It then forbids the
old identity tokens on any buyer-facing surface.

Two things this catches that a search for "TanCat" or "© TanCat" does not:

* a footer with **no copyright line at all** - there is no name in it to find, so
  only the footer element itself can be checked;
* a copyright marker whose **block** names nobody, e.g. ``&copy; 2026`` alone.

The one exemption is narrow and pinned: the canonical MariaDB licence text at the
top of ``LICENSE`` carries its own copyright line and must stay byte-identical
(``tests/test_licence_bsl.py`` enforces that). Everything after the ``Parameters``
heading is ours and is checked like any other surface.
"""

from __future__ import annotations

import re
from html import unescape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

COMPANY = "Cat Tan Operations Ltd"
COMPANY_NUMBER = "17576111"

#: The identity the company replaced. Each is a false statement on a buyer surface.
OLD_IDENTITY = ("sole-trader", "sole trader", "trading name of", "Louis Cattano", "lacattano")

#: A copyright marker. Matched case-insensitively: "All Rights Reserved" appears too.
MARKER = re.compile(r"&copy;|©|\(c\)\s*\d{4}|Copyright\s+\d{4}|All rights reserved", re.IGNORECASE)

LANDING_PAGES = tuple(sorted((ROOT / "landing").glob("*.html")))
DOCS_SITE_CONFIG = ROOT / "mkdocs.yml"


def buyer_facing_files() -> list[Path]:
    """Every file a buyer or visitor can read without cloning the repo."""
    files: list[Path] = [
        *LANDING_PAGES,
        ROOT / "NOTICE",
        ROOT / "LICENSE",
        ROOT / "README.md",
        ROOT / "SECURITY.md",
        DOCS_SITE_CONFIG,
    ]
    files.extend(sorted((ROOT / "docs" / "user").rglob("*.md")))
    return [path for path in files if path.exists()]


def _line_of(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _plain(block: str) -> str:
    """Strip tags and entities so one string compare works for HTML and text."""
    return unescape(re.sub(r"<[^>]+>", " ", block))


def footers(path: Path) -> list[tuple[int, str]]:
    """Every ``<footer>`` block in an HTML file, as (line, inner text)."""
    text = path.read_text(encoding="utf-8", errors="replace")
    return [
        (_line_of(text, match.start()), _plain(match.group(1)))
        for match in re.finditer(r"<footer\b[^>]*>(.*?)</footer>", text, re.DOTALL | re.IGNORECASE)
    ]


def _html_blocks(text: str) -> list[tuple[int, str]]:
    """Paragraphs that carry a marker. Footers are checked separately, all of them."""
    return [
        (_line_of(text, match.start()), _plain(match.group(1)))
        for match in re.finditer(r"<p\b[^>]*>(.*?)</p>", text, re.DOTALL | re.IGNORECASE)
        if MARKER.search(match.group(1))
    ]


def _paragraph_blocks(text: str) -> list[tuple[int, str]]:
    """Blank-line separated paragraphs that carry a marker."""
    blocks: list[tuple[int, str]] = []
    for match in re.finditer(r"(?:^|\n\n)([^\n][^\0]*?)(?=\n\n|\Z)", text):
        block = match.group(1)
        if MARKER.search(block):
            blocks.append((_line_of(text, match.start(1)), block))
    return blocks


def _parameter_blocks(text: str) -> list[tuple[int, str]]:
    """A BSL parameter and its continuation lines: the block a parameter belongs to."""
    lines = text.splitlines()
    starts = [n for n, line in enumerate(lines) if re.match(r"^[A-Z][A-Za-z ]+: ", line)]
    blocks: list[tuple[int, str]] = []
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(lines)
        block = "\n".join(lines[start:end])
        if MARKER.search(block):
            blocks.append((start + 1, block))
    return blocks


def _yaml_blocks(text: str) -> list[tuple[int, str]]:
    """A YAML line plus its indented continuation lines."""
    lines = text.splitlines()
    blocks: list[tuple[int, str]] = []
    for n, line in enumerate(lines):
        if not MARKER.search(line):
            continue
        end = n + 1
        while end < len(lines) and (lines[end].startswith((" ", "\t")) or not lines[end].strip()):
            end += 1
        blocks.append((n + 1, "\n".join(lines[n:end])))
    return blocks


def marker_blocks(path: Path) -> list[tuple[int, str]]:
    """(line, block) for every copyright marker on a buyer-facing surface."""
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix == ".html":
        return _html_blocks(text)
    if path.name == "LICENSE":
        return _parameter_blocks(text)
    if path.suffix in {".yml", ".yaml"}:
        return _yaml_blocks(text)
    return _paragraph_blocks(text)


def test_every_landing_page_has_a_footer_naming_the_company() -> None:
    """No footer, or a footer that names nobody, is the failure mode a search misses."""
    assert len(LANDING_PAGES) == 6, f"expected the six landing pages, found {len(LANDING_PAGES)}"

    problems: list[str] = []
    for page in LANDING_PAGES:
        blocks = footers(page)
        if not blocks:
            problems.append(f"{page.name}: no <footer> element")
            continue
        for line, block in blocks:
            if COMPANY not in block:
                problems.append(f"{page.name}:{line}: footer does not name {COMPANY}")
            elif COMPANY_NUMBER not in block:
                problems.append(f"{page.name}:{line}: footer names the company but not number {COMPANY_NUMBER}")

    assert problems == [], "a footer does not name the copyright owner:\n  " + "\n  ".join(problems)


def test_every_copyright_marker_names_the_company() -> None:
    """The marker is the hook: wherever it appears, the owner must be named in that block."""
    problems: list[str] = []
    seen: set[str] = set()
    for path in buyer_facing_files():
        for line, block in marker_blocks(path):
            seen.add(path.name)
            if COMPANY not in block:
                snippet = " ".join(block.split())[:110]
                problems.append(f"{path.relative_to(ROOT)}:{line}: marker names no owner -> {snippet}")

    # The marker scan must reach the two prose surfaces that carry one outside the
    # landing pages. mkdocs.yml is checked by its own test (a bare `copyright:` key
    # has no year for this pattern to hold on to).
    assert {"NOTICE", "LICENSE"} <= seen, f"the marker scan missed a surface: reached {sorted(seen)}"
    assert problems == [], "a copyright marker names no owner:\n  " + "\n  ".join(problems)


def test_no_buyer_facing_surface_carries_the_old_identity() -> None:
    """The company replaced a sole trader, a GitHub handle and a personal name."""
    problems: list[str] = []
    for path in buyer_facing_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        for token in OLD_IDENTITY:
            if token.lower() in text.lower():
                problems.append(f"{path.relative_to(ROOT)}: still says {token!r}")

    assert problems == [], "the old identity is still on a buyer-facing surface:\n  " + "\n  ".join(problems)


def test_the_docs_site_names_the_company_too() -> None:
    """mkdocs renders its own footer, so the config must carry the owner."""
    config = DOCS_SITE_CONFIG.read_text(encoding="utf-8")
    match = re.search(r"^copyright:\s*(?P<line>.+)$", config, re.MULTILINE)
    assert match is not None, "mkdocs.yml has no copyright line - the docs footer would be bare"
    assert COMPANY in match.group("line"), f"mkdocs copyright names no owner: {match.group('line')!r}"
    assert COMPANY_NUMBER in match.group("line"), "mkdocs copyright must carry the company number"
    author = re.search(r"^site_author:\s*(?P<line>.+)$", config, re.MULTILINE)
    assert author is not None and COMPANY in author.group("line"), "mkdocs.yml site_author must name the company"


def test_the_licence_text_exemption_is_narrow() -> None:
    """Only the canonical MariaDB text is exempt; our parameters are checked."""
    text = (ROOT / "LICENSE").read_text(encoding="utf-8")
    assert "Parameters" in text, "LICENSE lost its Parameters heading - the split is gone"
    head, _, parameters = text.partition("Parameters")
    assert len(MARKER.findall(head)) == 2, "the canonical licence text has exactly two MariaDB lines"
    assert "MariaDB plc" in head, "the canonical text's own copyright line must stay"
    assert len(marker_blocks(ROOT / "LICENSE")) >= 1, "the parameters carry markers and must be checked"
    assert COMPANY in parameters, "the Licensed Work parameter must name the copyright holder"
