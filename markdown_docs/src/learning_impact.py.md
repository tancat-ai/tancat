# `src/learning_impact.py`

## Purpose

AI-059 lab-only controlled baseline runner. `ControlledBaselineRunner` runs a
fixed command once per `BaselineLeg`, restores that leg's immutable store
snapshot, uses a fresh evidence directory, extracts metrics, and persists
`<output>/<leg>/metrics.json` plus `baseline_report.json`.

The runner sets `AI059_DISABLE_AUTO_LEARN=1` (and compatibility aliases) while
leaving `RAG_ENABLED` unchanged, so warm legs can read restored patterns without
polluting subsequent legs. Commands may use `{evidence_dir}`, `{leg}`, and
`{store_target}` tokens; replacement is literal rather than `str.format` to
avoid modifying braces in generated Python.

`restore_store_snapshot` supports both files and directories and `None` for an
empty cold store. Each leg also writes opt-in RAG retrieval diagnostics to
`rag_diagnostics.jsonl`, including query descriptions, result sources,
selectors, confidence, and site hashes. This module is not imported by the
production generation path.
