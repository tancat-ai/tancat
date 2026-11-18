"""A licence file we sign, verified offline, with no provider in the path (j-0309).

Why this class of test exists: the store key is only as durable as the store. The
signed file has to verify with no network, reject any edit, reject a foreign key,
and enforce the update window from its own payload - and the legacy key has to keep
working beside it, with the signed file winning when both are present.

Every test here uses a throwaway ed25519 key, and the fixture points the build's
trust root at it. The vendor's private key is not in this repository and must never
be: only the public key ships.
"""

from __future__ import annotations

import ast
import base64
import json
import socket
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from src.licensing import activation, entitlement, signed_file
from src.licensing.merchant import MERCHANT_OF_RECORD
from src.licensing.signed_file import REQUIRED_FIELDS, signed_file_text, verify_signed_file

ROOT = Path(__file__).resolve().parent.parent
SIGNED_MODULE = ROOT / "src" / "licensing" / "signed_file.py"

#: Modules whose presence in the verification path would mean a call is possible.
NETWORK_MODULES = ("socket", "urllib", "http", "requests", "httpx", "aiohttp", "ssl")


def _keypair() -> tuple[bytes, str]:
    """A throwaway ed25519 key: raw private bytes, base64 public key."""
    private = ed25519.Ed25519PrivateKey.generate()
    raw = private.private_bytes(
        serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption()
    )
    public = private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return raw, base64.b64encode(public).decode()


@pytest.fixture
def trusted_key(monkeypatch: pytest.MonkeyPatch) -> tuple[bytes, str]:
    """A throwaway key that becomes this build's trust root for the test."""
    private, public = _keypair()
    monkeypatch.setattr(signed_file, "VENDORED_PUBLIC_KEY_B64", public)
    return private, public


def _payload(**overrides: Any) -> dict[str, str]:
    purchased = date(2026, 11, 10)
    data = {
        "id": "TC-2026-000123",
        "product": "tancat",
        "buyer_ref": "order 4821 / buyer@example.com",
        "purchased_at": purchased.isoformat(),
        "window_end": (purchased + timedelta(days=365)).isoformat(),
        "tier": "pro",
    }
    data.update({k: v for k, v in overrides.items() if v is not None})
    return {k: str(v) for k, v in data.items() if v is not None}


def _write_licence(path: Path, private: bytes, **overrides: Any) -> dict[str, str]:
    payload = _payload(**overrides)
    path.write_text(signed_file_text(payload, private), encoding="utf-8")
    return payload


# ---------------------------------------------------------------------------
# The happy path, and the ways a file can be wrong
# ---------------------------------------------------------------------------


def test_a_valid_file_verifies_and_carries_the_payload(trusted_key: tuple[bytes, str]) -> None:
    private, public = trusted_key
    result = verify_signed_file(signed_file_text(_payload(), private), public)

    assert result.valid, result.reason
    assert result.licence is not None
    assert result.licence.id == "TC-2026-000123"
    assert result.licence.product == "tancat"
    assert result.licence.buyer_ref.startswith("order 4821")
    assert result.licence.tier == "pro"
    assert result.licence.window_end == date(2027, 11, 10)


def test_a_tampered_payload_is_refused(trusted_key: tuple[bytes, str]) -> None:
    """Every field is covered by the signature, so any edit breaks it."""
    private, public = trusted_key
    document = json.loads(signed_file_text(_payload(), private))

    for field, replacement in (
        ("tier", "free"),
        ("window_end", "2099-01-01"),
        ("purchased_at", "2020-01-01"),
        ("id", "TC-2026-999999"),
        ("buyer_ref", "someone else"),
    ):
        altered = json.loads(json.dumps(document))
        altered["payload"][field] = replacement
        result = verify_signed_file(json.dumps(altered), public)
        assert not result.valid, f"an edited {field} still verified"
        assert "signature does not verify" in result.reason


def test_a_file_signed_with_a_different_key_is_refused(trusted_key: tuple[bytes, str]) -> None:
    _, public = trusted_key
    foreign_private, _ = _keypair()
    text = signed_file_text(_payload(), foreign_private)

    result = verify_signed_file(text, public)
    assert not result.valid
    assert "signature does not verify" in result.reason

    # And the real trust root does not accept a throwaway key's signature either.
    assert not verify_signed_file(text).valid


def test_a_licence_for_another_product_is_refused(trusted_key: tuple[bytes, str]) -> None:
    private, public = trusted_key
    result = verify_signed_file(signed_file_text(_payload(product="not-tancat"), private), public)
    assert not result.valid
    assert "not for" in result.reason


def test_a_payload_missing_a_field_is_refused(trusted_key: tuple[bytes, str]) -> None:
    private, public = trusted_key
    payload = _payload()
    for field in REQUIRED_FIELDS:
        incomplete = {k: v for k, v in payload.items() if k != field}
        result = verify_signed_file(signed_file_text(incomplete, private), public)
        assert not result.valid, f"a payload without {field} verified"
        assert field in result.reason


def test_a_non_licence_file_is_refused_without_raising() -> None:
    for text in ("", "   ", "not json", "[]", '{"format": "tancat-licence/1"}', '{"format": "other/1"}'):
        assert not verify_signed_file(text).valid


# ---------------------------------------------------------------------------
# The window: from the file, at upgrade and at startup
# ---------------------------------------------------------------------------


def test_an_expired_window_refuses_an_upgrade_and_a_startup(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, trusted_key: tuple[bytes, str]
) -> None:
    private, _ = trusted_key
    purchased = date(2025, 1, 1)
    licence_path = tmp_path / "licence.signed.json"
    payload = _write_licence(
        licence_path,
        private,
        purchased_at=purchased.isoformat(),
        window_end=(purchased + timedelta(days=30)).isoformat(),
    )
    monkeypatch.setenv("AITEST_LICENCE_FILE", str(licence_path))
    monkeypatch.setattr(activation, "read_licence", lambda path=None: None)

    build = purchased + timedelta(days=400)

    upgrade = entitlement.upgrade_check(build_date=build, installed_version="0.1.0")
    assert not upgrade.allowed
    assert "after your update window ended" in upgrade.message
    assert payload["window_end"] in upgrade.message
    assert "0.1.0 keeps working" in upgrade.message

    startup = entitlement.startup_check(build_date=build, installed_version="0.1.0")
    assert not startup.allowed
    assert payload["window_end"] in startup.message


def test_a_build_inside_the_window_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, trusted_key: tuple[bytes, str]
) -> None:
    private, _ = trusted_key
    licence_path = tmp_path / "licence.signed.json"
    payload = _write_licence(licence_path, private)
    monkeypatch.setenv("AITEST_LICENCE_FILE", str(licence_path))
    monkeypatch.setattr(activation, "read_licence", lambda path=None: None)

    build = date.fromisoformat(payload["purchased_at"]) + timedelta(days=10)
    decision = entitlement.startup_check(build_date=build)
    assert decision.allowed
    assert decision.window_end == date.fromisoformat(payload["window_end"])


# ---------------------------------------------------------------------------
# Precedence, Free, and the merchant name
# ---------------------------------------------------------------------------


def test_no_file_and_no_key_is_free(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AITEST_LICENCE_FILE", str(tmp_path / "absent.json"))
    monkeypatch.setattr(activation, "read_licence", lambda path=None: None)

    state = entitlement.resolve()
    assert state.source == "none"
    assert state.tier == "free"
    assert entitlement.startup_check().allowed, "a Free install must never be refused"


def test_a_signed_file_wins_over_a_store_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, trusted_key: tuple[bytes, str]
) -> None:
    private, _ = trusted_key
    licence_path = tmp_path / "licence.signed.json"
    _write_licence(licence_path, private, tier="pro")
    monkeypatch.setenv("AITEST_LICENCE_FILE", str(licence_path))
    monkeypatch.setattr(activation, "read_licence", lambda path=None: {"key": "legacy", "key_created_at": "2020-01-01"})

    state = entitlement.resolve()
    assert state.source == "signed"
    assert state.tier == "pro"
    assert state.window_end == date(2027, 11, 10)


def test_a_broken_signed_file_falls_back_to_the_key_and_says_so(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A corrupted file must not strand a buyer who also holds a working key."""
    licence_path = tmp_path / "licence.signed.json"
    licence_path.write_text('{"format": "tancat-licence/1", "payload": {}, "signature": "AAAA"}', encoding="utf-8")
    monkeypatch.setenv("AITEST_LICENCE_FILE", str(licence_path))
    monkeypatch.setattr(
        activation,
        "read_licence",
        lambda path=None: {"key": "legacy", "key_created_at": "2026-01-01", "tier": "pro"},
    )

    state = entitlement.resolve()
    assert state.source == "legacy"
    assert state.problem, "the broken file must be reported, not swallowed"


def test_the_merchant_name_lives_in_one_constant() -> None:
    """A rename must be one edit; a literal elsewhere would drift."""
    spelled: list[str] = []
    for path in sorted((ROOT / "src").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        docstrings = {
            id(node.body[0].value)
            for node in ast.walk(tree)
            if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
            and node.body
            and isinstance(node.body[0], ast.Expr)
            and isinstance(node.body[0].value, ast.Constant)
            and isinstance(node.body[0].value.value, str)
        }
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings:
                if MERCHANT_OF_RECORD.lower() in node.value.lower():
                    spelled.append(path.relative_to(ROOT).as_posix())
                    break

    # Copy is what a rename has to change; explanatory docstrings may name the store.
    assert spelled == ["src/licensing/merchant.py"], (
        f"the merchant name is spelled in copy outside merchant.py: {spelled}"
    )
    assert MERCHANT_OF_RECORD
    assert MERCHANT_OF_RECORD in entitlement.MIGRATION_PARAGRAPH


# ---------------------------------------------------------------------------
# Nothing in verification can call out
# ---------------------------------------------------------------------------


def test_the_verification_module_imports_no_network_code() -> None:
    """A static check, so a future edit cannot quietly add a call."""
    tree = ast.parse(SIGNED_MODULE.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])

    offending = sorted(imported & set(NETWORK_MODULES))
    assert offending == [], f"signed_file.py imports network modules: {offending}"
    assert "activation" not in imported, "verification must not import the activation path"


def test_verification_works_with_the_socket_module_disabled(
    monkeypatch: pytest.MonkeyPatch, trusted_key: tuple[bytes, str]
) -> None:
    """The behavioural half: block the network and verify a real file."""
    private, public = trusted_key
    text = signed_file_text(_payload(), private)

    def _no_socket(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("verification tried to open a socket")

    monkeypatch.setattr(socket, "socket", _no_socket)
    monkeypatch.setattr(socket, "create_connection", _no_socket)

    result = verify_signed_file(text, public)
    assert result.valid, result.reason


def test_the_migration_paragraph_is_in_the_user_docs() -> None:
    """Existing key holders must be told, in the page they already read."""
    docs = (ROOT / "docs" / "user" / "reference" / "licensing.md").read_text(encoding="utf-8")
    assert "already hold" in docs.lower()
    assert "signed licence file" in docs
    assert "offline" in docs.lower() or "no call" in docs.lower()


# ---------------------------------------------------------------------------
# The signed file is the licence: it sets the tier, and issuing keeps the key out
# ---------------------------------------------------------------------------


def test_a_signed_file_grants_its_tier_with_no_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, trusted_key: tuple[bytes, str]
) -> None:
    """The point of the file: entitlement comes from it, not from a store key."""
    private, _ = trusted_key
    licence_path = tmp_path / "licence.signed.json"
    _write_licence(licence_path, private, tier="pro")
    monkeypatch.setenv("AITEST_LICENCE_FILE", str(licence_path))
    monkeypatch.setattr(activation, "read_licence", lambda path=None: None)
    monkeypatch.delenv("AITEST_LICENSE_KEY", raising=False)

    from src.licensing.license import effective_tier, license_status

    assert license_status().status == "valid"
    assert effective_tier() == "pro"


def test_the_issuing_script_refuses_a_key_inside_the_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The signing key must never live where a commit could pick it up."""
    sys_path = str(ROOT / "scripts" / "maintenance")
    import sys

    sys.path.insert(0, sys_path)
    try:
        import issue_licence
    finally:
        sys.path.remove(sys_path)

    private, _ = _keypair()
    inside = ROOT / ".licence-key-for-test"
    inside.write_bytes(base64.b64encode(private))
    try:
        monkeypatch.setenv("TANCAT_LICENCE_SIGNING_KEY_FILE", str(inside))
        monkeypatch.delenv("TANCAT_LICENCE_SIGNING_KEY", raising=False)
        with pytest.raises(issue_licence.SigningKeyLocationError):
            issue_licence.load_signing_key()
    finally:
        inside.unlink(missing_ok=True)


def test_the_issuing_script_writes_a_file_that_verifies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, trusted_key: tuple[bytes, str]
) -> None:
    private, public = trusted_key
    import sys

    sys.path.insert(0, str(ROOT / "scripts" / "maintenance"))
    try:
        import issue_licence
    finally:
        sys.path.remove(str(ROOT / "scripts" / "maintenance"))

    key_file = tmp_path / "signing.key"
    key_file.write_text(base64.b64encode(private).decode("ascii"), encoding="utf-8")
    out = tmp_path / "TC-1.json"
    monkeypatch.setenv("TANCAT_LICENCE_SIGNING_KEY_FILE", str(key_file))
    monkeypatch.delenv("TANCAT_LICENCE_SIGNING_KEY", raising=False)

    code = issue_licence.main(
        [
            "--id",
            "TC-2026-000999",
            "--buyer",
            "order 9001 / buyer@example.com",
            "--purchased",
            "2026-11-16",
            "--out",
            str(out),
        ]
    )
    assert code == 0
    result = verify_signed_file(out.read_text(encoding="utf-8"), public)
    assert result.valid, result.reason
    assert result.licence is not None
    assert result.licence.window_end == date(2027, 11, 16)
    assert issue_licence.public_key_b64(private) == public
