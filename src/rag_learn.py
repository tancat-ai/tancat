"""Self-learning RAG write path (AI-035 core + B-036 Phase 3 trigger).

When a generated test step **passes** against the live site, the resolved
``(action, description, locator, site)`` pair is verified. ``learn_from_evidence``
converts passed evidence steps into :class:`LearnedPattern` entries and writes
them to the RAG store — deduped on ``(action_type, description, site_hash)`` so
repeated facts bump ``hit_count`` instead of flooding the store.

Privacy (AI-035 §4): only the one-way ``sha256(domain)`` hash is stored — never
full URLs, story text, credentials, or screenshots. All learning is local.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any
from urllib.parse import urlparse

from src.rag_bundled import build_default_store
from src.rag_store import LearnedPattern, RAGStore

logger = logging.getLogger(__name__)

# Evidence step type → resolver action type. "navigate"/"goto" steps carry no
# locator and are skipped by design.
_STEP_TYPE_TO_ACTION = {
    "fill": "FILL",
    "click": "CLICK",
    "assertion": "ASSERT",
    "select": "SELECT",
}

# Only fully-passing steps are verified. "partial_pass" means a fallback was
# used — the locator is less certain, so it is not learned.
_LEARNED_STATUS = "passed"


def site_hash(domain: str) -> str:
    """One-way sha256 hash of a site domain (hex, first 16 chars).

    Deterministic for the same domain (case-insensitive), not reversible —
    the domain can never be recovered from the hash.
    """
    return hashlib.sha256(domain.strip().lower().encode("utf-8")).hexdigest()[:16]


def domain_from_url(url: str) -> str:
    """Extract the host (no port, lowercase) from a URL, or ``""``.

    ``https://www.saucedemo.com:8080/inventory.html`` → ``www.saucedemo.com``
    """
    if not url:
        return ""
    try:
        return urlparse(url).netloc.split(":")[0].lower()
    except ValueError:
        return ""


def _step_to_pattern(step: dict[str, Any]) -> LearnedPattern | None:
    """Map one evidence step to a LearnedPattern, or ``None`` when unlearnable.

    Skipped when the step: has no action mapping (navigate/unknown), has no
    label or locator (URL/state assertions), or has no page URL (no site to
    scope the pattern to).
    """
    action = _STEP_TYPE_TO_ACTION.get(str(step.get("type", "")).lower())
    if action is None:
        return None

    label = str(step.get("label", "") or "").strip()
    locator = str(step.get("locator", "") or "").strip()
    if not label or not locator:
        return None

    step_url = str(step.get("url", "") or "")
    domain = domain_from_url(step_url)
    if not domain:
        return None

    return LearnedPattern(
        action_type=action,
        description=label,
        locator=locator,
        site_hash=site_hash(domain),
    )


def learn_from_evidence(
    steps: list[dict[str, Any]],
    *,
    store: RAGStore | None = None,
) -> dict[str, int]:
    """Learn verified patterns from passed evidence steps (batched write).

    Args:
        steps: Evidence step dicts (``type``, ``label``, ``locator``, ``url``,
            ``result.status``) — exactly what ``EvidenceTracker`` records.
        store: Injectable store (tests); defaults to the production store.

    Returns:
        ``{"inserted": N, "exists": M}`` — new patterns vs. dedup'd repeats.
        A repeat still counts as a hit (``hit_count`` bumped in the store).

    Batched: one call per test file teardown, not per step. Failures are the
    caller's concern — the conftest hook wraps this so learning never breaks
    a test run.
    """
    store = store or build_default_store()
    inserted = 0
    exists = 0
    for step in steps:
        result = step.get("result") or {}
        if str(result.get("status", "")) != _LEARNED_STATUS:
            continue
        pattern = _step_to_pattern(step)
        if pattern is None:
            continue
        status, _hit = store.upsert_pattern(pattern)
        if status == "inserted":
            inserted += 1
        else:
            exists += 1

    if inserted or exists:
        logger.info(
            "Learned %d new pattern(s), %d already known (hit bumped)",
            inserted,
            exists,
        )
    return {"inserted": inserted, "exists": exists}
