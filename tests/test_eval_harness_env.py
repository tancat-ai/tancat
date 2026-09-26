"""The gate harness must load .env before dispatching.

A worktree or CI checkout has no exported LLM environment. Without
``load_dotenv()`` the harness silently auto-detected the provider instead of
honouring the operator's ``.env`` — the same silent-divergence class as B-095
(worktree runs measuring the wrong thing).
"""

from __future__ import annotations

import importlib.util
import types
from pathlib import Path
from unittest.mock import patch

_HARNESS_PATH = Path(__file__).resolve().parent.parent / "scripts" / "eval" / "eval_harness.py"


def _load_harness_module() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location("eval_harness_under_test", _HARNESS_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class TestEvalHarnessLoadsDotenv:
    def test_main_loads_dotenv_before_dispatch(self) -> None:
        harness = _load_harness_module()
        with patch.object(harness, "load_dotenv") as mock_load:
            result = harness.main([])  # no subcommand -> prints help, returns 0
        assert result == 0
        mock_load.assert_called_once()
