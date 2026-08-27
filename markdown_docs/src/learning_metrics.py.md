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
