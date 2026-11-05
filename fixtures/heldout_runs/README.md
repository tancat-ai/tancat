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
placeholders while the 2026-10-31 legs scored 113. The 113-placeholder sample must be built from the
**current** goldens, not from an archived copy of the tree:

```bash
python - <<'PY'
import json, shutil
from pathlib import Path

out = Path("scratch/dataset-113")
shutil.rmtree(out, ignore_errors=True)
out.mkdir(parents=True)
for src in Path("scripts/eval/dataset").glob("*.json"):
    data = json.loads(src.read_text(encoding="utf-8"))
    if data["id"] == "eval-005":
        for crit in data["golden_resolutions"]:
            if crit["criterion_index"] == 0:
                crit["placeholders"] = [p for p in crit["placeholders"] if p["description"] != "date of birth"]
    (out / src.name).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
PY

python scripts/eval/eval_harness.py rebuild \
  --evidence-dir fixtures/heldout_runs/2026-10-31/leg1_rag_on_bundled \
  --run-group 2026-10-31-leg1 \
  --dataset scratch/dataset-113 --dataset-size 113
```

The sample that produces is 113 placeholders and keys `9:9c867a239c27`; it re-scores the four
2026-10-31 legs to 102/113, 101/113, 101/113, 101/113 with gate 2 of 6, 4, 6 and 5.

**Do not build it with `git archive f538d4b scripts/eval/dataset`.** Those goldens predate the
target_page/outcome_page split: they carry `expected_page` and no `outcome_page`, so the re-score
reads an empty page and falls back to looking for a URL inside the locator. Every ASSERT whose
locator is `expect(page).to_have_url(...)` still matches that way, but the two page criteria keyed to
an element (`eval-001` c0 `product list`, `eval-004` c1 `alert demonstration header`) do not - gate 2
then reports 8, 6, 8 and 7 and looks like a change in the run. It is not: it is a stale sample. The
rebuild now refuses that dataset by name (d-0156), but the recipe must not tempt anyone to restore
it.

(`scratch/` is gitignored, so neither sample leaves the tree dirty; delete the folder afterwards if
you like. The paths are named relatively so Python resolves them on Windows too.)

The other three legs are the same command with `leg2_rag_off_bundled`, `leg3_rag_on_empty` and
`leg4_rag_off_empty` in `--evidence-dir` and their own `--run-group`. A rebuild refuses (exit 2) when
the declared size and the dataset it actually scored disagree, and when the dataset's goldens predate
the page split - both with the numbers and the rows named, so a leg cannot be stored against a sample
it was not scored on.

One `--run-group` per leg: that is the name `runs` lists and `diff-runs` takes. A rebuild never
invents a setting - anything not passed stays unknown in `run_settings`, and `runs` prints
`unknown`, not an empty string.

The numbers are pinned against `scripts/eval/known_gate_scores.json` by
`tests/test_eval_rescore.py`. A run with no committed evidence cannot be re-scored - the tool says
so (exit 5) rather than reading the missing evidence as a zero.
