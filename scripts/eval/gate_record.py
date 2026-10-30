"""The gate record: no figure without its mode and its seed configuration.

A bare ``78.8%`` is not a measurement. The same resolver scores differently
with the bundled RAG pack than without it, and that pack used to be built from
the same golden files the gate scores - so a number with no label cannot say
whether the tool was handed the answers (d-0060, j-0244).

Two rules, both mechanical:

* :func:`make_figure` refuses to build a figure without a non-empty ``mode``
  (what produced it: which leg, model or not) and ``seed`` (what the RAG store
  held). The label carries both, so the number can never travel alone.
* :func:`validate_record` checks a committed record against the rule: every
  figure this record owns carries both labels. The chain below it (``previous``)
  predates the rule and keeps its original shape; it must still name its
  provenance, so a stripped history entry is caught too.

No config system: two functions over plain dicts.
"""

from __future__ import annotations

from typing import Any

__all__ = ["make_figure", "validate_record"]

#: The two labels every figure carries. A figure missing either is refused.
REQUIRED_LABELS: tuple[str, ...] = ("mode", "seed")


def _blank(value: object) -> bool:
    return not str(value or "").strip()


def make_figure(
    *,
    correct: int,
    total: int,
    mode: str,
    seed: str,
    note: str = "",
    **extra: Any,
) -> dict[str, Any]:
    """Build a labelled figure. Raises ``ValueError`` without mode or seed.

    Args:
        correct: Placeholders resolved correctly.
        total: Placeholders scored.
        mode: What produced the number (e.g. ``"static resolver-only (no model)"``).
        seed: What the RAG store held (e.g. ``"bundled pack, 113 patterns"``).
        note: Optional free text recorded beside the figure.
        **extra: Further keys to record (they cannot override the labelled ones).

    Returns:
        A dict with the gate-1 numbers, the two labels and a one-line ``label``
        that reads ``"<correct>/<total> (<pct>%) - mode: <mode>; seed: <seed>"``.

    Raises:
        ValueError: A label is blank, or the counts cannot form a figure.
    """
    for name in REQUIRED_LABELS:
        value = mode if name == "mode" else seed
        if _blank(value):
            raise ValueError(f"a recorded figure needs a non-empty '{name}' - a number without it cannot be read")
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
        "label": f"{correct}/{total} ({accuracy}%) - mode: {mode.strip()}; seed: {seed.strip()}",
    }
    if note:
        figure["note"] = note
    for key, value in extra.items():
        if key in figure:
            raise ValueError(f"{key!r} is set by the label rule and cannot be overridden")
        figure[key] = value
    return figure


def _figure_problems(figure: dict[str, Any], where: str) -> list[str]:
    problems: list[str] = []
    for name in REQUIRED_LABELS:
        if _blank(figure.get(name)):
            problems.append(f"{where}: no '{name}' - the figure cannot say what produced it or what the seed held")
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


def validate_record(payload: dict[str, Any], *, cells_key: str = "static_leg_2026_10_30") -> list[str]:
    """Return the label problems in a committed gate record; ``[]`` means clean.

    Checks the record itself and the four measured cells it holds. The
    ``previous`` chain predates the label rule, so it is checked for provenance
    only (a ``mode`` or a ``source``), never for the strict pair.
    """
    problems = _figure_problems(payload, "record")
    for name, cell in (payload.get(cells_key, {}).get("cells") or {}).items():
        if not isinstance(cell, dict):
            problems.append(f"{cells_key}.cells.{name}: not a figure")
            continue
        problems.extend(_figure_problems(cell, f"{cells_key}.cells.{name}"))

    entry = payload.get("previous")
    level = 1
    while isinstance(entry, dict):
        if _blank(entry.get("mode")) and _blank(entry.get("source")):
            problems.append(f"previous[{level}]: no mode and no source - the record lost its provenance")
        entry = entry.get("previous")
        level += 1
    return problems
