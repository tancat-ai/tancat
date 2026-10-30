"""Which story files the eval holds out of the bundled RAG seed (j-0244 step 2).

The bundled RAG seed is built from the same ``eval-*.json`` golden keys the gate
scores, so the stories whose files are seeded cannot measure resolution - the
tool was handed their answers. The eval therefore scores a **held-out split**:
whole story files that are excluded from the seed (`src.rag_bundled.py`
``HELDOUT_STORY_FILES`` and its ``exclude=`` argument).

The owner's decision (2026-10-30): the 90% gate-1 target is read against that
split, and **which files are held back rotates each run**, so the sample grows
instead of the same 30 placeholders being scored forever.

* The default is still the fixed three - ``eval-007``, ``eval-008``,
  ``eval-010`` - so the figure recorded on 2026-10-30 keeps reproducing itself
  and stays comparable with itself. Rotation is opted into.
* Rotation is deterministic: a SHA-256 of the selector and the file name, never
  Python's ``hash()`` (randomised per process) and never filesystem order. Two
  runs on the same day (or with the same seed) pick the same split; a different
  day (or seed) picks a different one.
* An explicit list of files is allowed, and is validated: a name that is not a
  dataset file, or a file with no scored placeholders, is refused rather than
  silently dropped - a short split that looks full is the failure this whole
  job exists to stop.

Selectors (one flag on the eval resolver, ``--heldout-split``)::

    --heldout-split default                # the fixed three (also: no flag)
    --heldout-split date                   # today; stable all day, moves tomorrow
    --heldout-split date:2026-10-30         # a named day, for re-running a split
    --heldout-split seed:42                 # the same split every time, for that seed
    --heldout-split eval-001_x.json,eval-005_y.json,eval-006_z.json

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
    "split_files",
    "split_placeholders",
]

#: How many whole story files a split holds. Three keeps the split at roughly
#: 25-30 of the 113 scored placeholders, the size the first split used.
SPLIT_SIZE = 3

#: The fixed split the 2026-10-30 figure was measured on. Kept as the default so
#: that figure stays reproducible and comparable with itself (j-0244 step 2).
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


def _scored_files(dataset_dir: Path) -> list[str]:
    """The dataset file names that carry at least one scored placeholder."""
    names: list[str] = []
    for path in sorted(dataset_dir.glob("eval-*.json")):
        if split_placeholders(dataset_dir, (path.name,)) > 0:
            names.append(path.name)
    return names


def _from_explicit_list(dataset_dir: Path, selector: str) -> tuple[str, ...]:
    """An explicit comma-separated file list, validated (never silently trimmed)."""
    wanted = tuple(item.strip() for item in selector.split(",") if item.strip())
    for name in wanted:
        if not (dataset_dir / name).is_file():
            raise ValueError(f"{name!r} is not a dataset file in {dataset_dir}")
        if split_placeholders(dataset_dir, (name,)) == 0:
            raise ValueError(f"{name!r} carries no scored placeholders - it cannot be held out")
    if len(wanted) != SPLIT_SIZE or len(set(wanted)) != SPLIT_SIZE:
        raise ValueError(
            f"a split is {SPLIT_SIZE} different whole story files, not {len(wanted)} ({len(set(wanted))} distinct)"
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
        The chosen file names, in the order given (explicit) or sorted by the
        deterministic hash (rotation).

    Raises:
        ValueError: the selector is ambiguous, or an explicit list is invalid.
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
            f"or name the {SPLIT_SIZE} story files"
        )

    scored = _scored_files(dataset_dir)
    if len(scored) < SPLIT_SIZE:
        raise ValueError(f"only {len(scored)} scored dataset file(s) in {dataset_dir}; a split needs {SPLIT_SIZE}")
    ordered = sorted(scored, key=lambda name: (hashlib.sha256(f"{token}:{name}".encode()).hexdigest(), name))
    return tuple(ordered[:SPLIT_SIZE])


def describe_split(dataset_dir: Path, files: tuple[str, ...] | list[str]) -> dict[str, object]:
    """Describe a split so it can be recorded beside a figure.

    ``label`` is the one-line form printed with a score and written into a
    recorded figure; ``key`` is the equality form, so two figures can be checked
    for comparability instead of the reader assuming it.
    """
    names = tuple(files)
    stories = tuple(Path(name).stem.split("_", 1)[0] for name in names)
    placeholders = split_placeholders(dataset_dir, names)
    total = split_placeholders(dataset_dir, tuple(p.name for p in sorted(dataset_dir.glob("eval-*.json"))))
    return {
        "files": list(names),
        "stories": list(stories),
        "placeholders": placeholders,
        "total": total,
        "key": "|".join(stories),
        "label": f"held-out: {', '.join(stories)} ({placeholders} of {total} placeholders)",
    }
