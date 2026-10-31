# `src/rag_switches.py`

## High-Level Purpose

Holds the four per-part switches for RAG: the bundled golden pack, the Playwright doc chunks, the learned positives and the contrastive negatives. `RAG_ENABLED=0` turns the whole leg off; these switches sit inside that gate and turn one part off at a time, so a part can be measured alone.

A part that is off is inert at both ends: the writer writes nothing, `RAGStore.retrieve()` does not return its rows, and `PlaceholderScorer` neither counts nor reads its evidence.

## Module Metadata

- **Lines:** ~150
- **Imports:** `os`, `typing.TYPE_CHECKING`
- **Job:** j-0247
- **Shipped:** 2026-10-30

## Switches

| Part constant | Environment variable | `entry_type` | Default |
|---|---|---|---|
| `PART_GOLDEN` | `RAG_GOLDEN` | `golden` | on |
| `PART_DOC_CHUNKS` | `RAG_DOC_CHUNKS` | `doc` | on |
| `PART_LEARNED` | `RAG_LEARNED` | `learned` | on |
| `PART_NEGATIVES` | `RAG_NEGATIVES` | `learned_negative` | on |

Values are `1` (on) and `0` (off); unset means on, so a default run behaves exactly as it did before the switches existed. Any other value raises `RAGSwitchError`.

## Functions

### `part_enabled(part, environ=None) -> bool`
Whether *part* is on. Raises `KeyError` for an unknown part and `RAGSwitchError` for an unknown value.

### `entry_type_enabled(entry_type, environ=None) -> bool`
Whether a store row of that entry type belongs to a part that is on. Rows no part owns (a legacy row with no `entry_type`) stay enabled.

### `disabled_entry_types(environ=None) -> frozenset[str]`
The entry types whose part is off right now — what `RAGStore.retrieve()` filters out.

### `validate_rag_switches(environ=None) -> dict[str, bool]`
Reads every switch once and raises on a bad value. Called from `TestOrchestrator._build_rag_retriever()` and from the top of `eval_resolver._cmd_static()`, so a typo is refused at startup rather than half-way through a run. The eval call is the one that protects a measurement: that path's retriever build catches every exception and logs "RAG enabled but failed to init - disabling", which would turn a typo into a no-RAG number that looks real.

## Key Design Decisions

- **Default on, read per call.** Each switch is read from the environment where it is used, so a lab run can flip one part between legs without rebuilding the retriever.
- **A typo is refused, not read as on.** Silently treating `RAG_GOLDEN=yes` as enabled would measure the wrong configuration and make the number look real.
- **The part switches do not replace `RAG_ENABLED`.** The global gate still decides whether a retriever is built at all, and the store still accepts writes when it is off — unchanged behaviour on the existing path.
- **`environ` is injectable** so tests never depend on the process environment.
