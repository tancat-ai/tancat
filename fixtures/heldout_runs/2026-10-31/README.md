# Full-mode run evidence: 2026-10-31 (t-1146, four legs)

The fresh four-leg gate run the owner ordered on 2026-10-31, recorded as the
evidence behind the full-mode gate-1 cell in
`scripts/eval/known_gate_scores.json` (`full_mode_2026_10_31`).

**The design is a 2x2: RAG on/off against a bundled store / an empty store**, one
leg at a time, ~42 minutes each, on main at `f538d4b` (the same commit for all
four - it was the tip of `origin/main` that morning).

## The four legs

| directory | RAG master | store at start | gate 1 (full 113) | gate 2 |
|---|---|---|---|---|
| `leg1_rag_on_bundled` | on | 113 golden + 35 docs | **102/113 = 90.3%** | 0 |
| `leg2_rag_off_bundled` | off | 113 golden + 35 docs (never built) | 101/113 = 89.4% | 0 |
| `leg3_rag_on_empty` | on | empty (0 entries verified) | 101/113 = 89.4% | 0 |
| `leg4_rag_off_empty` | off | empty (0 entries verified) | 101/113 = 89.4% | 0 |

**Legs 2 and 4 are the same configuration, deliberately.** `RAG_ENABLED=0` means the
store is never constructed, so a store that holds the pack and a store that holds
nothing are indistinguishable to the pipeline. They are the repetition the owner's
rule asks for - not an independent variable - and they agree exactly (101/113 both).

**RAG is worth +1 placeholder in full mode**: 102 with the pack against 101 without,
the single difference being `eval-003` (7/8 with the pack, 6/8 without). RAG on
against an empty store equals RAG off (101/113), the expected null.

## The one caveat in this run

`eval-005`'s 6 tests timed out at 300 s in **every** leg (`tests_executed=0`,
`tests_timed_out=true`), so gate 2 is blind on that story in all four. Its 24
placeholders still score 20/24 in every leg. A cell that hid this would repeat the
sin it exists to fix.

## What is committed, and why

The shape is the same as the other run directories (see `../README.md`):

- `manifest.json`, `results.json`, `summary.txt`, `verification_strength.json`
- `emitted/` - the nine generated test files
- `junit/` - the per-test outcomes

**Not committed:** the raw pytest logs (`pytest/`) - `rescore.py` does not need them,
and the parent README says they stay out - and the harness's `out/evidence`
directory, which is 224 MB of screenshots captured during test execution.

**Machine-neutral**, like every published run: pytest's `hostname` attribute is
removed from every `junit/*.xml`, and the absolute worktree prefix of the machine
that produced the run is stripped from skip messages so the paths read relative.
Test names and outcome counts are unchanged.

`leg-settings.json` and `launch-settings.json` were added on 2026-11-04: this run's model, temperature,
thinking and launch config were only ever written into a gitignored run log
(`scratch/t-1146/leg{1..4}/run.log` and `legs.json`). The two files copy those values into the
tracked tree and name that log as the source, so the record survives a clean checkout. The endpoint's
`/props` snapshot is `null` with the source "unknown": the pipeline fetched it but never wrote it
into this run's evidence.

## In the store

Since j-0273 these four legs are rows in `evidence/run_results.sqlite`, named
`2026-10-31-leg1` .. `2026-10-31-leg4`. Read them with `eval_harness.py runs`. Because they score
113 placeholders and the 2026-11-04 legs score 114, `diff-runs` refuses to draw a delta between the
two runs.

## Re-score it

No model, no browser, no live site. The dataset has grown since this run (it holds 114 placeholders
today), so re-score against the files as they stood at the run's own commit:

```bash
git archive f538d4b scripts/eval/dataset | tar -x -C /tmp/ds-f538d4b
python scripts/eval/rescore.py --run-dir fixtures/heldout_runs/2026-10-31/leg1_rag_on_bundled \
  --dataset /tmp/ds-f538d4b/scripts/eval/dataset
# -> GATE 1 102/113 = 90.3%, GATE 2 6
```

The other three legs re-score to 101/113 with gate 2 of 4, 6 and 5.

**The gate-2 figure has moved since this run was recorded, and the manifest's 0 no longer
reproduces.** The run recorded `gate2_false_greens: 0` on 2026-10-31. `t-1183` (2026-11-02) made the
rule stop accepting the product's own "verified by element" verdict for an element that is not the
golden one, so today's re-score finds 6, 4, 6 and 5 hollow passes in the same four legs. The gate-1
numbers are unchanged. Nothing here is retro-edited: the manifest keeps what the run recorded, and
the store row keeps what today's rule computes, which is why `runs` shows a gate-2 figure the
manifest does not.

Without `--dataset` the command scores this evidence against today's 114 placeholders and prints
103/114 - a different sample, not a change in the run.
