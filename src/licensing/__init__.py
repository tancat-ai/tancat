"""Licensing - the tier table, and licence keys activated once and cached.

**One mechanism (owner, 2026-11-26):** a key the store issues with the order,
activated once through our relay, then read from the cache. The product calls the
relay at activation and at update, and at no other moment; there is no periodic check
and no second verification route.

``src/licensing/activation.py`` is the only file in the package that can reach the
network, and it does so through our relay, never the store directly.
"""

from src.licensing.activation import (
    Activation,
    ActivationResult,
    ValidationResult,
    activate,
    deactivate,
    validate,
)
from src.licensing.license import (
    LicenseResult,
    LicenseStatus,
    effective_tier,
    feature_enabled,
    license_status,
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
    "Activation",
    "ActivationResult",
    "LicenseResult",
    "LicenseStatus",
    "TierSpec",
    "ValidationResult",
    "activate",
    "deactivate",
    "effective_tier",
    "feature_enabled",
    "feature_required_tier",
    "is_paid_tier",
    "license_status",
    "limit_for",
    "tier_claims",
    "tier_label",
    "validate",
]
