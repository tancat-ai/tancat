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

**B-048 (2026-09-06):** `restore_store_snapshot` now refuses any target that
is, contains, or lies inside the production RAG store
(`get_storage().rag_path()`) or its `.embedder.json` companion — the AI-059
lab rebuild wiped the production store this way on 2026-08-31. Pass
`allow_production_store=True` for a deliberate, production-aware lab run.
Guard tests: `tests/test_learning_impact.py` (`test_restore_refuses_*`).

## Public API Additions

Refreshed 2026-10-02: public symbols present in the source and not listed above.

- `BaselineLegResult` (class): Result and persisted metadata for one leg.
- `BaselineLegResult.succeeded` (method of `BaselineLegResult`): `BaselineLegResult.succeeded() -> bool`
- `BaselineLegResult.to_dict` (method of `BaselineLegResult`): `BaselineLegResult.to_dict() -> dict[str, Any]`
- `ControlledBaselineReport` (class): Aggregate report containing independently persisted leg results.
- `ControlledBaselineReport.to_dict` (method of `ControlledBaselineReport`): `ControlledBaselineReport.to_dict() -> dict[str, Any]`
- `measurement_environment` (function): `measurement_environment(base: Mapping[str, str] | None = None) -> dict[str, str]` - Build an environment that disables all known auto-learning hooks. RAG_ENABLED is deliberately *not* changed: warm legs must still read their restored store. The extra aliases support older generated conftest templ...
- `ControlledBaselineRunner.__init__` (method of `ControlledBaselineRunner`): `ControlledBaselineRunner.__init__(*, evidence_root: str | Path, output_root: str | Path, store_target: str | Path | None = None, cwd: str | Path | None = None, base_env: Mapping[str, str] | None = None, timeout_s: float = 1800.0, metadata: Mapping[str, Any] | None = None) -> None`
- `lab_site_hash` (function): `lab_site_hash(identity: str = DEFAULT_LAB_SITE_IDENTITY) -> str` - Deterministic sentinel site hash for a lab store identity string.
- `build_lab_identity` (function): `build_lab_identity(*, site: str, input_version: str = '', story_set: str = '', run_tag: str = '') -> str` - Compose a structured lab identity for one experimental cell. A cell is scoped by (site, input/site-edit version, story set, run tag) rather than a single constant or the fragile host:port hash. Distinct cells produce...
- `rebuild_warm_store_from_evidence` (function): `rebuild_warm_store_from_evidence(evidence_dir: str | Path, *, store: Any, lab_site_identity: str = DEFAULT_LAB_SITE_IDENTITY, learn_negatives: bool = True) -> dict[str, int]` - Re-derive a lab-scoped warm RAG store from source evidence sidecars. Unlike the production learn path (rag_learn.learn_from_evidence), every pattern is tagged with a fixed LAB sentinel site_hash (derived from...
- `AUTO_LEARN_DISABLE_ENV` (constant): `AUTO_LEARN_DISABLE_ENV = 'AI059_DISABLE_AUTO_LEARN'`
- `AUTO_LEARN_DISABLE_VALUE` (constant): `AUTO_LEARN_DISABLE_VALUE = '1'`
- `DEFAULT_LAB_SITE_IDENTITY` (constant): `DEFAULT_LAB_SITE_IDENTITY = 'ai059-lab:ecommerce'`


## How It Works (Internals)

Private `_`-helpers - the module's real logic (8 items). Grouped under the public function that calls them.

### `restore_store_snapshot(snapshot: Path | None, target: Path, *, allow_production_store: bool = False) -> None` - function

- `_refuse_production_store_target(target: Path) -> None` (function): Raise when target would destroy the production RAG store (B-048). The 2026-08-31 AI-059 lab rebuild passed the production store path as the restore target and shutil.rmtree erased the golden/learned patterns w...

### `ControlledBaselineRunner.run(command: Sequence[str], legs: Sequence[BaselineLeg]) -> ControlledBaselineReport` - method of `ControlledBaselineRunner`

- `_storage_environment(store_target: Path) -> dict[str, str]` (function): Map a conventional .../evidence/rag_store.db target to storage env.
- `_with_lab_tokens(command: Sequence[str], *, evidence_dir: Path, leg: str, store_target: Path | None) -> list[str]` (function): Replace only the runner's explicit tokens in a command. We intentionally do not call str.format: generated Python snippets often contain braces. A caller may use {evidence_dir}, {leg}, and {store_target}...
- `_sha256_path(path: Path | None) -> str | None` (function): Return a deterministic SHA-256 for a snapshot file or directory.
- `_safe_leg_name(name: str) -> str` (function): Safe leg name; calls `isalnum`; returns str.
- `_decode_output(value: str | bytes | None) -> str` (function): Decode output; calls `decode`; returns str.

### `rebuild_warm_store_from_evidence(evidence_dir: str | Path, *, store: Any, lab_site_identity: str = DEFAULT_LAB_SITE_IDENTITY, learn_negatives: bool = True) -> dict[str, int]` - function

- `_lab_pattern_for_step(step: dict[str, Any], sentinel: str) -> Any | None` (function): Map one evidence step to a sentinel-scoped LearnedPattern, or None.
- `_lab_negative_pattern_for_step(step: dict[str, Any], sentinel: str) -> Any | None` (function): Map one FAILED evidence step to a sentinel-scoped learned_negative, or None. AI-058 Slice 2: mirrors _lab_pattern_for_step (same action / label / locator gate + sentinel scoping) but only a *locator-class* fai...
