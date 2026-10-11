#!/usr/bin/env python3
"""Regenerate the dependency licence record, or check that it is current.

``docs/licenses/DEPENDENCIES.md`` is a generated record. Its tables are built
from three sources:

- ``uv.lock`` - the authoritative package names and versions (the locked set).
- ``pyproject.toml`` - which section each *direct* dependency sits in.
- licence metadata - the licence and project URL for each package, collected
  with ``pip-licenses`` (the command in the document's "How this was
  generated" block) and refreshed by ``--write``.

The prose sections (verdict, flagged list, fonts, original assets) live here so
the whole document is reproducible and ``--check`` can diff it byte for byte.
Edit the prose in this file, not in the generated document.

Usage:
    python scripts/maintenance/licence_record.py --write    # refresh the file
    python scripts/maintenance/licence_record.py --check    # CI: fail if stale

``--check`` is stdlib-only, offline and platform-independent: it renders the
expected document from the lock and the licence metadata already recorded in the
committed file, so it runs as a fast blocking CI gate (the same shape as
``landing_assets_guard.py``). It deliberately does not run ``pip-licenses``:
that needs ``uv``, the network and a full ``--all-extras`` sync, and its package
list differs by platform (``appnope``/``pexpect``/``ptyprocess`` install only on
POSIX). ``--write`` runs it on the machine that refreshes the record.

What the guard does and does not prove: ``--check`` holds the package names,
the versions, the appendix count and the direct-dependency section membership to
``uv.lock``. It does **not** re-derive the licence strings - those are read from
the committed document - so a green check is not a licence audit and a wrong
licence name would pass. Only ``--write`` reads them fresh from ``pip-licenses``
(with ``METADATA_OVERRIDES`` for the platform-gated packages).
"""

from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

__all__ = ["OUTPUT", "check", "main", "render", "write"]

REPO_ROOT = Path(__file__).resolve().parents[2]
LOCK = REPO_ROOT / "uv.lock"
PYPROJECT = REPO_ROOT / "pyproject.toml"
OUTPUT = REPO_ROOT / "docs" / "licenses" / "DEPENDENCIES.md"

#: The recorded generator command, run by ``--write``. Kept identical to the
#: one in the document's "How this was generated" block.
PIP_LICENSES_CMD: tuple[str, ...] = (
    "uv",
    "run",
    "--all-extras",
    "--group",
    "docs",
    "--group",
    "dev",
    "--with",
    "pip-licenses",
    "pip-licenses",
    "--format=markdown",
    "--with-urls",
    "--order=license",
)

#: The root project is not a third-party dependency; it is described in the
#: document header, so it is excluded from the appendix.
ROOT_PACKAGE = "tancat"

#: Lock packages that do not install on every platform. ``pip-licenses`` cannot
#: see them on a Windows host, so their licence facts are filled from the
#: package metadata (all permissive: BSD / ISC / MIT). Recorded here so the
#: record is complete on any platform.
METADATA_OVERRIDES: dict[str, tuple[str, str]] = {
    "appnope": ("BSD License", "https://github.com/minrk/appnope"),
    "pexpect": ("ISC License (ISCL)", "https://pexpect.readthedocs.io/"),
    "ptyprocess": ("ISC License (ISCL)", "https://github.com/pexpect/ptyprocess"),
    "setuptools": ("MIT", "https://github.com/pypa/setuptools"),
    "wcwidth": ("MIT License", "https://github.com/jquast/wcwidth"),
}


def _norm(name: str) -> str:
    """Normalise a distribution name for matching (hyphen/underscore/dot/case)."""
    return re.sub(r"[-_.]", "", name).lower()


# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------


def read_lock(path: Path = LOCK) -> list[tuple[str, str]]:
    """Return ``(name, version)`` for every ``[[package]]`` in *path*, in order."""
    text = path.read_text(encoding="utf-8")
    return [
        (m.group(1), m.group(2)) for m in re.finditer(r'\[\[package\]\]\nname = "([^"]+)"\nversion = "([^"]+)"', text)
    ]


def lock_versions(path: Path = LOCK) -> dict[str, str]:
    """Return normalized name -> locked version (the root project included)."""
    return {_norm(name): version for name, version in read_lock(path)}


def _dep_name(spec: str) -> str:
    """Strip extras and version specifiers from a pyproject dependency string."""
    return re.split(r"[\[<>=!~; ]", spec.strip(), maxsplit=1)[0].strip().strip('"')


def read_sections(path: Path = PYPROJECT) -> list[tuple[str, list[str]]]:
    """Return the ordered (heading, dependency names) groups from pyproject."""
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    project = data["project"]
    groups = data.get("dependency-groups", {})
    extras = project.get("optional-dependencies", {})
    return [
        ("Runtime (`[project].dependencies`)", [_dep_name(d) for d in project["dependencies"]]),
        ("PDF extra (`[project.optional-dependencies].pdf`)", [_dep_name(d) for d in extras["pdf"]]),
        ("OCR extra (`[project.optional-dependencies].ocr`)", [_dep_name(d) for d in extras["ocr"]]),
        ("Docs group (`[dependency-groups].docs`)", [_dep_name(d) for d in groups["docs"]]),
        ("Dev group (`[dependency-groups].dev`)", [_dep_name(d) for d in groups["dev"]]),
    ]


def parse_pip_licenses(text: str) -> dict[str, tuple[str, str]]:
    """Parse a ``pip-licenses --format=markdown`` table: normalized -> (licence, url)."""
    out: dict[str, tuple[str, str]] = {}
    for line in text.splitlines():
        if not line.startswith("|") or "---" in line:
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 4 or cells[0] == "Name":
            continue
        out[_norm(cells[0])] = (cells[2], cells[3])
    return out


def _collect_metadata() -> dict[str, tuple[str, str]]:
    """Run the recorded pip-licenses command and return licence metadata."""
    print(f"running: {' '.join(PIP_LICENSES_CMD)}", file=sys.stderr)
    result = subprocess.run(PIP_LICENSES_CMD, check=True, capture_output=True, text=True, cwd=REPO_ROOT)
    return parse_pip_licenses(result.stdout)


def parse_appendix_metadata(text: str) -> dict[str, tuple[str, str]]:
    """Read the licence metadata already recorded in the committed document.

    ``--check`` uses this so it never needs the network or a full environment.
    """
    section = text.split("## Appendix: full locked set", 1)
    if len(section) != 2:
        return {}
    out: dict[str, tuple[str, str]] = {}
    for line in section[1].splitlines():
        if not line.startswith("|") or "---" in line:
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 4 or cells[0] == "Package":
            continue
        out[_norm(cells[0])] = (cells[2], cells[3])
    return out


def _parse_versioned_table(text: str) -> dict[str, tuple[str, str]]:
    """Parse a ``| Package | Version | ...`` table: normalized -> (display, version)."""
    out: dict[str, tuple[str, str]] = {}
    for line in text.splitlines():
        if not line.startswith("|") or "---" in line:
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 3 or cells[0] in ("Package", "Name"):
            continue
        out[_norm(cells[0])] = (cells[0], cells[1])
    return out


def _parse_direct_rows(text: str) -> dict[str, tuple[str, str]]:
    """Parse the direct-dependency tables (between the two section headings)."""
    region = text.split("## Direct dependencies", 1)[-1].split("## Flagged:", 1)[0]
    return _parse_versioned_table(region)


def _parse_appendix_rows(text: str) -> dict[str, tuple[str, str]]:
    """Parse the appendix table, keyed by normalized package name."""
    section = text.split("## Appendix: full locked set", 1)
    return _parse_versioned_table(section[1]) if len(section) == 2 else {}


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

HEADER = """# TanCat dependency licences

TanCat itself is **Apache-2.0** (see `LICENSE`, Copyright 2026 lacattano). This
file is the licence record for everything TanCat installs, taken from the locked
dependency set (`uv.lock`). It exists so the owner can confirm ownership and
licensing for a store or customer review.

How this was generated (re-run to refresh):

    python scripts/maintenance/licence_record.py --write

That runs the licence metadata collector over the locked set:

    uv run --all-extras --group docs --group dev --with pip-licenses \\
        pip-licenses --format=markdown --with-urls --order=license

CI job `licence-freshness` runs `--check`, which renders this document from
`uv.lock` and the committed licence metadata and fails when the two differ.

Scope: that guard holds the names, versions, count and section membership to `uv.lock`; the licence strings are read from this document, so a green check is not a licence audit.

## Verdict

- **Every direct dependency is permissive**: MIT, BSD-2/3-Clause, Apache-2.0,
  ISC or PSF. No AGPL, no SSPL, no proprietary, no commercial-only term.
- **Two transitive items are flagged** and are not strictly permissive:
  `text-unidecode` (GPL-2.0-or-later / Artistic-1.0 dual) and the `MPL-2.0`
  group (`certifi`, `orjson`, `tqdm`, and dev-only `fqdn`, `pathspec`). Details
  below.
- `pypdfium2` carries vague metadata ("dependency licenses"); the bundled
  PDFium is BSD-3-Clause, recorded in `DOCUMENT_READER_LICENSES.md`.

## Direct dependencies

Every package declared in `pyproject.toml`, with the licence it resolved to.
"Flag" is the one-line verdict; the full text is in the next section.
"""

FLAGGED = """## Flagged: non-permissive or unclear

| Package | Licence (as reported) | Flag |
|---|---|---|
| text-unidecode | Artistic License; GNU General Public License (GPL); GNU General Public License v2 or later (GPLv2+) | FLAG - dual GPL-2.0-or-later / Artistic-1.0. pip-licenses reports the GPL classifiers. The Artistic option is permissive, but the licence choice must be made and recorded; the GPL option alone would conflict with shipping Apache-2.0 TanCat. Pulled in by pytest-playwright -> python-slugify, so it is in the default install. |
| certifi | Mozilla Public License 2.0 (MPL 2.0) | FLAG - MPL-2.0 (weak, file-level copyleft), not permissive. Used unmodified as a library; keep it unmodified and it is compatible. |
| orjson | MPL-2.0 AND (Apache-2.0 OR MIT) | FLAG - MPL-2.0 AND (Apache-2.0 OR MIT). The Apache/MIT option applies, so it is effectively permissive; flagged because the metadata leads with MPL. |
| tqdm | MPL-2.0 AND MIT | FLAG - MPL-2.0 AND MIT. The MIT option applies; flagged because the metadata leads with MPL. |
| fqdn | Mozilla Public License 2.0 (MPL 2.0) | FLAG - MPL-2.0. Dev/Jupyter only (jupyter-events), not in the shipped runtime. |
| pathspec | Mozilla Public License 2.0 (MPL 2.0) | FLAG - MPL-2.0. Dev only (mypy), not in the shipped runtime. |
| pypdfium2 | BSD-3-Clause, Apache-2.0, dependency licenses | Note - metadata reads 'BSD-3-Clause, Apache-2.0, dependency licenses'. The bundled PDFium is BSD-3-Clause. Full record: docs/licenses/DOCUMENT_READER_LICENSES.md. |
| pillow | MIT-CMU | Note - MIT-CMU (permissive; a non-standard name, not a flag). |

MPL-2.0 is a weak, file-level copyleft. Using the packages unmodified as
libraries is fine and does not affect TanCat's Apache-2.0 licence. The flag is
recorded so the position is a decision, not an oversight. For `text-unidecode`,
the permissive Artistic option should be the one relied on.
"""

FONTS = """## Fonts

The landing page (`landing/index.html`, `landing/install.html`) loads three
fonts from Google Fonts:

| Font | Licence | Copyright |
|---|---|---|
| Inter | SIL Open Font License 1.1 | Copyright (c) 2016 The Inter Project Authors |
| JetBrains Mono | SIL Open Font License 1.1 | Copyright 2020 The JetBrains Mono Project Authors |
| Newsreader | SIL Open Font License 1.1 | Copyright 2020 The Newsreader Project Authors |

All three are OFL-1.1, which permits web and print use. They are fetched from
Google's CDN at page load and are **not redistributed** by the landing page.

The Pro install/licence PDF (`landing/tancat-pro-install-and-licence.pdf`) is
different: it **redistributes** four font files, bundled in
`docs/implementation/fonts/`, so the render cannot fall back to a font installed
on the build machine (it used to embed Segoe UI and Consolas from the host). They
are unmodified release files, all OFL-1.1:

| File | Face | Licence | Copyright | SHA-256 |
|---|---|---|---|---|
| `inter-regular.woff2` | Inter Regular (400) | OFL-1.1 | Copyright (c) 2016 The Inter Project Authors | `e06f6b1bc553aaea4e4668023ed0ab0a147129c3107f511bc7d03d361b0ae085` |
| `inter-bold.woff2` | Inter Bold (700) | OFL-1.1 | Copyright (c) 2016 The Inter Project Authors | `fa888127b6da015b65569f0351f3b5c391ad928904951f1c20e9f8462a8d95ea` |
| `inter-italic.woff2` | Inter Italic (400) | OFL-1.1 | Copyright (c) 2016 The Inter Project Authors | `2d078cb3bc8f934740d53b39dd23b0678f2f97477e49ec785dd9d8acd8b96bfc` |
| `jetbrains-mono-regular.woff2` | JetBrains Mono Regular (400) | OFL-1.1 | Copyright 2020 The JetBrains Mono Project Authors | `f1a7a03672cdd494ce0d5543fac6e4360fe22403c6de297fdc2e55a815f7baff` |

The source repositories are Inter (`docs/font-files/`, github.com/rsms/inter)
and JetBrains Mono (`fonts/webfonts/`, github.com/JetBrains/JetBrainsMono).
Newsreader is **not bundled**: the install/licence document has no serif text, so
the PDF never embeds it. The full OFL-1.1 text and both copyright notices are in
`docs/implementation/fonts/OFL-1.1.md`, next to the fonts as the licence requires,
and the four files are listed as PDF sources in `landing/asset-sources.json` so
the landing asset guard fails if a font changes without a re-render. Verified by
inspecting the rebuilt PDF: it embeds only `Inter-Regular`, `Inter-Bold`,
`Inter-Italic` and `JetBrainsMono-Regular` (Type0 subsets), no Microsoft face.

Rule: only `landing/tancat-pro-install-and-licence.pdf` is rendered to a shipped
document. Any other page that is ever printed must use the bundled open faces
under `docs/implementation/fonts/`, never a font the host happens to have -
because `docs/launch/lemon-squeezy-checklist.html` and `docs/walkthrough.md`
still declare host fonts in their CSS, and a headless render resolves those
against the build machine.
"""

ORIGINAL_ASSETS = """## Original TanCat assets

- `landing/logo_transparent.png` (the TanCat logo) and the icon set derived from
  it (`favicon.ico`, `icon-192.png`, `icon-512.png`, `apple-touch-icon.png`) are
  **original TanCat work**, created for this project. They are not third-party
  stock.
- `landing/noir_art.jpg` is **original TanCat artwork**, created for this
  project.
- `landing/streamlit_real_1280x820.png` is a real screenshot of the TanCat UI.

`landing/asset-sources.json` is generated by
`scripts/maintenance/make_landing_assets.py` (which rewrites it on every run and
therefore cannot carry a hand-written note), so this originality record lives
here instead.
"""


def _flag(licence: str) -> str:
    """The one-line verdict for a direct dependency's Flag column."""
    low = licence.lower()
    if "mit-cmu" in low or "dependency licenses" in low:
        return "Note"
    return ""


def _direct_table(names: Sequence[str], lock: Mapping[str, str], meta: Mapping[str, tuple[str, str]]) -> str:
    lines = ["| Package | Version | Licence | Flag |", "|---|---|---|---|"]
    for name in names:
        key = _norm(name)
        version = lock.get(key, "UNLOCKED")
        licence, _url = meta.get(key, ("UNKNOWN - run licence_record.py --write", ""))
        lines.append(f"| {name} | {version} | {licence} | {_flag(licence)} |")
    return "\n".join(lines)


def render(meta: Mapping[str, tuple[str, str]] | None = None) -> str:
    """Return the full expected document from the lock and *meta* licence facts."""
    meta = dict(meta or {})
    lock = lock_versions()
    parts = [HEADER.rstrip("\n"), ""]
    for heading, names in read_sections():
        parts.append(f"### {heading}")
        parts.append("")
        parts.append(_direct_table(names, lock, meta))
        parts.append("")
    parts.append(FLAGGED.rstrip("\n"))
    parts.append("")
    parts.append(FONTS.rstrip("\n"))
    parts.append("")
    parts.append(ORIGINAL_ASSETS.rstrip("\n"))
    parts.append("")

    locked = [(name, version) for name, version in read_lock() if _norm(name) != _norm(ROOT_PACKAGE)]
    parts.append(f"## Appendix: full locked set ({len(locked)} entries)")
    parts.append("")
    parts.append("The complete resolved environment, including transitive dependencies, for")
    parts.append("completeness. TanCat itself is described at the top of this file. Sorted by name.")
    parts.append("")
    parts.append("| Package | Version | Licence | URL |")
    parts.append("|---|---|---|---|")
    rows = []
    for name, version in locked:
        licence, url = meta.get(_norm(name), ("UNKNOWN - run licence_record.py --write", "-"))
        rows.append((name.lower(), f"| {name} | {version} | {licence} | {url} |"))
    parts.extend(row for _key, row in sorted(rows))
    return "\n".join(parts) + "\n"


# ---------------------------------------------------------------------------
# Check / write / CLI
# ---------------------------------------------------------------------------


def check(text: str | None = None, path: Path = OUTPUT) -> list[str]:
    """Return drift problems; an empty list means the record matches uv.lock.

    Compares the committed tables against ``uv.lock``: package set, per-package
    version, the listed direct dependencies, and the appendix count. A final
    whole-file render comparison also catches formatting or prose drift.
    """
    committed = path.read_text(encoding="utf-8") if text is None else text
    problems: list[str] = []

    locked = {_norm(name): version for name, version in read_lock() if _norm(name) != _norm(ROOT_PACKAGE)}
    appendix = _parse_appendix_rows(committed)

    for key in sorted(set(locked) - set(appendix)):
        problems.append(f"uv.lock has {key} {locked[key]}, the appendix does not")
    for key in sorted(set(appendix) - set(locked)):
        problems.append(f"the appendix has {appendix[key][0]}, uv.lock does not (dropped dependency?)")
    for key in sorted(set(locked) & set(appendix)):
        if appendix[key][1] != locked[key]:
            problems.append(f"{appendix[key][0]} is {appendix[key][1]} in the record, {locked[key]} in uv.lock")

    direct = _parse_direct_rows(committed)
    for heading, names in read_sections():
        for name in names:
            key = _norm(name)
            if key not in direct:
                problems.append(f"direct dependency {name} is missing from '{heading}'")
            elif direct[key][1] != locked.get(key):
                problems.append(
                    f"direct dependency {name} is {direct[key][1]} in the record, {locked.get(key)} in uv.lock"
                )

    count = re.search(r"## Appendix: full locked set \((\d+) entries\)", committed)
    appendix_section = committed.split("## Appendix: full locked set", 1)[-1]
    rows = sum(
        1
        for line in appendix_section.splitlines()
        if line.startswith("|") and "---" not in line and not line.startswith("| Package ")
    )
    if count and int(count.group(1)) != rows:
        problems.append(f"the appendix title says {count.group(1)} entries but the table has {rows} rows")

    if not problems and render(parse_appendix_metadata(committed)) != committed:
        problems.append("the record differs from a fresh render (formatting or prose drift); re-run --write")
    return problems


def write(path: Path = OUTPUT) -> Path:
    """Refresh the licence metadata and rewrite the document."""
    meta = _collect_metadata()
    for key, value in METADATA_OVERRIDES.items():
        meta.setdefault(key, value)
    path.write_text(render(meta), encoding="utf-8")
    return path


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if "--write" in args or "--refresh" in args:
        written = write()
        print(f"wrote {written.relative_to(REPO_ROOT)}")
        return 0
    if "--check" in args or not args:
        problems = check()
        if problems:
            print("FAIL: the dependency licence record is out of date with uv.lock:")
            for problem in problems:
                print(f"  - {problem}")
            print()
            print("Fix: python scripts/maintenance/licence_record.py --write")
            return 1
        print("OK: the dependency licence record matches uv.lock.")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
