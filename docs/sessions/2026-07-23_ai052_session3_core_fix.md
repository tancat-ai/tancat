# AI-052 — Observed Transitions — Session 3

> **Session 3 of 6** — the core fix: the resolver consumes the trail.
> Plan: `docs/plans/AI-052_observed_transitions_plan.md` (read §0 + this session).
> Date: 2026-07-23 (verify runs 2026-08-22)

---

## What was built

`_replace_placeholders_sequentially` now derives each step's page from the
**observed trail** instead of `infer_next_page_url`. Three states per step:

| State | Meaning | Action |
|---|---|---|
| verified | observed page with scraped DOM | scope resolution to it |
| evidenced/unknown | no scraped DOM for the step's page | stay on last verified anchor; skip honestly if unresolvable |
| pending evidence | we EMIT a real-href click to an unscraped page | next step cannot use the stale page → honest skip |

### Mechanisms (all in `src/placeholder_orchestrator.py`)

1. **Strict scoping** — trail journeys never fall back to searching ALL pages.
   Empty verified scope ⇒ honest `pytest.skip`, never a cross-page locator.
   Also plugged: strictly-skipped tokens are excluded from the Pass-3 batch
   fallback (which searches all pages) so skips stay skips; deferred ASSERTs
   grouped under an unscraped URL become unresolved instead of cross-page matches.
2. **Trail-driven transitions** — `current_url` advances only on OBSERVED,
   scraped landings (`canon(obs.to_url)`); `infer_next_page_url` is out of the
   strict path entirely (href-only evidence remains). GOTO resolves to its
   observed landing URL directly when the trail recorded one.
3. **`pending_evidence`** — when WE emit a click whose element carries a real
   href to an unscraped page, the runtime browser will be there; subsequent
   steps scope against that (unverified) target and skip honestly.
4. **Divergence-aware replay** — the trail's `selector_used` was PROVEN
   (successfully clicked during discovery). When the resolver picks a different
   element: keep ours if ours navigates via a real href (evidence handles the
   move); otherwise replay the proven selector so the generated test re-enacts
   the observed journey. If the resolver finds nothing scoped, fall back to the
   proven selector.
5. **Proven-static navigation intent** — the trail proves whether a click
   navigated. A navigation-intent description ("Cart") whose proven click
   stayed put (and our pick has no href either) is emitted as a verified
   navigation instead of a dead click.
6. **Divergence latch** — once our emitted path departs from the observed one,
   the trail describes a different journey than the test; obs scoping/replay
   stops and only our own verified anchor is trusted.

### En-route fixes found by live verification

- Trailing-slash mismatch: trail URLs come from `page.url` (`…com/`) while
  scrape keys are normalised (`…com`). All membership checks go through a
  per-journey `canon()` normalising map.
- Batch-fallback leak: honestly-skipped tokens previously fell through to the
  all-pages batch pass, resurrecting the exact cross-page locator being fixed.
- Step-0 handling: an action runs on its FROM-page, never its landing page;
  `to_url` is only used when `from_url` is empty (step 0 by construction).

## Why the plan grew (production-driven discoveries)

Six verify runs surfaced three deeper root causes beyond the original bug:

1. **Scraper/resolver disagreement** — discovery clicked
   `#add-to-cart-sauce-labs-backpack` for "Sauce Labs Backpack" while the
   resolver picked the title link; the generated test navigated somewhere the
   trail never saw. Mechanisms 3–5 exist because of this.
2. **No href evidence on saucedemo** — title links carry `href=""`
   (JS-driven navigation), so href-based detection cannot see the transition.
3. **Scraped DOM ≠ fresh DOM** — discovery clicks mutate the page
   (saucedemo swaps "Add to cart" → "Remove"), so proven selectors may be
   absent from the scrape inventory; replay therefore trusts `error is None`,
   not presence in `scraped_data`.

## Gate results

| Gate | Result |
|---|---|
| `scripts/smoke.py --json` | ✅ 39/39 |
| `ruff check .` / `ruff format --check .` | ✅ clean |
| `mypy src/ cli/` | ✅ clean |
| `pytest tests/ -n 3` | ✅ 2726 passed, 1 skipped |
| eval static | ✅ 97.9% (baseline held) |
| `verify_production saucedemo --keep` | ✅ **0 different-page errors**; 4 passed / 1 failed (AI-051) / 1 honest skip |
| `verify_production automationexercise --keep` | ✅ **0 different-page errors**; 6 passed / 1 failed (login-gated checkout modal, not a locator bug) |

## DoD assessment

✅ Zero `_LocatorNotFoundError … different page` across both sites (the headline).
✅ No new false passes — every pass is genuine; failures are real site/skeleton issues.
⚠️ Remaining failure on saucedemo is **AI-051** (post-login `to_have_url`
asserts the base URL) — explicitly out of scope for AI-052.
📝 automationexercise checkout is login-gated; skeletons without login steps
cannot pass it — candidate backlog note alongside AI-051's family.

## Files changed

| File | Change |
|---|---|
| `src/placeholder_orchestrator.py` | S3 core: strict scope, canon map, trail-driven transitions, divergence-aware replay, proven-static nav, divergence latch, matched_out param |
| `tests/test_resolver_observed_scope.py` | **new** — 19 tests (fixtures A/B/C/evidenced + replay, latch, trailing slash, alignment) |

(Joins the same uncommitted changeset as S1+S2; committed together.)

## Next

**Session 4** — delete the keyword-URL guessing in `src/url_inference.py`;
GOTO hygiene. The strict-scope path already ignores inference, so S4 is a
deletion + audit session.
