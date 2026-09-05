"""Licensing — tier config, claims, and ed25519 offline license validation.

Phase 6e. Open-core honesty (spec §5.4 / §7.6): the repo is Apache-2.0; a
license key is an *entitlement marker*, not DRM. A modified fork can strip any
check. The key's real value is ToS/support entitlement, honest tier enforcement
for the 99% who run stock builds, and the air-gap premium bundle. Everything
here is purely local — **zero network calls** (the egress audit gate enforces
that this stays true).
"""

from src.licensing.license import (
    GRACE_DAYS,
    LicenseResult,
    LicenseStatus,
    LicenseValidationError,
    SigningKeyError,
    effective_tier,
    feature_enabled,
    license_status,
    load_license,
    sign_license,
    vendor_public_key,
    verify_license,
)
from src.licensing.tiers import (
    DEFAULT_TIERS,
    FREE_TIER,
    TierSpec,
    feature_required_tier,
    is_paid_tier,
    limit_for,
    tier_claims,
    tier_label,
)

__all__ = [
    "DEFAULT_TIERS",
    "FREE_TIER",
    "GRACE_DAYS",
    "LicenseResult",
    "LicenseStatus",
    "LicenseValidationError",
    "SigningKeyError",
    "TierSpec",
    "effective_tier",
    "feature_enabled",
    "feature_required_tier",
    "is_paid_tier",
    "license_status",
    "limit_for",
    "load_license",
    "sign_license",
    "tier_claims",
    "tier_label",
    "vendor_public_key",
    "verify_license",
]
