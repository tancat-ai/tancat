# Session — 2026-08-02: CLI walkthrough driver, Load-Existing crash fix, and zero-pass pipeline investigation (shipped)

## Summary

Built a reusable CLI walkthrough driver (`scripts/cli_walkthrough.py` — 100/100 buttons
verified), fixed a **crash** in "Load Existing Generated Tests", and investigated why the
pipeline produced **0 passing tests**. Five mechanical pipeline bugs found and fixed
(consent pollution, POM selector drop, URL trailing-slash, FILL container-div match,
evidence-tracker post-navigation hang). Production verification improved but verdict is
still **FAIL** — remaining failures are *semantic* (see "Open work" below).

## Shipped this session

### 1. CLI walkthrough driver — `scripts/cli_walkthrough.py` (new)

Marker-driven subprocess driver: spawns `cli.main`, feeds input only when the expected
prompt appears on stdout. `python scripts/cli_walkthrough.py --pass nav|full|all`.
NAV pass 41/41, FULL pass 59/59 (real LLM + live automationexercise.com).

**Windows gotchas discovered while building it (documented in the script):**
- `BufferedReader.read()` on a child pipe blocks until EOF — must use `read1()`.
- A single pipe *write* containing multiple `\n` is consumed by the child's `input()`
  as ONE line — multi-line pastes must be written one line per write call.
- The CLI paste reader terminates on the FIRST empty line — pasted stories must have
  no blank lines (and a trailing newline supplies the terminator).
- Menu "prompt" args (e.g. `"Select LLM provider"`, `"Step type"`) are never printed —
  only the shortcut bar / `Enter selection:` are real markers.

### 2. CLI bug: "Load Existing Generated Tests" crashed (PermissionError)

`load_package_manifest()` was called with a **package directory** while expecting the
manifest *file* — `_load_from_file(dir)` read the directory as JSON (PermissionError on
Windows). Fixed at the source (`src/pipeline_artifact_manager.py` — directory-aware:
resolve `<dir>/package_manifest.json` or reconstruct) + both CLI callers pass
`reconstruct=True` (legacy `verify_*` packages have no manifest).
4 regression tests in `tests/test_pipeline_artifact_manager.py`.

### 3. Earlier session (also uncommitted until now): POM/Consent Mode invisible feedback

`src/cli/main.py` — State block now shows `Consent : …` / `POM Mode : ON/OFF`, toggle
handlers pause with a confirmation (also fixes a stray-Enter msvcrt bug where the
confirming Enter re-selected menu item 1).

## The zero-pass investigation → five mechanical fixes

`verify_production` verdict before: `0 passed, 2 skipped` — every test skipped.

| # | Root cause | Fix | Proof |
|---|---|---|---|
| 1 | POM mode **discarded resolved selectors**: `home_page.click('product name link')` → runtime fuzzy match (needs 2-word `_ELEMENTS` overlap) → `pytest.skip`. Resolver had already found `a[href="/product_details/1"]` (score 21). | `get_pom_method_call` emits `click(label, selector=...)`; generated POMs accept `selector=None` and click it directly. Generic `fill()` added (didn't exist → would skip). `src/pom_helpers.py`, `src/page_object_builder.py` | tests execute instead of skipping |
| 2 | **Consent-overlay pollution**: 1,448/2,328 scraped elements were OneTrust `.fc-*` preference-center markup (hidden in DOM). `_remove_consent_overlays` only matched **ID**-based selectors. POM was 1,806 lines of vendor-click methods. | Added `[class*="fc-"]`, `[id*="onetrust"]`, `[class*="onetrust"]` to `src/scraper.py` consent removal | POM 1806 → ~520 lines |
| 3 | URL assertions missing **trailing slash**: `to_have_url("https://automationexercise.com")` vs actual `.../` (site canonicalizes). Root seed came from `verify_production.py` site config without `/`. | `normalize_url()` in `src/url_resolver.py`, applied at all 3 emission points in `src/placeholder_orchestrator.py` (GOTO steps 1–4 + both ASSERT batch paths — one was missed initially) | |
| 4 | FILL resolved to a **container div**: saucedemo `[data-test="login-container"]` reports `accessible_name='Username'` (wraps the input) → Pass 1 fast-text matched it. `rank_candidates` had the fillability gate but Pass 1 did not. | FILL gate (`_is_fillable`) added to `pass1_text_match` in `src/element_matcher.py` | `FILL username` → `#user-name` |
| 5 | **Evidence-tracker hang** (the "timeout" the user flagged): after a click that navigates (login → inventory), `_record_step` re-ran `_get_element_metadata(dead_locator)` — each un-timed Playwright call waits the 30s default (×4 ≈ 120s/test) → whole suite hit the cap. | `_record_step` accepts `element_metadata=` (pre-captured before the click); passed from all click success paths (`src/evidence_tracker.py`, `src/locator_fallback.py`) | saucedemo suite: timeout 1/6 → completes 137s |
| 6 | `verify_production.py` timeout message printed literal `{max(60, min(180, len(test_funcs) * 25))}s` (plain string, not f-string); on timeout, partial pytest output was discarded. | f-string with real value; on `TimeoutExpired` saves partial stdout + counts evidence files → `"timed out after 180s — 1/6 tests completed"` | |

**Regression safety:** full suite 2042 passed / 1 skipped; ruff + mypy clean; eval static
still 100% resolution on existing golden keys.

## The timeout question (user asked "is that timeout needed? check early?")

The 1500s bash ceiling wasn't needed — actual run ≈ 613s; 900s is fine. The internal
suite cap IS a needed safety valve, but the real problem was fix #5 (the hang). The cap
formula was also too tight for legit slow sites: `min(180, tests*25)` killed a run where
6/7 tests had already passed; raised to `min(300, tests*30)`.

## Open work — the semantic layer (next session)

Verdict after fixes: saucedemo 2 passed/2 failed/2 skipped, automationexercise
2 passed/5 failed, 22/26 gates. Remaining failures are **meaning**, not machinery.
**Do NOT add site-specific lists** — match playwright.dev's own vocabulary instead
(ARIA roles, `getByRole`, `toBeVisible/toBeHidden`):

1. **Dialog-action scoping (agreed, highest ROI):** descriptions implying dismiss/confirm
   ("OK", "close popup") → structural query: `role="dialog"`/`alertdialog` containers →
   `role="button"` inside. General (ARIA), no vocabulary list. Narrowed 2328 → ~2 buttons
   in the "OK" case (real failure: resolver picked `input[name="csrfmiddlewaretoken"]`).

2. **Assertion-state polarity (agreed):** map to Playwright's own methods — "popup closed"
   → `expect(...).not.to_be_visible()` / `to_be_hidden()`. General polarity words
   (closed/gone/disappeared/removed/no longer). Current failure: `assert_visible('p.text-center', label='popup closed')`.

3. **Assert target role (try across sites):** "assert the home page title" matched a
   200-char paragraph. Prefer `role="heading"` for title-ish ASSERTs (mirror of B-025
   which skips headings for CLICK). **Upstream note below takes priority.**

4. **Generic targets — DROPPED (user review):** picking any product for generic
   "add to cart" is correct behavior (test asserts the badge; passes regardless). Not a defect.

5. **LLM re-ranking (user direction):** the `SemanticCandidateRanker`'s pick is
   "text-validated, fails, used anyway" — no retry, no output contract. User wants an
   ordered pipeline: scoring shortlist → LLM ranks with strict structured output
   (T-strings / langgraph for format) → validate → bounded small retry loops.

### Upstream finding (user-raised, investigate first): "assert the home page title" is an LLM decision

Chain: condition "verify it loads" → skeleton prompt says `{{ASSERT:what should be visible}}`
(steers toward element visibility) → LLM invents `{{ASSERT:home page title}}` →
`_is_page_state_assertion("home page title")` returns False ("title" is an element keyword)
→ element resolution picks the paragraph.

- The **golden key already encodes the target**: eval-002 criterion 0 →
  `ASSERT home page loaded → to_have_url("https://automationexercise.com")`.
- Likely to recur: "verify X page loads" is condition #1 of the most common story shape.
- Proposed fix (needs no new lists): steer the skeleton prompt toward page-state phrasing
  for load-style conditions (add a page-state ASSERT form to ALLOWED PLACEHOLDERS/example),
  and reconsider routing "title" through the URL/page-state path. Measure against eval-002's
  existing golden — should flip miss→hit with zero new goldens.

### Measurement (user-raised)

- Current CI gate = `resolution_accuracy` (strict selector match + `tolerance_selectors`),
  binary per placeholder. `test_pass_rate` (the "requirements met" signal) exists but only
  in `full` mode (live pytest), decoupled from the gate.
- Golden dataset already uses generic selectors for generic steps (`.add-to-cart.btn`)
  and tolerance_selectors — but requirement-equivalent picks (any product on the grid)
  still count as misses with no partial credit.
- Proposal: requirement-level equivalence in goldens (`requirement_equivalents`), score as
  exact / equivalent / wrong; keep test-pass-rate as the tiebreaker.

## Verification status

- `scripts/verify_production.py`: 22/26 gates (was 20/26 pre-session baseline) — verdict
  still FAIL (correctly; semantic work is open).
- Eval static: 100% all sites. Full pytest: 2042 passed, 1 skipped. ruff + mypy clean.
- Committed + pushed; CI monitored to green (see commit refs in BACKLOG.md).
