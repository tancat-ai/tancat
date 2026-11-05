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

A run directory may also carry the settings the store needs, when the evidence itself does not hold
them:

- `leg-settings.json` - one entry per leg: its `run_group`, the RAG store it ran against, and for
every value the artefact it came from - or `null` with a source that says `unknown`. Nothing is
inferred. `2026-10-31` and `2026-11-04` both carry one, because their model and launch config were
only ever written in a gitignored run log.
- `launch-settings.json` - the flat form of the same values, passed to `--settings-json` so the
per-file clock and the server launch config land in the store row.

## Re-score

```bash
python scripts/eval/rescore.py --run-dir fixtures/heldout_runs/2026-10-12
```

A run scored against a dataset that has since changed needs the dataset as it stood: the
2026-10-31 legs score 113 placeholders and today's dataset holds 114, so pass
`--dataset <dir>` (see `2026-10-31/README.md` for the `git archive` line that produces it).
Without it, `rescore` scores the old evidence against today's golden keys and the number moves.

## Put a run's legs in the store

The single place for run numbers is `evidence/run_results.sqlite` (`eval_runs`), read with
`eval_harness.py runs`. Kept evidence that is not in the store yet goes in with `rebuild`, which
re-scores the kept code and needs no model, no browser and no site:

```bash
python scripts/eval/eval_harness.py rebuild \
  --evidence-dir fixtures/heldout_runs/2026-11-04/leg1_rag_on_bundled \
  --run-group 2026-11-04-t1261-leg1 \
  --rag-enabled on --rag-store "bundled pack (entry count not recorded)" \
  --dataset-size 114 --provider openai-local --model Qwen3.8-27B-UD-Q4_K_XL_v2.gguf \
  --temperature 0.0 --thinking off \
  --settings-json fixtures/heldout_runs/2026-11-04/launch-settings.json
```

A rebuild re-scores the kept code against the dataset it resolves, and today's dataset holds 114
placeholders while the 2026-10-31 legs scored 113. Name that sample, or the rebuild scores old
evidence against today's golden keys - and refuses, because the declared size would not match:

```bash
mkdir -p scratch/dataset-f538d4b
git archive f538d4b scripts/eval/dataset | tar -x -C scratch/dataset-f538d4b

python scripts/eval/eval_harness.py rebuild \
  --evidence-dir fixtures/heldout_runs/2026-10-31/leg1_rag_on_bundled \
  --run-group 2026-10-31-leg1 \
  --dataset scratch/dataset-f538d4b/scripts/eval/dataset --dataset-size 113
```

(`scratch/` is gitignored, so the extracted dataset leaves the tree clean; delete the folder
afterwards if you like. It is named relatively so Python resolves it on Windows too.)

The other three legs are the same command with `leg2_rag_off_bundled`, `leg3_rag_on_empty` and
`leg4_rag_off_empty` in `--evidence-dir` and their own `--run-group`. A rebuild refuses (exit 2,
both numbers named) when the declared size and the dataset it actually scored disagree, so a leg
can no longer say size 113 and score out of 114.

One `--run-group` per leg: that is the name `runs` lists and `diff-runs` takes. A rebuild never
invents a setting - anything not passed stays unknown in `run_settings`, and `runs` prints
`unknown`, not an empty string.

The numbers are pinned against `scripts/eval/known_gate_scores.json` by
`tests/test_eval_rescore.py`. A run with no committed evidence cannot be re-scored - the tool says
so (exit 5) rather than reading the missing evidence as a zero.
