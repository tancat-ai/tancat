# `src/learning_metrics.py`

## Purpose

Pure AI-059 analyzer for existing `*.evidence.json` sidecars. It measures
per-test progress without golden locators or changes to generation behavior.
Ratios are returned as `0.0..1.0` values.

## Public API

- `analyze_sidecar(data)` analyzes one loaded sidecar mapping.
- `analyze_sidecars(evidence_dir)` scans sidecars in deterministic filename order,
  skipping malformed files and counting them in `errors`.
- `extract_metrics` is an alias for `analyze_sidecars`.
- `LearningImpactMetrics.to_dict()` produces a JSON-serializable report,
  including optional per-test records.

`mean_pass_depth` is the average number of contiguous passed steps before the
first failure divided by the observed step count. `first_pass_green_rate` is
the proportion of sidecars whose test status is `passed`. False positives are
never inferred from a pass: a human review must annotate `false_positive` on
the sidecar/test (or a step). The failure breakdown counts failed tests in the
locator, assertion, navigation, and infrastructure/timeout classes.

## Public API Additions

Refreshed 2026-10-02: public symbols present in the source and not listed above.

- `TestEvidenceMetric` (class): Metrics and classification for one evidence sidecar.
- `LearningImpactMetrics.to_dict` (method of `LearningImpactMetrics`): `LearningImpactMetrics.to_dict(*, include_per_test: bool = True) -> dict[str, Any]` - Return JSON-serializable metrics. per_test is useful for manual review and is included by default; callers persisting a compact run summary can disable it.
- `LearningImpactMetrics.from_dict` (method of `LearningImpactMetrics`): `LearningImpactMetrics.from_dict(data: Mapping[str, Any]) -> LearningImpactMetrics` - Load a previously persisted metric payload.
- `FAILURE_CLASSES` (constant): `FAILURE_CLASSES = ('locator_failure', 'assertion_failure', 'navigation_fail...`


## How It Works (Internals)

Private `_`-helpers - the module's real logic (8 items). Grouped under the public function that calls them.

### `analyze_sidecar(data: Mapping[str, Any]) -> TestEvidenceMetric` - function

- `_test_status(data: Mapping[str, Any], steps: Sequence[Mapping[str, Any]]) -> str` (function): Test status; calls `_status`, `_step_passed`; returns str.
- `_is_false_positive(data: Mapping[str, Any], steps: Sequence[Mapping[str, Any]] = ()) -> bool` (function): Read an explicit manual-review false-positive annotation. False positives cannot be inferred from a pass alone: a sidecar has no target envelope until a human has reviewed it. Several equivalent field locations are ac...
- `_normalise_failure_class(value: Any) -> str | None` (function): Normalise failure class; calls `_status`; returns str | None.
- `_declared_total_steps(data: Mapping[str, Any], observed_steps: Sequence[Mapping[str, Any]]) -> int` (function): Use an explicit planned-step count when a sidecar provides one.
- `_classify_step(step: Mapping[str, Any], test_error: str = '') -> str | None` (function): Classify step; calls `_error_text`, `_normalise_failure_class`, `_status`, `_step_result`, `classify_failure`; returns str | None.

### Internal utilities

- `_step_result(step: Mapping[str, Any]) -> Mapping[str, Any]` (function): Step result; returns Mapping[str, Any].
- `_bool_value(value: Any) -> bool` (function): Bool value; calls `_status`; returns bool.
- `_error_text(step: Mapping[str, Any], test_error: str = '') -> str` (function): Error text; calls `_step_result`; returns str.
