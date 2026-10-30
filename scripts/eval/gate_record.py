"""The gate record: no figure without its mode, its seed and its split.

A bare ``78.8%`` is not a measurement. The same resolver scores differently
with the bundled RAG pack than without it, and that pack is built from the same
golden files the gate scores - so a number with no label cannot say whether the
tool was handed the answers (d-0060, j-0244).

Three rules, all mechanical:

* :func:`make_figure` refuses to build a figure without a non-empty ``mode``
  (what produced it: which leg, model or not), ``seed`` (what the RAG store
  held) and ``split`` (which story files were held out, and how many
  placeholders that is). The label carries all three, so the number can never
  travel alone.
* :func:`compare_figures` says whether two figures may be read against each
  other. Two figures from different splits are **not comparable** - they are
  scores on different samples - and it says so instead of leaving the reader to
  assume.
* :func:`validate_record` checks a committed record against both rules: every
  figure this record owns carries all three labels, every cell carries a
  comparability note and the list of cells it may be read against, no cell may
  claim comparability across splits, and a held-out cell carries its per-file
  breakdown (so a rotation that keeps landing on an easy file is visible next to
  the number). The chain below the record (``previous``) predates the rule and
  keeps its original shape; it must still name its provenance, so a stripped
  history entry is caught too.

No config system: three functions over plain dicts.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

__all__ = ["compare_figures", "make_figure", "validate_record"]

#: The three labels every figure carries. A figure missing any is refused.
REQUIRED_LABELS: tuple[str, ...] = ("mode", "seed", "split")

#: Split kinds. ``heldout`` = a subset of story files excluded from the seed;
#: ``full`` = every story (the number a reader must not read as the headline).
SPLIT_KINDS: tuple[str, ...] = ("heldout", "full")


def _blank(value: object) -> bool:
    return not str(value or "").strip()


def make_figure(
    *,
    correct: int,
    total: int,
    mode: str,
    seed: str,
    split: str,
    split_key: str = "",
    split_kind: str = "heldout",
    split_files: list[str] | None = None,
    per_file: dict[str, str] | None = None,
    note: str = "",
    **extra: Any,
) -> dict[str, Any]:
    """Build a labelled figure. Raises ``ValueError`` without mode, seed or split.

    Args:
        correct: Placeholders resolved correctly.
        total: Placeholders scored.
        mode: What produced the number (e.g. ``"static resolver-only (no model)"``).
        seed: What the RAG store held (e.g. ``"bundled pack, 113 patterns"``).
        split: The split the number is scored on (e.g.
            ``"held-out: eval-007, eval-008, eval-010 (30 of 113 placeholders)"``).
        split_key: Equality form of the split (e.g. ``"eval-007|eval-008|eval-010"``);
            defaults to the label. Two figures are comparable only when this matches.
        split_kind: ``"heldout"`` (a held-out subset) or ``"full"`` (every story).
        split_files: The files the split holds out. Required in a committed record
            for a held-out cell: the site-separation guard reads it.
        per_file: Per-story counts beside the number (``{"eval-007": "7/13"}``).
            Required in a committed record for a held-out cell.
        note: Optional free text recorded beside the figure.
        **extra: Further keys to record (they cannot override the labelled ones).

    Returns:
        A dict with the gate-1 numbers, the three labels and a one-line ``label``
        that reads ``"<correct>/<total> (<pct>%) - mode: ...; seed: ...; split: ..."``.

    Raises:
        ValueError: A label is blank, the counts cannot form a figure, or the
            split kind is unknown.
    """
    values = {"mode": mode, "seed": seed, "split": split}
    for name in REQUIRED_LABELS:
        if _blank(values[name]):
            raise ValueError(f"a recorded figure needs a non-empty '{name}' - a number without it cannot be read")
    if split_kind not in SPLIT_KINDS:
        raise ValueError(f"split_kind must be one of {SPLIT_KINDS}, got {split_kind!r}")
    if total <= 0:
        raise ValueError(f"total must be positive, got {total}")
    if not 0 <= correct <= total:
        raise ValueError(f"correct ({correct}) must be between 0 and {total}")

    accuracy = round(100 * correct / total, 1)
    figure: dict[str, Any] = {
        "gate1_correct": correct,
        "gate1_total": total,
        "gate1_accuracy_pct": accuracy,
        "mode": mode.strip(),
        "seed": seed.strip(),
        "split": split.strip(),
        "split_key": (split_key or split).strip(),
        "split_kind": split_kind,
        "label": (
            f"{correct}/{total} ({accuracy}%) - mode: {mode.strip()}; seed: {seed.strip()}; split: {split.strip()}"
        ),
    }
    if split_files is not None:
        figure["split_files"] = list(split_files)
    if per_file is not None:
        figure["per_file"] = dict(per_file)
    if note:
        figure["note"] = note
    for key, value in extra.items():
        if key in figure:
            raise ValueError(f"{key!r} is set by the label rule and cannot be overridden")
        figure[key] = value
    return figure


def compare_figures(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """Say whether *a* and *b* may be read against each other.

    Two figures from **different splits** are not comparable: they are scores on
    different samples. Two figures from the same split in **different modes** are
    not comparable either. A different seed on the same split in the same mode is
    the one comparison that is always allowed - that is the with/without-pack
    pair the leak was measured with.

    Returns:
        ``{"comparable": bool, "why": <one sentence naming both sides>}``.
    """
    a_key = str(a.get("split_key") or a.get("split") or "")
    b_key = str(b.get("split_key") or b.get("split") or "")
    a_split = str(a.get("split") or "") or a_key
    b_split = str(b.get("split") or "") or b_key
    a_mode = str(a.get("mode") or "")
    b_mode = str(b.get("mode") or "")

    if a_key != b_key:
        return {
            "comparable": False,
            "why": (
                f"not comparable: {a_split} and {b_split} are different splits, "
                "so the two numbers are scores on different samples"
            ),
        }
    if a_mode != b_mode:
        return {
            "comparable": False,
            "why": f"not comparable: same split ({a_split}) but different modes ({a_mode} vs {b_mode})",
        }
    same_seed = str(a.get("seed") or "") == str(b.get("seed") or "")
    return {
        "comparable": True,
        "why": (
            f"comparable: same split ({a_split}) and same mode ({a_mode})"
            + ("" if same_seed else "; only the seed configuration differs, which is the measured variable")
        ),
    }


def _figure_problems(figure: dict[str, Any], where: str) -> list[str]:
    problems: list[str] = []
    for name in REQUIRED_LABELS:
        if _blank(figure.get(name)):
            problems.append(
                f"{where}: no '{name}' - the figure cannot say what produced it, what the seed held "
                "or which stories it was scored on"
            )
    label = str(figure.get("label") or "")
    if figure.get("gate1_correct") is not None and not _blank(label):
        for name in REQUIRED_LABELS:
            if f"{name}:" not in label:
                problems.append(f"{where}: the label does not state its '{name}'")
    total = figure.get("gate1_total")
    correct = figure.get("gate1_correct")
    if isinstance(total, int) and isinstance(correct, int) and not 0 <= correct <= total:
        problems.append(f"{where}: {correct}/{total} is not a possible score")
    return problems


def _cell_problems(cell: dict[str, Any], where: str, dataset_dir: Path | None) -> list[str]:
    problems = _figure_problems(cell, where)
    if _blank(cell.get("comparability")):
        problems.append(
            f"{where}: no 'comparability' note - a reader must not have to assume what it may be read against"
        )
    if not isinstance(cell.get("comparable_with"), list):
        problems.append(f"{where}: 'comparable_with' must be a list (empty when nothing compares)")
    if cell.get("split_kind") != "heldout":
        return problems

    if not cell.get("per_file"):
        problems.append(
            f"{where}: no per-file breakdown - a rotation that keeps landing on an easy file would be invisible"
        )
    if not cell.get("split_files"):
        problems.append(f"{where}: no 'split_files' - the site-separation guard cannot check the split")
        return problems

    # t-1119: the seed's +20 golden bonus answers on site_hash, not on the file.
    # A split that holds one file of a site out and leaves its sibling seeded
    # hands the answer back, so the record is refused rather than merely avoided.
    from heldout_split import separating_pairs

    resolved = dataset_dir or _default_dataset_dir()
    missing = [name for name in cell["split_files"] if not (resolved / str(name)).is_file()]
    if missing:
        problems.append(f"{where}: split_files names {missing[0]!r}, which is not in {resolved}")
        return problems
    for held, seeded, site_hash in separating_pairs(resolved, cell["split_files"]):
        problems.append(
            f"{where}: split holds out {held} while {seeded} stays seeded, and both share site_hash "
            f"{site_hash} - the seed would hand its answers back (t-1119)"
        )
    return problems


def _default_dataset_dir() -> Path:
    """The committed eval dataset (``scripts/eval/dataset``), for the site guard."""
    return Path(__file__).resolve().parent / "dataset"


def validate_record(
    payload: dict[str, Any],
    *,
    cells_key: str = "static_leg_2026_10_30",
    dataset_dir: Path | None = None,
) -> list[str]:
    """Return the label problems in a committed gate record; ``[]`` means clean.

    Checks the record itself, the four measured cells it holds, and whether any
    cell claims comparability across splits. The ``previous`` chain predates the
    label rule, so it is checked for provenance only (a ``mode`` or a
    ``source``), never for the strict trio.
    """
    problems = _figure_problems(payload, "record")
    if not isinstance(payload.get("split_placeholders"), int):
        problems.append("record: no integer 'split_placeholders' beside the split")
    elif payload.get("gate1_total") != payload["split_placeholders"]:
        problems.append(
            f"record: gate1_total {payload.get('gate1_total')} is not the split's placeholder count "
            f"{payload['split_placeholders']}"
        )

    raw_cells = (payload.get(cells_key, {}) or {}).get("cells") or {}
    site_dataset_dir = dataset_dir or _default_dataset_dir()
    cells: dict[str, dict[str, Any]] = {}
    for name, cell in raw_cells.items():
        where = f"{cells_key}.cells.{name}"
        if not isinstance(cell, dict):
            problems.append(f"{where}: not a figure")
            continue
        cells[name] = cell
        problems.extend(_cell_problems(cell, where, site_dataset_dir))

    # A cell may not claim comparability with another split (j-0244 step 2).
    for name, cell in cells.items():
        for other_name in cell.get("comparable_with") or []:
            other = cells.get(other_name)
            if other is None:
                problems.append(f"{cells_key}.cells.{name}: comparable_with names {other_name!r}, which is not a cell")
                continue
            if str(cell.get("split_key")) != str(other.get("split_key")):
                problems.append(
                    f"{cells_key}.cells.{name}: claims comparability with {other_name!r}, which scores a "
                    "different split - different splits are not comparable"
                )

    entry = payload.get("previous")
    level = 1
    while isinstance(entry, dict):
        if _blank(entry.get("mode")) and _blank(entry.get("source")):
            problems.append(f"previous[{level}]: no mode and no source - the record lost its provenance")
        entry = entry.get("previous")
        level += 1
    return problems
