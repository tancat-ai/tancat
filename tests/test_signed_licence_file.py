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

from src.licensing import entitlement, signed_file
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

    build = date.fromisoformat(payload["purchased_at"]) + timedelta(days=10)
    decision = entitlement.startup_check(build_date=build)
    assert decision.allowed
    assert decision.window_end == date.fromisoformat(payload["window_end"])


# ---------------------------------------------------------------------------
# Precedence, Free, and the merchant name
# ---------------------------------------------------------------------------


def test_no_file_and_no_key_is_free(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AITEST_LICENCE_FILE", str(tmp_path / "absent.json"))

    state = entitlement.resolve()
    assert state.source == "none"
    assert state.tier == "free"
    assert entitlement.startup_check().allowed, "a Free install must never be refused"


def test_the_merchant_of_record_is_unnamed_and_sits_in_one_constant() -> None:
    """No provider is signed yet, so the copy names the role and nobody else."""
    assert MERCHANT_OF_RECORD == "our merchant of record", "a provider is named in the constant"

    from src.licensing import merchant

    assert "merchant of record" in merchant.MERCHANT_OF_RECORD
    # No module may hardcode a store or provider name in copy.
    provider_names = ("lemon squeezy", "lemonsqueezy", "paddle", "polar.sh", "stripe", "gumroad", "creem")
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
                low = node.value.lower()
                if any(name in low for name in provider_names):
                    spelled.append(path.relative_to(ROOT).as_posix())
                    break

    assert spelled == [], f"a provider is named in product copy: {spelled}"


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


# ---------------------------------------------------------------------------
# The signed file is the licence
# ---------------------------------------------------------------------------


def test_a_signed_file_grants_its_tier_with_no_token(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, trusted_key: tuple[bytes, str]
) -> None:
    """The point of the file: entitlement comes from it, and nothing else."""
    private, _ = trusted_key
    licence_path = tmp_path / "licence.signed.json"
    _write_licence(licence_path, private, tier="pro")
    monkeypatch.setenv("AITEST_LICENCE_FILE", str(licence_path))

    from src.licensing.license import effective_tier, license_status

    assert license_status().status == "valid"
    assert effective_tier() == "pro"


def test_nothing_in_the_licensing_package_can_make_a_call() -> None:
    """j-0309: the licensing path never touches the network, at all.

    Parsing modules may import ``urllib.parse`` (a pure string module); anything
    that can open a connection must not appear anywhere in ``src/licensing/``.
    """
    network = {"socket", "http", "requests", "httpx", "aiohttp", "ssl", "ftplib", "smtplib"}

    offenders: dict[str, list[str]] = {}
    for path in sorted((ROOT / "src" / "licensing").rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        found: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".")[0] in network or alias.name in {"urllib.request", "urllib.error"}:
                        found.add(alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                module = node.module
                if module.split(".")[0] in network or module in {"urllib.request", "urllib.error"}:
                    found.add(module)
        if found:
            offenders[path.relative_to(ROOT).as_posix()] = sorted(found)

    assert offenders == {}, f"the licensing package can call out: {offenders}"


def test_the_activation_path_is_gone() -> None:
    """No store activation module, no store ids, no activate URL anywhere in src/."""
    assert not (ROOT / "src" / "licensing" / "activation.py").exists()
    text = "\n".join(
        path.read_text(encoding="utf-8", errors="replace") for path in (ROOT / "src").rglob("*.py")
    ).lower()
    assert "api.lemonsqueezy.com" not in text
    assert "licenses/activate" not in text


# ---------------------------------------------------------------------------
# The trust root is a real key, not a placeholder
# ---------------------------------------------------------------------------

#: Keys that must never ship as the trust root: the 2026-09-28 pair the 2026-11-18
#: ceremony superseded.
RETIRED_OR_PLACEHOLDER_KEYS = {
    "2XisSdAOFhJ3ciNZDNudV9GyYK6CeDF2zcMw7wXVbP8=",  # ceremony 2026-09-28, retired
}


def test_the_vendored_trust_root_is_a_real_key() -> None:
    """A placeholder (all zeros, a repeated byte, a retired key) must fail here."""
    from src.licensing.license import VENDORED_PUBLIC_KEY_B64, vendor_public_key

    raw = base64.b64decode(VENDORED_PUBLIC_KEY_B64)
    assert len(raw) == 32, f"the trust root must be 32 raw bytes, not {len(raw)}"
    assert raw != b"\x00" * 32, "the trust root is all zeros - a placeholder"
    assert len(set(raw)) > 1, "the trust root is a single repeated byte - a placeholder"
    assert VENDORED_PUBLIC_KEY_B64 not in RETIRED_OR_PLACEHOLDER_KEYS, "a retired key is shipping as the trust root"
    assert vendor_public_key() == VENDORED_PUBLIC_KEY_B64


def test_a_file_signed_with_the_owner_key_verifies_against_the_vendored_root() -> None:
    """The acceptance test, if the owner's key is present on this machine.

    Read-only: the key is loaded in memory and never written anywhere. Skipped on a
    machine that does not hold it - which is the normal case for a contributor.
    """
    key_path = Path("C:/Users/l_a_c/.clowder/secrets/tancat-licence-signing.key")
    if not key_path.exists():
        pytest.skip("the owner's signing key is not on this machine")

    private = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
    assert isinstance(private, ed25519.Ed25519PrivateKey)
    raw = private.private_bytes(
        serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption()
    )

    result = verify_signed_file(signed_file_text(_payload(), raw))  # no public_key: the vendored root
    assert result.valid, result.reason
    assert result.licence is not None and result.licence.tier == "pro"


# ---------------------------------------------------------------------------
# The issuing script
# ---------------------------------------------------------------------------


def _issue_module() -> Any:
    import sys

    sys.path.insert(0, str(ROOT / "scripts" / "maintenance"))
    try:
        import issue_licence
    finally:
        sys.path.remove(str(ROOT / "scripts" / "maintenance"))
    return issue_licence


def test_the_issuing_script_refuses_a_key_inside_the_repository(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The signing key must never live where a commit could pick it up."""
    issue_licence = _issue_module()

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
    issue_licence = _issue_module()

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


def test_the_issuing_script_accepts_the_pem_key_form(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The owner's key is a PKCS8 PEM, so the script must read that form too."""
    private, public = _keypair()
    key = ed25519.Ed25519PrivateKey.from_private_bytes(private)
    pem = key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())
    key_file = tmp_path / "signing.pem"
    key_file.write_bytes(pem)
    out = tmp_path / "TC-PEM.json"

    issue_licence = _issue_module()
    monkeypatch.setenv("TANCAT_LICENCE_SIGNING_KEY_FILE", str(key_file))
    monkeypatch.delenv("TANCAT_LICENCE_SIGNING_KEY", raising=False)
    assert issue_licence.main(["--id", "TC-2026-000777", "--buyer", "x", "--out", str(out)]) == 0

    result = verify_signed_file(out.read_text(encoding="utf-8"), public)
    assert result.valid, result.reason
