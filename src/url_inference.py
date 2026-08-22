"""URL transition resolution for journey-aware placeholder resolution.

AI-052 principle (no-guessing): a URL transition is derived ONLY from
evidence — the clicked element's own ``href``. Description keywords are never
turned into URLs ("description says inventory, so probably /inventory.html" is
banned): the observed trail (``ObservedTrail``) is the source of truth for
where a step lands. Keyword branches (login/checkout/continue/finish/
transfer/pay → discovered-URL lookup) were deleted in Session 4; the strict
trail path never consults this module at all.

Extracted from placeholder_orchestrator.py to separate URL inference
into its own independently testable module.
"""

from __future__ import annotations

import logging
from urllib.parse import urljoin

logger = logging.getLogger(__name__)


def infer_next_page_url(
    action: str,
    description: str,
    matched_element: dict[str, str],
    scraped_data: dict[str, list[dict[str, str]]],
    current_url: str | None,
) -> str | None:
    """Return the transition target of a resolved CLICK — its own ``href`` only.

    Evidence-only: the element's ``href`` is a fact about where the click goes.
    Anything else (keyword patterns, description text) would be a guess and is
    intentionally not implemented. Trail-driven callers don't call this at all;
    non-trail callers get ``None`` for elements without a real href, which the
    caller treats as "no observed transition".
    """
    if action != "CLICK":
        return None

    href = str(matched_element.get("href", "")).strip()
    if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
        return None

    if href.startswith(("http://", "https://")):
        return href
    if current_url:
        return urljoin(current_url, href)
    return href
