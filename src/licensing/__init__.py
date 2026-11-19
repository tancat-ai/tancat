"""Licensing - the tier table, and one signed licence file verified offline.

**One mechanism (j-0309):** a signed licence file we issue, or nothing (Free). There
is no token format and no activation step. Everything here is purely local -
**zero network calls**, enforced by the AST test over this package and by the egress
audit gate.
"""

from src.licensing.license import (
    VENDORED_PUBLIC_KEY_B64,
    LicenseResult,
    LicenseStatus,
    effective_tier,
    feature_enabled,
    license_status,
    vendor_public_key,
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
    "VENDORED_PUBLIC_KEY_B64",
    "LicenseResult",
    "LicenseStatus",
    "TierSpec",
    "effective_tier",
    "feature_enabled",
    "feature_required_tier",
    "is_paid_tier",
    "license_status",
    "limit_for",
    "tier_claims",
    "tier_label",
    "vendor_public_key",
]
