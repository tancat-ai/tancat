# Session: 2026-08-03 (continued) — Export Gate & Runnable Exports (B-031, B-032)

**Branch:** `main` · **Commits:** (see git log)

## What this session covered

Continued from the CLI-review session: closed **B-032** (one-liner) and **B-031** (the big one — exports were stubs/broken and never validated end-to-end).

## B-032 — Export run-history DB copy (one-liner family)

`src/export_service.py` copied `evidence/playwright_tests.db` — **nothing in the repo creates that file** (the SQLite layer writes `evidence/run_results.sqlite` since AI-012). The copy was a silent no-op.

- `_find_sqlite_db()` prefers `run_results.sqlite`, falls back to legacy `playwright_tests.db`; WAL/SHM files follow the found name; README note + `has_sqlite` check updated.
- `src/pipeline_artifact_manager._count_run_results` checks `run_results.sqlite` first (with legacy fallback). Note: its `except sqlite3.OperationalError, sqlite3.DatabaseError:` is NOT a bug on this codebase — Python 3.14 (PEP 758) restored parenthesless except targets, and ruff format (target-version py314) canonicalizes to that form. Same for `evidence_index.py`'s pre-existing tuple-excepts.

## B-031 — Runnable, validated exports (the big one)

### Confirmed state (from the CLI review)
- 34/35 exports in `exported_tests/` were `def test_x(page): pass` stubs.
- The one real export (`20260802_181655_...`) was non-importable: POM imports with no `pages/` dir (glob `po_*.py` matched nothing — generated pages are `home_page.py`/`cart_page.py`), `HomePage(page, evidence_tracker)` NameError, dead `@pytest.mark.evidence(condition_ref=..., story_ref=...)` decorators.

### Fixes shipped

| Fix | Where | Detail |
|-----|-------|--------|
| POM glob | `src/export_service.py` | `pages/*.py` minus `__init__.py` — the real package now ships all 5 pages (home, cart, checkout, products, generated) |
| True POM-mode export | `src/code_postprocessor.py` | `strip_evidence_from_test_code(..., preserve_pom_calls=True)` keeps imports/instantiations/method calls; only the `evidence_tracker` arg drops from `HomePage(page, evidence_tracker)` → `HomePage(page)`. Previously POM-mode silently emitted flat output with a dead `pages/` dir |
| Evidence decorators | `_strip_evidence_decorators()` | Strips bare, arg-carrying, multi-line, and whitespace variants (paren-balance line consumer). Old regex matched only the bare form |
| B-020 assert family | `_strip_tracker_asserts()` | `assert_hidden` → `to_be_hidden()` (the live gap: survived exports → runtime NameError), plus disabled/enabled/checked/empty/text/text_contains/value/count — in both test code and POMs |
| Stub guard | `src/export_service.py` | `_guard_stub_source()` raises `ValueError` when a source package has no test functions, or every test body is only `pass`/`...`/`pytest.skip()` |
| Export collision guard | `src/export_service.py` | Same-second same-slug exports get `_1`, `_2`… suffixes instead of silent overwrite |

### New: `scripts/export_gate.py` — the export's `verify_production`

9 gates against a **deterministic golden fixture** (`fixtures/golden_package/` + `fixtures/golden_site/`, served on `127.0.0.1:8123` by the script — no external network, CI-able):

1. Source passes stub guard
2. Export FLAT succeeds
3. Export POM succeeds
4. Flat artifacts clean (no evidence_tracker, no decorators, no POM remnants, no stubs, playwright import)
5. POM artifacts clean (pages shipped, no tracker refs, POM imports present in tests)
6. Run-history DB copied (B-032) — tri-state: skip when the source has no DB
7. Both suites collect (importability — each export collected in its own pytest invocation to avoid same-basename module collisions)
8. Flat export executes and passes (golden mode) / offline note (real-package mode)
9. POM export executes and passes (golden mode)

Real-package mode: `--source <pkg>` (offline artifact + collect gates), `--run-remote` to execute the flat export against the live target. Export dirs deleted on pass unless `--keep`.

The golden fixture mirrors a real generated package: arg-carrying `@pytest.mark.evidence(...)` decorators, evidence-aware POMs, `evidence/run_results.sqlite`, POM-mode test file with `HomePage(page, evidence_tracker)` + `home_page.click(label, selector=...)` calls.

## Verification

- Full suite: **2122 passed / 1 skipped** (was 2102; +20 new tests: stub-guard ×4, POM generated-names ×1, POM-preserve ×2, DB copy ×2, decorator forms ×4, assert family ×5, preserve-POM strip ×2)
- ruff check + format clean; mypy clean (4 modules + script); smoke 35/35
- **Export gate: golden 9/9 PASS** (flat + POM suites execute and pass against localhost)
- **Export gate: real 20260803 package 8/8 PASS** (26 tests collect clean; flat + POM artifacts clean)
- Exported flat suite of the real package converts correctly: `evidence_tracker.navigate/click/assert_visible/assert_hidden` → `page.goto/page.locator/expect(...).to_be_visible()/.to_be_hidden()`, decorators gone, POM calls inlined with resolved selectors

## Notes / latent issues found

- The 20260803 CLI-review package has **no `run_results.sqlite`** in its evidence dir (sidecar JSONs + PNGs only) — the gate correctly reports "nothing to copy". The product's SQLite layer only writes run history when runs are recorded through storage; CLI-review flows bypass it. Not an export bug.
- Generated packages carry duplicate POM imports/instantiations (generation artifact); exports inherit them but remain runnable (proven by execution gate).
- `exported_tests/` still holds the 34 historical stub exports — candidate for a retention sweep (stub guard means new ones can't be created).

## Follow-up (same session) — Test-pack relabel: the audit claim was wrong; guard + eval-static-in-CI shipped

### Finding: no mislabeled network tests existed

Re-verified the audit's claim that `tests/integration/test_pom_mode_end_to_end.py`
"hits live automationexercise.com with NO slow/integration marker" — **false**:
- All 6 tests are offline string-transformation / JSON-schema checks; the URLs
  live in a module-level `SAMPLE_TEST_CODE` constant, never executed.
- `test_pipeline_end_to_end.py`: the 2 LLM-dependent tests already carry
  `slow`+`integration`; the 4 `file://` mock-scrape tests are offline.
- `test_rag_store.py` real-embedder tests: marked `slow`; the unmarked
  `test_dimension` never loads the model (lazy `dimension` property).
- CI already applies `-m "not slow and not integration"` via pytest.ini addopts.

### Shipped
1. **`tests/test_no_live_network_in_default_suite.py`** — static guard: AST-scans
   the suite and FAILS if any unmarked test executes a navigation call
   (`goto`/`navigate`/`scrape_url`/`scrape_all`/`run_pipeline`/`attempt_login`)
   with a live-site URL literal. Skips tests that explicitly mock the network
   layer (AsyncMock/MagicMock/monkeypatch/patch). Positive controls verified:
   planted live goto/scrape/unmocked-pipeline flagged; mocked + config-assert
   tests ignored; real suite passes.
2. **CI `eval-static` job** — `eval_harness.py run --mode static --min-accuracy 79`
   (offline, ~0.5s, exit 2 below floor) runs in parallel with lint/type-check.
   Verified locally: floor 79/100 → exit 0; floor 101 → exit 2.
3. **BACKLOG structural-problems #3/#4 revised** with the corrected findings.

Note: `.github/workflows/ci.yml` is a protected file (AGENTS.md) — modified per
explicit instruction to wire eval-static into CI as part of this item.

### CI integration follow-ups (commit 8a44d75 + 210d030)
- **Sanitizer false positive**: `project_sanitizer` flagged
  `fixtures/golden_package/test_golden_flow.py` as a misplaced test (it would
  have been auto-moved into `tests/` and collected+failed there). Added
  `fixtures` to `SKIP_DIRS` — fixture-data dirs hold test-named files that are
  data, not collectable tests.
- **Eval-static CI failure**: `persist_results` opens
  `evidence/run_results.sqlite`, which does not exist in a fresh checkout
  (`evidence/` is gitignored) → `sqlite3.OperationalError: unable to open
  database file`. The pre-commit hook already used `--no-persist`; the CI job
  now matches. Latent harness robustness note: `persist_results` does not
  create the parent dir — a future fix could `mkdir(parents=True)` so plain
  `eval run` works on fresh checkouts.

Still open from the test-pack item: contract/adversarial/resilience layers,
`verify_production`/`export_gate` in CI (needs the mock layer), network-test
relabels beyond what's already marked (none found).

## Open items (next sessions)

- **B-036** — consumer config architecture (env gates → always-on/UI) + RAG resolution fix chain (bundled golden keys incl. checkout leg, auto-seed, auto-learn)
- Test-pack restructure (contract/adversarial/resilience layers, eval static in CI, relabel network tests)
- Mock-site catalog build (e-commerce mock first, with injectable overlay)
- Eval-002 golden-key expansion (checkout/payment leg)
- Housekeeping: `generated_tests/` 1.3GB retention policy; stale `.pytest_cache/lastfailed` (602 entries); archived stub exports sweep
