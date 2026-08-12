# `src/flow_memory.py`

## High-Level Purpose

**Cross-site flow memory** (AI-042). Locator memory can't transfer across
sites (only ~3% of learned locator pairs overlap across sites — B-047 locks
locators to their site), but navigation *shape* does: login → browse → cart →
checkout is near-identical across e-commerce sites. This module learns those
flows from passing evidence and serves them back to URL resolution when
site-specific resolution fails.

A flow is a transition tuple: `(from_route, action, description, to_route)`.
Routes are normalized URL path keywords ("login", "dashboard", "cart") —
**never raw URLs** (AI-035 §4 privacy: full URLs/credentials/story text are
never stored). Aggregation is cross-site: each pattern tracks the set of
distinct sites (one-way sha256 hashes) that verified it, so a transition seen
on ≥2 sites is a learned cross-site flow; single-site flows stay site
evidence.

```
evidence sidecars → FlowMemoryStore.learn_from_sidecars(evidence_dir)
    ├─ flow_transitions(steps)    # passing steps → (transition, site) pairs
    ├─ normalize_route(url)       # URL → route keyword ("cart.html" → "cart")
    └─ upsert_flow()              # dedup on (from, action, desc, to); hit + site set
    → evidence/flow_memory.json   # atomic tmp + os.replace

consumption: PlaceholderOrchestrator GOTO/URL-assertion chain
    UrlResolver → resolve_url → flow_resolved_url(store, ...) → heuristic → seed
```

**Consumers:** `PlaceholderOrchestrator` (step 2.5 in the GOTO/URL chain and
the page-state ASSERT fallback), `generated_tests/conftest.py` teardown hook,
`scripts/synthesize_stories.py` parent-side sweep.

## Module Metadata

- **Lines:** ~440
- **Imports:** `json`, `logging`, `os`, `re`, `dataclasses`, `pathlib`,
  `typing`, `urllib.parse`, `src.rag_learn` (`domain_from_url`, `site_hash`),
  `src.storage` (`get_storage`)
- **Spec:** roadmap item AI-042 (Tier 4 §16) — cross-site flow memory
- **Shipped:** 2026-08-12

## Public API

### `normalize_route(url: str) -> str`
URL → normalized route keyword: scheme/host/query dropped, extensions
stripped (`cart.html` → `cart`), index/default/home collapse to `"home"`,
purely-numeric segments (ids) dropped, lowercase `/`-joined
(`checkout-step-one`), then page-type aliases canonicalized (`view_cart`/
`basket` → `cart`, `inventory` → `products`, `signin`/`auth` → `login` —
exact whole-route match only, so `checkout-step-one`/`-two` stay distinct
flow states). The aliases are the learned analog of `url_resolver`'s
hardcoded groups: without them, cross-site flows can't transfer (saucedemo's
`cart.html` never reaches automationexercise's `view_cart` — AI-042 session-2
finding).

### `clean_description(label: str) -> str`
Strips action prefixes (`"Click: view cart link"`) and placeholder wrappers
(`"{{CLICK:view cart link}}"`) to the plain description.

### `FlowTransition` (dataclass)
`from_route`, `action`, `description`, `to_route` + `key` (case-insensitive
dedup key).

### `flow_transitions(steps) -> list[tuple[FlowTransition, str]]`
Extracts `(transition, site_identity)` pairs from evidence steps. `navigate`
steps set the current-page context (their destination becomes the `from_route`
of following actions). Only fully-passing steps emit; same-page actions
(`from == to`) are dropped; page context advances after every step that
records a URL.

### `FlowPattern` (dataclass)
Aggregated transition: `hit_count`, `site_hashes: set[str]`, `site_count`
property.

### `FlowMemoryStore`
JSON-file store (`evidence/flow_memory.json`, atomic writes, corrupt-tolerant
load):
- `upsert_flow(transition, site)` — dedup bumps hit_count + site set
- `learn_from_evidence(steps)` — passed-only learning with per-transition
  site identity
- `learn_from_sidecars(evidence_dir)` — sweep (gates on
  `test.status == "passed"`; never raises)
- `query(from_route, action=None, description=None)` — ranked by
  (site_count, hit_count)
- `route_hints(from_route, *, min_sites=1)` — `[(to_route, hits, sites)]`
- `stats()` / `clear()`

### `flow_resolved_url(store, *, description, from_url, scraped_urls, min_sites=1) -> str | None`
The consumption hook: which scraped destination route do flows say is
reachable from the current page for this description? Description tokens
match against both learned action labels and the destination-route
vocabulary (so "dashboard page is loaded" matches a flow whose `to_route`
is "dashboard").

## Design Notes

- **Site-specific evidence always wins:** the orchestrator runs flow memory
  only after UrlResolver and `resolve_url` fail — flows fill gaps, never
  override site evidence.
- **Guardrails:** passed-only learning, same-page actions dropped, non-empty
  non-URL descriptions, `min_sites` filter for cross-site strictness
  (2 = only flows verified on ≥2 sites).
- **Privacy:** routes are generic page vocabulary — no full URLs, credentials,
  or story text; site identity is a one-way sha256.
- **Hermetic tests:** `TestOrchestrator` constructs the store only when
  `FLOW_MEMORY_ENABLED != "0"` (tests set it to `"0"` in
  `tests/conftest.py`, mirroring `RAG_ENABLED=0`).
