# Feature Completion Checklist

## Status Summary

| Feature Doc | Status | Key Remaining Work |
|---|---|---|
| `docs/session_02_placeholder_resolver.md` | Implemented | Monitor only |
| `docs/session_03_orchestrator.md` | Partial | Add scraper retry/backoff and partial-failure reporting |
| `docs/session_04_final_polish.md` | Partial | Close debug cleanup and align docs with shipped behavior |
| `docs/plans/AI-016_plan.md` | Implemented | Monitor only |
| `docs/plans/AI-017_plan.md` | Not implemented | Build living test plan module, tests, and Streamlit sign-off flow |
| `docs/plans/AI-018_plan.md` | Implemented | Monitor only |
| `docs/plans/AI-019_plan.md` | Implemented | Complete end-to-end validation evidence |
| `docs/plans/AI019_section1_audit.md` | Implemented | None |
| `docs/plans/AI019_section2_prompts.md` | Implemented | None |
| `docs/plans/AI019_section3_validation.md` | Partial | Run full validation flow and capture outputs |
| `docs/plans/AI-020_plan.md` | Implemented | Minor UI polish only |
| `docs/plans/AI-021_plan.md` | Partial | Build real Gantt UI and expose grouping/detail modes |
| `docs/plans/AI-022_plan.md` | Partial | Build richer heat map grouping/trend UI |
| `docs/session_05_pipeline_rebuild_plan.md` | Partial | Complete page-object execution path, package completeness, UAT, and validation |

## Phase 1: Missing Foundation

- [x] Implement `src/test_plan.py`
- [x] Implement `tests/test_test_plan.py`
- [x] Add typed CRUD helpers for review/edit/remove/add flows
- [x] Add confirmation/sign-off helpers
- [x] Wire minimal Living Test Plan review flow into `streamlit_app.py`
- [x] Block generation until all plan conditions are reviewed and signed off

## Phase 2: Session 05 Backend Completion

- [x] Make generated test packages import and use generated `pages/*.py` modules
- [x] Add missing package artifact(s), including `coverage_summary.json`
- [x] Tighten page-object generation and execution-path tests
- [x] Add mocked end-to-end pipeline integration coverage

## Phase 3: Validation And Hardening

- [ ] Complete AI-019 end-to-end validation checklist
- [ ] Add scraper retry/backoff support
- [ ] Add scraper partial-failure metadata/reporting
- [ ] Reduce remaining debug-only prints in core paths
- [x] Replace Windows-fragile stateful scraper thread launch with a subprocess-backed implementation
- [x] Make test plan sign-off act as the primary save-and-approve action in the UI

## Phase 4: Evidence UX Completion

- [ ] Upgrade AI-021 to a real Gantt visualization
- [ ] Expose Gantt grouping modes in the UI
- [ ] Add per-bar detail cards for evidence context
- [ ] Upgrade AI-022 to a richer grouped heat map
- [ ] Feed test-plan confirmation state into heat map confidence views
- [ ] Add trend/summary panels after grouped data is stable
- [ ] Fix evidence viewer screenshot selection so segments prefer meaningful post-action states over consent-blocked or pre-action captures
- [x] Replace raw placeholder-token labels in evidence views with cleaner user-facing step descriptions
- [x] Fix multi-page evidence attribution so downstream URLs like `/view_cart` and `/checkout` reliably receive their own interaction points
- [ ] Fix suite heatmap background/image selection so the selected page and its evidence points stay in sync
- [x] Add focused tests for consent-overlay-heavy runs and multi-page evidence segmentation
- [x] Improve navigate screenshots by dismissing common consent overlays before evidence capture when possible

## Phase 5: Closeout

- [ ] Add one reproducible real UAT path and checklist
- [ ] Verify Streamlit generate/run/download flow end-to-end
- [ ] Run full `ruff`, `mypy`, and `pytest`
- [ ] Update planning docs to reflect final shipped behavior
