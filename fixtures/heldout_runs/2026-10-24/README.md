# Held-out run evidence: 2026-10-24

Two legs ran on 2026-10-24 for j-0196 (the popup/click fix, B-109). Both are
`full --regenerate`, same model (`Qwen3.8-27B-UD-Q4_K_XL_v2.gguf` at
`http://localhost:8080/v1`), temperature 0.0, pipeline linear, RAG on against the
bundled store (113 golden patterns + 35 doc chunks).

| leg | commit | purpose | gate 1 | gate 2 | tests |
|---|---|---|---|---|---|
| `ad489aa` | `ad489aa` | the PRE-fix baseline (guessed-URL deletion, no click fix) | 95/113 = 84.1% | 0 | 43/62 |
| `10d8a32` | `10d8a32` | the fix tip (dismissal + reveal + retry, B-109) | **97/113 = 85.8%** | 0 | 48/62 |

The re-scoreable bundle in this directory is the **10d8a32** leg. It is the run
B-110 and B-111 are recorded from, and it is what
`python scripts/eval/rescore.py --run-dir fixtures/heldout_runs/2026-10-24` reads.

## What is committed, and why

- `manifest.json`, `results.json`, `summary.txt`, `verification_strength.json` -
  the run metadata, per-placeholder results and per-test verdicts (same shape as
  the other run directories).
- `emitted/` - the nine generated test files.
- `junit/` - the per-test outcomes.

`excerpts/` is an addition to the layout for this run, because two backlog
records (B-109, B-110, B-111) cite log lines that live in files this repository
deliberately does not commit (the harness stderr and the raw pytest logs - see
`../README.md`). Each excerpt file names its source, keeps the ORIGINAL line
numbers in a left gutter so a `file:line` citation can be checked directly, and
states the `sed` command that produced it:

- `pipeline_stderr_10d8a32.txt` - the 10d8a32 harness stderr lines behind
  B-110's citations (the `#google_vignette` navigation, the 412-element capture,
  the observed trail).
- `pytest_test_eval_002_10d8a32.txt` - the eval-002 pytest log lines behind
  B-110 (`PageMismatchError`) and B-111 (the `Blue Top` timeout, the FAILED
  lines).
- `pipeline_stderr_ad489aa.txt` - the ad489aa harness stderr lines behind
  B-109's citation (the `cartModal` click timeout).
- `emitted_test_eval_002_ad489aa.py` - test_06 from the ad489aa leg's emitted
  file, showing the skip that became a real assertion in the 10d8a32 leg (B-111).

The full logs are regenerable: re-running the same command on the same commit
reproduces the shape (`grep -n` in the excerpt headers names the exact source
path). They are not committed because the raw logs carry local absolute paths
and are ~620-680 KB each.

## Normalised for publication

The repository is public until release, so the `junit/` XML in every committed
run (not only this one) is the run's output with two machine-identifying fields
removed, and nothing else touched:

- pytest's `hostname="<machine>"` attribute is removed from `<testsuite>`.
- absolute local paths inside skip messages are made relative, in the same form
  the sibling `classname`/`name` attributes already use, e.g.
  `scratch/gate1_out_.../test_eval_001.py:44: specificity guard: ...`.

Test, failure, skip and error counts and every test name are unchanged - the
normalisation was scripted against a per-file fingerprint and refuses to write
when the fingerprint would change. The excerpts are CR-free so one file line is
one line for every reader, and each one states its citation convention (left
gutter = the original log line; the entries give both that and the excerpt's own
file line).

## Re-score

```bash
python scripts/eval/rescore.py --run-dir fixtures/heldout_runs/2026-10-24
```

Expected: `GATE 1 (resolution accuracy): 97/113 = 85.8%`, `GATE 2 (hollow
passes): 0`.

This run is not pinned in `scripts/eval/known_gate_scores.json` - it is the
evidence for the B-109 fix and the two records it exposed, not a gate-chain
entry. `tests/test_eval_rescore.py` pins only the chained runs and is unaffected.
