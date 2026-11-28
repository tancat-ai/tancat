"""t-1488: the CLI export command obeys the cap through the one export path.

The UI case is pinned by ``test_streamlit_evidence_exports.py``; this is the other
half. The CLI writes a file, so it takes the metered branch of ``export_evidence``:
past the cap it must print the meter's own sentence, exit non-zero, and leave no
file behind. Inside the cap it writes the file and records exactly one export.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from src.usage_meter import UsageMeter

CSV_HEADER = "test_name\nx\n"


def _entries(count: int) -> list[dict[str, str]]:
    now = datetime.now(UTC).isoformat()
    return [{"format": "csv", "output": "", "at": now} for _ in range(count)]


@pytest.fixture
def ledger(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """The meter's own ledger, redirected to a file this test owns."""
    path = tmp_path / "usage_ledger.json"
    monkeypatch.setattr(UsageMeter, "_ledger", lambda self: path)
    return path


class _Index:
    """One matching row, so the command does not stop at 'nothing exported'."""

    def search(self, **_kwargs: object) -> list[object]:
        return [object()]


def _export(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Run the real CLI command against a throwaway index; return its output path.

    ``main`` returns None on success and raises SystemExit on refusal, so the exit
    status is the assertion, not a return value.
    """
    import cli.evidence_cli as cli
    import src.evidence_export as evidence_export

    monkeypatch.setattr(cli, "_build_index", _Index)
    # The bytes are not the subject here - the cap is. Keep the builder cheap.
    monkeypatch.setattr(evidence_export, "_csv_text", lambda index, **kwargs: CSV_HEADER)

    out = tmp_path / "evidence.csv"
    cli.main(["export", "--format", "csv", "--output", str(out)])
    return out


def test_past_the_cap_the_cli_refuses_and_writes_nothing(
    tmp_path: Path,
    ledger: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    limit = UsageMeter().exports_limit
    assert limit is not None, "this test needs a capped tier"
    ledger.write_text(json.dumps({"exports": _entries(limit), "runs": []}), encoding="utf-8")

    with pytest.raises(SystemExit) as exit_info:
        _export(tmp_path, monkeypatch)

    assert exit_info.value.code == 1
    captured = capsys.readouterr()
    combined = captured.out + captured.err
    assert "evidence-export limit reached" in combined, combined
    assert not (tmp_path / "evidence.csv").exists(), "a capped export still wrote the file"


def test_inside_the_cap_the_cli_writes_the_file(tmp_path: Path, ledger: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    ledger.write_text(json.dumps({"exports": [], "runs": []}), encoding="utf-8")
    before = UsageMeter().count_exports_this_month()

    out = _export(tmp_path, monkeypatch)

    assert out.exists()
    assert out.read_text(encoding="utf-8").startswith("test_name")
    assert UsageMeter().count_exports_this_month() == before + 1, "the export was not charged"
