"""Tests for the egress audit gate (Phase 6 6a — "no data leaves your deployment").

Hermetic: classification is pure string analysis; the only repo scan asserted
is the real product runtime (which must stay clean), plus fixture files for
the flagging rules.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

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


# ---------------------------------------------------------------------------
# t-1521: the scanner reads structure, and the two holes are closed
# ---------------------------------------------------------------------------


def _module() -> Any:
    import importlib.util
    import sys

    module_path = Path(__file__).resolve().parent.parent / "scripts" / "audit_egress.py"
    spec = importlib.util.spec_from_file_location("audit_egress_under_test", module_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolves the module by name
    spec.loader.exec_module(module)
    return module


def _scan(tmp_path: Path, source: str, name: str = "sample.py") -> list:
    module = _module()

    target = tmp_path / name
    target.write_text(source, encoding="utf-8")
    sites: list = []
    module.audit_file(target, sites)
    return sites


def test_an_aliased_client_is_still_found(tmp_path: Path) -> None:
    """`import httpx as hx; hx.get(...)` used to be invisible (t-1521)."""
    sites = _scan(
        tmp_path,
        "import httpx as hx\n\ndef f():\n    return hx.get('https://telemetry.example.com/beacon')\n",
    )

    assert len(sites) == 1
    assert sites[0].primitive == "httpx.get"
    assert sites[0].classification == "FLAGGED"


def test_a_dynamic_getattr_call_is_flagged(tmp_path: Path) -> None:
    """`getattr(httpx, 'get')(...)` hides the verb; that is a finding, not a pass."""
    sites = _scan(
        tmp_path,
        "import httpx\n\ndef f():\n    return getattr(httpx, 'get')('https://telemetry.example.com')\n",
    )

    assert len(sites) == 1
    assert sites[0].classification == "FLAGGED"
    assert "dynamic" in sites[0].reason


def test_a_second_call_inside_an_allow_listed_function_is_flagged(tmp_path: Path) -> None:
    """The allow-list names ONE call site, not a whole function (t-1521)."""
    sites = _scan(
        tmp_path,
        "import urllib.request\n\nFEED_URL = 'https://pypi.org/pypi/tancat/json'\n\n"
        "def _fetch(url):\n"
        "    urllib.request.urlopen(url)\n"
        "    return urllib.request.urlopen('https://telemetry.example.com/collect')\n",
        name="version_check.py",
    )

    assert len(sites) == 2
    # Neither call is allowed any more: the allow-list covered the whole function before.
    assert not any(site.classification == "ALLOW-LISTED" for site in sites)
    assert any("second call" in site.reason for site in sites)


def test_the_two_real_allow_listed_call_sites_are_named(tmp_path: Path) -> None:
    """The repo's own calls: the PyPI feed and our licence relay, and nothing else."""
    import subprocess
    import sys

    root = Path(__file__).resolve().parent.parent
    out = subprocess.run(
        [sys.executable, str(root / "scripts" / "audit_egress.py"), "--json"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    import json

    payload = json.loads(out)
    allowed = {
        site["file"]: site["reason"] for site in payload["call_sites"] if site["classification"] == "ALLOW-LISTED"
    }

    assert payload["verdict"] == "CLEAN"
    assert "src/version_check.py" in allowed
    assert "src/licensing/activation.py" in allowed
    assert "relay" in allowed["src/licensing/activation.py"].lower()


def test_the_allow_list_is_found_from_a_deep_temp_path(tmp_path: Path) -> None:
    """The CI shape: a POSIX temp path several levels deep (t-1532).

    The local run passed because a Windows temp path has no "/" in it, so a
    separator-counting rule matched. On CI the same fixture lives at
    /tmp/pytest-…/…/version_check.py and no longer matched, so the "second call"
    reason never fired. The rule is now "the file's name, when it is outside the
    repo", which does not care how deep the directory is.
    """
    module = _module()
    deep = tmp_path / "a" / "b" / "c" / "version_check.py"
    deep.parent.mkdir(parents=True)
    deep.write_text("def _fetch(url):\n    pass\n", encoding="utf-8")

    entry = module._allow_list_for("/tmp/pytest-1/test_x0/version_check.py", deep)

    assert entry, "the allow-list is not found from a deep POSIX temp path"
    assert "_fetch" in entry
