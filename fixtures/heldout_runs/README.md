# Held-out run evidence

Committed re-score input for the live held-out gate runs, so a recorded gate number can be
recomputed from the repository alone - no model, no browser, no live site.

Layout: one directory per run, named for the run date. The files are exactly what
`scripts/eval/eval_evidence.py` reads:

- `manifest.json` - run metadata and the gate numbers this run recorded.
- `results.json` - the per-placeholder result.
- `emitted/` - the per-story generated test files.
- `junit/` - the per-test outcomes (pytest JUnit XML).
- `verification_strength.json` - the product's per-test verdicts.

Not committed: the raw pytest logs (`pytest/`) and the harness log - `rescore.py` does not need them.

Re-score:

```bash
python scripts/eval/rescore.py --run-dir fixtures/heldout_runs/2026-10-12
```

The numbers are pinned against `scripts/eval/known_gate_scores.json` by
`tests/test_eval_rescore.py`. A run with no committed evidence cannot be re-scored - the tool says
so (exit 5) rather than reading the missing evidence as a zero.
