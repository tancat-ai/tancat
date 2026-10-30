"""Per-part switches for RAG, so each part can be measured alone (j-0247).

RAG has four parts:

======  ================  ======================  ==========================
part    entry type         written by              read / scored in
======  ================  ======================  ==========================
golden  ``golden``         ``RAGStore.add_patterns``        bonus (+20)
                           (bundled pack, rag_ingest)
docs    ``doc``            ``RAGStore.add_docs``            retrieval only
                           (bundled docs, rag_ingest)       (never scored)
learned ``learned``        ``rag_learn.learn_from_evidence``  bonus (+5)
negatives ``learned_negative`` ``rag_learn.learn_negatives_from_evidence``
                                                             penalty (-5)
======  ================  ======================  ==========================

``RAG_ENABLED=0`` turns the whole leg off. These four switches sit *inside*
that gate and turn one part off at a time, so a baseline can be taken with one
part dark and the rest as they are.

Values are ``1`` (on) or ``0`` (off); unset means **on**, so a default run
behaves exactly as it did before these switches existed. Any other value is
refused with :class:`RAGSwitchError` rather than silently treated as on - a
typo must not quietly measure the wrong thing.

An off part is inert at both ends: the writer writes nothing, retrieval does
not return its rows, and the scorer neither counts its evidence nor reads it.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Mapping

__all__ = [
    "PART_DOC_CHUNKS",
    "PART_ENTRY_TYPES",
    "PART_GOLDEN",
    "PART_LEARNED",
    "PART_NEGATIVES",
    "PART_SWITCH_ENV",
    "RAGSwitchError",
    "disabled_entry_types",
    "part_enabled",
    "validate_rag_switches",
]

#: The bundled golden pack: verified placeholder -> selector mappings.
PART_GOLDEN = "golden"
#: The Playwright documentation chunks (retrieved, never scored today).
PART_DOC_CHUNKS = "doc_chunks"
#: Learned positives from evidence (``entry_type="learned"``).
PART_LEARNED = "learned"
#: Contrastive negatives from failed steps (``entry_type="learned_negative"``).
PART_NEGATIVES = "negatives"

#: Part -> environment variable that switches it.
PART_SWITCH_ENV: dict[str, str] = {
    PART_GOLDEN: "RAG_GOLDEN",
    PART_DOC_CHUNKS: "RAG_DOC_CHUNKS",
    PART_LEARNED: "RAG_LEARNED",
    PART_NEGATIVES: "RAG_NEGATIVES",
}

#: Part -> the ``entry_type`` its rows carry in the store.
PART_ENTRY_TYPES: dict[str, str] = {
    PART_GOLDEN: "golden",
    PART_DOC_CHUNKS: "doc",
    PART_LEARNED: "learned",
    PART_NEGATIVES: "learned_negative",
}

_ENTRY_TYPE_TO_PART: dict[str, str] = {entry: part for part, entry in PART_ENTRY_TYPES.items()}

_ON = "1"
_OFF = "0"


class RAGSwitchError(ValueError):
    """A RAG part switch holds a value that is neither ``1``, ``0`` nor unset.

    Refused loudly: silently reading a typo as "on" would measure the wrong
    configuration and make the number look real.
    """


def _read_switch(env_var: str, environ: Mapping[str, str] | None = None) -> bool:
    """Return the switch in *env_var* as a bool; raise on anything unexpected."""
    source = os.environ if environ is None else environ
    raw = source.get(env_var, "")
    value = str(raw).strip()
    if value in ("", _ON):
        return True
    if value == _OFF:
        return False
    raise RAGSwitchError(f"{env_var}={raw!r} is not a switch value: set it to 1 (on, the default) or 0 (off)")


def part_enabled(part: str, environ: Mapping[str, str] | None = None) -> bool:
    """Whether *part* of RAG is switched on (default on when unset).

    Args:
        part: One of :data:`PART_SWITCH_ENV`'s keys.
        environ: Injectable environment (tests); defaults to ``os.environ``.

    Raises:
        KeyError: *part* is not a known part.
        RAGSwitchError: the switch holds an unknown value.
    """
    return _read_switch(PART_SWITCH_ENV[part], environ)


def entry_type_enabled(entry_type: str, environ: Mapping[str, str] | None = None) -> bool:
    """Whether a store row of *entry_type* belongs to a part that is on.

    Rows of an entry type that no part owns (a legacy row without an
    ``entry_type``) are not covered by any switch and stay enabled.
    """
    part = _ENTRY_TYPE_TO_PART.get(str(entry_type))
    if part is None:
        return True
    return part_enabled(part, environ)


def disabled_entry_types(environ: Mapping[str, str] | None = None) -> frozenset[str]:
    """The ``entry_type`` values whose part is switched off right now."""
    return frozenset(entry_type for part, entry_type in PART_ENTRY_TYPES.items() if not part_enabled(part, environ))


def validate_rag_switches(environ: Mapping[str, str] | None = None) -> dict[str, bool]:
    """Read every switch once; raise :class:`RAGSwitchError` on a bad value.

    Called when the retriever is built, so a typo is refused at startup rather
    than half-way through a run.
    """
    return {part: part_enabled(part, environ) for part in PART_SWITCH_ENV}
