# Session: 2026-08-03 — CLI Review, Backlog Audit (B-029→B-036) & Fix Batch 1

**Branch:** `main` · **Commits:** (see git log)

## What this session covered

Two phases:

1. **CLI review of `test_20260803_101815_...`** (automationexercise, "browse products & add to cart") — 9/13 passed, checkout cluster (t10–t13) failed. Root-caused the failures and audited the product (evidence, exports, testing strategy, config architecture) → logged **B-029 → B-036** plus two strategy sections.
2. **Fix batch 1** — implemented B-029, B-033, B-034, B-035, B-030 (5 of the 8 fix items).

## Phase 1 — Findings (the audit)

### The checkout-cluster failures (B-029)
All 4 failures shared one signature: the cart header-link click recorded `passed` after a **30.5s fallback marathon** with **no navigation** — Google's FreeCmp consent dialog + `#google_vignette` ad overlay swallowed the click; the last-resort JS `el.click()` returns "success" without navigating; the tracker has no post-click URL verification. The next step then fast-failed with the misleading "element exists on a different page" error.

Confirmed by live reproduction (3× identical timing signature: 2ms no-op on Continue Shopping, ~30.4s marathon on Cart click). New tool: **`scripts/debug_step_through.py`** — runs real generated tests headed, pauses after every tracker step, prints the overlay/modal state the auto-dismiss hides.

### B-030 (resolver)
`{{CLICK:Check Out}}` resolved to `#do_action` (wrapper div) instead of `.btn.btn-default.check_out`. Root cause found during fix phase: the **B-025 "clickable container" bonus (+10)** outranked the real anchor's interactive bonus (+3 role +2 href = +5).

### Evidence layer (B-033/034/035)
- Failed fast-fail steps had **no screenshot, no diagnosis** (`screenshot is None` was even *asserted* in a unit test — the bug was codified as intended behaviour).
- Sidecar written only at test END — killed/timed-out tests left orphaned PNGs invisible to the evidence index.
- `evidence/run_results.sqlite` was **corrupted** (integrity check: "database disk image is malformed", Tree 10 page 26) — the UI evidence page would raise instead of self-healing.

### Exports (B-031/032)
- 34 of 35 exports in `exported_tests/` are stubs (`def test_x(page): pass`); the one real export is non-importable (POM imports with no `pages/` dir).
- POM export globs `pages/po_*.py` but generated pages are `home_page.py` — matches nothing.
- Export run-history copy is orphaned since AI-012: copies `playwright_tests.db`, but nothing creates that file (the SQLite layer writes `run_results.sqlite`).

### Testing strategy (meta)
2,095 green unit tests coexisted with 7 real bugs: tests assert internal invariants against MagicMocks; the fast-fail screenshot test *enshrined* B-033; network tests mislabeled (`test_pom_mode_end_to_end.py` hits live automationexercise.com with no `slow`/`integration` marker); eval + verify_production are outside CI; no adversarial/contract/resilience layers. Golden dataset `eval-002` stops at the cart page — zero checkout/payment keys, so the skip family ('Proceed To Checkout', 'Place Order') is invisible to the harness.

**Mock-site strategy:** make deterministic local mocks the primary test target (closer to a real user's own site — no consent/ad noise). Research catalog logged in `mock_sites/README.md` (8 product types; e-commerce mock = priority #1). Key design rule: every mock supports an **injectable consent/ad overlay** so the B-029 race is testable deterministically.

### Config architecture (B-036)
Consumer product — env-var feature gates don't fit. `RAG_ENABLED`, `LANGGRAPH_ENABLED` (dead — graph not wired into the user-facing path), `OCR_BACKEND`, `JIRA_PROJECT_KEY` are dev-era leftovers; API keys already use the right pattern (`secure_config.py`, Fernet-encrypted). RAG fix design: always-on with graceful degradation, bundled golden patterns auto-seeded, auto-learn from consumer's own runs.

## Phase 2 — Fix batch 1 (implemented, shipped)

### Cluster 1 — `src/evidence_tracker.py` (B-029 + B-033 + B-035, one pass)
- **B-029**: post-click navigation verification — a "successful" click on a link whose URL never changes now dismisses overlays + retries once, then amends the recorded step from `passed` to `failed` (no more silent false-pass). Unscoped `button.btn-success.close-modal` dismissal scoped to modal containers.
- **B-033**: failed steps always carry a screenshot + failure note (fast-fail included); every step records its `url`; screenshot failures log a warning. Flipped the enshrined test (`screenshot is None` → must have screenshot + failure note + url).
- **B-035**: sidecar persists incrementally (first step + any failed/partial step) — killed processes leave real evidence.
- +3 B-029 contract tests (pass / same-page-skip / swallow→amend).

### B-034 — DB self-heal (`src/sqlite_persistence.py` + `src/evidence_index.py`)
- `SQLitePersistence.__init__` recreates a corrupt database file at construction.
- `EvidenceIndex._execute/_commit` recover + retry on `DatabaseError`; `_recover()` never drops a healthy DB (guard added after live run showed a transient error wiping the table).
- Fixed Python-2 `except A, B:` syntax (×2, worked by accident).
- +2 corruption-resilience tests. **Live `evidence/run_results.sqlite` healed + rebuilt: 359 sidecars indexed, verified stable.**

### B-030 — resolver (`src/placeholder_scorers.py`)
- B-025 container bonus **+10 → +3** (below link/button +3 role +2 href = +5) — interactive elements win when both match; containers still win text-only matches.
- Eval static **100%** across all 5 datasets (no regression); +2 regression tests.

## Verification

- Full suite: **2102 passed / 1 skipped** (was 2095; +7 new tests)
- ruff, format, mypy clean; eval static 100%; smoke 35/35
- CI: all gates green

## Open items (next sessions)

- **B-031** — export gate + broken exports (biggest remaining product bug: exports are stubs/broken; no end-to-end validation)
- **B-032** — export DB orphan (`playwright_tests.db` → `run_results.sqlite`, one-liner)
- **B-036** — consumer config architecture (env gates → always-on/UI) + RAG resolution fix chain (bundled golden keys incl. checkout leg, auto-seed, auto-learn)
- Test-pack restructure (contract/adversarial/resilience layers, eval static in CI, relabel network tests)
- Mock-site catalog build (e-commerce mock first, with injectable overlay)
- Eval-002 golden-key expansion (checkout/payment leg)
- Housekeeping: `generated_tests/` 1.3GB retention policy; stale `.pytest_cache/lastfailed`
