"""UAT records the RAG state and, when instrumented, the RAG contribution (t-0488).

These exercise the recording helpers and the JSON shape only — no pipeline run,
no LLM, no browser.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(_SCRIPTS_DIR))

import uat  # noqa: E402


def test_rag_contribution_is_none_when_uninstrumented(monkeypatch: pytest.MonkeyPatch) -> None:
    """UAT does not set the diagnostics path, so there is no contribution number."""
    monkeypatch.delenv("AI059_RAG_DIAGNOSTICS_PATH", raising=False)
    assert uat._rag_contribution_since(0) is None  # noqa: SLF001
    assert uat._rag_diagnostic_line_count() == 0  # noqa: SLF001


def test_rag_contribution_counts_only_this_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """When instrumented, the summary covers only records this run appended."""
    path = tmp_path / "rag_usage.jsonl"
    records = [
        {"action": "CLICK", "description": "old", "usage": [{"matched": True, "bonus": 5}]},
        {
            "action": "CLICK",
            "description": "new",
            "decisive": True,
            "usage": [{"matched": True, "bonus": 3}, {"matched": False, "bonus": 0}],
        },
        # A retrieval record (no usage) must not count as a scored placeholder.
        {"action": "CLICK", "description": "new", "results": []},
    ]
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
    monkeypatch.setenv("AI059_RAG_DIAGNOSTICS_PATH", str(path))

    assert uat._rag_diagnostic_line_count() == 3  # noqa: SLF001
    summary = uat._rag_contribution_since(1)  # noqa: SLF001
    assert summary == {
        "source": str(path),
        "records": 1,
        "decisive": 1,
        "matched": 1,
        "bonus": 3,
    }


def test_site_result_dict_carries_rag_fields() -> None:
    result = uat.SiteResult(site_id="tancat", site_name="tancat.dev", pom_mode=True)
    result.rag_enabled = True
    result.rag_contribution = {"records": 2, "decisive": 1, "matched": 2, "bonus": 4, "source": "x"}

    data = result.to_dict()
    assert data["rag_enabled"] is True
    assert data["rag_contribution"]["decisive"] == 1
