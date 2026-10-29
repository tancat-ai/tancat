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
Exception: when a backlog record cites a log line, that line is committed as a numbered excerpt
under `<run>/excerpts/` so a reviewer can open the citation from a clean checkout. The 2026-10-24
run does this (see its `README.md`); each excerpt names its source file and the `sed` command that
produced it.

Published runs are machine-neutral: pytest's `hostname` attribute is removed from every committed
`junit/*.xml`, and absolute local paths inside skip messages are made relative. Test names and
outcome counts are unchanged. The normalisation is documented per run (see `2026-10-24/README.md`).

Re-score:

```bash
python scripts/eval/rescore.py --run-dir fixtures/heldout_runs/2026-10-12
```

The numbers are pinned against `scripts/eval/known_gate_scores.json` by
`tests/test_eval_rescore.py`. A run with no committed evidence cannot be re-scored - the tool says
so (exit 5) rather than reading the missing evidence as a zero.
