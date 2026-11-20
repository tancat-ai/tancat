"""The licence file we sign with ed25519 and verify offline (j-0309).

Why this exists: the Lemon Squeezy key is verified by calling Lemon Squeezy. When
the store shuts down, every installed copy that has not activated yet stops
working - a payment provider's business decision becomes our customers' outage.
A licence file we sign ourselves has no such dependency: the buyer receives it at
purchase, the product verifies the signature against a public key compiled into
the build, and nothing on that path can call anybody.

**Format** (JSON, one file, human-readable)::

    {
      "format": "tancat-licence/1",
      "payload": {
        "id": "TC-2026-000123",
        "product": "tancat",
        "buyer_ref": "order 4821 / buyer@example.com",
        "purchased_at": "2026-11-17",
        "window_end": "2027-11-17",
        "tier": "pro"
      },
      "signature": "<base64url ed25519 signature of the canonical payload>"
    }

The signature covers ``json.dumps(payload, sort_keys=True, separators=(",", ":"))``
encoded as UTF-8, so a changed byte anywhere in the payload - a date, the tier, the
id - fails verification. The signing key never ships: the build carries only the
public key (``license.VENDORED_PUBLIC_KEY_B64``), the same trust root the existing
token path uses.

**The update window comes from the file**, not from a store's ``created_at``: the
issuing script writes ``window_end`` when it signs, and the product reads it from
there. ``purchased_at`` is recorded for the buyer's records and for the window
check's sanity, not as the source of truth.

**Verification makes no call of any kind.** This module imports only the standard
library's codecs and ``cryptography``; no socket, no urllib, no http. A test
enforces both the imports and the behaviour with the socket module disabled.
"""

from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass
from datetime import date
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric import ed25519

from src.licensing.license import VENDORED_PUBLIC_KEY_B64
from src.licensing.tiers import tiers

__all__ = [
    "FORMAT",
    "PRODUCT",
    "REQUIRED_FIELDS",
    "SignedLicence",
    "SignedLicenceResult",
    "canonical_payload",
    "sign_payload",
    "signed_file_text",
    "verify_signed_file",
]

#: The format marker. A file with a different one is refused rather than guessed at.
FORMAT = "tancat-licence/1"

#: The product these licences are for. A licence for anything else is refused.
PRODUCT = "tancat"

#: Fields a payload must carry. Empty values are refused, not defaulted.
REQUIRED_FIELDS = ("id", "product", "buyer_ref", "purchased_at", "window_end", "tier")


@dataclass(frozen=True)
class SignedLicence:
    """The payload of a verified licence file."""

    id: str
    product: str
    buyer_ref: str
    purchased_at: date
    window_end: date
    tier: str

    def to_payload(self) -> dict[str, str]:
        return {
            "id": self.id,
            "product": self.product,
            "buyer_ref": self.buyer_ref,
            "purchased_at": self.purchased_at.isoformat(),
            "window_end": self.window_end.isoformat(),
            "tier": self.tier,
        }


@dataclass(frozen=True)
class SignedLicenceResult:
    """Outcome of verifying a licence file. Never raises for a bad file."""

    status: str  # "valid" | "invalid"
    reason: str = ""
    licence: SignedLicence | None = None

    @property
    def valid(self) -> bool:
        return self.status == "valid" and self.licence is not None

    def allows(self, build_date: date) -> bool:
        """True when a build released on *build_date* is inside the window."""
        return self.valid and self.licence is not None and build_date <= self.licence.window_end


def canonical_payload(payload: dict[str, Any]) -> bytes:
    """The exact bytes the signature covers.

    Sorted keys and no whitespace, so the same payload produces the same bytes on
    every machine and in every JSON implementation.
    """
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode((text + "=" * (-len(text) % 4)).encode("ascii"))


def sign_payload(payload: dict[str, Any], private_key: bytes) -> dict[str, Any]:
    """Sign *payload*; returns the file's JSON structure.

    The private key is the vendor's, held outside this repository. This function
    exists so the issuing script (and only it) has one code path, and so tests can
    sign with a throwaway key.
    """
    if len(private_key) != 32:
        raise ValueError("ed25519 private key must be 32 raw bytes")
    key = ed25519.Ed25519PrivateKey.from_private_bytes(private_key)
    signature = key.sign(canonical_payload(payload))
    return {"format": FORMAT, "payload": payload, "signature": _b64(signature)}


def signed_file_text(payload: dict[str, Any], private_key: bytes) -> str:
    """The licence file as text, ready to save or email."""
    return json.dumps(sign_payload(payload, private_key), indent=2, ensure_ascii=False) + "\n"


def _parse_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def verify_signed_file(
    text: str,
    public_key_b64: str | None = None,
) -> SignedLicenceResult:
    """Verify a licence file's signature and payload, offline.

    *public_key_b64* defaults to the vendored trust root; tests pass a throwaway
    key. Never raises: a bad file comes back as ``status="invalid"`` with the
    reason a buyer can act on.
    """
    if not text or not text.strip():
        return SignedLicenceResult("invalid", "The licence file is empty.")

    try:
        document = json.loads(text)
    except json.JSONDecodeError as exc:
        return SignedLicenceResult("invalid", f"The licence file is not valid JSON: {exc}.")

    if not isinstance(document, dict):
        return SignedLicenceResult("invalid", "The licence file must hold one JSON object.")

    if document.get("format") != FORMAT:
        return SignedLicenceResult(
            "invalid", f"Unknown licence format {document.get('format')!r}; this build reads {FORMAT!r}."
        )

    payload = document.get("payload")
    signature = document.get("signature")
    if not isinstance(payload, dict) or not isinstance(signature, str) or not signature.strip():
        return SignedLicenceResult("invalid", "The licence file has no payload or no signature.")

    missing = [field for field in REQUIRED_FIELDS if not str(payload.get(field, "")).strip()]
    if missing:
        return SignedLicenceResult("invalid", "The licence payload is missing: " + ", ".join(missing) + ".")

    # Signature first: nothing below trusts the payload until it verifies.
    try:
        public = ed25519.Ed25519PublicKey.from_public_bytes(base64.b64decode(public_key_b64 or VENDORED_PUBLIC_KEY_B64))
    except ValueError, TypeError, binascii.Error:
        return SignedLicenceResult("invalid", "This build's licence public key is not readable.")

    try:
        public.verify(_unb64(signature), canonical_payload(payload))
    except InvalidSignature, ValueError, binascii.Error:
        return SignedLicenceResult(
            "invalid",
            "The licence signature does not verify: the file was altered, or it was signed with a different key.",
        )

    if str(payload["product"]).strip().lower() != PRODUCT:
        return SignedLicenceResult("invalid", f"This licence is for {payload['product']!r}, not for {PRODUCT!r}.")

    purchased = _parse_date(payload["purchased_at"])
    window_end = _parse_date(payload["window_end"])
    if purchased is None or window_end is None:
        return SignedLicenceResult("invalid", "The licence's dates are not readable (expected YYYY-MM-DD).")
    if window_end < purchased:
        return SignedLicenceResult("invalid", "The licence's update window ends before it starts.")

    tier = str(payload["tier"]).strip().lower()
    if tier not in tiers():
        return SignedLicenceResult("invalid", f"The licence names an unknown tier {payload['tier']!r}.")

    return SignedLicenceResult(
        "valid",
        "The licence signature verifies.",
        SignedLicence(
            id=str(payload["id"]).strip(),
            product=PRODUCT,
            buyer_ref=str(payload["buyer_ref"]).strip(),
            purchased_at=purchased,
            window_end=window_end,
            tier=tier,
        ),
    )
