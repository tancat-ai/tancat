# Next Sessions — Improvements to the generator, to tancat.dev, and a viability check

> **Purpose.** One place to hold the improvement list for the next several sessions, plus an
> honest commercial assessment. Written 2026-09-15, at the end of a session that produced
> hard evidence about how much the product can currently be trusted.
>
> **How to use it.** Each part is ordered by "what unblocks the most". Every item names its
> BACKLOG id, so status lives in `BACKLOG.md` and this file only points at it. Update the
> measurement appendix after each session so progress is comparable.
>
> **Read Part C first if you are deciding whether to keep building.** It answers the question
> directly.

---

## 1. Where we are — the evidence in one page

All of the following comes from running one well-formed 35-criterion story against
`tancat.dev` served locally (`http://localhost:8079/`), and from reading the resulting report
and sidecars. Raw artefacts: `generated_tests/test_20260915_194227_*`, `report_local.md`.

| Measure | Result | Verdict |
|---|---|---|
| Criteria covered by the generator | **35 / 35** → 48 tests | ✅ good — decomposition works |
| Tests reported | 23 failed / 25 passed | ❌ misleading in both directions |
| Failures that are actually **our** bug | **18 of 23** | ❌ report is 78% noise |
| Passes that verify **nothing** | **~10 of 25** | ❌ worse than noise — manufactured confidence |
| Failures with `Available Elements: []` | **20 of 23** | ❌ diagnostics cannot help the user |
| Self-healing outcome | fixed **0**, ~1 hour, twice through the suite | ❌ was a no-op |
| Suite wall-clock | **673–1002s** | ❌ a 50-test suite is 15+ minutes |
| Per evidence step | **~5s** (full-page shot + lossless WebP) | ❌ dominates everything |

**Plain reading:** the tool decomposes a story correctly, then resolves the elements badly,
then reports the result untrustworthily, then fails to repair it, then takes a long time doing
so. Nothing in that chain is a small bug; each one is a specific, fixable defect with a
reproducer.

---

## 2. Part A — Generator improvements (ordered)

### A1. The selector builders emit selectors that match nothing — **do this first**

Two defects in `src/scraper.py`, both producing a selector that matches **zero** elements.

- **Tailwind variant classes are mangled.** `hover:text-amber-200` becomes `.hover` (a class
  that does not exist). Seen in the wild as `.hover`, `.sm`, `.md`, `.text-` fragments.
  **12 of the 23 failures** are this.
- **`a[href]` loses its host.** `https://github.com/…` becomes `a[href="/tancat-ai/…"]`, which
  never matches an attribute. **3 of the 23 failures** — and all three links return HTTP 200,
  so the tests are red for links that work.

Together: **15 of 23 failures are one defect.** Fixing this is the single highest-value change
available.

→ **B-065**. Expected outcome: the reds drop from 23 to roughly 8.

### A2. Stop reporting green for things that were never checked — **the most dangerous item**

When the resolver cannot find a real match it falls back to an element that IS present, the
assertion passes, and the test reports success for a condition it never examined.
**17 different assertions across 17 tests all target `#contact`** — for "How It Works heading",
"first header nav link scrolls to section", "meta description tag", "Open Graph tags", "privacy
policy link" and "every image has alt text". About **10 of the 25 passes are meaningless**.

The run reports ✅ for the broken noir image, the `TBD` purchase links, the missing meta
description, and the missing privacy/terms links.

→ **B-069**. Two parts: (a) mark fallback-resolved assertions `unverified` and emit an honest
`pytest.skip` rather than a passing assert; (b) for attribute conditions ("href does not contain
TBD", "href is a live video") the emitted check must read the attribute — not assert that a
container is visible.

Note the irony and the lesson: this is the same failure mode the landing page has. Green that
means nothing is worse than red.

### A3. Self-healing cannot work as wired (partly fixed, partly not)

- **Fixed this session (B-067):** `_extract_test_function` matched the raw pytest node id, so
  `test_x[chromium]` never matched `def test_x(…)`. **Every** extraction failed, the reviewer
  was never called, and self-healing fixed nothing while still running the suite twice. This is
  the "it failed and took ages" report.
- **Still broken (B-068):** now that the reviewer IS called, it is given **no page elements** —
  the UI builds `SelfHealingRunner(max_iterations=3)` with no `scraped_data`, and
  `classify_failure` always sets `failure_url=None`. The model says so itself and declines:

  > *"Since no scraped page elements are available … this cannot be fixed automatically."*
  > → `fixable: false, confidence: 0.2`

  The element records already exist in `scrape_manifest.json`. They are simply never passed in.
- **Still wasteful (B-070):** when it applies nothing it still runs the full suite again — ~22
  minutes of no-op on a 48-test package.

→ **B-068 + B-070**. Until B-068 lands, the self-healing claim on the landing page is not true.

### A4. Story → criteria: well-formed input still loses tests

- A **prose** story with no numbered criteria collapses to **exactly one test** — the guard that
  should route it to the LLM splitter only matches quantity words (`maximum`, `at least`,
  `limit`, `how many`). → **B-062**
- Numbered criteria with **group headings** are truncated at the first heading: 35 criteria → 5.
  The parser breaks on the first non-numbered, non-empty line. → **B-063**

Both present identically to the user: "my story produced far fewer tests than it describes".
These matter commercially, because the customer's first action is to paste a story.

### A5. Suite cost — make a 50-test suite finish in minutes, not a quarter hour

The per-step evidence capture is ~5s, dominated by a **full-page screenshot + lossless WebP
re-encode of a 6533px page**. `method=2` bought ~30% (B-064). The remaining lever is the capture
itself: bound the page height, capture the viewport for passing steps, or take full-page
evidence only on failure.

Careful: this trades evidence completeness for speed, so it is a **product decision** — raise it
with the user, do not implement unilaterally.

→ Follow-on to **B-064**.

### A6. Smaller but real

- **B-071** — Streamlit watcher spams `ModuleNotFoundError: torchvision` tracebacks. The existing
  `folderWatchBlacklist` cannot work (the noise is module introspection, not folder scanning).
- **B-066** — a bare `uv sync` / `uv run` uninstalls the optional extras, making the local suite
  red for no product reason. Docs corrected; the pre-commit hooks still strip them.
- **B-061** — `eval_harness --regenerate` reports `Tests executed: 0` two different ways.
- The eval harness's `false_positive_rate` does **not** catch any of the A2 class: it only counts
  ASSERT placeholders that miss a hand-written golden key, so it reads zero when a test diverges
  but still passes.

---

## 3. Part B — tancat.dev improvements (ordered)

Full audit with evidence is in the session notes. Split into "cannot sell without it" and
"expected on a page like this".

### B1. Cannot sell without these

| # | Problem | Evidence |
|---|---|---|
| 1 | **You cannot take money.** Both purchase buttons point at `lemonsqueezy.com/l/TANCAT-PRO-TBD` and `-AIRGAP-TBD` | a buyer clicking "Buy Pro" gets a dead page |
| 2 | **The demo does not exist.** "Watch 3-Min Walkthrough" (hero *and* footer) is `loom.com/share/YOUR_VIDEO_ID_HERE` | the page promises a 3-minute demo |
| 3 | **No privacy policy and no terms**, while collecting an e-mail address and selling licences | EU/GDPR expectation; no link anywhere, not even the footer |
| 4 | **No `meta description`, no Open Graph, no canonical, no favicon** | sharing the link on LinkedIn/Slack produces a bare URL; `favicon.ico` 404s |

### B2. Broken or weak

| # | Problem |
|---|---|
| 5 | **Noir Art image is a remote Google URL returning 403** — the hero panel renders blank |
| 6 | **No demo/docs path for a buyer** — the only routes are GitHub and an in-page anchor |
| 7 | **No FAQ** — air-gapped install, which LLM, how evidence is exported, what the licence covers |
| 8 | **Zero `<form>` elements** — interest capture is one `mailto:` link |
| 9 | **No social proof at all** — no testimonials, logos or case study, on a page aimed at regulated buyers |
| 10 | **No support route** — no issues link, no stated response time beyond a blurb |
| 11 | **No `robots.txt`, no `sitemap.xml`** |
| 12 | **No social links** (GitHub only; no LinkedIn, where these buyers are) |

### B3. Decisions, not bugs

- **Competitor prices printed on the page as "anchors"** ("Anchor: testRigor $450/mo Pro; Mabl
  $499/mo", "QA Wolf $8k/mo+, $90k median ACV"). They read like internal notes, they drift, and
  they invite comparison shopping. Deliberate per the changelog — but they need an owner and a
  review date.
- **Pricing is a range with a tilde** ("~$299-499"), so the Buy buttons can never be fixed-price
  checkout links.
- **"© TanCat"** with no legal entity (not incorporated) — already known.
- The 3-minute duration is stated for a video that does not exist.

### B4. Verified fine — do not "fix" these

All real external links are live (repo, `SECURITY.md`, `LICENSE`, `egress-audit.md`, `tancat.dev`
→ all 200). The licence claim matches the file (genuinely Apache-2.0). Every image has alt text.
One H1, sensible H2/H3 nesting. All 7 in-page anchors resolve. `lang` and viewport meta present.
Mobile is fine at 375px — `scrollWidth` reports 376 vs 375 but the page cannot scroll sideways;
a rounding artefact, not a defect (checked, not assumed).

---

## 4. Part C — Commerciality: is this worth money?

### The blunt version of the question

*"It looks like it might not be worth any money — it seems no better than just using an LLM with
Playwright."* That is the right question to ask, and the honest answer today is:

> **As it stands, no. Not because the idea is wrong, but because the output cannot be trusted.**
> A QA lead would discover that in week one, and the discovery would be fatal to the sale.

### What the product claims vs what it does

| Claim on the site | Reality after this session |
|---|---|
| "Paste a user story → get executable Playwright pytest tests with real DOM selectors" | It does generate them — and 18 of 23 reported failures are our own bad selectors |
| Implied: the tests are trustworthy | ~10 of 25 passes check nothing; the run reports ✅ for a broken image and dead purchase links |
| Self-healing locators | Was a **complete no-op**; even repaired, the reviewer is given no element data |
| Audit-grade evidence bundles | The evidence *capture* works; the *verdict* it carries does not. Evidence of an untrustworthy run is not evidence |
| Bounded egress / air-gap | **True and verifiable in CI.** The strongest asset on the page |
| Per-deployment pricing, no per-seat | True, and a genuine differentiator against per-seat SaaS |

### Why "just use an LLM + Playwright" is a real threat

Because for the *happy path* it wins: an engineer with Claude/Cursor writes a comparable test in
minutes, and — crucially — **they know which of their tests are meaningful**. They get no
evidence bundle, no traceability, no air-gap story, and no reuse across a suite. But at the
"generate me a test" level, the commodity already does the job.

So the product cannot charge for "generate Playwright from English". That is now table stakes.

### What is actually defensible

Three things that are hard to replicate by hand, and that fit a specific buyer:

1. **Honest verification.** No false greens, every pass provably checked its condition, every
   skip carrying a reason. If the tool can say "these 40 tests genuinely passed, these 6 are
   unverified, here is why", that is worth paying for — and it is exactly what an LLM one-shot
   cannot give you.
2. **Evidence and traceability.** Per-step screenshots, per-step URL, HTML/Jira reports, role-based
   views, JUnit/CSV — for teams who have to *prove* testing happened. This is the audit buyer.
3. **Runs entirely inside the customer's environment**, with a bounded-egress claim verified in
   CI. For banking/healthcare/defence, this removes a procurement blocker that no cloud SaaS can
   remove.

The buyer is therefore **the regulated engineering team that must show its working**, not "anyone
who wants tests fast". That buyer will not accept a run that reports noise, and will pay well for
one that does not.

### The gates that must pass before this is sellable

Measure on a **held-out** story set, live regeneration, not frozen captures:

| # | Gate | Today |
|---|---|---|
| 1 | Live resolution accuracy ≥ 90% on a held-out set | ~50% on a plain static page (eval static's 97.9% measures frozen captures, not regeneration) |
| 2 | **Zero** false greens — every passing test provably checked its condition | ~10 false greens on one 48-test run |
| 3 | Self-healing fixes ≥ 30% of locator failures, with element context | 0% |
| 4 | A prose story yields the criteria a human would list; headings never truncate | 1 test from prose; 35→5 with headings |
| 5 | A 50-test suite completes in ≤ 5 minutes | 673–1002s |
| 6 | A stranger can buy from the site | cannot — Buy links are `TBD` |

### Recommendation

**Spend the next 4–5 sessions on trust, then re-measure.** Items A1 and A2 alone should move
gates 1 and 2 materially. If gates 1–2 pass on a held-out set, the air-gap/evidence positioning is
sellable to a real niche. If they do not, the honest pivot is to sell the **evidence and
traceability layer** ("prove your testing happened, entirely inside your network") rather than
"AI generates your tests" — the same code, a claim that the current engine can actually support.

### What NOT to build right now

- **No new features** until gates 1 and 2 pass. Every feature added now is built on a base whose
  output cannot be trusted.
- **Do not chase competitor feature parity.** Feature lists are not the gap; trust is.
- **Do not polish the landing page as if it were launch-ready.** Fix the six blockers in B1, then
  leave it alone.
- **Do not market self-healing** until B-068 lands and it demonstrably fixes something.

---

## 5. Session plan (suggested order)

| Session | Do | Why now | Done when |
|---|---|---|---|
| 1 | **B-065** — fix the two selector builders (Tailwind variants, href host) | removes 15 of 23 reds in one change | landing-page run reds ≈ 8 |
| 2 | **B-069** — stop false greens (unverified → honest skip; attribute asserts read attributes) | the green/red signal becomes truthful | 0 false greens on the same run |
| 3 | **B-068 + B-070** — give the reviewer element context; stop the no-op re-run | makes the self-healing claim true | self-heal fixes ≥ 1 real locator failure; no-op self-heal < 5 min |
| 4 | **B-062 + B-063** — story→criteria (prose, headings) | the customer's first action | prose story yields > 1 test; headed list keeps all criteria |
| 5 | Evidence cost (A5) + **B-061/B-066/B-071** cleanups | a 50-test suite in ≤ 5 min | suite ≤ 5 min |
| 6 | **tancat.dev B1** — privacy/terms, meta+OG+favicon, noir image, real Buy + demo links | cannot sell without it | a stranger can buy and watch the demo |
| 7 | **Re-measure** against the Part C gates and decide the positioning | the commercial decision | gates 1–6 recorded in the appendix |

If only one session happens, do **Session 1**.

---

## 6. Appendix A — measurement log

Record one row per session so drift is visible. All numbers from live regeneration unless noted.

| Date | Run | Resolution | False greens | Failures | Suite time | Notes |
|---|---|---|---|---|---|---|
| 2026-09-15 | 35-criterion landing-page story, 48 tests, local page | — (not measured on this run) | ~10 of 25 passes | 23 (18 ours, 5 real) | 673–1002s | baseline for this plan |
| 2026-09-15 | eval harness static (frozen captures) | 97.9% | 0 | — | <1s | **not** a live-regeneration measure |
| 2026-09-17 | **B-065 fix** — same story re-generated (35 tests), local page | — | **12 of 31 passes** (B-069 class unchanged) | 4 — **all** `target="_blank"` nav checks (B-072, new item); **0 selector failures** | 437s | Session 1 done: B-065's 18 selector reds → 0. All 4 remaining reds are the new new-tab class; the page's real defects are hidden by the 12 false greens → Session 2 (B-069) unblocks honest reporting. Re-run hit a 2h server-wedge detour (agent + pipeline share one llama.cpp slot) — see `docs/sessions/2026-09-16_b065_rerun_llm_stall.md` |

---

## 7. Appendix B — BACKLOG references

| Id | Item | Status at time of writing |
|---|---|---|
| B-062 | Prose story collapses to one test | open |
| B-063 | Numbered criteria truncated at the first heading | open |
| B-064 | Flat 600s pytest ceiling killed healthy suites | ✅ fixed |
| B-065 | Selector builders emit unmatchable selectors (Tailwind variants, href host) | ✅ fixed 2026-09-17 (re-run verified; ship pending) |
| B-066 | Bare `uv sync` / `uv run` strips optional extras | open |
| B-067 | Self-healing no-op on `[chromium]` node ids | ✅ fixed |
| B-068 | Self-heal reviewer given no page elements | open |
| B-069 | False passes — 17 tests assert the same element | open |
| B-070 | Self-heal re-runs the whole suite when it fixes nothing | open |
| B-071 | Streamlit watcher `torchvision` traceback spam | open |
| B-072 | `target="_blank"` link tests fail post-click navigation check | open — found 2026-09-17 by the B-065 re-run |
| B-060 / B-061 | Mock page scoping / eval-harness `Tests executed: 0` | fixed / open |

---

*Written 2026-09-15. Status of every item above lives in `BACKLOG.md` — this document points at
it, and does not restate status.*
