"""End-to-end licence loop with the real signing CLI (launch step 3, t-0422).

Proves the fulfilment loop the product actually ships:

    scripts/license_gen.py gen-keys
    scripts/license_gen.py sign --tier pro
        -> signed token file
        -> the product's loader (all three activation routes)
        -> the deployment reports the pro tier.

The vendored trust root is the owner's signing pair, which is deliberately not
in this repository. The test therefore generates a throwaway keypair with the
real signing tool and monkeypatches the vendored public key to that throwaway
pair for the duration of the test only. It never touches, needs, or writes the
owner's key.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

from src.licensing import license as _license_module
from src.licensing.license import (
    LicenseStatus,
    effective_tier,
    feature_enabled,
    license_status,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
LICENSE_GEN_PATH = REPO_ROOT / "scripts" / "license_gen.py"


def _load_license_gen() -> Any:
    """Load scripts/license_gen.py as a module without importing the package."""
    spec = importlib.util.spec_from_file_location("license_gen_under_test", LICENSE_GEN_PATH)
    assert spec is not None and spec.loader is not None, "could not load scripts/license_gen.py"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def signed_pro_token(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    """Sign a 30-day pro token with a throwaway key, and trust that key.

    Returns the token. Clears the two env routes and redirects the default key
    file to a temp dir, so each test starts from a genuinely unlicensed state.
    """
    gen = _load_license_gen()
    keys_dir = tmp_path / "signing"
    public_key_b64 = gen._gen_keys(keys_dir)

    token_file = tmp_path / "issued.key"
    rc = gen.main(
        [
            "sign",
            "--private-key",
            str(keys_dir / "license_signing_private_key.pem"),
            "--deployment-id",
            "loop-test",
            "--tier",
            "pro",
            "--days",
            "30",
            "--out",
            str(token_file),
        ]
    )
    assert rc == 0
    token = token_file.read_text(encoding="utf-8").strip()
    assert token and token.count(".") == 1

    monkeypatch.setattr(_license_module, "VENDORED_PUBLIC_KEY_B64", public_key_b64)
    monkeypatch.setattr("src.secure_config._config_dir", lambda: tmp_path / "config")
    monkeypatch.delenv("AITEST_LICENSE_KEY", raising=False)
    monkeypatch.delenv("AITEST_LICENSE_FILE", raising=False)
    return token


def _assert_pro(result: Any) -> None:
    assert result.status == LicenseStatus.VALID
    assert result.tier == "pro"
    assert "License valid" in result.headline
    assert "pro tier" in result.headline
    assert "loop-test" in result.headline


def test_route_a_environment_variable_reports_pro(signed_pro_token: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AITEST_LICENSE_KEY", signed_pro_token)
    result = license_status()
    _assert_pro(result)
    assert effective_tier() == "pro"


def test_route_b_license_file_variable_reports_pro(
    signed_pro_token: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    key_file = tmp_path / "from-env-file.key"
    key_file.write_text(signed_pro_token + "\n", encoding="utf-8")
    monkeypatch.setenv("AITEST_LICENSE_FILE", str(key_file))
    _assert_pro(license_status())


def test_route_c_default_key_file_reports_pro(
    signed_pro_token: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "license.key").write_text(signed_pro_token + "\n", encoding="utf-8")
    _assert_pro(license_status())


def test_pro_tier_unlocks_paid_features(signed_pro_token: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AITEST_LICENSE_KEY", signed_pro_token)
    assert feature_enabled("pom") is True
    assert feature_enabled("ci_runs") is True
    assert feature_enabled("jira_export") is True


def test_without_a_key_the_deployment_stays_free(signed_pro_token: str) -> None:
    """Guard against a test that passes because the machine happens to be licensed."""
    result = license_status()
    assert result.status == LicenseStatus.UNLICENSED
    assert result.tier == "free"
    assert feature_enabled("pom") is False
