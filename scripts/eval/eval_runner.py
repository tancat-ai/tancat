"""eval_runner.py — Orchestrates eval harness runs.

Handles three stages:
  1. Static validation: parse generated code, compare against golden keys
  2. Test execution: run generated tests via pytest (optional, --full mode)
  3. Persistence: write results to SQLite eval_runs table

Pure orchestration — delegates to eval_metrics.py and golden_validator.py.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from eval_metrics import HarnessReport, StoryResult
from golden_validator import load_golden_key, validate_dataset

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# SQLite eval_runs table
# ---------------------------------------------------------------------------

_EVAL_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS eval_runs (
    run_id      TEXT PRIMARY KEY,
    story_id    TEXT NOT NULL,
    site        TEXT NOT NULL,
    placeholders_total   INTEGER NOT NULL DEFAULT 0,
    placeholders_correct INTEGER NOT NULL DEFAULT 0,
    resolution_accuracy  REAL NOT NULL DEFAULT 0.0,
    test_pass_rate       REAL NOT NULL DEFAULT 0.0,
    false_positive_rate  REAL NOT NULL DEFAULT 0.0,
    skeleton_completeness REAL NOT NULL DEFAULT 0.0,
    generation_duration  REAL NOT NULL DEFAULT 0.0,
    mode         TEXT NOT NULL DEFAULT 'static',
    raw_report   TEXT,
    created_at   TEXT NOT NULL,
    pipeline     TEXT NOT NULL DEFAULT 'linear',
    generation_mode TEXT NOT NULL DEFAULT 'captured',
    rag_enabled  INTEGER NOT NULL DEFAULT 0,
    pom_mode     INTEGER NOT NULL DEFAULT 0,
    provider     TEXT NOT NULL DEFAULT '',
    model        TEXT NOT NULL DEFAULT '',
    git_commit   TEXT NOT NULL DEFAULT ''
)
"""

_EVAL_INDEX_SQL = "CREATE INDEX IF NOT EXISTS idx_eval_runs_story ON eval_runs(story_id)"


def _get_git_commit() -> str:
    """Return the current git HEAD commit hash, or empty string on failure."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return ""


def _ensure_eval_table(conn: sqlite3.Connection) -> None:
    """Create eval_runs table and index if they don't exist."""
    conn.execute(_EVAL_SCHEMA_SQL)
    conn.execute(_EVAL_INDEX_SQL)
    conn.commit()


# ---------------------------------------------------------------------------
# Static validation
# ---------------------------------------------------------------------------


def run_static_validation(
    dataset_dir: Path,
    code_map: dict[str, str],
    durations: dict[str, float] | None = None,
) -> list[StoryResult]:
    """Run static validation against golden keys (no browser needed).

    Args:
        dataset_dir: Path to scripts/eval/dataset/
        code_map: Dict mapping story_id to generated Python code string.
        durations: Optional dict mapping story_id to generation duration in seconds.

    Returns:
        List of StoryResult, one per story.
    """
    return validate_dataset(dataset_dir, code_map, durations or {})


# ---------------------------------------------------------------------------
# Test execution (--full mode)
# ---------------------------------------------------------------------------


def run_generated_tests(
    test_file: Path,
    pytest_timeout: float = 120.0,
) -> tuple[int, int, int, int, float, str]:
    """Execute a single test file via pytest and parse results.

    Returns:
        (total, passed, failed, skipped, duration, raw_output)
    """
    import sys

    cmd = [
        sys.executable,
        "-m",
        "pytest",
        str(test_file),
        "-v",
        "--tb=short",
        "--override-ini=log_cli_level=ERROR",
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=pytest_timeout + 30,
        )
    except subprocess.TimeoutExpired:
        return (0, 0, 0, 0, 0.0, "pytest execution timed out")

    output = result.stdout + result.stderr

    # Parse summary line: "=== 5 passed, 1 failed, 0 skipped in 12.34s ==="
    total = passed = failed = skipped = 0
    duration = 0.0
    import re as _re

    passed_re = _re.compile(r"(\d+)\s+passed")
    failed_re = _re.compile(r"(\d+)\s+failed")
    skipped_re = _re.compile(r"(\d+)\s+skipped")
    duration_re = _re.compile(r"in\s+([\d.]+)s")
    for line in output.splitlines():
        pm = passed_re.search(line)
        fm = failed_re.search(line)
        sm = skipped_re.search(line)
        if pm:
            passed = int(pm.group(1))
            total += passed
        if fm:
            failed = int(fm.group(1))
            total += failed
        if sm:
            skipped = int(sm.group(1))
            total += skipped
        dur_m = duration_re.search(line)
        if dur_m:
            duration = float(dur_m.group(1))
        if pm or fm or sm or dur_m:
            break

    return (total, passed, failed, skipped, duration, output)


def run_full_validation(
    dataset_dir: Path,
    code_map: dict[str, str],
    durations: dict[str, float] | None = None,
    test_files: dict[str, Path] | None = None,
    pytest_timeout: float = 120.0,
) -> list[StoryResult]:
    """Run full validation: static + test execution.

    Args:
        dataset_dir: Path to scripts/eval/dataset/
        code_map: Dict mapping story_id to generated Python code string.
        durations: Optional dict mapping story_id to generation duration.
        test_files: Optional dict mapping story_id to Path of generated test file.
            If provided, tests are executed via pytest.
        pytest_timeout: Timeout for each pytest run in seconds.

    Returns:
        List of StoryResult with both resolution and test metrics populated.
    """
    # Stage 1: Static validation
    results = validate_dataset(dataset_dir, code_map, durations or {})

    # Stage 2: Test execution (if files provided)
    if test_files is None:
        return results

    for story in results:
        test_file = test_files.get(story.story_id)
        if test_file is None or not test_file.exists():
            logger.info("No test file for %s — static validation only (no execution)", story.story_id)
            continue

        logger.info("Executing tests for %s: %s", story.story_id, test_file)
        total, passed, failed, skipped, duration, raw_output = run_generated_tests(
            test_file,
            pytest_timeout=pytest_timeout,
        )

        story.tests_executed = total
        story.tests_passed = passed

        # Estimate false positives: tests that passed but had wrong locators
        # A test is false positive if it passed but any of its ASSERT locators were wrong
        if test_file is not None and passed > 0:
            wrong_asserts = [r for r in story.resolutions if r.action == "ASSERT" and not r.matched]
            story.tests_false_positive = len(wrong_asserts)
        else:
            story.tests_false_positive = 0

    return results


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def persist_results(
    db_path: Path,
    stories: list[StoryResult],
    mode: str = "static",
    *,
    pipeline: str = "linear",
    generation_mode: str = "captured",
    rag_enabled: bool = False,
    pom_mode: bool = False,
    provider: str = "",
    model: str = "",
    git_commit: str = "",
) -> list[str]:
    """Write eval results to SQLite eval_runs table.

    Args:
        db_path: Path to SQLite database file.
        stories: List of StoryResult to persist.
        mode: "static", "resolver", "full", or "semantic".
        pipeline: "linear" or "graph" — which skeleton pipeline was used.
        generation_mode: "regenerated" or "captured".
        rag_enabled: Whether RAG-enhanced scoring was active.
        pom_mode: Whether POM-mode output was enabled.
        provider: LLM provider name (e.g. "openai-local").
        model: LLM model path or identifier.
        git_commit: Git commit hash for the code that produced these results.

    Returns:
        List of run_ids inserted.
    """
    import sqlite3

    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    try:
        _ensure_eval_table(conn)
        run_ids: list[str] = []
        timestamp = datetime.now(UTC).isoformat()

        for story in stories:
            report = HarnessReport(stories=[story])
            run_id = f"eval-{uuid.uuid4().hex[:8]}"

            conn.execute(
                """
                INSERT INTO eval_runs
                    (run_id, story_id, site, placeholders_total, placeholders_correct,
                     resolution_accuracy, test_pass_rate, false_positive_rate,
                     skeleton_completeness, generation_duration, mode, raw_report, created_at,
                     pipeline, generation_mode, rag_enabled, pom_mode, provider, model, git_commit)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    story.story_id,
                    story.site,
                    report.total_placeholders,
                    report.correct_resolutions,
                    report.resolution_accuracy(),
                    report.test_pass_rate(),
                    report.false_positive_rate(),
                    report.skeleton_completeness(),
                    story.generation_duration_s,
                    mode,
                    json.dumps(report.to_dict()),
                    timestamp,
                    pipeline,
                    generation_mode,
                    1 if rag_enabled else 0,
                    1 if pom_mode else 0,
                    provider,
                    model,
                    git_commit,
                ),
            )
            run_ids.append(run_id)

        conn.commit()
        return run_ids
    finally:
        conn.close()


def load_eval_history(
    db_path: Path,
    story_id: str | None = None,
) -> list[dict[str, Any]]:
    """Load eval history from SQLite.

    Args:
        db_path: Path to SQLite database file.
        story_id: Optional filter by story_id.

    Returns:
        List of dicts with eval_run data, oldest first.
    """
    import sqlite3

    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        _ensure_eval_table(conn)
        if story_id is not None:
            rows = conn.execute(
                "SELECT * FROM eval_runs WHERE story_id = ? ORDER BY created_at",
                (story_id,),
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM eval_runs ORDER BY created_at").fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Runner (unified entry point)
# ---------------------------------------------------------------------------


class EvalRunner:
    """Unified eval harness runner.

    Parameters
    ----------
    dataset_dir :
        Path to the golden keys directory (scripts/eval/dataset/).
    code_dir :
        Path to the captures directory (scripts/eval/captures/).
    db_path :
        Path to the SQLite database for persistence.
    test_output_dir :
        Optional path to directory containing generated test files
        (for --full mode execution).
    """

    def __init__(
        self,
        dataset_dir: Path,
        code_dir: Path,
        db_path: Path,
        test_output_dir: Path | None = None,
        regenerate: bool = False,
        use_graph: bool = False,
    ) -> None:
        self.dataset_dir = dataset_dir
        self.code_dir = code_dir
        self.db_path = db_path
        self.test_output_dir = test_output_dir
        self.regenerate = regenerate
        self.use_graph = use_graph

    def _load_code_map(self) -> dict[str, str]:
        """Load all captured code files into a map keyed by story_id."""
        code_map: dict[str, str] = {}
        for golden_file in sorted(self.dataset_dir.glob("*.json")):
            golden = load_golden_key(golden_file)
            story_id = golden["id"]

            # Try to find matching capture file
            capture_name = f"{story_id.split('_')[1]}_code.py" if "_" in story_id else None
            if capture_name is not None:
                capture_file = self.code_dir / capture_name
                if capture_file.exists():
                    code_map[story_id] = capture_file.read_text(encoding="utf-8")

        # Also scan captures dir for any code files
        for code_file in self.code_dir.glob("*_code.py"):
            # Try to match by filename pattern: saucedemo_code.py -> eval-001
            site_name = code_file.stem.replace("_code", "")
            for golden_file in self.dataset_dir.glob("*.json"):
                golden = load_golden_key(golden_file)
                if golden["site"] == site_name and golden["id"] not in code_map:
                    code_map[golden["id"]] = code_file.read_text(encoding="utf-8")
                    break

        return code_map

    def _persist_regenerated_tests(self, code_map: dict[str, str]) -> None:
        """Write regenerated code to ``test_output_dir`` for the execution phase.

        ``_load_test_files`` globs ``test_*.py`` files whose stem contains the
        site name — write one deterministic file per story (``test_<site>.py``)
        so full-mode actually executes the JUST-regenerated tests and reports a
        pass rate instead of "Tests executed: 0".
        """
        if self.test_output_dir is None:
            return
        self.test_output_dir.mkdir(parents=True, exist_ok=True)
        for golden_file in sorted(self.dataset_dir.glob("*.json")):
            golden = load_golden_key(golden_file)
            story_id = golden["id"]
            site = golden["site"]
            code = code_map.get(story_id, "")
            if not code.strip():
                logger.warning("No regenerated code for %s — skipping test persistence", story_id)
                continue
            out_path = self.test_output_dir / f"test_{site}.py"
            out_path.write_text(code, encoding="utf-8")
            logger.info("Persisted regenerated tests for %s → %s", story_id, out_path)

    def _load_test_files(self) -> dict[str, Path]:
        """Map story_ids to generated test files for execution."""
        test_files: dict[str, Path] = {}
        if self.test_output_dir is None:
            return test_files

        for golden_file in sorted(self.dataset_dir.glob("*.json")):
            golden = load_golden_key(golden_file)
            story_id = golden["id"]
            site = golden["site"]

            # Look for test file matching site name
            for test_file in self.test_output_dir.glob("test_*.py"):
                if site in test_file.stem:
                    test_files[story_id] = test_file
                    break

        return test_files

    def run(
        self,
        mode: str = "static",
        pytest_timeout: float = 120.0,
        persist: bool = True,
    ) -> HarnessReport:
        """Execute the eval harness.

        Args:
            mode: "static" (resolution only) or "full" (resolution + test execution).
            pytest_timeout: Timeout for individual pytest runs (seconds).
            persist: Whether to write results to SQLite.

        Returns:
            HarnessReport with all metrics computed.
        """
        # Auto-manage mock server for lv_insurance (eval-005) — the mock
        # insurance SPA requires a local HTTP server.  ThreadingHTTPServer
        # handles concurrent Playwright requests without crashing.
        # The server runs as a daemon thread — auto-stops when the process exits.
        _mock_server = self._ensure_mock_server()
        if self.regenerate:
            code_map, durations = self._regenerate_code()
            # Phase 1d: When regenerating via graph, save captures for future CI gates
            if self.use_graph and code_map:
                self._save_captures(code_map)
            # Full mode: persist regenerated code so the test-execution phase
            # can actually run it — without this the executor finds no test
            # files and "Tests executed: 0" is reported every run.
            if mode == "full" and self.test_output_dir is not None:
                self._persist_regenerated_tests(code_map)
        else:
            code_map = self._load_code_map()
            durations = {}

        if mode == "full":
            test_files = self._load_test_files()
            results = run_full_validation(
                self.dataset_dir,
                code_map,
                durations=durations,
                test_files=test_files,
                pytest_timeout=pytest_timeout,
            )
        else:
            results = run_static_validation(self.dataset_dir, code_map, durations)

        if persist:
            # B-036 Phase 4: LANGGRAPH_ENABLED env gate removed — --use-graph
            # is the only supported selector for graph pipeline runs.
            pipeline_type = "graph" if self.use_graph else "linear"
            gen_mode = "regenerated" if self.regenerate else "captured"
            rag_enabled = os.environ.get("RAG_ENABLED", "1") == "1"
            git_commit = _get_git_commit()
            run_ids = persist_results(
                self.db_path,
                results,
                mode,
                pipeline=pipeline_type,
                generation_mode=gen_mode,
                rag_enabled=rag_enabled,
                git_commit=git_commit,
            )
            logger.info("Persisted %d eval results: %s", len(run_ids), run_ids)

        return HarnessReport(stories=results)

    def _ensure_mock_server(self) -> Any | None:
        """Auto-start the mock HTTP server if any story needs it.

        A dataset opts in via ``base_url`` on ``http://localhost:8781`` and an
        optional ``mock_dir`` field (served as the server root). Legacy
        datasets without ``mock_dir`` (eval-005 / lv_insurance) keep the
        repo-root serving behaviour.

        Returns a ``MockServer`` instance that auto-stops on exit, or None
        if no mock server is needed.
        """
        mock_dir: str | None = None
        for dataset_file in self.dataset_dir.glob("*.json"):
            try:
                data = json.loads(dataset_file.read_text(encoding="utf-8"))
            except OSError, json.JSONDecodeError:
                continue
            base_url = data.get("base_url", "")
            if "localhost:8781" not in base_url:
                continue
            # Prefer the dataset's declared mock_dir; fall back to repo root
            # (eval-005 legacy behaviour serves generated_tests/mock_insurance_site.html
            #  from the working directory).
            mock_dir = data.get("mock_dir") or os.getcwd()
            break
        if mock_dir is None:
            return None

        from scripts.mock_server import MockServer

        logger.info("Auto-starting mock server for %s (dir=%s)...", Path(mock_dir).name, mock_dir)
        return MockServer.start(port=8781, directory=mock_dir)

    def _regenerate_code(self) -> tuple[dict[str, str], dict[str, float]]:
        """Regenerate code for all stories using the live pipeline.

        When ``self.use_graph`` is True, the multi-agent LangGraph pipeline
        is used for skeleton generation instead of the linear path.

        Each story gets a fresh orchestrator to avoid URL resolver state
        contamination across concurrent stories.
        """
        if self.use_graph:
            return self._regenerate_code_via_graph()

        import asyncio

        from src.llm_client import LLMClient
        from src.orchestrator import TestOrchestrator
        from src.test_generator import TestGenerator

        code_map: dict[str, str] = {}
        durations: dict[str, float] = {}

        async def process_story(golden_file: Path):
            golden = load_golden_key(golden_file)
            story_id = golden["id"]

            try:
                start = datetime.now(UTC).timestamp()
                # Fresh orchestrator per story — prevents state contamination
                client = LLMClient()
                generator = TestGenerator(client=client)
                orchestrator = TestOrchestrator(generator, pom_mode=False)  # flat mode for validator compatibility
                code = await orchestrator.run_pipeline(
                    user_story=golden["user_story"],
                    conditions="\n".join(golden["conditions"]),
                    target_urls=[golden["base_url"]],
                )
                durations[story_id] = datetime.now(UTC).timestamp() - start
                code_map[story_id] = code
                logger.info("Regenerated %s", story_id)
            except Exception as e:
                logger.error("Failed to regenerate %s: %s", story_id, e)
                code_map[story_id] = ""

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        # Process sequentially to avoid browser/resource conflicts
        async def run_sequential():
            for f in sorted(self.dataset_dir.glob("*.json")):
                await process_story(f)

        loop.run_until_complete(run_sequential())

        return code_map, durations

    def _regenerate_code_via_graph(self) -> tuple[dict[str, str], dict[str, float]]:
        """Regenerate code using the LangGraph multi-agent pipeline.

        Each story gets a fresh orchestrator to prevent URL resolver
        state contamination. Stories are processed sequentially to
        avoid browser/resource conflicts.
        """
        import asyncio

        from src.llm_client import LLMClient
        from src.orchestrator import TestOrchestrator
        from src.test_generator import TestGenerator

        code_map: dict[str, str] = {}
        durations: dict[str, float] = {}

        logger.info(
            "Regenerating code via graph pipeline for %d stories (sequential)...",
            len(list(self.dataset_dir.glob("*.json"))),
        )

        async def process_story(golden_file: Path):
            golden = load_golden_key(golden_file)
            story_id = golden["id"]

            try:
                start = datetime.now(UTC).timestamp()

                # Fresh orchestrator per story
                client = LLMClient()
                generator = TestGenerator(client=client)
                orchestrator = TestOrchestrator(generator, pom_mode=False)  # flat mode for validator compatibility

                # Step 1: Generate skeleton via graph
                state = await orchestrator.run_pipeline_via_graph(
                    user_story=golden["user_story"],
                    conditions="\n".join(golden["conditions"]),
                    target_urls=[golden["base_url"]],
                    auto_confirm=True,
                )

                if state is None:
                    logger.warning("Graph pipeline returned None for %s \u2014 using linear fallback", story_id)
                    code = await orchestrator.run_pipeline(
                        user_story=golden["user_story"],
                        conditions="\n".join(golden["conditions"]),
                        target_urls=[golden["base_url"]],
                    )
                elif not state.test_code:
                    logger.warning("Graph produced empty code for %s \u2014 using linear fallback", story_id)
                    code = await orchestrator.run_pipeline(
                        user_story=golden["user_story"],
                        conditions="\n".join(golden["conditions"]),
                        target_urls=[golden["base_url"]],
                    )
                else:
                    # Step 2: Feed graph skeleton into standard pipeline
                    code = await orchestrator.run_pipeline(
                        user_story=golden["user_story"],
                        conditions="\n".join(golden["conditions"]),
                        target_urls=[golden["base_url"]],
                        prebuilt_skeleton=state.test_code,
                    )

                durations[story_id] = datetime.now(UTC).timestamp() - start
                code_map[story_id] = code
                logger.info("Regenerated %s via graph", story_id)
            except Exception as e:
                logger.error("Failed to regenerate %s via graph: %s", story_id, e)
                code_map[story_id] = ""

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        async def run_sequential():
            for f in sorted(self.dataset_dir.glob("*.json")):
                await process_story(f)

        loop.run_until_complete(run_sequential())

        return code_map, durations

    def _save_captures(self, code_map: dict[str, str]) -> None:
        """Save regenerated code as capture files for future static CI comparison."""
        site_map = {
            "eval-001": "saucedemo",
            "eval-002": "automationexercise",
            "eval-003": "demoqa",
            "eval-004": "theinternet",
            "eval-005": "lv_insurance",
            "eval-006": "ecommerce_mock",
        }
        for story_id, code in code_map.items():
            site = site_map.get(story_id, story_id)
            capture_file = self.code_dir / f"{site}_code.py"
            capture_file.write_text(code, encoding="utf-8")
            logger.info("Saved capture: %s (%d chars)", capture_file.name, len(code))

    def run_semantic_comparison(self) -> dict[str, Any]:
        """Locator-level comparison: golden keys vs capture files. Fast, no browser."""
        import re

        results: dict[str, Any] = {"per_story": {}, "total_ph": 0, "total_matched": 0}
        site_map = {
            "eval-001": "saucedemo",
            "eval-002": "automationexercise",
            "eval-003": "demoqa",
            "eval-004": "theinternet",
            "eval-005": "lv_insurance",
            "eval-006": "ecommerce_mock",
        }

        for golden_file in sorted(self.dataset_dir.glob("*.json")):
            golden = load_golden_key(golden_file)
            story_id = golden["id"]
            site = site_map.get(story_id, story_id)
            capture_file = self.code_dir / f"{site}_code.py"

            if not capture_file.exists():
                results["per_story"][story_id] = {"error": "Capture not found"}
                continue

            capture_code = capture_file.read_text(encoding="utf-8")

            # Extract (action, description) → locator from capture
            capture_map: dict[tuple[str, str], str] = {}
            for line in capture_code.splitlines():
                m = re.match(
                    r'\s*evidence_tracker\.(\w+)\(["\']([^"\']+)["\'].*label=["\']([^"\']+)["\']',
                    line,
                )
                if m:
                    action = m.group(1).upper().replace("ASSERT_VISIBLE", "ASSERT").replace("NAVIGATE", "GOTO")
                    capture_map[(action, m.group(3))] = m.group(2)

            # Compare golden key placeholders against capture locators
            story_total = 0
            story_matched = 0
            for crit in golden.get("golden_resolutions", []):
                for ph in crit.get("placeholders", []):
                    story_total += 1
                    ph_action = ph["action"]
                    ph_desc = ph["description"]
                    expected_loc = ph.get("expected_locator", "")
                    tolerance = ph.get("tolerance_selectors", [])

                    for (ca_action, ca_desc), ca_loc in capture_map.items():
                        if ca_action == ph_action:
                            ca_tokens = set(ca_desc.lower().split())
                            ph_tokens = set(ph_desc.lower().split())
                            if ca_tokens & ph_tokens:
                                if ca_loc == expected_loc or ca_loc in tolerance:
                                    story_matched += 1
                                    break

            results["per_story"][story_id] = {
                "total": story_total,
                "matched": story_matched,
                "accuracy": story_matched / story_total * 100 if story_total else 0,
            }
            results["total_ph"] += story_total
            results["total_matched"] += story_matched

        results["accuracy"] = results["total_matched"] / results["total_ph"] * 100 if results["total_ph"] else 0
        return results

    def print_semantic_report(self, results: dict[str, Any]) -> None:
        """Print the semantic comparison report."""
        print("=" * 70)
        print("SEMANTIC COMPARISON (locator-level — no browser)")
        print("=" * 70)
        print(f"\n  Placeholders evaluated: {results['total_ph']}")
        print(f"  Semantic matches:      {results['total_matched']}")
        print(f"  Accuracy:              {results['accuracy']:.1f}%")
        print()
        print("-" * 70)
        for story_id, data in sorted(results["per_story"].items()):
            if "error" in data:
                print(f"  {story_id}: ERROR — {data['error']}")
            else:
                print(f"  {story_id}: {data['matched']}/{data['total']} ({data['accuracy']:.1f}%)")
        print("=" * 70)
