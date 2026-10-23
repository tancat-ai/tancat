# Session - D1: the three resolver cuts (2026-10-22, t-0855)

**Question:** the owner's D1 decision from the j-0187 deeper walk ("i agree") queued three
resolver cuts after the page-cursor re-measure. Do they hold - and what do they remove?

**Answer: all three are in, on branch `task/d1-resolver-cuts`, one commit with three clear
parts. Nothing pushes until the owner's pass.** (a) the learned cross-site transition is
gone from the resolver's GOTO branch; (b) `UrlResolver` no longer invents common path
candidates when nothing was scraped; (c) the link picker now falls back to the
browser-computed accessible name, so a link whose visible text is absent or ambiguous can
still be named. 4002 pytest, smoke 39/39, ruff + mypy clean, static eval 91/96 = 94.8%
unchanged.

## 1. The rule these serve

The owner's rule (2026-10-21): **a navigation is only valid when its destination is
KNOWN.** Known means: the URL the human gave us, the story's route concepts mapped onto
pages the browser really reached, or a page the pipeline really scraped. Two paths still
broke that rule, and the link picker had one gap.

## 2. The three cuts

### (a) The learned store is out of the GOTO branch

`src/placeholder_orchestrator.py`, GOTO branch of `_resolve_placeholder_for_page`: the
"Step 2.5 (AI-042)" block (flow memory) is removed, and the source list in the comment now
reads three sources, not four.

Flow memory learns "on site X, a link labelled *dashboard* leads to /h2x.html" from earlier
runs and could type that URL for a page **this** run never visited. It never fired in a
measured run, but it is exactly the guess the rule forbids: a URL from an earlier
experiment, not from the input or the page.

**Not cut:** the two page-state ASSERT branches still consult flow memory (they resolve a
URL *assertion*, a different question - "which page are we on?" rather than "where do we
send the browser?"). Recorded here so the difference is deliberate, not a miss.

### (b) `UrlResolver` no longer fabricates destinations

`src/url_resolver.py::build_mapping` step 4 is removed, with the now-unused
`build_common_path_candidates` import and the module docstring updated.

With nothing scraped, the resolver used to generate `/products`, `/cart`, `/checkout` ...
from a shared route vocabulary and map keywords onto them. That was switched back on
2026-08-03 because SPA sites expose no hrefs for journey discovery. **The page-cursor fix
(t-0847) removed the reason it existed**: the journey now reaches such pages the human way,
by clicking the link that names them, so a generated URL is only a guess.

`build_common_path_candidates` itself stays: it builds the *scrape candidate list*
(`orchestrator._build_candidate_urls`, `PlaceholderOrchestrator._build_candidate_urls`) -
pages to try scraping. A page that really loads then becomes a known page by being
scraped, which is source 3 of the rule. Only the *destination* fabrication is gone.

### (c) The browser-computed accessible name, as a back-up for poor labels

`src/journey_scraper.py::_discover_link_selector` now tries the markup first (unchanged),
then the browser's own accessible names (`_a11y_link_candidates`, via Playwright
`aria_snapshot(boxes=True)` and the existing `src/aria_parser.py`). A match maps back to the
DOM anchor carrying the same href, so the emitted selector keeps the usual shape.

This is the owner's own follow-up (his words: "it's a back up for poorly labled sites").
The markup can only see what the site wrote; two links both labelled "Shop", or an
icon-only anchor whose image carries the name, are named correctly only by the browser.

**Found while doing it, not fixed here:** the two existing a11y call sites in
`journey_scraper.py` (`_scrape_current_page` and the `capture` step) pass the raw flat CDP
result (`{"nodes": [...]}`) straight into `AccessibilityEnricher.enrich`, which expects a
tree with `children` - so those two calls enrich nothing. `src/scraper.py` does it
correctly via `_transform_cdp_ax_tree`. Fixing it would change resolution broadly, so it is
reported, not touched; the new call site uses the parsed snapshot and is unaffected.

## 3. Tests

- `tests/test_t0855_link_a11y_name.py` (new, 7 tests): the accessible name wins an
  ambiguous pair of "Shop" links and an icon-only image link; **both controls fail without
  the a11y pass** (markup alone cannot tell them apart); the markup still wins where it
  names the link; a missing snapshot changes nothing.
- `tests/test_t0855_resolver_cuts.py` (new, 5 tests): the learned store really does answer
  the GOTO (control), and the branch now skips instead; no candidates are fabricated with
  no scraped URLs; real scraped pages still map; the branch skips end to end.
- `tests/test_url_resolver.py::test_build_mapping_with_concepts_no_scraped_urls` was
  **inverted**: it pinned the fabrication (2026-08-03). It now pins the rule.
- `tests/test_flow_memory.py::test_goto_resolves_via_flow_memory_when_site_resolution_fails`
  was **inverted** for the same reason, with the flow-store control kept so the test fails
  for the right cause.

## 4. What was run

| Gate | Result |
|---|---|
| pytest (full) | 4002 passed |
| smoke | 39/39 |
| ruff check + format | clean |
| mypy `src/ cli/` | clean (165 files) |
| eval static (gate 1) | 91/96 = 94.8%, unchanged |

The static gate cannot move: it is computed from frozen captures and has no GOTO goldens.
The four-leg held-out re-measure is **not** run here - it still needs the owner's go, and it
is the only thing that measures these cuts on live data.

## 5. What this does not change

- No prompt, model, temperature or scoring change: the draw stays like-for-like.
- The ASSERT ranking path is untouched (the verifier's report and the t-0851 A/B both showed
  its misses on frozen July data are model noise, and nothing here touches it).
- The frozen-capture fixtures are untouched.
- The eval harness's own flow-memory path (`scripts/eval/eval_resolver.py`) is untouched: it
  is the measurement instrument's stub, its store is empty at eval time, and changing it
  would alter how the gate is scored. One-line follow-up if the owner wants the harness to
  mirror the product exactly.
