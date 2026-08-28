"""Self-learning RAG write path (AI-035 core + B-036 Phase 3 trigger).

When a generated test step **passes** against the live site, the resolved
``(action, description, locator, site)`` pair is verified. ``learn_from_evidence``
converts passed evidence steps into :class:`LearnedPattern` entries and writes
them to the RAG store — deduped on ``(action_type, description, site_hash)`` so
repeated facts bump ``hit_count`` instead of flooding the store.

``pattern_from_patch`` / ``learn_from_patch`` implement AI-035's *original*
trigger — the self-healing loop's corrected locator (``confidence=1.0``,
``source="self_healing"``), wired in ``SelfHealingRunner``.

Privacy (AI-035 §4): only the one-way ``sha256(domain)`` hash is stored — never
full URLs, story text, credentials, or screenshots. All learning is local.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from src.failure_classifier import FailureCategory, classify_failure
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


#: Opt-in production scope key (AI-061). When set, it participates in the RAG
#: site identity so two distinct projects served on the same host:port stay
#: isolated instead of bleeding learned/golden bonuses into each other. Unset
#: preserves the legacy host[:port] scoping (B-047 port-keeping).
RAG_SCOPE_ENV = "AITEST_RAG_SCOPE"


def effective_site_identity(base_url: str = "") -> str:
    """Resolve the RAG site identity for scoping, honoring an opt-in scope key.

    AI-061: when ``AITEST_RAG_SCOPE`` is set, the identity is ``scope:<value>``
    so two projects on the same ``host:port`` (e.g. two different localhost
    projects, or ``lv_insurance`` vs a solo ``ecommerce`` run both on
    ``localhost:8781``) stay isolated. When unset, falls back to the legacy
    ``host[:port]`` identity from :func:`domain_from_url` (B-047 port keeping),
    unchanged.

    The same identity string is used at BOTH learn time (this module) and
    resolve time (``PlaceholderOrchestrator``) so a pattern learned under a
    scope is only applied when the resolver runs under the same scope.
    """
    scope = os.environ.get(RAG_SCOPE_ENV, "").strip()
    if scope:
        return f"scope:{scope}"
    return domain_from_url(base_url)


def site_hash(site_identity: str) -> str:
    """One-way sha256 hash of a site identity (hex, first 16 chars).

    The identity is ``host`` or ``host:port`` (case-insensitive) — see
    ``domain_from_url``. Deterministic for the same identity, not reversible:
    the identity can never be recovered from the hash.

    B-047: a port-qualified identity (``localhost:8782``) hashes separately
    from ``localhost:8783``, so concurrent mock sites learn site-correct
    patterns instead of collapsing into one shared ``localhost`` bucket.
    """
    return hashlib.sha256(site_identity.strip().lower().encode("utf-8")).hexdigest()[:16]


def domain_from_url(url: str) -> str:
    """Extract the site identity — ``host[:port]``, lowercase — or ``""``.

    The port is kept (B-047) so localhost mock sites scope independently:
    ``http://localhost:8781/generated_tests/mock.html`` → ``localhost:8781``.
    Real sites with no explicit port are unchanged:
    ``https://www.saucedemo.com/inventory.html`` → ``www.saucedemo.com``.
    Userinfo (``user:pass@``) is stripped before returning.
    """
    if not url:
        return ""
    try:
        netloc = urlparse(url).netloc
        if "@" in netloc:
            netloc = netloc.rsplit("@", 1)[-1]
        return netloc.lower()
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
    identity = effective_site_identity(step_url)
    if not identity:
        return None

    return LearnedPattern(
        action_type=action,
        description=label,
        locator=locator,
        site_hash=site_hash(identity),
    )


#: Failure classes that make a failed step a CONFIRMED locator negative (AI-058).
#: Everything else — assertion failures, strict violations, navigation errors,
#: unknown/infra — must never poison the store: precision is everything.
_LOCATOR_FAILURE_CATEGORIES: set[FailureCategory] = {FailureCategory.LOCATOR_TIMEOUT}


def _step_to_negative_pattern(step: dict[str, Any]) -> LearnedPattern | None:
    """Map one FAILED evidence step to a ``learned_negative`` pattern, or None.

    AI-058 contrastive store: only **locator-class** failures (locator
    timeout / element-not-found, classified by :func:`classify_failure`) that
    carry a resolved selector and a site identity become negatives. Infra
    flakes (LLM timeout, navigation non-arrival, assertion failures, unknown)
    are excluded so they can never down-weight a healthy element. Mirrors
    ``_step_to_pattern`` for positives (same dedup key + one-way hashing).
    """
    action = _STEP_TYPE_TO_ACTION.get(str(step.get("type", "")).lower())
    if action is None:
        return None
    label = str(step.get("label", "") or "").strip()
    locator = str(step.get("locator", "") or "").strip()
    if not label or not locator:
        return None
    result = step.get("result") or {}
    if str(result.get("status", "")) in ("passed", "partial_pass"):
        return None
    error = str(result.get("error", "") or "")
    try:
        detail = classify_failure(error)
    except Exception:
        return None
    if detail.category not in _LOCATOR_FAILURE_CATEGORIES:
        return None
    step_url = str(step.get("url", "") or "")
    identity = effective_site_identity(step_url)
    if not identity:
        return None
    return LearnedPattern(
        action_type=action,
        description=label,
        locator=locator,
        site_hash=site_hash(identity),
        confidence=0.9,
        source="learned_negative",
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


def learn_negatives_from_evidence(
    steps: list[dict[str, Any]],
    *,
    store: RAGStore | None = None,
) -> dict[str, int]:
    """Record ``learned_negative`` patterns from failed locator-class steps.

    AI-058: the contrastive half of :func:`learn_from_evidence`. Converts each
    FAILED step that classifies as a locator-class failure (with a resolved
    selector) into a ``learned_negative`` entry so the resolver down-weights
    elements that failed before. Infra flakes never reach the store.

    Best-effort — a bad step can never break a run.
    """
    store = store or build_default_store()
    inserted = 0
    exists = 0
    for step in steps:
        pattern = _step_to_negative_pattern(step)
        if pattern is None:
            continue
        try:
            status, _hit = store.upsert_negative_pattern(pattern)
        except Exception as exc:
            logger.warning("Learned-negative record failed (non-fatal): %s", exc)
            continue
        if status == "inserted":
            inserted += 1
        else:
            exists += 1
    if inserted or exists:
        logger.info(
            "Learned %d negative pattern(s), %d already known (hit bumped)",
            inserted,
            exists,
        )
    return {"inserted": inserted, "exists": exists}


def learn_from_evidence_sidecars(
    evidence_dir: str | Path,
    *,
    store: RAGStore | None = None,
) -> dict[str, int]:
    """Sweep ``evidence/*.evidence.json`` sidecars and learn passed steps.

    B-047 deferred fix (parent-side sweep): the pytest subprocess hook
    (``generated_tests/conftest.py``) cannot open the Milvus-lite store while
    a resolve-and-learn parent process holds it — every subprocess
    ``learn_from_evidence`` call raises ``DataDirLockedError`` and is
    swallowed by the conftest try/except, so batch runs learn nothing. This
    does the same learning IN the parent, after a subprocess run wrote its
    sidecars: no lock contention, same dedup + site scoping.

    Mirrors the conftest gate exactly: only sidecars whose test fully passed
    (``test.status == "passed"``) are learned; ``learn_from_evidence`` then
    enforces the per-step ``result.status == "passed"`` filter.

    Never raises — learning is best-effort (corrupt sidecars are counted in
    ``errors`` and skipped, matching the "never break the run" contract).

    Returns:
        ``{"sidecars": K, "inserted": N, "exists": M, "errors": E}`` — K
        sidecar files scanned, N new patterns, M dedup'd repeats (hit
        bumped), E unreadable/skipped files.
    """
    sidecars = list(Path(evidence_dir).glob("*.evidence.json"))
    totals = {"sidecars": len(sidecars), "inserted": 0, "exists": 0, "errors": 0}
    for sidecar in sidecars:
        try:
            data = json.loads(sidecar.read_text(encoding="utf-8"))
            if str((data.get("test") or {}).get("status", "")) != "passed":
                continue
            result = learn_from_evidence(data.get("steps") or [], store=store)
            totals["inserted"] += result["inserted"]
            totals["exists"] += result["exists"]
        except Exception as exc:  # best-effort — never break the run
            totals["errors"] += 1
            logger.warning(
                "Evidence sidecar sweep failed for %s (non-fatal): %s",
                sidecar,
                exc,
            )
    return totals


# ---------------------------------------------------------------------------
# Self-healing write path (AI-035 original trigger)
# ---------------------------------------------------------------------------
# When the self-healing loop fixes a broken locator, the corrected
# ``(description, locator)`` pair is written back to the store with
# ``confidence=1.0`` (verified by the repair loop — it re-runs the test)
# and ``source="self_healing"``. Same dedup + site scoping as the evidence
# path (B-036 Phase 3).

# Playwright method → resolver action type.
_CODE_METHOD_TO_ACTION: dict[str, str] = {
    "click": "CLICK",
    "fill": "FILL",
    "press": "CLICK",
    "check": "CLICK",
    "uncheck": "CLICK",
    "select_option": "SELECT",
}

# Evidence labels arrive as ``{{CLICK:view cart link}}`` (placeholder form) or
# ``Click: view cart link`` (natural-language form). Both reduce to the
# placeholder description the resolver looks up by.
_PLACEHOLDER_LABEL_RE = re.compile(r"\{\{([A-Z_]+):(.*?)\}\}")
_ACTION_PREFIX_RE = re.compile(
    r"^(?:click|fill|type|select|assert|enter|press|navigate|goto)\s*:\s*(.+)$",
    re.IGNORECASE,
)
_SELECTOR_IN_LOCATOR_RE = re.compile(r"\.locator\(\s*(['\"])(.*?)\1")


def _action_from_code(line: str) -> str | None:
    """Map a Playwright code line to a resolver action type, or ``None``."""
    lowered = line.lower()
    if any(token in lowered for token in ("expect(", "to_be_", "to_have_", "assert_")):
        return "ASSERT"
    for method, action in _CODE_METHOD_TO_ACTION.items():
        if f".{method}(" in lowered:
            return action
    return None


def _selector_from_code(line: str) -> str | None:
    """Extract the selector string from a code line, or ``None``.

    Handles both the raw Playwright API (``page.locator("...")``) and the
    generated evidence-tracker API (``evidence_tracker.click("...", ...)``,
    ``.fill("...")``, ``.assert_visible("...")``, ``.select_option("...")``)
    — the first quoted string argument of the tracked method.
    """
    match = _SELECTOR_IN_LOCATOR_RE.search(line)
    if match:
        return match.group(2).strip()
    # evidence_tracker.click('a[href="/cart.html"]', label='Cart link')
    tracker = re.search(
        r"evidence_tracker\.(?:click|fill|select_option|assert_visible|assert_hidden|assert_text|assert_text_contains|assert_disabled|assert_enabled|assert_checked|assert_count|assert_value)\(\s*(['\"])(.*?)\1",
        line,
    )
    if tracker:
        return tracker.group(2).strip()
    return None


def _clean_label(label: str) -> str:
    """Reduce an evidence step label to the placeholder description."""
    label = label.strip()
    placeholder = _PLACEHOLDER_LABEL_RE.fullmatch(label)
    if placeholder:
        return placeholder.group(2).strip()
    prefix = _ACTION_PREFIX_RE.match(label)
    if prefix:
        return prefix.group(1).strip()
    return label


def _description_from_evidence(
    old_selector: str | None,
    evidence_steps: list[dict[str, Any]] | None,
) -> str | None:
    """Find the step whose locator matches the OLD (failed) selector.

    The step's label is the anchor: generated tests label steps with the
    placeholder description (``{{CLICK:view cart link}}``) or a natural
    description (``Click: view cart link``).
    """
    if not old_selector or not evidence_steps:
        return None
    for step in evidence_steps:
        locator = str(step.get("locator", "") or "").strip()
        if not locator:
            continue
        if locator == old_selector or old_selector in locator or locator in old_selector:
            label = str(step.get("label", "") or "").strip()
            if label:
                return _clean_label(label)
    return None


def pattern_from_patch(
    old_text: str,
    new_text: str,
    *,
    base_url: str,
    description: str | None = None,
    evidence_steps: list[dict[str, Any]] | None = None,
) -> LearnedPattern | None:
    """Build a learned pattern from a self-healing locator-replacement patch.

    Args:
        old_text: The original (failed) code line, e.g.
            ``page.locator("#wrong-btn").click()``.
        new_text: The corrected line, e.g. ``page.locator("#add-to-cart").click()``.
        base_url: Any URL of the target site — only its host[:port] is hashed.
        description: Explicit description (wins over evidence extraction).
        evidence_steps: Evidence sidecar steps, used to recover the
            placeholder description anchored to the failed selector.

    Returns:
        A ``LearnedPattern`` (``confidence=1.0``, ``source="self_healing"``)
        or ``None`` when the patch is not a locator replacement, no corrected
        selector is recoverable, no site identity is derivable, or no
        description anchor is available.
    """
    action = _action_from_code(new_text)
    if action is None:
        return None
    locator = _selector_from_code(new_text)
    if not locator:
        return None
    identity = effective_site_identity(base_url)
    if not identity:
        return None
    if not description:
        description = _description_from_evidence(_selector_from_code(old_text), evidence_steps)
    if not description:
        return None
    return LearnedPattern(
        action_type=action,
        description=description,
        locator=locator,
        site_hash=site_hash(identity),
        confidence=1.0,
        source="self_healing",
    )


def learn_from_patch(
    *,
    old_text: str,
    new_text: str,
    base_url: str,
    description: str | None = None,
    evidence_steps: list[dict[str, Any]] | None = None,
    store: RAGStore | None = None,
) -> dict[str, int]:
    """Write one self-healing-corrected locator to the RAG store.

    Never raises — self-healing must not break if learning fails (the same
    guard as the evidence teardown hook). Returns
    ``{"inserted": 0|1, "exists": 0|1}`` (``exists`` = dedup'd repeat, hit
    bumped).
    """
    try:
        pattern = pattern_from_patch(
            old_text,
            new_text,
            base_url=base_url,
            description=description,
            evidence_steps=evidence_steps,
        )
        if pattern is None:
            return {"inserted": 0, "exists": 0}
        store = store or build_default_store()
        status, _hit = store.upsert_pattern(pattern)
        # AI-058: the OLD selector is a CONFIRMED negative. The self-heal
        # replacement pair (old selector failed → new selector verified) is the
        # highest-precision contrastive signal the store can receive.
        old_selector = _selector_from_code(old_text)
        if old_selector:
            negative = LearnedPattern(
                action_type=pattern.action_type,
                description=pattern.description,
                locator=old_selector,
                site_hash=pattern.site_hash,
                confidence=1.0,
                source="learned_negative",
            )
            try:
                store.upsert_negative_pattern(negative)
            except Exception as exc:
                logger.warning("Self-healing negative write failed (non-fatal): %s", exc)
        logger.info(
            "Learned self-healing pattern: %s '%s' -> %s (%s)",
            pattern.action_type,
            pattern.description,
            pattern.locator,
            status,
        )
        return {"inserted": 1, "exists": 0} if status == "inserted" else {"inserted": 0, "exists": 1}
    except Exception as exc:
        logger.warning("Self-healing pattern learn failed (non-fatal): %s", exc)
        return {"inserted": 0, "exists": 0}
