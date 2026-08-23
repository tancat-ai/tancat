# AI-052 — Observed Transitions (stop guessing next-page URLs)

> Plan of record for AI-052. Each session below is self-contained: fresh context,
> one deliverable, its own gates. Read only the session you're in (plus §0 context).
> Backlog: `BACKLOG.md` → AI-052. Root-cause evidence: `docs/sessions/2026-08-21_peer_verification.md`
> + this plan's §0 (re-verified 2026-08-22).
>
> **PROGRESS (2026-08-23):** S1 ✅ · S2 ✅ · S3 ✅ (core fix — zero different-page errors on
> BOTH verify sites) · S4 ✅ (keyword-URL guessing deleted; evidence-only transitions) ·
> **S5 ✅ (ARIA role gate, penalty-first; resolver-mode A/B 97.9% = 97.9% — zero golden
> regressions. Records: `docs/sessions/2026-08-23_ai052_session4_no_guessing.md`,
> `docs/sessions/2026-08-23_ai052_session5_role_gate.md`). Next: S6** (regression sweep,
> docs sync, ship). Session records:
> `docs/sessions/2026-07-23_ai052_session1_observed_trail.md`,
> `docs/sessions/2026-07-23_ai052_session2_plumbing.md`,
> `docs/sessions/2026-07-23_ai052_session3_core_fix.md`. Status flips to `✅` only at S6.

---

## 0. Shared context (read once)

### The bug (confirmed 2026-08-22, 4-run matrix)

Generated saucedemo tests click a product title link (`#item_4_title_link` →
`inventory-item.html?id=4`), then click an add-to-cart button that **only exists on
the inventory page** → runtime `_LocatorNotFoundError: element exists on a different
page`. Reproduced on saucedemo (RAG on AND off) and automationexercise (3 runs,
`.btn.check_out` while on `/products`). NOT RAG-dependent, NOT LangGraph-dependent
(linear `run_pipeline` only), NOT POM-only. Probabilistic: depends on whether the
LLM skeleton inserts a "view product, then add" sequence.

### Root cause (verified in code, 2026-08-22)

Two decoupled URL mechanisms disagree:

1. **Journey scraper OBSERVES reality.** `JourneyScraper._scrape_journey_sync`
   (`src/journey_scraper.py:386`) reads `new_url = page.url` after each click and,
   on change, scrapes the actual landing page into `output[new_url]`. The ordered
   trail is available via `get_pages_visited()` (`journey_scraper.py:414`).
2. **That observation is discarded.** `scraped_data` (flat URL→elements dict,
   merged at `orchestrator.py:486-506`) is passed to the resolver, but the ordered
   per-journey trail is only stored as `PipelineRunResult.pages_visited`
   (diagnostics, `orchestrator.py:638`) — **never passed to the resolver.**
3. **The resolver re-guesses.** `_replace_placeholders_sequentially`
   (`placeholder_orchestrator.py:484`) takes no trail. It advances `current_url`
   via `infer_next_page_url()` (`src/url_inference.py`) — keyword + href guessing.
   When the guessed URL isn't in `scraped_data`, `_build_scoped_pages`
   (`placeholder_orchestrator.py:1185`) returns `{}` → resolver falls back to
   **ALL pages** (`element_matcher.find_best_element_for_current_page:743`
   "Collects candidates from ALL pages first") → a cross-page locator wins.

### The principle (agreed with user)

- A URL is usable **only if a specific scraped element points to it** (real `href`).
  Text→URL fabrication ("description says inventory, so probably site.com/inventory")
  is banned.
- Prefer **observation over inference**: the browser already told us where the click
  landed. Consume that fact; don't re-guess it.
- When we have **no observation**, be honest: `pytest.skip` with a clear reason.
  Never emit a locator for a page we have no evidence for. A shorter journey is
  better than a complete-but-wrong one.

### Three states a "next page" can be in (replaces the current guess/nothing binary)

| State | Meaning | Action |
|---|---|---|
| `verified` | observed/scraped page we have DOM for | scope next step to it |
| `evidenced` | real `href` target, page not scraped | advance, but next step unverifiable → skip if unresolvable on from-page |
| `unknown` | no observation, no element/href | stay honest; skip if next step unresolvable on from-page |

### Gate stack (run before accepting any session)

`scripts/smoke.py` → `pytest -q --tb=short` → **eval harness static**
(`scripts/eval/eval_harness.py run --mode static`, baseline 97.9%) →
`ruff check` + `mypy` → **`scripts/verify_production.py saucedemo --keep`**
(session 3+4 only; ~10min, needs llama.cpp :8080).
**Never commit untracked `generated_tests/test_*.py`** (see 2026-08-21 session).

### File map (touch points)

- `src/journey_scraper.py` — observation source (context_log, get_pages_visited)
- `src/orchestrator.py:671` `_scrape_journeys_statefully` — plumb trail out
- `src/orchestrator.py:562` `run_pipeline` — pass trail to resolver
- `src/placeholder_orchestrator.py:484` `_replace_placeholders_sequentially` — consume trail
- `src/placeholder_orchestrator.py:1185` `_build_scoped_pages` — honest scoping
- `src/element_matcher.py:743,963` — role-aware candidate collection
- `src/url_inference.py` — keyword branch deletion (session 4)

---

## Session 1 — Data model + capture observed transition trails

**Goal:** `JourneyScraper` emits a structured, per-journey observed transition trail.
No resolver changes yet — capture only. Proves the observation is available.

**Deliverables**
1. New dataclass `ObservedTrail` (or extend `JourneyResult`) in `src/journey_scraper.py`:
   - `steps: list[ObservedStep]` where `ObservedStep = {index, action, description,
     selector_used, from_url, to_url, navigated: bool, scraped: bool, error: str|None}`
   - `pages_visited: list[str]` (ordered, deduped) — already exists, keep.
2. In `_scrape_journey_sync`, populate `ObservedStep` at each step using the existing
   `current_url` / `new_url = page.url` / `output` writes (lines ~255-390). The
   "click caused navigation" block (line 386) already has both URLs — record them.
   Reuse `_context_log` as the raw source; add a typed getter `get_observed_trail()`.
3. Expose via `JourneyResult` (Phase B `execute_journey` path too, not just discovery).

**Do NOT** change any resolution logic. This session is pure capture + types.

**Tests** `tests/test_journey_observed_trail.py`
- A journey with navigate→click(navigates)→assert yields a trail with 3 steps,
  correct from/to URLs, `navigated=True` on the click, `scraped=True` where output
  gained a key.
- A journey whose click finds no locator → trail step `error` set, trail ends early.
- `get_observed_trail()` matches `get_pages_visited()` ordering.

**Gates:** smoke, pytest, eval static 97.9%, ruff, mypy.
**Definition of done:** trail is correct on a live `scripts/debug.py scrape` of
saucedemo login→inventory (manual check, print trail).

---

## Session 2 — Plumb the trail into the resolver (no behaviour change)

**Goal:** the observed trail reaches `_replace_placeholders_sequentially` and is
logged per step. Resolution still uses the old guess — this session only wires data
through, so it's low-risk and proves the plumbing.

**Deliverables**
1. `_scrape_journeys_statefully` (`orchestrator.py:671`) returns
   `observed_trails: dict[journey_test_name, ObservedTrail]` alongside
   `(scraped_data, pages_visited)`.
2. `run_pipeline` stores `observed_trails` on `PipelineRunResult` and passes it to
   `_replace_placeholders_sequentially`.
3. `_replace_placeholders_sequentially` accepts `observed_trails` (default `{}` for
   back-compat with tests/CLI callers) and, for each journey, logs
   `[resolve] <journey> observed trail: [url0 -> url1 -> url2]` at debug level.

**Do NOT** change which `current_url` is used for scoping yet.

**Tests** `tests/test_orchestrator_trail_plumbing.py`
- Stub `JourneyScraper` returning a known trail → assert it arrives in
  `_replace_placeholders_sequentially` (spy on the log or a callback).
- Back-compat: calling `_replace_placeholders_sequentially` without `observed_trails`
  still works (default `{}`).

**Gates:** smoke, pytest, eval static 97.9%, ruff, mypy.
**Definition of done:** debug log shows the real observed trail for a saucedemo run
(`PIPELINE_DEBUG=1`), matching Session 1's capture.

---

## Session 3 — Resolver consumes the trail (lookup replaces guess) + honest scoping

**Goal:** the core AI-052 fix. The resolver derives `current_url` from the observed
trail (a fact) instead of `infer_next_page_url` (a guess). Unobserved steps →
honest `pytest.skip`, never a cross-page locator.

**Deliverables**
1. In `_replace_placeholders_sequentially`, for journey `J` step `i`:
   - If `observed_trails[J]` has a step for this index with a `to_url` that is in
     `scraped_data` → `current_url = to_url` (**verified**).
   - Else if the previous step's `to_url` is a real `href` target not scraped
     (**evidenced**) → advance but mark next step unverifiable.
   - Else (**unknown**) → `current_url` stays on the last verified page; if the next
     step's element isn't found on that page → `pytest.skip("next page '<desc>' not in
     scrape inventory — journey did not reach it")`.
2. `_build_scoped_pages`: when `current_url` is verified, scope to it. When the step
   is `evidenced`/`unknown`, scope to the **from-page** (last verified) — do NOT fall
   back to all pages. (This is the line that currently produces AI-052.)
3. Keep `infer_next_page_url` as a **last-resort hint for GOTO only** (keyword branch
   stays until Session 4 deletes it) — element CLICK/FILL scoping must not depend on it.

**Mapping detail (the tricky part):** the skeleton's placeholder order must align with
the observed trail's step order. The trail was built from the *same* journey steps
(`_scrape_journeys_statefully` builds `JourneyStep`s from `journey.steps`
placeholders), so index alignment should hold — but ASSERTs map to `scrape` steps and
GOTOs to `navigate`. Build an explicit index map in Session 2's plumbing if needed;
verify against the four captured failure fixtures.

**Tests** `tests/test_resolver_observed_scope.py` (fixtures from real runs)
- Fixture A (saucedemo, 2026-08-20): trail shows title-link → `?id=4`; assert the
  following add-to-cart step resolves to `pytest.skip`, NOT
  `#add-to-cart-sauce-labs-fleece-jacket`.
- Fixture B (automationexercise, 2026-08-03): `.btn.check_out` while on `/products`
  → now skips instead of cross-page click.
- Fixture C (happy path): a trail where every step lands on a scraped page → all
  resolve as before (no regression).
- `evidenced` case: real href to unscraped page → next step skips honestly.

**Gates:** smoke, pytest, eval static 97.9%, ruff, mypy, **`verify_production saucedemo --keep`**
(expect: the wrong-page `_LocatorNotFoundError` is GONE; the affected step now skips;
gate count may drop slightly because a step is honestly skipped rather than failing —
that is correct and acceptable).
**Definition of done:** zero `_LocatorNotFoundError: ... different page` across
saucedemo + automationexercise verify runs; no new false passes.

---

## Session 4 — Delete the keyword-URL guessing + GOTO hygiene

**Goal:** remove the banned text→URL fabrication. After Session 3, element scoping no
longer depends on it; only GOTO/URL-assert resolution may still use URL lookups, and
those must be evidence-based.

**Deliverables**
1. `src/url_inference.py`: delete the keyword branches in
   `_infer_click_transition_url` (login/checkout/continue/finish/transfer/pay
   keyword→`_find_discovered_url`). Keep only the `href`-based return (real element
   href). Update the module docstring to state the no-guessing principle.
2. Audit callers of `infer_next_page_url` and `resolver.resolve_url`:
   - GOTO/URL-assert paths may use `resolve_url` **only** when it returns a URL that
     is a real scraped/known page (UrlResolver mapping built from discovered URLs,
     `orchestrator.py:541`) — that's evidence-based, keep.
   - `journey_scraper._infer_url_from_description` (line 423): this one *navigates
     and scrapes*, so it self-corrects, but it still invents a URL from a description.
     Replace with: only navigate to a URL that is already in the discovered URL set
     (evidence), else record `step_skipped` and stop guessing.
3. `tests/test_url_inference.py`: rewrite to assert the keyword branches are gone
   (a "login" click with no href returns `None`, not a discovered URL).

**Gates:** smoke, pytest, eval static (may shift — record new number), ruff, mypy,
**`verify_production saucedemo --keep` + `automationexercise --keep`**.
**Definition of done:** no code path turns a description keyword into a URL;
verify runs clean; eval static recorded (update baseline only if a *verified*
improvement, per eval-harness rules).

---

## Session 5 — (Optional, deferred) ARIA role-aware candidate collection

**Goal:** a second, independent defence — even if scoping is ever empty again, the
resolver prefers the *right kind* of element (role=button for a click-step) using the
ARIA data we already capture (`src/accessibility_enricher.py`).

**Why separate/optional:** it's a scoring change (regeneration-sensitive, AI-037
lesson). Only build if Sessions 3-4 leave any residual cross-page risk or if
role-mismatch false picks appear in eval.

**Deliverables (if built)**
1. `element_matcher`: add a role gate to passes 0-3 — for a CLICK step, strongly
   prefer `role in (button, link)` matching the implied action; penalize candidates
   whose role contradicts the step. Use `accessible_name`/`aria_label` already in the
   element records.
2. Penalty-first (not hard filter) to avoid skipping genuine link-clicks.
3. `tests/test_element_matcher_role_gate.py`.

**Gates:** full stack incl. eval **full** (`--mode full --regenerate`) since this
changes resolution quality — compare to baseline.
**Definition of done:** no regression in eval full; role-mismatch picks reduced.

---

## Session 6 — Regression sweep, docs, ship

**Goal:** prove the fix end-to-end and sync all tracking docs.

**Deliverables**
1. Run `scripts/uat.py --all-sites --save results.json` (needs LM Studio/llama.cpp
   :8080) — record before/after pass rates.
2. Re-run eval harness `--mode full --regenerate`; if resolution accuracy moved,
   `eval_harness.py compare` then `baseline --save` only on verified improvement.
3. Update `BACKLOG.md` AI-052 → ✅ with per-session commit refs; add AI-051 note if
   the login `to_have_url` failure (sibling, post-login URL assert) is still open.
4. Update `docs/plans/ROADMAP_ROADTO_PRODUCTION.md` — add AI-051/AI-052 entries (they
   were missing from the roadmap), bump "Last updated", fix Phase 7 stale checkboxes.
5. `python scripts/maintenance/kanban.py` to regenerate `kanban.html`.
6. Session record: `docs/sessions/2026-MM-DD_ai052_observed_transitions.md`.
7. Commit `BACKLOG.md` + `kanban.html` together.

**Gates:** smoke, pytest, eval static + full, ruff, mypy, verify_production both sites.
**Definition of done:** ship-it checklist green; no open `_LocatorNotFoundError`
different-page failures; all docs in sync.

---

## Open questions (resolve in the session noted)

1. **(S3)** Skeleton-placeholder-index ↔ observed-trail-index alignment: confirm
   ASSERT→`scrape` and GOTO→`navigate` mapping holds for all four fixtures. If not,
   build an explicit index map in S2 plumbing.
2. **(S3)** `evidenced` vs scrape-on-demand: current plan = honest skip (option a).
   Reconsider only if journeys are unacceptably short after S3. (Scrape-on-demand =
   option b, larger; revisit as its own item if needed.)
3. **(S4)** Does deleting the keyword branch drop eval static below 97.9%? If a real
   regression, isolate which GOTO/URL-assert goldens depend on it and decide case-by-case.

## Out of scope (separate items)

- **AI-051** — post-login `to_have_url` landing-target assert (sibling generation bug).
- **AI-046** — model A/B re-test (thinking-ON effect on page-awareness is an open
  question there; this fix should make the resolver robust *regardless* of model).
- **AI-039** TanCat rename, **AI-044-B** visual grounding — unchanged.
