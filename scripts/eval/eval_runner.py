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
import sqlite3
import subprocess
import uuid
from collections.abc import Callable
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
    git_commit   TEXT NOT NULL DEFAULT '',
    temperature_sent REAL,
    server_defaults  TEXT,
    thinking         TEXT
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
    """Create eval_runs table and index if they don't exist.

    Newer columns (temperature_sent, server_defaults, thinking) are added to
    pre-existing databases via ALTER TABLE so historical rows keep NULL
    (accurate: the delivered sampling config was unknown for those runs).
    """
    conn.execute(_EVAL_SCHEMA_SQL)
    conn.execute(_EVAL_INDEX_SQL)
    for column_decl in (
        "temperature_sent REAL",
        "server_defaults TEXT",
        "thinking TEXT",
    ):
        try:
            conn.execute(f"ALTER TABLE eval_runs ADD COLUMN {column_decl}")
        except sqlite3.OperationalError:
            pass  # column already exists (fresh table or previously migrated)
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
    on_story: Callable[[str], None] | None = None,
) -> list[StoryResult]:
    """Run full validation: static + test execution.

    Args:
        dataset_dir: Path to scripts/eval/dataset/
        code_map: Dict mapping story_id to generated Python code string.
        durations: Optional dict mapping story_id to generation duration.
        test_files: Optional dict mapping story_id to Path of generated test file.
            If provided, tests are executed via pytest.
        pytest_timeout: Timeout for each pytest run in seconds.
        on_story: Optional per-story hook called with ``story_id`` before its
            tests execute (used to serve the correct localhost-mock root).

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

        if on_story is not None:
            on_story(story.story_id)

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
    temperature_sent: float | None = None,
    server_defaults: str = "",
    thinking: str = "",
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
                     pipeline, generation_mode, rag_enabled, pom_mode, provider, model, git_commit,
                     temperature_sent, server_defaults, thinking)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    temperature_sent,
                    server_defaults,
                    thinking,
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


def rag_enabled_by_config() -> bool:
    """Deprecated local mirror — kept for import compatibility.

    The single source of truth now lives in
    ``src.orchestrator.rag_enabled_by_config`` (B-036 semantics: missing
    ``RAG_ENABLED`` means enabled; only ``=0`` opts out).
    """
    from src.orchestrator import rag_enabled_by_config as _pipeline_gate

    return _pipeline_gate()


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
        # Phase 6 6a follow-up (eval fix): per-story mock serving. ``story_id``
        # -> served directory for localhost-mock datasets; the single mock
        # server on :8781 is (re)started per story so each mock family is
        # served at root (golden keys reference root-relative URLs).
        self._story_mock_dirs: dict[str, str] = {}
        self._mock_server: Any | None = None
        self._mock_serving_dir: str | None = None

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
        # Auto-manage mock serving (Phase 6 6a follow-up): the :8781 server is
        # (re)started per story so each mock family is served at root (golden
        # keys reference root-relative URLs). No server starts until a mock
        # story actually processes.
        self._story_mock_dirs = self._build_mock_dirs()
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
                on_story=self._on_story_mock_swap,
            )
        else:
            results = run_static_validation(self.dataset_dir, code_map, durations)

        if persist:
            # B-036 Phase 4: LANGGRAPH_ENABLED env gate removed — --use-graph
            # is the only supported selector for graph pipeline runs.
            pipeline_type = "graph" if self.use_graph else "linear"
            gen_mode = "regenerated" if self.regenerate else "captured"
            # Record the pipeline's ACTUAL RAG gate (B-036: default-on),
            # not raw env presence — see rag_enabled_by_config().
            rag_enabled = rag_enabled_by_config()
            git_commit = _get_git_commit()
            provider, model = self._loaded_model_identity()
            temperature_sent, server_defaults, thinking = self._sampling_identity(self.use_graph)
            run_ids = persist_results(
                self.db_path,
                results,
                mode,
                pipeline=pipeline_type,
                generation_mode=gen_mode,
                rag_enabled=rag_enabled,
                git_commit=git_commit,
                provider=provider,
                model=model,
                temperature_sent=temperature_sent,
                server_defaults=server_defaults,
                thinking=thinking,
            )
            logger.info("Persisted %d eval results: %s", len(run_ids), run_ids)

        return HarnessReport(stories=results)

    def _build_mock_dirs(self, repo_root: Path | None = None) -> dict[str, str]:
        """Map each localhost-mock story to the directory it must be served from.

        A dataset opts in via ``base_url`` on ``http://localhost:8781`` and an
        optional ``mock_dir`` field (served as the server root). Legacy
        datasets without ``mock_dir`` (eval-005 / lv_insurance) are served
        from the repo root (their ``generated_tests/...`` URLs resolve there).

        Each mock family must be served at root — golden keys reference
        root-relative URLs (``/cart.html`` etc.) — so stories with different
        mock dirs cannot share one server: :meth:`_ensure_mock_serves` swaps
        the server per story.

        Args:
            repo_root: Injectable repo root (tests use a scratch dir);
                defaults to the module's own location
                (``<repo>/scripts/eval/eval_runner.py``).
        """
        repo_root = (repo_root or Path(__file__).resolve().parent.parent.parent).resolve()
        result: dict[str, str] = {}
        for dataset_file in sorted(self.dataset_dir.glob("*.json")):
            try:
                data = json.loads(dataset_file.read_text(encoding="utf-8"))
            except OSError, json.JSONDecodeError:
                continue
            base_url = data.get("base_url", "")
            if "localhost:8781" not in base_url:
                continue
            story_id = str(data.get("id") or dataset_file.stem)
            mock_dir = data.get("mock_dir") or ""
            if mock_dir:
                result[story_id] = str((repo_root / mock_dir).resolve())
            else:
                # Legacy (eval-005): served from the repo root so
                # ``/generated_tests/mock_insurance_site.html`` resolves.
                result[story_id] = str(repo_root)
        return result

    def _ensure_mock_serves(self, mock_dir: str | None) -> None:
        """(Re)start the :8781 mock server when *mock_dir* differs from the current one.

        Stories that don't need the mock (live-site datasets) pass ``None``
        and leave any running server untouched. Restarting is cheap (daemon
        thread + ``allow_reuse_address``) and happens per story in both the
        regeneration and execution phases.
        """
        if mock_dir is None:
            return
        if self._mock_server is not None and self._mock_serving_dir == mock_dir:
            return
        if self._mock_server is not None:
            self._mock_server.stop()
            self._mock_server = None
        from scripts.mock_server import MockServer

        self._mock_server = MockServer.start(port=8781, directory=mock_dir)
        self._mock_serving_dir = mock_dir

    def _on_story_mock_swap(self, story_id: str) -> None:
        """Execution-phase hook: serve the right mock root for *story_id*."""
        self._ensure_mock_serves(self._story_mock_dirs.get(story_id))

    def _loaded_model_identity(self) -> tuple[str, str]:
        """Best-effort (provider, model) of the LLM that produced this run.

        Recorded into ``eval_runs`` so A/B runs across model swaps are
        comparable (the 3.6-vs-3.8 comparison this fix came from was
        hampered by an empty ``model`` column). Returns ``("", "")`` when
        no endpoint is reachable.
        """
        try:
            from src.llm_providers import auto_detect_provider

            provider = auto_detect_provider()
            return str(provider.provider_name), str(provider.get_loaded_model(timeout=5) or "")
        except Exception:
            return "", ""

    def _sampling_identity(self, use_graph: bool) -> tuple[float | None, str, str]:
        """Resolved (temperature_sent, server_defaults, thinking) for a run.

        ``temperature_sent`` is the sampling temperature the pipeline actually
        delivers: graph runs always send 0 (agents pin ``temperature=0``);
        linear runs send ``AITEST_LLM_TEMPERATURE`` or the 0.0 pipeline
        default (``src.llm_client.llm_temperature_default``). ``None`` is
        never produced for new runs — it only existed for legacy rows before
        the pin.

        ``thinking`` records the thinking-mode policy of the run, so a future
        session can never be misled about what a number was measured with
        (the 2026-08-18 root cause: thinking models burning the token budget
        on reasoning and returning empty content). "off" = the structured
        calls (skeleton generation + resolution ranking) send
        ``enable_thinking=False`` explicitly — the linear pipeline default
        since the fix. "model-default" = graph stages currently inherit the
        model/server default (measured opt-in/out per stage is future work).

        ``server_defaults`` is a best-effort JSON snapshot of the endpoint's
        advertised sampling defaults (``/props`` on llama.cpp), so future A/Bs
        can tell model differences from launch-config differences. Falls back
        to ``{}`` when the endpoint isn't reachable.
        """
        thinking = "model-default" if use_graph else None
        if use_graph:
            temperature_sent = 0.0
        else:
            try:
                from src.llm_client import enable_thinking_default, llm_temperature_default

                temperature_sent = llm_temperature_default()
                thinking = "on" if enable_thinking_default() else "off"
            except Exception:
                temperature_sent = None
                thinking = thinking or "off"

        server_defaults: dict[str, float | int | str] = {}
        try:
            import httpx

            from src.llm_providers import auto_detect_provider

            provider = auto_detect_provider()
            base_url = str(provider.base_url)
            if not base_url.startswith("http"):
                base_url = "".join(("http://", base_url))
            # OpenAI-compatible providers use an <origin>/v1 base; /props lives
            # at the origin (llama.cpp's own endpoint).
            base_url = base_url.rstrip("/")
            if base_url.endswith("/v1"):
                base_url = base_url[: -len("/v1")]
            props = {}
            try:
                resp = httpx.get(f"{base_url}/props", timeout=5)
                if resp.status_code == 200:
                    props = resp.json()
            except Exception:
                props = {}
            # Server identity + build (mirrors llm-benchmarks' bench_manifest).
            server_defaults["model_path"] = props.get("model_path", "")
            server_defaults["build_info"] = props.get("build_info", "")
            server_defaults["model_ftype"] = props.get("model_ftype", "")
            # Sampling defaults the server would apply if unset.
            params = props.get("default_generation_settings", {}).get("params", {})
            for key in ("temperature", "top_p", "top_k", "min_p", "seed", "repeat_penalty"):
                if key in params:
                    server_defaults[key] = params[key]
            server_defaults["n_ctx"] = props.get("default_generation_settings", {}).get("n_ctx", 0)
            # Serving reality from /slots (n_ctx + speculative are the fields
            # that ACTUALLY differ between launches — see the 262k-vs-156k and
            # draft-mtp-on/off config drift that confounded the model A/B).
            try:
                slots = httpx.get(f"{base_url}/slots", timeout=5).json()
                if isinstance(slots, list) and slots:
                    s0 = slots[0]
                    server_defaults["slot_n_ctx"] = s0.get("n_ctx", 0)
                    server_defaults["speculative"] = bool(s0.get("speculative", False))
            except Exception:
                pass
        except json.JSONDecodeError:
            pass
        except Exception:
            pass
        return temperature_sent, json.dumps(server_defaults, sort_keys=True), thinking

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
        from src.semantic_candidate_ranker import DEFAULT_RESOLUTION_TIMEOUT
        from src.test_generator import TestGenerator

        code_map: dict[str, str] = {}
        durations: dict[str, float] = {}

        async def process_story(golden_file: Path):
            golden = load_golden_key(golden_file)
            story_id = golden["id"]

            try:
                start = datetime.now(UTC).timestamp()
                # Serve the right mock root for this story (localhost-mock
                # stories share the :8781 port; each family must be served at
                # root for golden-key page-scoping to match).
                self._ensure_mock_serves(self._story_mock_dirs.get(story_id))
                # Fresh orchestrator per story — prevents state contamination
                client = LLMClient()
                generator = TestGenerator(client=client)
                # Explicit consumer: eval measures resolution, so the timeout is
                # passed deliberately (default lives in DEFAULT_RESOLUTION_TIMEOUT).
                orchestrator = TestOrchestrator(
                    generator, pom_mode=False, resolution_timeout=DEFAULT_RESOLUTION_TIMEOUT
                )  # flat mode for validator compatibility
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
        from src.semantic_candidate_ranker import DEFAULT_RESOLUTION_TIMEOUT
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
                # Explicit consumer: eval measures resolution, so the timeout is
                # passed deliberately (default lives in DEFAULT_RESOLUTION_TIMEOUT).
                orchestrator = TestOrchestrator(
                    generator, pom_mode=False, resolution_timeout=DEFAULT_RESOLUTION_TIMEOUT
                )  # flat mode for validator compatibility

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
