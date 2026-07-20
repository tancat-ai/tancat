# Feature Spec — URL-Based Assertions for Page-State Verification

**Created:** 2026-07-20
**Status:** Draft
**Priority:** Medium — skipped tests are better than false greens, but skipped tests degrade user trust
**Depends on:** `src/placeholder_resolver.py`, `src/intent_matcher.py`, `src/placeholder_orchestrator.py`, `src/skeleton_parser.py`
**Backlog ref:** B-021

---

## 1. Problem Statement

Page-state assertions like "home page visible" or "dress products page visible" cannot
resolve to any DOM element because they describe **pages**, not **elements**. The
`PageStateAssertStrategy` in `src/intent_matcher.py` correctly rejects all elements
for these placeholders, but the end result is a `pytest.skip()` — the test is skipped
with the message:

```
Skipping: unresolved placeholders for: 'home page visible'; 'dress products page'
```

### Why This Matters

1. **User intent is valid.** When a user writes "home page visible" they mean "I want to
   verify the test is on the home page." This is a legitimate assertion.

2. **DOM elements are poor proxies.** A page heading like "AutomationExercise" may appear
   on multiple pages (`/` and `/products` both show it). Asserting on a shared DOM element
   gives false confidence.

3. **URL is the ground truth.** `expect(page).to_have_url("https://automationexercise.com/")`
   is the most precise way to verify which page the test is on. A heading assertion cannot
   distinguish `/` from `/products` if both show the same branding.

### Concrete Failure (automationexercise.com, 2026-07-20)

| User Story Assertion | Resolver Behavior | Result |
|---|---|---|
| `home page visible` | `PageStateAssertStrategy` rejects all elements | `pytest.skip()` — test skipped |
| `dress products page visible` | `PageStateAssertStrategy` rejects all elements | `pytest.skip()` — test skipped |

The user navigates to `https://automationexercise.com/` (which works), but the ASSERT
placeholder for "home page" can't resolve.

---

## 2. Root Cause

The `ASSERT` action resolves against **scraped DOM elements** only. The resolver knows
nothing about URLs or page identity. When a description describes a page rather than an
element, no candidate survives the `IntentMatcher` filter.

The relevant code path:

```
PlaceholderResolver.rank_candidates()
  → IntentMatcher.matches(action="ASSERT", description="home page visible")
    → PageStateAssertStrategy.match() → returns False for ALL elements
      → element excluded from ranking
  → result: empty candidate list → unresolved placeholder → pytest.skip()
```

---

## 3. Solution Design

### Approach: URL-Aware ASSERT Resolution

Extend the `ASSERT` resolution pipeline to recognise page-state assertions and map them
to URL assertions instead of DOM element assertions.

### When to trigger URL resolution

The `PageStateAssertStrategy` already detects page-state descriptions. Instead of
returning `False` (reject all elements), it should **signal the orchestrator** that this
placeholder needs URL-based resolution rather than element-based resolution.

### How URL resolution works

The existing `PlaceholderResolver.resolve_url()` method already maps description keywords
to scraped URLs. The same logic can map "home page" → the base URL, "dress products page"
→ a URL containing `/products` or `/category_products/...`.

### Generated code

Instead of emitting a `page.locator(...)` assertion, emit `expect(page).to_have_url(...)`:

```python
# Current (broken): placeholder skips
pytest.skip("Skipping: unresolved placeholders for: 'home page visible'")

# Desired: URL assertion
expect(page).to_have_url("https://automationexercise.com/")
```

---

## 4. Implementation Plan

### Phase 1: Signal propagation

1. **`PageStateAssertStrategy`** — return a signal value (e.g., `"url"`) instead of `False`
   when the description matches page-state terms. Change interface from `bool | None` to
   `bool | str | None` where `str` means URL resolution requested.

2. **`IntentMatcher`** — propagate the URL signal through the match chain so the
   orchestrator knows to use `resolve_url()` instead of `rank_candidates()`.

### Phase 2: URL resolution in the orchestrator

3. **`PlaceholderOrchestrator._replace_placeholders_sequentially()`** — when a placeholder
   signals URL resolution, call `PlaceholderResolver.resolve_url(description, scraped_data, known_urls)`
   instead of `rank_candidates()`.

4. **Code generation** — when the resolved target is a URL, emit:
   ```python
   expect(page).to_have_url("<resolved_url>")
   ```
   instead of the standard `expect(page.locator(...)).to_be_visible()`.

### Phase 3: Extended URL matching

5. **`PlaceholderResolver.resolve_url()`** — extend the keyword-to-URL mapping:
   | Description Keywords | URL Match Signal |
   |---|---|
   | `"home page"`, `"landing page"`, `"start page"` | Base URL (path is `/` or empty) |
   | `"products page"`, `"<category> products page"` | URL containing `/products` or `/category_products` |
   | `"cart page"`, `"shopping cart page"` | URL containing `/view_cart` |
   | `"checkout page"` | URL containing `/checkout` |
   | `"returned to <page>"` | Map `<page>` via keywords above |

### Phase 4: Skeleton parser update

6. **`SkeletonParser`** — no new placeholder action needed. `ASSERT` stays as the action,
   but the description signals URL intent. The parser already handles `ASSERT:description`.

---

## 5. Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| New placeholder action? | No — reuse `ASSERT` | Adding `ASSERT_URL` fragments the placeholder vocabulary and confuses the LLM. The description already carries sufficient signal |
| URL matching strategy | Keyword-based + path analysis | Matches existing `resolve_url()` pattern. No LLM calls needed |
| What if URL resolution fails? | Fall back to `pytest.skip()` | Same as current behaviour — better than a false match |
| Multiple page references per test | Each `ASSERT` resolved independently | One test may navigate from home → products → cart. Each page-state ASSERT maps to the appropriate URL |

---

## 6. Files Changed

| File | Change |
|---|---|
| `src/intent_matcher.py` | `PageStateAssertStrategy.match()` returns URL signal instead of `False` |
| `src/intent_matcher.py` | `IntentMatcher.match()` forward URL signal |
| `src/placeholder_resolver.py` | `resolve_url()` — extend keyword mapping |
| `src/placeholder_orchestrator.py` | Branch on URL signal → call `resolve_url()` → emit `to_have_url()` code |
| `tests/test_intent_matcher.py` | Test URL signal return for page-state descriptions |
| `tests/test_placeholder_resolver.py` | Test URL resolution for page-state keywords |
| `tests/test_placeholder_orchestrator.py` | Test end-to-end: page-state ASSERT → `to_have_url()` in generated code |

---

## 7. Acceptance Criteria

1. `{{ASSERT:home page visible}}` resolves to `expect(page).to_have_url("<base_url>")`
2. `{{ASSERT:dress products page visible}}` resolves to `expect(page).to_have_url("<url containing /products>")`
3. `{{ASSERT:cart page visible}}` resolves to `expect(page).to_have_url("<url containing /view_cart>")`
4. Existing element-level ASSERT resolution is not affected (no regression)
5. When URL resolution fails (unknown page reference), test is skipped with clear message
6. All existing tests pass (ruff clean, mypy clean, pytest zero regressions)

---

## 8. Relationship to Existing Features

- **B-014 ASSERT scoring** — scoring changes only affect element-level ASSERT. URL
  assertions bypass scoring entirely (no element to score).
- **B-014 Step-context resolution** — URL assertions may also benefit from step context
  (e.g., "returned to home page" after a click). The step-context spec's context-threading
  mechanism can feed the `known_urls` list to `resolve_url()`.
- **AI-010 POM mode** — in POM mode, page objects already know their URLs. URL assertions
  could use `self.url` or `self.path` from the page object instead of raw URLs.

---

*Last updated: 2026-07-20*
