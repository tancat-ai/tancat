"""Cross-site flow memory — AI-042.

Locator memory can't transfer across sites (verified: only ~3% of learned
locator pairs overlap across sites — B-047 locks locators to their site), but
navigation *shape* does: login → browse → cart → checkout is near-identical
across e-commerce sites. This module learns those flows from passing evidence
and serves them back to URL resolution when site-specific resolution fails.

A flow is a transition tuple::

    (from_route, action, description, to_route)

Routes are normalized URL path keywords ("login", "dashboard", "cart") —
**never raw URLs** (AI-035 §4 privacy: full URLs/credentials/story text are
never stored; routes are generic page vocabulary). Aggregation is
cross-site: each pattern tracks the set of distinct sites (one-way sha256
hashes) that verified it, so a transition seen on ≥2 sites is a learned
cross-site flow; single-site flows remain site evidence.

Learning gates (mirror the RAG evidence path):
- only fully-passing steps (``result.status == "passed"``) are learned,
- same-page actions (``from_route == to_route``) are dropped — they don't
  advance the flow,
- descriptions are cleaned of action prefixes and must not be URL-shaped.

Consumption: :func:`flow_resolved_url` answers "which scraped destination
route do flows say is reachable from this page for this description?". The
orchestrator calls it **only after** site-specific resolution (UrlResolver,
``resolve_url``) fails — flow memory fills gaps, it never overrides site
evidence.
"""

from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from src.rag_learn import domain_from_url, site_hash
from src.storage import get_storage

logger = logging.getLogger(__name__)

#: Evidence step type → resolver action type (mirrors rag_learn, plus
#: navigate is intentionally absent — navigate steps set flow context).
_STEP_TYPE_TO_ACTION: dict[str, str] = {
    "click": "CLICK",
    "fill": "FILL",
    "assertion": "ASSERT",
    "select": "SELECT",
    "type": "FILL",
    "press": "CLICK",
}

# Evidence labels arrive as ``Click: view cart link`` (tracker ``_clean_label``)
# or ``{{CLICK:view cart link}}`` (older placeholders). Both reduce to the
# plain description.
_ACTION_PREFIX_RE = re.compile(
    r"^(?:click|fill|type|select|assert|enter|press|navigate|goto)\s*:\s*(.+)$", re.IGNORECASE
)
_PLACEHOLDER_LABEL_RE = re.compile(r"\{\{([A-Z_]+):(.*?)\}\}")

#: File extensions stripped from route segments (``cart.html`` → ``cart``).
_ROUTE_EXTENSIONS: tuple[str, ...] = (".html", ".htm", ".php", ".aspx", ".asp", ".jsp", ".do", ".action")
#: Segments that mean "the site root".
_HOME_SEGMENTS: frozenset[str] = frozenset({"", "index", "default", "home", "homepage", "main", "start"})

#: Page-type canonicalization — the learned analog of ``url_resolver``'s
#: hardcoded alias groups (AI-042 finding: cross-site flows only transfer when
#: sites share route vocabulary; saucedemo's ``inventory.html``/``cart.html``
#: must reach automationexercise's ``/products``/``view_cart``). Applied to the
#: **whole route after cleaning, exact match only** — partial matches are
#: deliberately NOT canonicalized (``checkout-step-one`` vs ``checkout-step-two``
#: are distinct flow states that must never collapse).
_ROUTE_ALIASES: dict[str, str] = {
    "cart": "cart",
    "basket": "cart",
    "view_cart": "cart",
    "shopping_cart": "cart",
    "shopping-cart": "cart",
    "products": "products",
    "inventory": "products",
    "login": "login",
    "signin": "login",
    "sign-in": "login",
    "auth": "login",
}

_LEARNED_STATUS = "passed"


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def normalize_route(url: str) -> str:
    """Map a URL to its normalized route keyword — never the raw URL.

    Rules:
    - scheme/host/query/fragment are dropped (route is site-agnostic),
    - file extensions are stripped (``cart.html`` → ``cart``),
    - index/default/home segments collapse to ``"home"``,
    - purely-numeric segments (ids: ``/category_products/1``) are dropped,
    - the result is a lowercase ``/``-joined keyword ("checkout-step-one"),
    - whole-route page-type aliases are canonicalized ("view_cart" → "cart",
      "inventory" → "products") so cross-site flows transfer across the shared
      e-commerce vocabulary — exact match only, step pages stay distinct.
    """
    if not url:
        return "home"
    try:
        parsed = urlparse(str(url))
        path = (parsed.path or "/").lower()
    except ValueError:
        return "home"
    if path in ("", "/"):
        return "home"

    segments = [s for s in path.split("/") if s]
    cleaned: list[str] = []
    for segment in segments:
        for ext in _ROUTE_EXTENSIONS:
            if segment.endswith(ext):
                segment = segment[: -len(ext)]
                break
        if not segment or segment in _HOME_SEGMENTS or segment.isdigit():
            continue
        cleaned.append(segment)
    if not cleaned:
        return "home"
    route = "/".join(cleaned)
    return _ROUTE_ALIASES.get(route, route)


def _tokens(text: str) -> set[str]:
    """Lowercase word tokens (split on non-alphanumerics: ``checkout-step-one``
    → ``{checkout, step, one}``)."""
    return {t for t in re.split(r"[^a-z0-9]+", (text or "").lower()) if t}


def clean_description(label: str) -> str:
    """Strip action prefixes / placeholder wrappers from an evidence label."""
    label = (label or "").strip()
    if not label:
        return ""
    match = _PLACEHOLDER_LABEL_RE.search(label)
    if match:
        return match.group(2).strip()
    match = _ACTION_PREFIX_RE.match(label)
    if match:
        return match.group(1).strip()
    return label


@dataclass(frozen=True)
class FlowTransition:
    """One navigation transition extracted from a passing evidence step."""

    from_route: str
    action: str
    description: str
    to_route: str

    @property
    def key(self) -> tuple[str, str, str, str]:
        return (self.from_route, self.action, self.description.lower(), self.to_route)


@dataclass
class FlowPattern:
    """An aggregated (possibly cross-site) flow transition."""

    from_route: str
    action: str
    description: str
    to_route: str
    hit_count: int = 0
    site_hashes: set[str] = field(default_factory=set)

    @property
    def site_count(self) -> int:
        return len(self.site_hashes)

    @property
    def key(self) -> tuple[str, str, str, str]:
        return (self.from_route, self.action, self.description.lower(), self.to_route)


def flow_transitions(steps: Iterable[dict[str, Any]]) -> list[tuple[FlowTransition, str]]:
    """Extract ``(transition, site_identity)`` pairs from evidence steps.

    ``navigate`` steps set the current-page context (their destination route
    becomes the ``from_route`` of the following actions). Only fully-passing
    non-navigate steps emit transitions; a step whose page did not change
    (``from == to``) is dropped. The page context advances after every step
    that records a URL (failed steps too — the recorded URL is factual even
    when the action failed; the *emitted* transition still requires pass).

    The site identity is ``host[:port]`` of the step's own recorded URL — the
    site that verified this transition.
    """
    transitions: list[tuple[FlowTransition, str]] = []
    current_route = "home"
    for step in steps:
        if not isinstance(step, dict):
            continue
        step_type = str(step.get("type", "")).lower()
        result = step.get("result") or {}
        status = str(result.get("status", ""))

        if "navigate" in step_type:
            target = str(step.get("value", "") or step.get("url", "") or "")
            current_route = normalize_route(target)
            continue

        step_url = str(step.get("url", "") or "")
        to_route = normalize_route(step_url)

        if status == _LEARNED_STATUS:
            action = _STEP_TYPE_TO_ACTION.get(step_type)
            description = clean_description(str(step.get("label", "") or ""))
            if (
                action is not None
                and description
                and not description.lower().startswith(("http", "www."))
                and to_route != current_route
                and to_route != "home"
            ):
                transitions.append(
                    (
                        FlowTransition(
                            from_route=current_route,
                            action=action,
                            description=description,
                            to_route=to_route,
                        ),
                        domain_from_url(step_url),
                    )
                )

        if step_url:
            current_route = to_route
    return transitions


# ---------------------------------------------------------------------------
# Store
# ---------------------------------------------------------------------------


class FlowMemoryStore:
    """JSON-file store of learned flows (AI-042).

    One file per workspace: ``evidence/flow_memory.json``. Writes are atomic
    (tmp file + ``os.replace``). Load/save never raise — a missing or corrupt
    file starts empty and learning is best-effort (mirrors the RAG store's
    "never break the run" contract).
    """

    DEFAULT_FILE = "flow_memory.json"
    _SCHEMA_VERSION = 1

    def __init__(self, path: Path | None = None) -> None:
        if path is None:
            path = get_storage().evidence_dir() / self.DEFAULT_FILE
        self._path = Path(path)
        self._patterns: dict[tuple[str, str, str, str], FlowPattern] = {}
        self._last_learned_at: str | None = None
        self.load()

    # -- persistence -------------------------------------------------------

    @property
    def path(self) -> Path:
        return self._path

    def load(self) -> None:
        """Load patterns from disk; a missing/corrupt file starts empty."""
        self._patterns = {}
        self._last_learned_at = None
        if not self._path.exists():
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            for entry in data.get("patterns", []) or []:
                pattern = FlowPattern(
                    from_route=str(entry["from_route"]),
                    action=str(entry["action"]),
                    description=str(entry["description"]),
                    to_route=str(entry["to_route"]),
                    hit_count=int(entry.get("hit_count", 1)),
                    site_hashes={str(s) for s in entry.get("site_hashes", [])},
                )
                self._patterns[pattern.key] = pattern
            self._last_learned_at = data.get("last_learned_at")
        except Exception as exc:
            logger.warning("Flow memory store unreadable at %s — starting empty: %s", self._path, exc)

    def save(self) -> None:
        """Atomically persist patterns (tmp + os.replace)."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": self._SCHEMA_VERSION,
            "last_learned_at": self._last_learned_at,
            "patterns": [
                {
                    "from_route": p.from_route,
                    "action": p.action,
                    "description": p.description,
                    "to_route": p.to_route,
                    "hit_count": p.hit_count,
                    "site_hashes": sorted(p.site_hashes),
                }
                for p in self._patterns.values()
            ],
        }
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.replace(tmp, self._path)

    def clear(self) -> None:
        self._patterns = {}
        self._last_learned_at = None
        if self._path.exists():
            self._path.unlink()

    # -- learning ----------------------------------------------------------

    def upsert_flow(self, transition: FlowTransition, site: str) -> str:
        """Add one transition for one site; dedup bumps hit_count + site set.

        Returns ``"inserted"`` or ``"exists"`` (repeat — hit bumped).
        """
        key = transition.key
        pattern = self._patterns.get(key)
        if pattern is None:
            self._patterns[key] = FlowPattern(
                from_route=transition.from_route,
                action=transition.action,
                description=transition.description,
                to_route=transition.to_route,
                hit_count=1,
                site_hashes={site},
            )
            return "inserted"
        pattern.hit_count += 1
        pattern.site_hashes.add(site)
        return "exists"

    def learn_from_evidence(self, steps: Iterable[dict[str, Any]]) -> dict[str, int]:
        """Learn flows from evidence steps (passed-only, dedup'd, site-scoped).

        Each transition carries the site identity (``host[:port]``) of the
        step that verified it; the store hashes it one-way and tracks site
        diversity per pattern.
        """
        inserted = 0
        exists = 0
        for transition, site_identity in flow_transitions(steps):
            if not site_identity:
                continue
            if self.upsert_flow(transition, site_hash(site_identity)) == "inserted":
                inserted += 1
            else:
                exists += 1
        if inserted or exists:
            self._last_learned_at = _now_iso()
            self.save()
        return {"inserted": inserted, "exists": exists}

    def learn_from_sidecars(self, evidence_dir: str | Path) -> dict[str, int]:
        """Sweep ``evidence/*.evidence.json`` sidecars and learn flows.

        Only sidecars whose test fully passed (``test.status == "passed"``)
        are learned — the same gate as the RAG parent-side sweep. Never
        raises; corrupt sidecars count toward ``errors``.
        """
        sidecars = list(Path(evidence_dir).glob("*.evidence.json"))
        totals = {"sidecars": len(sidecars), "inserted": 0, "exists": 0, "errors": 0}
        for sidecar in sidecars:
            try:
                data = json.loads(sidecar.read_text(encoding="utf-8"))
                if str((data.get("test") or {}).get("status", "")) != _LEARNED_STATUS:
                    continue
                result = self.learn_from_evidence(data.get("steps") or [])
                totals["inserted"] += result["inserted"]
                totals["exists"] += result["exists"]
            except Exception as exc:
                totals["errors"] += 1
                logger.warning("Flow sidecar sweep failed for %s (non-fatal): %s", sidecar, exc)
        return totals

    # -- querying ----------------------------------------------------------

    def query(
        self,
        from_route: str,
        action: str | None = None,
        description: str | None = None,
    ) -> list[FlowPattern]:
        """Flows leaving ``from_route``, optionally filtered, ranked by
        (site_count desc, hit_count desc, to_route)."""
        desc_lower = (description or "").lower().strip()
        results = [
            p
            for p in self._patterns.values()
            if p.from_route == from_route
            and (action is None or p.action == action)
            and (not desc_lower or p.description.lower() == desc_lower)
        ]
        results.sort(key=lambda p: (-p.site_count, -p.hit_count, p.to_route))
        return results

    def route_hints(
        self,
        from_route: str,
        *,
        action: str | None = None,
        description: str | None = None,
        min_sites: int = 1,
    ) -> list[tuple[str, int, int]]:
        """Destination routes reachable from this page — ``[(to_route,
        hit_count, site_count)]``, ranked. ``min_sites`` enforces the
        cross-site guardrail (2 = only flows verified on ≥2 sites)."""
        hints: dict[str, tuple[int, int]] = {}
        for pattern in self.query(from_route, action=action, description=description):
            if pattern.site_count < min_sites:
                continue
            hits, sites = hints.get(pattern.to_route, (0, 0))
            hints[pattern.to_route] = (hits + pattern.hit_count, sites + pattern.site_count)
        return sorted(
            ((route, hits, sites) for route, (hits, sites) in hints.items()),
            key=lambda item: (-item[2], -item[1], item[0]),
        )

    def stats(self) -> dict[str, Any]:
        """Summary for UI/diagnostics."""
        sites: set[str] = set()
        for pattern in self._patterns.values():
            sites.update(pattern.site_hashes)
        return {
            "patterns": len(self._patterns),
            "sites": len(sites),
            "cross_site": sum(1 for p in self._patterns.values() if p.site_count >= 2),
            "last_learned_at": self._last_learned_at,
            "path": str(self._path),
        }


def _now_iso() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Consumption
# ---------------------------------------------------------------------------


def flow_resolved_url(
    store: FlowMemoryStore,
    *,
    description: str,
    from_url: str,
    scraped_urls: Iterable[str],
    min_sites: int = 1,
) -> str | None:
    """Resolve a GOTO / URL-assertion description via cross-site flow memory.

    Site-specific resolution must run first — this fills the gap with learned
    navigation shape: flows say which destination routes are reachable from
    the current page, and the description is matched (token overlap) against
    both the learned action labels and the destination-route vocabulary.

    Returns the first scraped URL whose route is a flow-supported destination,
    or ``None`` when no flow supports it.
    """
    from_route = normalize_route(from_url)
    desc_tokens = _tokens(clean_description(description))

    route_to_url: dict[str, str] = {}
    for url in scraped_urls:
        route = normalize_route(url)
        if route and route != "home":
            route_to_url.setdefault(route, url)

    best: FlowPattern | None = None
    for pattern in store.query(from_route=from_route):
        if pattern.site_count < min_sites:
            continue
        if pattern.to_route not in route_to_url:
            continue
        if desc_tokens:
            pat_tokens = _tokens(pattern.description) | _tokens(pattern.to_route)
            if not (desc_tokens & pat_tokens):
                continue
        if best is None or (pattern.site_count, pattern.hit_count) > (best.site_count, best.hit_count):
            best = pattern

    if best is None:
        return None
    return route_to_url[best.to_route]
