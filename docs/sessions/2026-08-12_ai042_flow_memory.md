# 2026-08-12 — AI-042 session 1: cross-site flow memory (learner + store + consumption)

**Roadmap:** Tier 4 §16 (AI-042 Cross-Site Flow Memory). Session 1 delivered the
learner, the store, and the GOTO/URL-assertion consumption hook; the eval
holdout measurement is the session-2 follow-up.

## Problem

Locator memory can't transfer across sites (only ~3% of learned locator pairs
overlap — B-047 locks locators to their site), but navigation *shape* does:
login → browse → cart → checkout is near-identical across e-commerce sites.
Every test run regenerates flows from scratch; the sidecar URL traces (B-033
per-step `url`) held the flow information but nothing learned it
(`_step_to_pattern` deliberately skips navigate steps).

## What shipped

**`src/flow_memory.py`** (~440 lines):

1. **`normalize_route(url)`** — URL → normalized route keyword (scheme/host/
   query dropped, extensions stripped, numeric id segments dropped,
   index/home → "home"). Never stores raw URLs (AI-035 §4 privacy).
2. **`flow_transitions(steps)`** — passing sidecar steps → `(transition,
   site_identity)` pairs. `navigate` steps set page context; same-page
   actions (`from == to`) dropped; page context advances after every
   URL-recording step (failed steps included — the URL is factual).
3. **`FlowMemoryStore`** — JSON file store (`evidence/flow_memory.json`,
   atomic tmp + os.replace, corrupt-tolerant load). Dedup on
   `(from_route, action, description, to_route)` bumps `hit_count` and
   grows the `site_hashes` set → `site_count` (site diversity). `min_sites`
   guardrail (2 = cross-site-verified only) in `route_hints`.
4. **`flow_resolved_url(store, description, from_url, scraped_urls)`** — the
   consumption hook: destination routes flows say are reachable from the
   current page, matched by token overlap against both action labels and the
   destination-route vocabulary.

**Wiring:**
- `PlaceholderOrchestrator.__init__` gains `flow_store` (default None = zero
  overhead); step 2.5 in the GOTO/URL chain (after UrlResolver + resolve_url,
  before heuristic/seed — site evidence always wins) and the page-state
  ASSERT fallback.
- `TestOrchestrator` constructs the store by default unless
  `FLOW_MEMORY_ENABLED=0` (tests set it in `tests/conftest.py` — hermetic,
  mirroring `RAG_ENABLED=0`).
- Learning rides the existing paths: `generated_tests/conftest.py` teardown
  hook and `synthesize_stories.py` parent-side sweep
  (`FlowMemoryStore().learn_from_sidecars(...)`).

**Real-data seed:** swept 908 production sidecars → **64 flow patterns, 6
distinct sites, 4 cross-site flows** (home→cart, home→checkout ×2 sites each),
plus the saucedemo checkout chain
(`checkout-step-one --continue--> checkout-step-two --finish-->
checkout-complete`) and the banking mock flow
(`dashboard --Transfer Money--> transfer --submit--> transfer_success`).

## Tests

33 tests in `tests/test_flow_memory.py`: route normalization, description
cleaning, transition extraction (passed-only gate, same-page drop, context
advance, no-url safety), store (dedup, site diversity, persistence round-trip,
corrupt file, clear, query ranking, route_hints min_sites, sidecar sweep
gates), and the consumption hook (unseen-site resolution via cross-site flow,
destination-vocabulary matching, None cases, min_sites) plus two orchestrator
integration tests (GOTO resolves via flow when site resolution fails; disabled
store is a literal no-op).

## Verification

- ruff + mypy clean (src + tests)
- 33 flow tests pass; 125 orchestrator/rag_learn tests pass; 171
  URL-assertion/orchestrator tests pass (the block I touched)
- Real-data sweep: 908 sidecars → 64 patterns, 0 errors

## Next session (AI-042 eval holdout)

Per roadmap: hold out one eval dataset as an "unseen site" and measure
first-pass accuracy vs today. Plan: build flow memory from real sidecars of
N sites (already seeded), then run the eval harness (`--mode static` /
regenerate) on the held-out site with the store on vs off and compare
GOTO/URL-assertion resolution. Also consider: (a) skeleton guidance (deferred
— prompt changes are regeneration-sensitive, AI-037 lesson), (b) surfacing
flow stats in the Streamlit "Learned Patterns" section, (c) a prune button
(parity with RAG prune).

---

# Session 2 (same day): eval holdout measurement + route canonicalization

## Measurement (`scripts/eval/flow_holdout_eval.py`)

For each eval dataset's URL-assert/GOTO golden placeholders, checks flow
resolution with **holdout integrity** (the target site's own site hash is
excluded from the verifying sites) and **from-context reachability** (the
target site's known URLs include the flow's from-route — the page the
pipeline would be on at resolution time).

Initial result — **0/4 non-home URL asserts** (3 home targets are seed-fallback
scope, not flow memory's). Root cause: cross-site flows only transfer when
sites share route vocabulary. saucedemo's flows end at `inventory`/`cart`;
automationexercise's pages are `products`/`view_cart`. The url_resolver's
hardcoded alias groups (cart↔basket, products↔inventory) exist precisely
because sites disagree on route names — flow memory had no learned analog.

## Fix: route canonicalization in `normalize_route`

`_ROUTE_ALIASES` — exact whole-route match after cleaning:
- view_cart / basket / shopping_cart / shopping-cart → **cart**
- inventory → **products**
- signin / sign-in / auth → **login**

Deliberately exact-match only: `checkout-step-one` and `checkout-step-two`
stay distinct flow states (collapsing them would destroy the
step-one → continue → step-two flow).

Re-seed from 908 sidecars: **64 → 89 patterns, 5 cross-site** (up from 4 —
the vocabulary merge created new overlaps).

## Result: 0 → 3/4

| Golden (held-out site) | Route | Holdout | Context | Cross-site |
|---|---|---|---|---|
| automationexercise "products page title" | products | ✓ | ✓ (from home) | — |
| automationexercise "cart page title" | cart | ✓ | ✓ (from products) | — |
| ecommerce "cart page title" | cart | ✓ | ✓ (from home) | ✓ (2 sites) |
| ecommerce "checkout page title" | checkout | ✗ (flows co-verified on target port 8781) | | |

End-to-end verified: `flow_resolved_url` on automationexercise's scraped pages
returns `view_cart`/`products` using ONLY non-automationexercise flows
(saucedemo + mocks).

## Caveats (documented in the script)

- 3/7 goldens target "home" — trivially resolved by the orchestrator's
  seed-URL fallback; not flow memory's scope.
- ecommerce "checkout" excluded: the only flows to checkout were co-verified
  on localhost:8781 — the target mock port. Port collision makes mocks
  indistinguishable (B-047 hashes host[:port]); strict holdout excludes them.
- No GOTO placeholders exist in any golden set — the hook is exercised via
  URL asserts; a GOTO-flavored dataset would test it directly.

## Follow-ups (optional, not roadmap items)

- GOTO-flavored golden scenario to exercise the hook directly.
- Streamlit "Learned Patterns" section: show flow stats + prune button
  (parity with RAG prune).
- Skeleton guidance (roadmap option (a)): deliberately deferred — prompt
  changes are regeneration-sensitive (AI-037 lesson).

---

# Session 2 addendum: customer-value analysis

`docs/analysis/ai042_flow_memory_customer_value.md` — data-grounded analysis of
what the feature is worth to a customer. Headline numbers: 27.4% of evidence
steps are navigation-class, 7.3% of golden placeholders are URL-assert/GOTO
class (the flow-memory target), eval holdout 0 → 3/4, and the honest boundary:
element-level resolution (the dominant skip cause) is the RAG layer's job;
single-page-form customers see near-zero benefit. Optional roadmap follow-ups
AI-042-F1..F4 added to ROADMAP §16.

---

# Session 2 addendum 2: F1 shipped — GOTO-flavored eval + navigation corpus

User question answered: **is GOTO important enough in Playwright's own
documentation to give value from its own data set?** Yes — navigation is
first-class in Playwright's docs (`page.goto` is the core API, actionability
explicitly exempts navigation: "navigation actions are not subject to
actionability checks"). But our curated corpus (3 files) had ONE navigation
section — the data set underrepresents it. So F1 had two halves:

1. **`docs/rag_corpus/playwright/04-navigation.md`** — curated navigation
   reference (goto, load states, URL assertions, SPA/soft navigation, the
   "wrong navigation is silent until the next assertion" consequence).
2. **`scripts/eval/dataset/eval-008_goto_navigation.json`** — GOTO-flavored
   banking-mock dataset: 2 GOTO goldens ("go to the transfer page" →
   transfer.html, "navigate to bill payments" → payments.html) plus URL
   asserts, each carrying `expected_page` (the from-context).

**Wiring:** `eval_resolver._resolve_placeholder` gains the flow path for
GOTO/URL/url_assertion placeholders — `flow_resolved_url` with
`expected_page` as from-context, before element matching. `run_resolver_eval`
constructs the workspace store. 3 hermetic tests
(`tests/test_eval_goto_flow.py`): GOTO goldens resolve via flows built from
synthetic evidence; baseline (no store) never resolves the URL; wrong
from-context is honored.

**Stateful scraped pages:** the banking mock session-gates every page
(localStorage session; stateless scrape redirects to the login wall). Added
`scripts/eval/scraped_pages/http_localhost_8781_*.json` — login-wall index
captured first, then the gated pages in one authenticated context. This also
made eval-007 static-testable.

**Results:**
- banking_mock resolver accuracy: **9/26 → 13/26 (34.6% → 50.0%)**
- overall resolver: 32.1% → **35.8%**
- holdout eval: 3/7 → **6/11** (both eval-008 GOTOs resolvable)
- static harness gate unchanged: **97.9%** (eval-008 is 0/0 without a capture)
- ruff/mypy clean; full suite green

**Honest caveat:** the eval-008 flows come from the banking mock's own
evidence on a sibling port (8782, from resolve_and_learn runs) vs the eval's
8781 — port-hash separation makes it "cross-site" per B-047 but it's the same
mock, so it exercises the hook rather than proving unseen-site transfer. The
automationexercise URL asserts remain the true holdout story (saucedemo +
mocks only).

---

# Session 2 addendum 3: AI-042-F3 shipped — cross-test flow chaining

The within-test learner only sees the journey inside one test function; 904/908
real sidecars contain a single navigation, so the suite-level shape (login test
→ products test → cart test) was invisible. F3 chains **adjacent,
fully-passing tests in name order**: terminal page of test N → entry page of
test N+1, as a GOTO transition whose description is the destination route name.

**Design findings from the real corpus:**
- The top-level `generated_tests/evidence/` is a MIXED dir (different sites,
  different stories) — chaining there creates nonsense. Guard: same-site pairs
  only (`domain_from_url` equality).
- Pre-B-033 sidecars have `url=None` on steps — `_sidecar_routes` falls back
  to navigate `value` for entry/terminal.
- Failed tests break the chain (adjacent passing pair only).

**Shipped (`src/flow_memory.py`):** `_sidecar_routes`, `chain_suite_transitions`
(pure), `FlowMemoryStore.learn_suite_flows()`; `FlowPattern.source`
(`within_test` | `suite_chain`); `stats()` split. Wired into
`synthesize_stories.py` parent sweep. 11 new tests (45 total).

**Re-seed result:** 24 new suite-chain patterns (store 89 → **113**, cross-site
5 → **8**), including the valuable cart↔checkout↔products chains verified on
**2 sites**; holdout eval strict cross-site 1/11 → **2/11**; theinternet and
banking chains are coherent per-site. Some chains are suite-ORDER adjacencies
rather than navigation edges (checkout-step-one → products) — real facts, but
consumers should prefer hit-count/site-count ranked (the flow_resolved_url
ranking already does).

**Remaining F-series:** F2 (Streamlit stats + prune — the source split is ready
for it), F4 (skeleton guidance, deliberately deferred).

---

# Session 2 addendum 4: F3 product-path wiring

F3's learner was script-only (synthesize_stories). Real product runs never
chained: each test's conftest hook learns within-test flows, but nothing
chained the package afterwards. Closed the gap:

- **`PipelineRunService.run_saved_test`** (shared UI + CLI post-run hook):
  when `persist=True` (a real run), calls `learn_suite_flows(<package>/evidence)`
  — best-effort, never breaks the run. 2 new tests (persist chains, preview
  doesn't; the class-attribute patch needs the `self` arg — unbound-method
  semantics).
- **`scripts/verify_production.py`**: same hook after the execution gate.

Now every run path feeds suite flows: UI, CLI, verify_production (product),
synthesize_stories (training). 52 tests pass across the flow/goto/run-service
files; ruff/mypy clean.

---

# Session 2 addendum 5: AI-042-F2 shipped — flow stats + prune in the sidebar

`SidebarConfig._render_flow_memory()` (src/ui/ui_sidebar.py) — parity with the
RAG "Learned Patterns" section (B-036 Phase 4):

- "Flow Memory" subheader showing `format_flow_stats_summary(stats)`:
  Patterns · Sites · Cross-site · Suite chains (the F3 source split surfaces
  here).
- Two-step prune button → `FlowMemoryStore.clear()` — all flows are learned
  (there is no golden/docs tier to keep, unlike RAG), so prune clears the
  whole store. Confirmation mirrors the RAG prune UX.
- Empty store degrades to a hint ("no flows learned yet — run a passing suite
  to learn navigation shape"); store failure degrades to a note — the
  always-on/best-effort contract.

Testing: pure `format_flow_stats_summary` helper (unit-tested) + 2 lightweight
stubbed-UI tests (fake `st` + patched store) covering the stats caption and
the empty-store degradation — 4 new tests (51 total in the flow/UI files).

With F1, F2, F3 all shipped, the AI-042 follow-up series is complete (F4
remains deliberately deferred — prompt changes are regeneration-sensitive).
