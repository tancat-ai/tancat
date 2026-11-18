#!/usr/bin/env python3
"""Issue a signed licence file (j-0309).

The signing key is the vendor's and lives **outside this repository**: the product
ships only the public key. This script refuses to read a key from inside the repo,
so an accidental commit cannot happen by using it.

Usage::

    TANCAT_LICENCE_SIGNING_KEY_FILE=~/keys/tancat-licence.key \
        python scripts/maintenance/issue_licence.py \
        --id TC-2026-000123 --buyer "order 4821 / buyer@example.com" \
        --purchased 2026-11-17 --out ~/licences/TC-2026-000123.json

The key is 32 raw ed25519 bytes, base64-encoded, in the environment
(``TANCAT_LICENCE_SIGNING_KEY``) or in a file named by
``TANCAT_LICENCE_SIGNING_KEY_FILE``. The window ends ``--months`` after the
purchase date (12 by default) and is written into the signed payload, so the
product never derives it from a store's record.

It prints the public key it corresponds to; compare that with
``src/licensing/license.py``'s ``VENDORED_PUBLIC_KEY_B64`` before sending the file
to a buyer.
"""

from __future__ import annotations

import argparse
import base64
import os
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from cryptography.hazmat.primitives import serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import ed25519  # noqa: E402

from src.licensing.activation import add_months  # noqa: E402
from src.licensing.signed_file import PRODUCT, signed_file_text  # noqa: E402


class SigningKeyLocationError(RuntimeError):
    """The signing key was pointed at a path inside the repository."""


def _inside_repo(path: Path) -> bool:
    try:
        path.resolve().relative_to(REPO_ROOT.resolve())
    except ValueError:
        return False
    return True


def load_signing_key() -> bytes:
    """The raw private key, from the environment or a file outside the repo."""
    path_env = os.environ.get("TANCAT_LICENCE_SIGNING_KEY_FILE", "").strip()
    if path_env:
        key_path = Path(path_env).expanduser()
        if _inside_repo(key_path):
            raise SigningKeyLocationError(
                "The signing key is inside this repository. It must live outside it - move it first."
            )
        encoded = key_path.read_text(encoding="utf-8").strip()
    else:
        encoded = os.environ.get("TANCAT_LICENCE_SIGNING_KEY", "").strip()

    if not encoded:
        raise SigningKeyLocationError(
            "No signing key: set TANCAT_LICENCE_SIGNING_KEY (base64) or TANCAT_LICENCE_SIGNING_KEY_FILE."
        )

    raw = base64.b64decode(encoded)
    if len(raw) != 32:
        raise SigningKeyLocationError(f"The signing key must be 32 raw ed25519 bytes, not {len(raw)}.")
    return raw


def public_key_b64(private_key: bytes) -> str:
    """The base64 public key that verifies files signed with *private_key*."""
    key = ed25519.Ed25519PrivateKey.from_private_bytes(private_key)
    raw = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    return base64.b64encode(raw).decode("ascii")


def build_payload(licence_id: str, buyer: str, purchased: date, months: int, tier: str) -> dict[str, str]:
    """The payload the product reads. The window end is written here, not derived later."""
    return {
        "id": licence_id,
        "product": PRODUCT,
        "buyer_ref": buyer,
        "purchased_at": purchased.isoformat(),
        "window_end": add_months(purchased, months).isoformat(),
        "tier": tier,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Issue a signed TanCat licence file.")
    parser.add_argument("--id", required=True, help="Licence id, e.g. TC-2026-000123")
    parser.add_argument("--buyer", required=True, help="Buyer reference: order id, or the buyer's email")
    parser.add_argument("--purchased", default=date.today().isoformat(), help="Purchase date (YYYY-MM-DD)")
    parser.add_argument("--months", type=int, default=12, help="Update window in months (default 12)")
    parser.add_argument("--tier", default="pro", help="Tier the licence grants (default pro)")
    parser.add_argument("--out", required=True, help="Where to write the signed file")
    args = parser.parse_args(argv)

    try:
        purchased = date.fromisoformat(args.purchased)
    except ValueError:
        print(f"ERROR: --purchased must be YYYY-MM-DD, not {args.purchased!r}", file=sys.stderr)
        return 2

    try:
        key = load_signing_key()
    except SigningKeyLocationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    payload = build_payload(args.id, args.buyer, purchased, args.months, args.tier)
    out = Path(args.out).expanduser()
    if _inside_repo(out):
        print("ERROR: write the licence outside the repository - it is issued to a buyer.", file=sys.stderr)
        return 2
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(signed_file_text(payload, key), encoding="utf-8")

    print(f"wrote {out}")
    print(f"licence id: {payload['id']}")
    print(f"window: {payload['purchased_at']} -> {payload['window_end']}")
    print(f"public key (compare with VENDORED_PUBLIC_KEY_B64): {public_key_b64(key)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
