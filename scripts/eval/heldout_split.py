"""Which story files the eval holds out of the bundled RAG seed (j-0244).

The bundled RAG seed is built from the same ``eval-*.json`` golden keys the gate
scores, so the stories whose files are seeded cannot measure resolution - the
tool was handed their answers. The eval therefore scores a **held-out split**:
whole story files that are excluded from the seed (``exclude=`` on
``src.rag_bundled.load_golden_patterns`` / ``ensure_bundled_seeded``).

The owner's decision (2026-10-30): the 90% gate-1 target is read against that
split, and **which files are held back rotates each run**, so the sample grows
instead of the same 30 placeholders being scored forever.

**A split holds out whole sites, not single files (t-1119, j-0244 step 3).** The
seed's +20 golden bonus gates on the pattern's ``site_hash``, not on the file
that produced it: ``eval-007_banking_mock`` and ``eval-008_goto_navigation``
share a site and both hash to ``bebd95a0fea633c3``, so holding one out while the
other stays seeded hands the answer back (identical ``description`` /
``expected_locator`` pairs, and locator-only overlap on the login form). Groups
are therefore the unit of rotation: files are grouped by the ``site_hash`` their
dataset gives them, and a group is held out whole or not at all. That is also
why a rotated split can carry four files where it used to carry three.

* The default is still ``eval-007``, ``eval-008``, ``eval-010`` - which is
  already two whole groups - so the figure recorded on 2026-10-30 keeps
  reproducing itself (30 of the 113 placeholders) and stays comparable with
  itself. Rotation is opted into.
* Rotation is deterministic: a SHA-256 of the selector and the group key, never
  Python's ``hash()`` (randomised per process), never filesystem order. Two runs
  on the same day (or with the same seed) pick the same split; a different day
  (or seed) picks a different one.
* An explicit list of files is allowed, and is validated: a name that is not a
  dataset file, a file with no scored placeholders, a list that is not whole
  groups, or a list that separates a site are all refused rather than silently
  accepted - a split that looks full but was handed the answers is the failure
  this whole job exists to stop.

Selectors (one flag on the eval resolver, ``--heldout-split``)::

    --heldout-split default                # the fixed three (also: no flag)
    --heldout-split date                   # today; stable all day, moves tomorrow
    --heldout-split date:2026-10-30         # a named day, for re-running a split
    --heldout-split seed:42                 # the same split every time, for that seed
    --heldout-split eval-007_...,eval-008_...,eval-010_....json

The split list lives here and only here: the record validator reads it to refuse
a figure that separates a site, and the eval resolver passes the same list to the
seed exclusion it computes - there is no second copy in ``src/``.

A rotation must not be able to weaken the sample quietly - picking an easy file
is the same failure in a new coat. What makes that visible: every recorded
figure names its split (the files) and carries a per-file breakdown beside the
number, so a split that keeps scoring well on the same one or two files shows it
in the record, next to the figure it is flattering.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

__all__ = [
    "DEFAULT_SPLIT",
    "SPLIT_SIZE",
    "describe_split",
    "separating_pairs",
    "site_groups",
    "split_files",
    "split_placeholders",
]

#: How many whole **site groups** a rotated split holds. Three keeps the split
#: at roughly 25-40 of the 113 scored placeholders, the size the first split
#: used; because a group can hold two files, a rotated split can carry four.
SPLIT_SIZE = 3

#: The fixed split the 2026-10-30 figure was measured on, and the only copy of
#: the list. It is two whole groups (the banking pair + ambiguous_mock), so it
#: satisfies the site rule by construction. Kept as the default so that figure
#: stays reproducible and comparable with itself (j-0244 step 2).
DEFAULT_SPLIT: tuple[str, ...] = (
    "eval-007_banking_mock.json",
    "eval-008_goto_navigation.json",
    "eval-010_ambiguous_mock.json",
)

#: A named day or a seed, spelled as prefixes so a bare token is never guessed.
_DATE_PREFIX = "date"
_SEED_PREFIX = "seed"


def split_placeholders(dataset_dir: Path, files: tuple[str, ...] | list[str]) -> int:
    """How many scored placeholders the named story files carry between them."""
    total = 0
    for name in files:
        data = json.loads((dataset_dir / name).read_text(encoding="utf-8"))
        for criterion in data.get("golden_resolutions", []):
            total += len(criterion.get("placeholders", []))
    return total


def _dataset_files(dataset_dir: Path) -> list[str]:
    """Every dataset file name, sorted."""
    return [path.name for path in sorted(dataset_dir.glob("eval-*.json"))]


def _scored_files(dataset_dir: Path) -> list[str]:
    """The dataset file names that carry at least one scored placeholder."""
    return [name for name in _dataset_files(dataset_dir) if split_placeholders(dataset_dir, (name,)) > 0]


def _site_hash(dataset_dir: Path, name: str) -> str:
    """The site identity the seed scopes this file's golden patterns under.

    The same function the seed uses (``src.rag_bundled.golden_site_hash``),
    so a group is exactly the set of files that can answer for each other.
    """
    from src.rag_bundled import golden_site_hash

    data = json.loads((dataset_dir / name).read_text(encoding="utf-8"))
    return golden_site_hash(str(data.get("site", "")), str(data.get("base_url", "")))


def site_groups(dataset_dir: Path) -> dict[str, tuple[str, ...]]:
    """Story files grouped by the ``site_hash`` their dataset gives them.

    The unit of a split: a group is held out whole or not at all, because the
    seed's +20 golden bonus answers on ``site_hash``, not on the file (t-1119).
    Groups are keyed by site hash and hold sorted file names; empty (unscored)
    files are left out.
    """
    groups: dict[str, list[str]] = {}
    for name in _scored_files(dataset_dir):
        groups.setdefault(_site_hash(dataset_dir, name), []).append(name)
    return {site_hash: tuple(sorted(names)) for site_hash, names in sorted(groups.items())}


def separating_pairs(dataset_dir: Path, files: tuple[str, ...] | list[str]) -> list[tuple[str, str, str]]:
    """Same-site pairs a split would split: (held out file, seeded sibling, site hash).

    Empty means the split holds every affected site whole. This is what both the
    splitter (which refuses such a list) and the record validator (which refuses
    such a figure) check.
    """
    held = set(files)
    pairs: list[tuple[str, str, str]] = []
    for site_hash, group in site_groups(dataset_dir).items():
        inside = sorted(held & set(group))
        outside = sorted(set(group) - held)
        if inside and outside:
            pairs.append((inside[0], outside[0], site_hash))
    return pairs


def _from_explicit_list(dataset_dir: Path, selector: str) -> tuple[str, ...]:
    """An explicit comma-separated file list, validated (never silently trimmed)."""
    wanted = tuple(item.strip() for item in selector.split(",") if item.strip())
    for name in wanted:
        if not (dataset_dir / name).is_file():
            raise ValueError(f"{name!r} is not a dataset file in {dataset_dir}")
        if split_placeholders(dataset_dir, (name,)) == 0:
            raise ValueError(f"{name!r} carries no scored placeholders - it cannot be held out")
    if len(wanted) != len(set(wanted)):
        raise ValueError(f"a split cannot name the same file twice: {wanted}")
    separated = separating_pairs(dataset_dir, wanted)
    if separated:
        held, seeded, site_hash = separated[0]
        raise ValueError(
            f"{held} and {seeded} share site_hash {site_hash}: holding one out and leaving the other "
            "seeded hands the answer back - hold the whole group out or none of it"
        )
    return wanted


def split_files(dataset_dir: Path, selector: str | None = None) -> tuple[str, ...]:
    """Choose the held-out story files.

    Args:
        dataset_dir: Directory holding the ``eval-*.json`` stories.
        selector: ``None``/``"default"`` for the fixed three; ``"date"``,
            ``"date:YYYY-MM-DD"`` or ``"seed:<value>"`` to rotate; a
            comma-separated list of file names for an explicit split.

    Returns:
        The chosen file names: the explicit list in the order given, otherwise
        sorted. A rotated split is ``SPLIT_SIZE`` whole site groups, so it holds
        three or four files.

    Raises:
        ValueError: the selector is ambiguous, an explicit list is invalid or
            separates a site, or the dataset has fewer groups than a split needs.
    """
    if selector is None or selector.strip() in ("", "default"):
        return DEFAULT_SPLIT

    text = selector.strip()
    if "," in text or text.endswith(".json"):
        return _from_explicit_list(dataset_dir, text)

    if text == _DATE_PREFIX:
        token = f"date:{time.strftime('%Y-%m-%d')}"
    elif text.startswith(f"{_DATE_PREFIX}:"):
        token = text
    elif text.startswith(f"{_SEED_PREFIX}:"):
        if not text.split(":", 1)[1].strip():
            raise ValueError("seed: needs a value, e.g. seed:42")
        token = text
    else:
        raise ValueError(
            f"{selector!r} is ambiguous - say 'default', 'date', 'date:<YYYY-MM-DD>', 'seed:<value>', "
            f"or name the story files"
        )

    groups = site_groups(dataset_dir)
    if len(groups) < SPLIT_SIZE:
        raise ValueError(f"only {len(groups)} site group(s) in {dataset_dir}; a split needs {SPLIT_SIZE}")
    ordered = sorted(
        groups, key=lambda site_hash: (hashlib.sha256(f"{token}:{site_hash}".encode()).hexdigest(), site_hash)
    )
    chosen = sorted(name for site_hash in ordered[:SPLIT_SIZE] for name in groups[site_hash])
    return tuple(chosen)


def describe_split(dataset_dir: Path, files: tuple[str, ...] | list[str]) -> dict[str, object]:
    """Describe a split so it can be recorded beside a figure.

    ``label`` is the one-line form printed with a score and written into a
    recorded figure; ``key`` is the equality form, so two figures can be checked
    for comparability instead of the reader assuming it.
    """
    names = tuple(files)
    stories = tuple(Path(name).stem.split("_", 1)[0] for name in names)
    placeholders = split_placeholders(dataset_dir, names)
    total = split_placeholders(dataset_dir, tuple(_dataset_files(dataset_dir)))
    sites = sorted({_site_hash(dataset_dir, name) for name in names})
    return {
        "files": list(names),
        "stories": list(stories),
        "placeholders": placeholders,
        "total": total,
        "site_hashes": sites,
        "key": "|".join(stories),
        "label": f"held-out: {', '.join(stories)} ({placeholders} of {total} placeholders)",
    }
