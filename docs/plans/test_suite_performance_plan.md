# Test Suite Performance Optimization Plan

**Date:** 2026-05-21  
**Status:** In Progress  
**Author:** Cline (AI Agent)

---

## Problem Statement

The test suite takes **724.68s (12 minutes)** to run 778 tests with coverage enabled. Without coverage, the same tests run in **~1.7s** — a 425x difference.

## Root Cause Analysis

### Primary: Coverage Overhead on Browser Tests

- **66 tests** instantiate real Playwright browsers (`sync_playwright().start()`)
- Coverage instrumentation adds overhead to every line executed during browser interactions
- Coverage run shows **10.9s periodic spikes** corresponding to batches of browser tests
- Without coverage: 742 tests in 1.7s. With coverage: 778 tests in 724s

### Secondary Issues

| Issue | Impact | Location |
|-------|--------|----------|
| Unregistered pytest markers | 4 warnings per run; `slow`/`integration` tests always run | `pytest.ini`, `tests/integration/test_pipeline_end_to_end.py` |
| 18 `LLMClient()` instantiations | Each test creates fresh provider instances | Across 6+ test files |
| `asyncio.run()` in integration tests | Conflicts with coverage event loop tracking on Windows | `tests/integration/test_pipeline_end_to_end.py` (3 tests) |
| Collection warnings | `TestCase` dataclass and `TestOrchestratorResult` confuse pytest collector | `cli/color.py`, `tests/cli/test_orchestrator.py` |
| No parallel execution | All tests run sequentially | Project-wide |

## Optimizations (Implementation Order)

### 1. Register pytest markers

- **Effort:** 2 min
- **Impact:** High — enables selective test exclusion
- **Change:** Add `markers = slow, integration` to `pytest.ini`
- **Result:** `pytest -m "not slow and not integration"` excludes 2 long-running integration tests

### 2. Disable coverage for integration tests

- **Effort:** 3 min
- **Impact:** High — removes coverage overhead from browser-heavy integration tests
- **Change:** Add `@pytest.mark.no_cover` handling in `conftest.py`
- **Result:** Integration tests run without coverage instrumentation

### 3. Module-level LLMClient fixture

- **Effort:** 5 min
- **Impact:** Medium — reduces provider instantiation overhead
- **Change:** Replace per-test `LLMClient()` with `@pytest.fixture(scope="module")`
- **Result:** Single shared client per test module

### 4. Add pytest-xdist for parallel execution

- **Effort:** 2 min
- **Impact:** Medium — parallelizes independent unit tests
- **Change:** Add `pytest-xdist` to dev dependencies, document `-n auto` usage
- **Result:** ~0.5-0.8s for unit tests on multi-core machines

### 5. Suppress collection warnings

- **Effort:** 3 min
- **Impact:** Low — clean test output
- **Change:** Rename `TestCase` → `TestInputCase`, `TestOrchestrationResult` → `OrchestrationResult`
- **Result:** No more `PytestCollectionWarning` messages

## Expected Results

| Scenario | Before | After (estimated) |
|----------|--------|-------------------|
| `pytest` (no coverage) | 1.7s | 1.7s (already fast) |
| `pytest --cov` (unit only) | 724s | ~60-90s |
| `pytest -m "not slow"` | 1.7s | 1.7s (explicit exclusion) |
| `pytest -n auto` | 1.7s | ~0.5-0.8s |

## Files Modified

- `pytest.ini` — marker registration
- `tests/conftest.py` — no_cover handling, shared fixtures
- `pyproject.toml` — pytest-xdist dependency
- `tests/integration/test_pipeline_end_to_end.py` — no_cover markers
- `cli/color.py` — TestCase rename (if needed)
- `tests/cli/test_orchestrator.py` — TestOrchestrationResult rename (if needed)

---

## Implementation Log

- [x] Plan documented
- [ ] Step 1: Register pytest markers
- [ ] Step 2: Disable coverage for integration tests
- [ ] Step 3: Shared LLMClient fixture
- [ ] Step 4: Add pytest-xdist
- [ ] Step 5: Suppress collection warnings
- [ ] Final verification run