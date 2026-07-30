# AI-036 — Persistent POM Cache with Change Detection

**Created:** 2026-07-30
**Status:** Scoping
**Priority:** Medium (Tier 3 — Developer Experience)
**Depends on:** None (standalone, but complements AI-035 Self-Learning RAG & AI-029 Workspace Storage)
**Roadmap ref:** Phase 3 — Developer Experience & Efficiency

---

## 1. Problem Statement

Every pipeline run regenerates the same Page Object Model classes from scratch.
For a user testing the same site week after week:

- **Day 1:** Pipeline scrapes saucedemo → resolves `#user-name` → generates `HomePage.py`
- **Day 30:** Pipeline re-scrapes saucedemo → re-resolves `#user-name` → generates identical `HomePage.py`
- **Day 365:** Same thing, 365 times. The tool has "learned" the site 365 times but forgets every time.

This wastes time on repeat runs, but more importantly, it **silently masks DOM changes**.
If saucedemo changes `#user-name` to `#username-field`, the pipeline quietly generates
a new POM with the new selector. The user never knows a breaking change happened.

---

## 2. Product Goals — How This Fits

### 2.1 "Don't lock people in"

The cache is **plain `.py` files in a local directory** — standard Python, no proprietary
format, no database dependency. Users can:

- `git add cache/poms/` and version-control their POMs
- Edit cached selectors directly in their editor
- Delete the cache directory at any time — no data loss, pipeline falls back to full scrape
- Take the cached POMs and use them outside the tool (they're just page objects)

The export workflow is unchanged: `export_service.py` still produces clean, standalone
test packages. The cache is a local development accelerator, not a lock-in mechanism.

### 2.2 "Help manual testers become automation testers"

Manual testers don't know what a "selector" is. When the cache detects a DOM change,
it reports in plain language:

```
⚠ Changes detected on saucedemo:
  - The "username" field changed from #user-name to #username-field
  - The "checkout" button changed from #checkout to .checkout-btn
```

This teaches testers *what* changed without requiring them to debug Playwright
error messages. They see the diff, learn the pattern, and gain confidence in
reading DOM changes over time.

### 2.3 "Make automation testers more efficient"

On repeat runs for a stable site, the pipeline skips journey discovery and
placeholder resolution for cached pages. Estimated savings per run:

| Phase | Without cache | With cache (stable) |
|-------|--------------|---------------------|
| Journey discovery | ~12s | ~0s (skip when cache valid) |
| Placeholder resolution | ~15s | ~2s (verify cached selectors) |
| POM generation | ~1s | ~0s (load from file) |
| **Total** | **~28s** | **~2s** |

For 10 daily runs on a stable site: **~4.5 min/day saved** (260s → 20s).

### 2.4 "Decrease time between deploy and test completion"

When a site deploys a change, the cache detects which selectors are stale and
**only re-resolves those**. Instead of re-scraping the entire site, the pipeline
does a targeted re-resolution of the broken selectors. This means:

- Small change (e.g., one button renamed): **~5s** instead of ~28s
- Large change (e.g., entire page redesigned): full re-scrape triggered

### 2.5 "Increase test output reporting and usability"

The cache produces a **change report** as a pipeline artifact:

```
cache/reports/saucedemo/2026-07-30/changelog.json
```

This is machine-readable JSON that can be fed into dashboards, CI/CD pipelines,
or slack notifications. Example:

```json
{
  "site": "saucedemo",
  "run_timestamp": "2026-07-30T15:00:00Z",
  "status": "partial_change",
  "pages_scanned": 5,
  "selectors_total": 24,
  "selectors_stale": 3,
  "selectors_resolved": 3,
  "stale_selectors": [
    {
      "description": "username",
      "old_locator": "#user-name",
      "new_locator": "#username-field",
      "page_url": "https://www.saucedemo.com"
    }
  ]
}
```

---

## 3. Architecture

### 3.1 Data Flow

```
Pipeline run starts
    │
    ├─ Cache lookup: cache/poms/<site_hash>/manifest.json
    │   ├─ MISS → full pipeline (scrape → resolve → generate POM → write cache)
    │   └─ HIT → load cached POMs, verify selectors against live DOM
    │           │
    │           ├─ ALL VALID → skip scrape, use cached POMs  (fast path)
    │           │
    │           └─ SOME STALE → targeted re-resolution
    │                           ├─ stale selectors re-resolved
    │                           ├─ cache updated with new selectors
    │                           └─ changelog appended
    │
    └─ Pipeline continues with POMs (cached or fresh)
```

### 3.2 Module: `src/pom_cache.py`

New module, zero-dependency on existing pipeline code.

```python
class POMCache:
    """Persistent cache for generated Page Object Model classes.

    Directory structure:
        cache/poms/<site_hash>/
            manifest.json          # Site metadata + selector index
            homepage.py            # Generated POM class (same format as export)
            checkout_page.py
            ...
            changelog.jsonl        # Append-only change log (one JSON object per line)

    The cache is keyed by site domain hash (SHA-256 of hostname).
    This is NOT reversible — no URLs are stored in plain text.
    """

    def __init__(self, cache_dir: str = "cache/poms") -> None:
        ...

    def get(self, url: str) -> POMCacheEntry | None:
        """Return cached POMs for a site, or None if no cache exists."""

    def put(self, url: str, page_objects: list[GeneratedPageObject]) -> POMCacheEntry:
        """Store generated POMs for a site."""

    def verify(
        self, entry: POMCacheEntry, page: Page
    ) -> CacheVerificationResult:
        """Test each cached selector against the live DOM.

        Returns:
            - ALL_VALID: all selectors resolve
            - PARTIAL_STALE: some selectors fail (list of failed descriptions)
            - ALL_STALE: all selectors fail (site structure changed)
        """

    def update(
        self, entry: POMCacheEntry, re_resolved: dict[str, str]
    ) -> POMCacheEntry:
        """Replace stale selectors with newly resolved ones."""

    def get_changelog(self, url: str) -> list[dict]:
        """Return the append-only change log for a site."""
```

### 3.3 Integration Points

The cache integrates at two points in the existing pipeline:

**Point A — Before journey discovery (in `TestOrchestrator.run_pipeline()`)**
```python
# New: check cache before scraping
cache = POMCache()
cached = cache.get(starting_url)
if cached:
    verification = cache.verify(cached, browser_page)
    if verification == ALL_VALID:
        # Skip journey discovery entirely
        pom_classes = cache.load_poms(cached)
        # Fast path: use cached POMs directly
    elif verification == PARTIAL_STALE:
        # Run journey discovery only for affected pages
        stale_descriptions = [s.description for s in verification.stale]
        scraped_data = scrape_targeted_pages(stale_descriptions)
        re_resolved = resolve_stale_selectors(stale_descriptions, scraped_data)
        cache.update(cached, re_resolved)
```

**Point B — After POM generation (in `PlaceholderOrchestrator._build_page_object_artifacts()`)**
```python
# After generating POMs, write to cache
cache.put(starting_url, generated_page_objects)
```

### 3.4 Cache Entry Format

`manifest.json`:
```json
{
  "site_hash": "a1b2c3d4e5f6...",
  "domain": "saucedemo.com",
  "created": "2026-07-30T15:00:00Z",
  "last_verified": "2026-07-30T15:00:00Z",
  "pages": {
    "https://www.saucedemo.com": {
      "class_name": "HomePage",
      "file": "homepage.py",
      "selectors": {
        "username": "#user-name",
        "password": "#password",
        "login_button": "#login-button"
      }
    },
    "https://www.saucedemo.com/inventory.html": {
      "class_name": "InventoryPage",
      "file": "inventory_page.py",
      "selectors": {
        "add_to_cart_backpack": "#add-to-cart-sauce-labs-backpack",
        "shopping_cart_link": "[data-test='shopping-cart-link']"
      }
    }
  }
}
```

### 3.5 Verification Strategy

The `verify()` method tests each cached selector against the live DOM:

1. **Bulk test**: `page.locator(selector).count()` for each cached selector
2. **All count > 0**: `ALL_VALID` — fast path, no per-selector verification needed
3. **Some count == 0**: `PARTIAL_STALE` — those selectors need re-resolution
4. **All count == 0**: `ALL_STALE` — site structure changed, full re-scrape needed

**False positive risk**: A selector might match a *different* element than originally
intended (e.g., `#user-name` now matches a different element on the page). The
verification only checks *existence*, not *correctness*. This is acceptable because:

- If the element changed function but kept the same ID, the generated test would
  fail at runtime (pytest), and the self-healing loop (Phase 2) would catch it
- The cache is a *performance* optimization, not a correctness guarantee
- Full re-resolution is always a fallback option

---

## 4. Cache Invalidation

### 4.1 Manual invalidation

```bash
# Delete cache for a specific site
rm -rf cache/poms/saucedemo.com/

# Delete all caches
rm -rf cache/poms/

# Add to .gitignore
echo "cache/" >> .gitignore
```

### 4.2 Automatic invalidation

- `ALL_STALE` verification result → full cache entry deleted, full re-scrape
- `PARTIAL_STALE` → stale selectors updated, rest of cache preserved
- Cache entries older than 30 days (configurable) → flagged as `low_confidence`
  on next verification (prompts user to re-verify, but doesn't force re-scrape)

### 4.3 CLI controls

```bash
# Run with cache disabled
uv run python scripts/uat.py saucedemo --no-cache

# Clear cache for a specific site
uv run python scripts/uat.py saucedemo --clear-cache

# Show cache status
uv run python scripts/uat.py saucedemo --cache-status
```

---

## 5. Comparison with Related Features

| Feature | What it does | Relationship |
|---------|-------------|--------------|
| **AI-036 POM Cache** (this spec) | Persists POM classes across runs, detects DOM changes | Primary feature |
| **AI-035 Self-Learning RAG** | Writes back corrected locators to RAG store from self-healing loop | **Complementary** — AI-036 handles *pre-run* caching, AI-035 handles *post-run* learning. Together they form a complete feedback loop: cache → detect → heal → learn |
| **AI-029 Workspace Storage** | Abstracts all storage paths through `StorageBackend` | **Dependency** — POM cache should use `StorageBackend` (once AI-029 ships) instead of hardcoded `cache/poms/` |
| **Phase 2 Self-Healing** | Fixes broken locators at test runtime | **Downstream** — self-healing fixes what the cache detects. The cache could also *seed* the self-healing loop with pre-verified selectors |

---

## 6. What This Is NOT

- **Not a CI/CD lock-in**: The cache is a local developer tool. CI/CD pipelines should use `--no-cache` for clean runs, or opt-in with `--cache` for faster feedback.
- **Not a replacement for version control**: The cache is ephemeral. `git add cache/poms/` is optional. The export workflow is the source of truth for production tests.
- **Not a selector oracle**: The cache stores *known-good* selectors, but doesn't guarantee they'll work forever. Verification is best-effort, not authoritative.
- **Not a database**: Pure filesystem. No SQLite, no schema migrations, no server process.

---

## 7. Roadmap Placement

### Phase 3 — Developer Experience & Efficiency (current)

| Priority | Feature | Effort | Impact |
|----------|---------|--------|--------|
| P0 | LV Insurance Resolution Gap | 1-2 sessions | Correctness — 46% of tests currently fail |
| **P1** | **AI-036 POM Cache** | **1 session** | **Speed + change awareness — 20-30% faster repeat runs** |
| P2 | POM Selector Caching (cross-site) | 0.5 session | Nice-to-have — reuse selectors across similar sites |

### Why P1? (not P0)

The LV Insurance gap is a **correctness** issue — almost half the tests fail to resolve.
The POM cache is a **speed + awareness** improvement. Correctness comes first, but
the POM cache is valuable enough to ship immediately after.

### Estimated session count

- **Session 1**: `src/pom_cache.py` module, integration into `TestOrchestrator.run_pipeline()`, verification logic
- **Session 2 (optional)**: CLI controls (`--cache-status`, `--clear-cache`), changelog reporting, changelog.jsonl export

---

## 8. Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|------------|
| Stale cache produces wrong tests | Test generation succeeds but tests fail at runtime | Verification checks selector existence; self-healing catches runtime failures |
| Cache grows unbounded | Disk usage | Per-site cache is <100KB; 30-day TTL; manual `rm -rf` |
| Cache collision (same hash, different site) | Wrong POMs loaded | SHA-256 collision probability is negligible; add domain string to hash input |
| User expects cache to be source of truth | Tests break silently | Clear documentation: "cache is a performance optimization, not a source of truth" |
| Cache misleads during active development | Old selectors used for a changed page | `PARTIAL_STALE` triggers re-resolution automatically; `--no-cache` for CI |

---

## 9. Open Questions

1. **Should the cache be aware of the LLM provider?** If the user switches from
   Qwen to GPT-4, the resolution quality changes. Should cached selectors be invalidated?
   *Proposal: No — selectors are DOM facts, not LLM opinions. A `#user-name` is correct
   regardless of which LLM resolved it.*

2. **Should the cache store the full POM source or just the selector index?**
   *Proposal: Both. The manifest.json is the fast index for verification, and the .py
   files are the full POM for direct loading.*

3. **Should the changelog be surfaced in the Streamlit UI?**
   *Proposal: Yes, but as a follow-up. Phase 1 is CLI-only. Phase 2 adds a Streamlit
   panel showing "DOM changes detected since last run."*

4. **Should the cache work with the eval harness?**
   *Proposal: No — eval harness tests golden key accuracy, which requires fresh
   resolution every time. Eval runs should use `--no-cache` by default.*

---

## 10. Acceptance Criteria

1. ✅ Pipeline with cache MISS (first run) → generates POMs, writes to cache, runs full pipeline
2. ✅ Pipeline with cache HIT (all selectors valid) → skips journey discovery, uses cached POMs, completes in <10s
3. ✅ Pipeline with cache HIT (some selectors stale) → re-resolves only stale selectors, logs changes, updates cache
4. ✅ Pipeline with cache HIT (all selectors stale) → deletes cache entry, runs full pipeline
5. ✅ Change log (`changelog.jsonl`) is append-only and contains diff of old→new selectors
6. ✅ `--no-cache` flag disables cache lookup and write
7. ✅ `--cache-status` prints summary of cached sites and their verification states
8. ✅ `--clear-cache` deletes all cache entries for the target site
9. ✅ Cache directory is gitignored by default (`cache/` in `.gitignore`)
10. ✅ No regressions: `ruff` clean, `mypy` clean, all existing tests pass