# Parity: where two modes, five reports and three surfaces must agree

Owner's words, 2026-10-29: "we might need a pre launch item to check that we are getting the same
output in pom and non pom. same for our evidence reports... and also of 3 input methods, cli,
streamlit and ci. we should check we have parity in situations where its expected."

This document says where parity IS expected, where it is NOT, and how it is measured. Without that
split the check is a swamp: every difference looks like a bug, and the real ones hide.

**Parity is parity of the product output, not of the interface.** Two runs agree when they produce
the same package, the same verdicts and the same report contents. Progress text, prompts, default
workspace paths and anything a person clicks are outside this gate by design.

## The fixed-input rule

With a live model every run differs, so parity is never measured on a fresh generation. One of:

- **one story, one skeleton, both modes** - the method of the archived comparator
  (`scripts/archive/debug_scripts/compare_pom_vs_standard.py`): parse the story once, generate ONE
  skeleton, hand that exact skeleton to both modes. Promoted here rather than re-invented.
- **a recorded set** - a package and an evidence set checked in under `fixtures/`, which is what
  `scripts/parity_check.py` uses today: `fixtures/golden_package/` and `fixtures/parity/sidecars/`.
  The sidecars deliberately do NOT sit in a directory named `evidence/` - that name is gitignored
  everywhere in this repo because it is the runtime output path, and a tracked fixture under it
  would need a negation exception that silently rots. A neutral name needs no exception.

Anything compared across two live model calls is noise, not parity.

## Axis 1 - POM vs flat, one fixed input

MUST agree:

- the set of tests produced (names and order) and the per-criterion verdict: resolved, skipped,
  unverified;
- the logical step sequence per test: action, target (selector or URL), and order;
- per-test pass/fail;
- evidence step count and per-step status;
- gate 1 and gate 2 numbers;
- bundle shape: the files a shopper of the export gets, minus the layout difference below.

Gate 1 and gate 2 are properties of a RUN, not of emitted source, so the offline check can only
compare them when a pair has been recorded. Until step 1b records `fixtures/parity/gates/pom.json`
and `flat.json` (each `{"gate1": ..., "gate2": ...}`), the row is printed as **pending** - not
skipped silently, and not guessed, because a guessed number would pass and prove nothing.

MAY differ (documented, checked as such, never failed):

- file layout: `pages/` plus test files (POM) vs one test file (flat);
- selectors inline (flat) vs carried by page-object methods (POM);
- step labels: the page-object call carries its label, the flat export drops it;
- export structure and the blank lines the flat strip leaves behind.

## Axis 2 - one package, five report formats

From ONE evidence set, these must state the same facts:

| format | file | must agree on |
|---|---|---|
| HTML | `report.html` | test count, passed/failed, each test's status |
| JSON | report dicts / package JSON | test count, passed/failed, per-test status |
| NDJSON | `.ndjson` | full sidecar: step order, per-step status, `page_mismatch`, `navigation` |
| JUnit | `.xml` | testcases, failures; one `<failure>` per failed test |
| CSV | `.csv` | one row per test: status, step count, step types |

Covered today by `scripts/parity_check.py`: counts and statuses in all five, the step total in CSV,
the failures in JUnit, and that NDJSON keeps `page_mismatch` and `navigation.redirected` - the two
fields a redirect or a page divergence lives in.

Not compared: HTML markup, wording, and the per-step overlay inside the HTML. The overlay has its
own tests (`tests/test_evidence_overlay_*`), and markup is presentation.

## Axis 3 - CLI, Streamlit, CI

MUST agree:

- the package produced (same files, same tests, same order);
- the verdicts (per-criterion and per-test);
- the report contents;
- the exit status: pass is 0, a failed gate is non-zero, in all three.

MUST NOT be compared:

- progress text, prompts, spinner wording;
- default workspace and output paths (each surface owns its defaults);
- anything rendered in the UI as presentation;
- timing.

**Status: not implemented yet.** This is step 2. The shape is: drive the CLI through `cli/main.py`,
the Streamlit path through its service layer (`src/pipeline_run_service.py`, not a browser), and CI
through `action.yml` plus the workflow, all on the same recorded input. It stays scoped to the
package and the verdicts, never to the text.

## What exists, and what this adds

| script | covers | gap this check fills |
|---|---|---|
| `scripts/export_gate.py` | both modes, artifact validity, suites run | does not compare the two modes' verdicts |
| `scripts/uat.py --flat` | two-mode plumbing over two mock sites | does not compare them to each other |
| `scripts/ci_action_selftest.py` | the CI action's own behaviour | does not compare CI to CLI or UI |
| `scripts/verify_production.py` | the product works end to end | not a cross-mode or cross-surface comparison |

## What step 1 measures, exactly

Axis 1 is measured on the **export boundary**: one recorded package is exported in both modes and
the two exports are compared. That catches the class that actually bit us - the flat strip eating a
step, a page object losing its tracker call, a bundle missing the run-history DB - because the flat
export is exactly what the product ships to a flat user.

It does **not** compare two live generations. That leg needs the shared-skeleton method above and
is step 1b, not this job; the reason is stated so nobody reads a green table as more than it is.

Axis 2 is measured on one recorded evidence set, so all five formats read the same source facts.

## Running the check

```bash
python scripts/parity_check.py              # both axes, fixed fixture, offline
python scripts/parity_check.py --json        # machine-readable rows
python scripts/parity_check.py --keep        # keep the temporary export dirs
```

It prints a table of `axis / artefact / expected / actual / verdict`, exits 1 on any unexpected
difference, and its last line carries the counts (total, per axis, differences, allowed, pending).
Quote that line rather than a number copied into prose. It lists the documented allowed differences
separately so a reviewer can see that the
difference was considered, not missed. CI runs it as the `parity-check` job beside `verify-baseline`.

No model, no browser, no network: both axes read a fixed package and a fixed evidence set.

## Adding a comparison

1. Decide the axis and say whether the artefact MUST agree or MAY differ - add it to this file
   first, with the reason.
2. Add it to `check_mode` or `check_reports` in `scripts/parity_check.py`: `report.add(...)` for a
   must, `report.allowed(...)` for a may.
3. Make it fail on difference. A check that cannot fail is not a check.
