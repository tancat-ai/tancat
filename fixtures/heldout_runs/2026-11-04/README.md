# Full-mode run evidence: 2026-11-04 (t-1261, four legs)

The four-leg gate run the owner ordered on 2026-11-03/04, published so every number in it can be
re-scored from a clean checkout - no model, no browser, no live site.

**The design is the same 2x2 as `../2026-10-31/`: RAG on/off against a bundled store / an empty
store**, one leg at a time, on main at `d61bca7` (the same commit for all four). Where 2026-10-31
scores 113 placeholders, this run scores 114: `scripts/eval/dataset/eval-005` gained one criterion
between the two commits. That is why the two runs are **not comparable**, and why the store refuses
to draw a delta between them.

## The four legs

| directory | RAG master | store at start | gate 1 (full 114) | gate 2 |
|---|---|---|---|---|
| `leg1_rag_on_bundled` | on | the bundled pack (entry count not recorded) | **102/114 = 89.5%** | 4 |
| `leg2_rag_off_bundled` | off | the bundled pack (never built: `RAG_ENABLED=0`) | 102/114 = 89.5% | 5 |
| `leg3_rag_on_empty` | on | empty (the store was moved aside for this leg) | 103/114 = 90.4% | 3 |
| `leg4_rag_off_empty` | off | empty (never built: `RAG_ENABLED=0`) | 102/114 = 89.5% | 4 |

Gate 2 did not clear: three checks still pass on the wrong element on every leg (`eval-003` c0,
`eval-003` c5, `eval-006` c7), and `eval-002`'s two rows become skips instead of substitutions on
legs 3 and 4. `eval-005` is killed by the per-file clock in every leg (746 s against 730 s), so its
4 tests ran and 6 did not - the counts below keep that, which the 2026-10-31 record could not.

## What is committed, and why

The shape is the same as the other run directories (see `../README.md`):

- `manifest.json`, `results.json`, `summary.txt`, `verification_strength.json`
- `emitted/` - the nine generated test files
- `junit/` - the per-test outcomes, including `test_eval_005.xml` (the killed run)
- `leg-settings.json` - every value the store holds for these legs, each with the artefact it came
  from, and `null` + "unknown" where nothing recorded it
- `launch-settings.json` - the flat form the backfill passes to `--settings-json`, so the clock and
  the server launch config end up in the store row

**Not committed:** the raw pytest logs (`pytest/`), the 54 MB `leg*_out/` evidence directory, and
the harness log - `rescore.py` needs none of them.

**Machine-neutral:** pytest's `hostname` attribute is removed from every `junit/*.xml`, and the
absolute checkout prefix is stripped from skip messages so paths read relative. Two files in the run
directories carried it (`test_eval_001.xml`, `test_eval_003.xml` on most legs); a grep for
`C:\Users` across this directory returns nothing. The model is published as its file name; the full
local path stays in the run log, which is not committed.

## Re-score it

No model, no browser, no live site:

```bash
python scripts/eval/rescore.py --run-dir fixtures/heldout_runs/2026-11-04/leg1_rag_on_bundled
# -> GATE 1 102/114 = 89.5%, GATE 2 4
```

The other legs re-score to 102/114 (gate 2: 5), 103/114 (3) and 102/114 (4). All four were re-scored
from this directory after publication and matched their manifests exactly.

## Put the four legs in the store

The rows were written by `rebuild`, which re-scores this evidence and needs no model:

```bash
python scripts/eval/eval_harness.py rebuild \
  --evidence-dir fixtures/heldout_runs/2026-11-04/leg1_rag_on_bundled \
  --run-group 2026-11-04-t1261-leg1 \
  --rag-enabled on --rag-store "bundled pack (entry count not recorded)" \
  --dataset-size 114 --provider openai-local --model Qwen3.8-27B-UD-Q4_K_XL_v2.gguf \
  --temperature 0.0 --thinking off \
  --settings-json fixtures/heldout_runs/2026-11-04/launch-settings.json
```

Then `python scripts/eval/eval_harness.py runs` lists the leg with its model, store and dataset size,
and `diff-runs 2026-11-04-t1261-leg1 2026-11-04-t1261-leg3` compares two legs of the same sample.
The `2026-10-31` directory carries the same two files, because its launch config and model were only
ever written in a gitignored run log.

These four commands were run on j-0273 and the rows are in the store: `runs` prints the four legs
above with their manifests' gate-1 numbers, and `diff-runs` between leg1 and leg3 reports the one
placeholder that differs (`eval-003`).
