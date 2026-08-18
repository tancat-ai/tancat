"""Tests for the egress audit gate (Phase 6 6a — "no data leaves your deployment").

Hermetic: classification is pure string analysis; the only repo scan asserted
is the real product runtime (which must stay clean), plus fixture files for
the flagging rules.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import scripts.audit_egress as audit

REPO_ROOT = Path(__file__).resolve().parent.parent


def _write(tmp_path: Path, name: str, content: str) -> Path:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


def test_product_runtime_is_clean() -> None:
    """The real product runtime must have zero flagged call sites."""
    result = audit.run_audit(audit.DEFAULT_SCOPE)
    assert result.errors == []
    assert result.scanned_files > 100  # src/ is substantial
    assert result.sites, "expected to find the known call sites"
    assert result.flagged == []


def test_hardcoded_third_party_call_is_flagged(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "phone_home.py",
        'import httpx\n\ndef telemetry() -> None:\n    httpx.get("https://telemetry.example.com/beacon")\n',
    )
    result = audit.run_audit([str(path)])
    (site,) = result.sites
    assert site.classification == "FLAGGED"
    assert "telemetry.example.com" in site.statement


def test_user_configured_call_is_allowed(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "client.py",
        "def chat(base_url: str) -> None:\n    httpx.Client(base_url=f'{base_url}/v1', timeout=300)\n",
    )
    result = audit.run_audit([str(path)])
    (site,) = result.sites
    assert site.classification == "USER-CONFIGURED"


def test_urllib_parse_is_not_a_call_site(tmp_path: Path) -> None:
    """urllib.parse is pure URL manipulation, not outbound traffic."""
    path = _write(
        tmp_path,
        "parser.py",
        "from urllib.parse import urljoin\n\ndef join(base: str, p: str) -> str:\n    return urljoin(base, p)\n",
    )
    result = audit.run_audit([str(path)])
    assert result.sites == []


def test_identifier_ending_in_requests_is_not_a_call_site(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "ranker.py",
        "def rank() -> None:\n    pass3_requests.append((1, 'a', 'b'))  # not an HTTP client\n",
    )
    result = audit.run_audit([str(path)])
    assert result.sites == []


def test_httpx_type_names_are_not_call_sites(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "types.py",
        "import httpx\n\ndef handle(e: httpx.ConnectError) -> None:\n    pass\n",
    )
    result = audit.run_audit([str(path)])
    assert result.sites == []


def test_missing_scope_item_is_a_scan_error(tmp_path: Path) -> None:
    result = audit.run_audit([str(tmp_path / "does_not_exist.py")])
    assert result.errors
    assert audit.main(["--scope", str(tmp_path / "does_not_exist.py")]) == 1


def test_main_exit_codes(tmp_path: Path) -> None:
    clean = _write(tmp_path, "clean.py", "def f(base_url: str) -> None:\n    httpx.get(base_url)\n")
    flagged = _write(tmp_path, "bad.py", 'import httpx\nhttpx.get("https://beacon.example.com/x")\n')

    assert audit.main(["--scope", str(clean)]) == 0
    assert audit.main(["--scope", str(flagged)]) == 1
    # --json shape
    assert audit.main(["--scope", str(flagged), "--json"]) == 1


def test_json_manifest_shape(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    flagged = _write(tmp_path, "bad.py", 'import httpx\nhttpx.get("https://beacon.example.com/x")\n')
    audit.main(["--scope", str(flagged), "--json"])
    import json

    payload = json.loads(capsys.readouterr().out)
    assert payload["verdict"] == "FLAGGED"
    assert payload["flagged"][0]["file"].endswith("bad.py")
    assert payload["flagged"][0]["classification"] == "FLAGGED"
