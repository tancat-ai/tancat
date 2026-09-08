#!/usr/bin/env python3
"""Vendor-side license key generator (Phase 6e, spec §5.4).

Held by Cat Tan Operations — this script is **not** part of the product
runtime. It creates the seller's ed25519 signing key and signs license tokens
for a deployment. The corresponding public key ships in the deployment (vendored
in ``src/licensing/license.py``). It is the trust root for all stock builds and
is deliberately not overridable by the customer (B-050); rotation ships with a
product release (docs/security/license-key-ops.md).

Usage::

    python scripts/license_gen.py --gen-keys --keys-dir ./secrets
        # writes secrets/license_signing_private_key.pem (PEM) and prints the
        # public key (base64 raw) to embed in a deployment.

    python scripts/license_gen.py --sign \\
        --private-key ./secrets/license_signing_private_key.pem \\
        --deployment-id "acme-prod" --tier pro \\
        --days 365 --out license.key
        # writes the signed token to license.key (or prints it with --json).

Only non-interactive, fully offline, stdlib + cryptography.
"""

from __future__ import annotations

import argparse
import base64
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from src.licensing.license import LicenseClaims, sign_license

VALID_TIERS = ("free", "self-serve", "pro", "airgap")


def _gen_keys(keys_dir: Path) -> str:
    """Generate a signing keypair; returns the base64 public key (raw)."""
    keys_dir.mkdir(parents=True, exist_ok=True)
    priv = ed25519.Ed25519PrivateKey.generate()
    pem = priv.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    key_path = keys_dir / "license_signing_private_key.pem"
    key_path.write_bytes(pem)
    pub = priv.public_key()
    pub_b64 = base64.b64encode(pub.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)).decode()
    print(f"Private key written: {key_path}")
    print(
        f"Public key (vendored trust root — embed in src/licensing/license.py;\n    rotation ships with a product release):\n    {pub_b64}"
    )
    return pub_b64


def _sign(
    private_key_path: Path,
    *,
    deployment_id: str,
    tier: str,
    claims: list[str],
    days: int,
    issuer: str,
) -> str:
    """Sign a license token; returns the token string."""
    priv = serialization.load_pem_private_key(private_key_path.read_bytes(), password=None)
    assert isinstance(priv, ed25519.Ed25519PrivateKey)  # typing narrow
    raw_priv = priv.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    now = datetime.now(UTC)
    claims_obj = LicenseClaims(
        deployment_id=deployment_id,
        tier=tier,
        claims=tuple(claims),
        issued_at=now.isoformat(),
        expires_at=(now + timedelta(days=days)).isoformat(),
        issuer=issuer,
    )
    return sign_license(claims_obj, raw_priv)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Vendor-side ed25519 license key generator (Phase 6e).")
    sub = parser.add_subparsers(dest="command", required=True)

    gen = sub.add_parser("gen-keys", help="Generate the signing keypair.")
    gen.add_argument("--keys-dir", default="./secrets", help="Directory to write the private key PEM.")

    sign = sub.add_parser("sign", help="Sign a license token for a deployment.")
    sign.add_argument("--private-key", required=True, help="Path to the signing private key PEM.")
    sign.add_argument("--deployment-id", required=True, help="Deployment identifier (e.g. 'acme-prod').")
    sign.add_argument("--tier", required=True, choices=VALID_TIERS, help="Tier to grant.")
    sign.add_argument("--claim", action="append", default=[], help="Extra feature claim (repeatable).")
    sign.add_argument("--days", type=int, default=365, help="Validity in days (default 365).")
    sign.add_argument("--issuer", default="cat-tan-operations")
    sign.add_argument("--out", help="Write the token to this file (default: stdout).")
    sign.add_argument("--json", action="store_true", help="Emit machine-readable JSON on stdout.")

    args = parser.parse_args(argv)

    if args.command == "gen-keys":
        _gen_keys(Path(args.keys_dir))
        return 0

    token = _sign(
        Path(args.private_key),
        deployment_id=args.deployment_id,
        tier=args.tier,
        claims=args.claim,
        days=args.days,
        issuer=args.issuer,
    )
    if args.out:
        Path(args.out).write_text(token + "\n", encoding="utf-8")
        print(f"License written to {args.out}")
        if args.json:
            print(json.dumps({"token": token, "deployment_id": args.deployment_id, "tier": args.tier}))
        return 0
    if args.json:
        print(json.dumps({"token": token, "deployment_id": args.deployment_id, "tier": args.tier}))
    else:
        print(token)
    return 0


if __name__ == "__main__":
    sys.exit(main())
