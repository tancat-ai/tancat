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
| 1 | Live resolution accuracy ≥ 90% on a held-out set | **≈74% — FAIL** (measured 2026-09-24, Session 7: 7 wrong-element mappings + 1 emitter bug out of 34 tests) |
| 2 | **Zero** false greens — every passing test provably checked its condition | **FAIL — ≥2 found** (2026-09-24: `tc01_30` canonical "passed" by asserting visibility of a div; `tc01_27` asserted two headings rather than a contact link). B-069(a+b) fixed the *false-green-by-fallback* class; this is a different one — head/attribute criteria silently weakened. Detail: `docs/sessions/2026-09-24_session7_re_measure.md` |
| 3 | Self-healing fixes ≥ 30% of locator failures, with element context | **UNMEASURABLE on the 09-24 package — 0/8 fixed, 0 LLM calls** (2026-09-24). B-068 + B-070 verified working in production (reviewer gets real element context; the no-op re-run is gone), and the pre-screen correctly declined all 8 reds because they are **assertion** failures, not locator failures. A real measurement needs deliberate DOM mutation to produce `LOCATOR_TIMEOUT`s — method recorded in `docs/sessions/2026-09-24_session7_re_measure.md` §4b/§7 |
| 4 | A prose story yields the criteria a human would list; headings never truncate | fixed 2026-09-21 (B-062 + B-063) — 35/35 with headings, prose routed to the splitter |
| 5 | A 50-test suite completes in ≤ 5 minutes | **≈5.2 min projected — BORDERLINE** (2026-09-24: 34 tests in 210s = 6.2s/test; was 673–1002s baseline, 437s on the 09-17 re-run) |
| 6 | A stranger can buy from the site | **NO** — the site now routes to "Request licence"; real checkout is parked on the licence-key mapping |

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
| 1 | **B-065** — fix the two selector builders (Tailwind variants, href host) | removes 15 of 23 reds in one change | ✅ done 2026-09-17, shipped 09-18 — 0 selector reds on re-run |
| 2 | **B-069** — stop false greens (unverified → honest skip; attribute asserts read attributes) | the green/red signal becomes truthful | ✅ done 2026-09-19 (a+b) — 09-17 false-green classes verified red on live replay |
| 3 | **B-068 + B-070** — give the reviewer element context; stop the no-op re-run | makes the self-healing claim true | ✅ done 2026-09-20 — reviewer gets the scrape manifest; no-op heals stop re-running (fix-rate still to measure, session 7) |
| 4 | **B-062 + B-063** — story→criteria (prose, headings) | the customer's first action | ✅ done 2026-09-21 — 35/35 with headings; prose routed to the splitter |
| 4b | **B-072** — `target="_blank"` clicks false-fail; resolve/404 criteria click at all | the last selector-adjacent red class (4/4 remaining reds on the 09-17 re-run) | ✅ done 2026-09-21 — new-tab clicks detected/verified/closed; resolve criteria read the href (live replay 8/8) |
| 5 | Evidence cost (A5) + **B-061/B-066/B-071** cleanups | a 50-test suite in ≤ 5 min | ✅ done 2026-09-21 — encode was 87% of step cost; `method=0` + keep-PNG-if-no-shrink + per-page probe cache; live 10-test A/B 163.6s → 57.8s (≈4.8 min projected at 50; the full live 50-test re-measure lands in session 7) |
| 6 | **tancat.dev B1** — privacy/terms, meta+OG+favicon, noir image, real Buy + demo links | cannot sell without it | a stranger can buy and watch the demo |
| 7 | **Re-measure** against the Part C gates and decide the positioning | the commercial decision | ✅ done 2026-09-24 — gates 1–6 recorded in the appendix; **gates 1 and 2 FAIL** (≈74% resolution, ≥2 false greens), gate 5 borderline, gate 3 still unmeasured. Record: `docs/sessions/2026-09-24_session7_re_measure.md` |
| 8 | **B-086** — head/attribute criteria must resolve honestly or skip, never emit a weakened `assert_visible` | it is the only thing left between us and gates 1–2 | ✅ done 2026-09-24 — document-level assertion family added (`_DOCUMENT_TARGETS` + intercept in the emit chokepoint); 22 unit tests; live replay 5/5 pass present, 5/5 correctly FAIL when the tags are removed; 3330 pytest. **Closes the head class only** — criteria 28/29/30/31 |
| 8b | **B-087** — `must_be_url` must not apply to a `mailto:` criterion | a false red, 0.25 sessions | `document_assertion`-style scheme vocabulary in `attribute_predicate` |
| 8c | **B-088** — page-level and section-scoped criteria still resolve to a visible lookalike | the remaining blocker for gates 1–2: 4 reds (16, 22, 24, 27-in-part) + 1 false green (27) | those criteria resolve to the right element or emit an honest skip |

Sessions 1–5 are done, and Session 7's re-measure ran on 2026-09-24. Session 6 (tancat.dev B1) is **partly** done: the meta/OG/favicon, privacy/terms, robots/sitemap and the pricing-card corrections are committed on `feat/landing-b1-trust-blockers`, and the privacy/terms links were verified live by the Session 7 run. Still blocked there: the Noir Art image (needs the source file), the demo video (record after the gates pass), and the real checkout (needs the Lemon Squeezy key mapping).

**Next: gate 1's wrong-element resolver class — then the trust surface.** Session 13 (2026-09-25)
re-scored gate 2 and found the "16" was a metric artefact: the honest number is **3**, all `eval-006`,
and all one defect — the resolver answered the cart-page, checkout-page and order-success criteria with
`#place-order` (a button that exists only on `checkout.html`). The same family shows up in the unverified
list: `main:has-text("Your Accounts …")` for account balances, `#transfer-error` for a **success** message,
`.text` for a form title, and criteria with **no assertion emitted at all**. Gate 1 is **82/113 (72.6%)**
strict against the golden (Session 12's 86/113 was a different LLM draw — same code, ±3–5 placeholders of
LLM variance; the re-score is reproducible via `scratch/rescore.py`, execution only, no LLM). Do **not**
re-tune on the landing page. Open items: **B-097** (per-test `pytest.skip` granularity — one unresolved
placeholder still hides every resolved step), **B-100** (let the product report its own verification
strength instead of the harness guessing), **B-101** (golden-quality audit — several goldens expect the
weaker check). **Watch:** the LLM server's 600s generation timeouts killed 4 of 9 stories in one pass under
load; the harness now flags that loudly (exit 3) rather than scoring the partial run.
Records: `docs/sessions/2026-09-24_session10_heldout_gates.md`,
`..._session11_b054_spa_pool.md`, `docs/sessions/2026-09-25_b095_b096_pass1_twins.md`.

---

## 6. Appendix A — measurement log

Record one row per session so drift is visible. All numbers from live regeneration unless noted.

| Date | Run | Resolution | False greens | Failures | Suite time | Notes |
|---|---|---|---|---|---|---|
| 2026-09-15 | 35-criterion landing-page story, 48 tests, local page | — (not measured on this run) | ~10 of 25 passes | 23 (18 ours, 5 real) | 673–1002s | baseline for this plan |
| 2026-09-15 | eval harness static (frozen captures) | 97.9% | 0 | — | <1s | **not** a live-regeneration measure |
| 2026-09-17 | **B-065 fix** — same story re-generated (35 tests), local page | — | **12 of 31 passes** (B-069 class unchanged) | 4 — **all** `target="_blank"` nav checks (B-072, new item); **0 selector failures** | 437s | Session 1 done: B-065's 18 selector reds → 0. All 4 remaining reds are the new new-tab class; the page's real defects are hidden by the 12 false greens → Session 2 (B-069) unblocks honest reporting. Re-run hit a 2h server-wedge detour (agent + pipeline share one llama.cpp slot) — see `docs/sessions/2026-09-16_b065_rerun_llm_stall.md` |
| 2026-09-19 | **B-069 (a+b) shipped** — 14-criterion story via `ci_generate.py` BLOCKED (27B stalled ×2 on the skeleton prompt, 600s timeouts); live replay of the **exact emitted calls** on the real landing page instead | — (no fresh live regeneration) | **0 of the 09-17 false-green classes remain green** — TBD purchase hrefs ×2, `YOUR_VIDEO_ID_HERE` video ×2, "no TBD in links", "all anchor links valid" (4/24 placeholder hrefs) all now FAIL with precise diagnostics | TBD/placeholder criteria red (honest) | n/a | Session 2 done (a+b): `attribute_predicate` + `count_assertion_from_description` + `assert_no_forbidden`/`assert_attribute_all`; 48 tests, 3198 pytest, smoke 39/39, eval static 97.9%. Full-LLM re-run pending a healthy model — story saved at `scratch/b069b_story.md` |
| 2026-09-20 | **B-068 + B-070 shipped** — self-heal reviewer now loads `scrape_manifest.json` element context; no-op heals stop re-running the suite | — | — | — | — | Session 3 done: wiring verified against real manifest data (`scratch/verify_b068_real_data.py`); the ≥30% fix-rate gate is a MEASUREMENT — recorded for session 7 |
| 2026-09-21 | **B-062 + B-063 shipped** — prose story no longer collapses to one test; headed criteria no longer truncate (35/35, deterministic, zero LLM calls) | — | — | — | — | Session 4 done: +5 tests, e2e replays in `scratch/verify_b062_e2e.py` / `verify_b063_e2e.py`; 3295 pytest, eval static 97.9% |
| 2026-09-21 | **B-072 shipped** — live replay of the 09-17 red class against the real landing page (`scratch/verify_b072_live.py`, self-hosted) | — (no fresh live regeneration) | 0 — TBD/placeholder criteria still red | **0 selector-adjacent reds** — the 4 reds (tc01_20..23) pass via the href check; the `_blank` GitHub click itself detected, verified (`matched_href=True`), recorded, closed | n/a | Session 4b done: 8/8 live cases, +11 unit tests, 3306 pytest, smoke 39/39, eval static 97.9%. Environment finding: headless Chromium 151 creates new tabs up to ~8s after the click (`scratch/probe_delay*.py`) — observation windows sized to that; a stray-tab cleanup rides on `navigate()` |
| 2026-09-21 | **Session 5 shipped** — A5 (evidence encode) + B-061/B-066/B-071; live 10-test A/B on the real landing page (`scratch/a5_gate_suite`, file://, old vs new encoder, same tests) | — (not a regeneration run) | 0 (B-069 state unchanged) | 0 — 10/10 pass on both encoder versions | 163.6s → **57.8s** (≈13.6 → ≈4.8 min projected at 50) | A5: the lossless WebP `method=2` re-encode was ~2.3s of the ~2.7s per step (screenshot itself ~0.3s); now `method=0` + keep-PNG-when-WebP-would-not-shrink + per-page probe cache — both formats lossless, extension follows content, all MIME maps handle both. B-061 (conftest copy + 700s timeout + TIMED OUT report), B-066 (`uv run --all-extras` hooks), B-071 (watcher off). Watch item **B-078** opened: re-measure the encoder when Pillow/Chromium ship better lossless options (`scratch/bench_evidence_real.py`). Gates: 3309 pytest, smoke 39/39, ruff + mypy clean, eval static 97.9% |
| 2026-09-24 | **Session 7 — the re-measure**: 35-criterion landing story, live regeneration, local serve of the **post-Session-6** page (`test_20260924_002444_*`) | **≈74% — FAIL** against the ≥90% gate (7 wrong-element mappings + 1 emitter bug of 34 tests) | **FAIL — ≥2 false greens**: `tc01_30` (canonical URL) passed by asserting visibility of a styled div; `tc01_27` (Air-Gap contact link) asserted two headings. `tc01_29`'s OG-image half uses the same weakened pattern | **8 failed / 26 passed** — 7 of the 8 reds are OURS (6 wrong-element resolutions + 1 emitter bug); the 8th (`tc01_13`) is a criterion that no longer matches the page by design. **0 page defects** | **210s for 34 tests** (6.2s/test → ≈5.2 min projected at 50; was 673–1002s baseline, 437s on 09-17) | Session 6 fixed the *page* (privacy/terms links and the contact section verified live by real assertions); Session 7 shows the *generator* is now the whole problem. One root cause: the resolver has no concept of `<head>`/attribute-only criteria, so it falls back to a visible element and the assertion is weakened to match. Generation 3356s / 63 LLM calls. Self-healing not exercised (gate 3 still unmeasured). 35 criteria → **34** tests (one lost). Environment note: two accidental `ci_generate` runs + three HTTP servers shared the single :8080 slot — a one-line probe went 1m52s → 2.1s after cleanup; the scratch harness's 10× retry absorbed the agent-shares-the-slot problem (zero wedges in 56 min). Full record: `docs/sessions/2026-09-24_session7_re_measure.md`. New items: **B-086** (head/attribute criteria → honest resolution or skip, never a weakened assert), **B-087** (`must_be_url` misapplied to a mailto criterion) |
| 2026-09-24 | **Session 10 — the held-out gate re-measure**: 9 committed golden stories (6 sites, 62 conditions, 113 placeholders), live regeneration + scrape + pytest, worktree @ b11ee8f, thinking=off | **75/113 = 66.4% — FAIL** (gate 1 ≥90). Best: automationexercise 100%, demoqa 88%, theinternet 86%. Worst: lv_insurance **38%**, ambiguous_mock 50%, banking_mock 54/77%, ecommerce_mock 69%, saucedemo 75% | **FAIL — 16 wrong-ASSERT-locator passes of 49** (gate 2 = 0). Example: theinternet `tc04` "accept JS alert" checks `#content` (page container, always visible) | 14 of 63 red / 77.8% pass | ~44 min total (regeneration 28 min, execution 16 min) | **The Session 7 landing-page result did not generalize.** 36 of the 38 misses are on the stateful/auth-gated stories → B-054/B-055/AI-064. Also found a harness defect: two stories on one site overwrite each other's test file (**B-094**). Dead ends recorded: `eval_resolver --mode live` (no login) = 15.9%; `eval_resolver --mode static` is a RAG benchmark (35.4% RAG-off), not the gate. Full record: `docs/sessions/2026-09-24_session10_heldout_gates.md`. New items: **B-093** (gate fail), **B-094** (harness collision) |
| 2026-09-24 | **Session 11 — B-054 fix**: multi-step SPA candidate-pool defect. `rank_candidates` hard-dropped `is_visible is False` elements for non-ASSERT actions, so later-step fields never entered the pool; `IntentMatcher._is_fillable` omitted `date`/`time`/`spinbutton`. Fixed both. Live re-run of **lv_insurance** (`eval-005`), same story/llm | **9/24 (38%) → 16/24 (67%)** on lv_insurance (worst story) | 0 false greens on the re-run | tests still 0/10 passed — one unresolved placeholder skips the whole test (B-096) | ~5 min generation + suite | The backlog's stated B-054 mechanism ("one text block") was not the held-out cause — the elements ARE captured; two filters threw them away. Residual = pass-1 first-match + `main*`/`addDriver*` ambiguity → B-096. **Gate 1 re-scored: 75/113 (66.4%) → 82/113 (72.6%)**; the entire gain is lv_insurance (9/24 → 16/24), every other story identical. Still FAIL (≥90); gate 2 unchanged at 16 false greens. Gates: 3440 pytest / 1 skipped, smoke 39/39, eval static 97.9%, ruff + mypy clean. Record: `docs/sessions/2026-09-24_session11_b054_spa_pool.md` |
| 2026-09-25 | **Session 13 — gate 2 re-scored, and the harness bug that was hiding the metric**: re-executed the two half-run emissions (`scratch/rescore3.log`; execution only, no LLM, so it is reproducible) | **82/113 (72.6%)** — strict vs the golden, metric unchanged | **3** (not 16) — all `eval-006` | 35/62 passed | ~13 min (execution only) | The metric was asking "did the test use the golden's selector?" — it now asks "did this criterion's own test prove the claim?" (verified by the golden answer, a distinctively-named element, or — for page criteria — a URL assertion on the criterion's page; a **global container never verifies**; outcome polarity enforced). The goldens are the *weaker* test in places: `[data-test="title"]` is saucedemo's shared page header, and `[data-test="cart-list-container"]` proves a list exists where the generated test asserted the backpack itself. **Harness bug:** `pytest.ini` enables `-n 4`, and under xdist the outcome prints *before* the node id, so the console parse returned `{}` and **every run this session reported 0 false greens** — outcomes now come from `--junitxml` with a loud conservative fallback. Verification split: golden 14 · distinctive element 2 · page arrival 6 · unverified 15. Also fixed: page-mismatch now fails the step, partial-run detection (exit 3), the harness's `.env`, the `ollama` default, and the 120s-vs-700s `pytest_timeout` default. The 3 are one defect: the resolver answered cart-page / checkout-page / order-success with `#place-order` (exists only on `checkout.html`). |
| 2026-09-25 | **Session 12 — B-095 + B-096**: worktree measurement integrity + Pass-1 same-page twins. **B-095** the eval harness never `sys.path.insert`ed the checkout, so a worktree run silently imported main's `src`; both entry points now do. **B-096** found the real mechanism was not scrape order: the required fields carry `text="Years Licensed *"` while the optional `addDriver*` twins do not, and the scraper records `accessible_name="*"` for the required fields — `normalise_element_text` trusted that marker and never saw the label. Fixed marker stripping + source fallback, Pass-1 candidate collection with a deterministic scorer tie-break, and word-boundary single-word phrases (`license` was matching `licensed` and was blocked from `Driving License Number` by ratio `== 3`). Live lv re-run | **16/24 (67%) → 19/24 (79%)** on lv_insurance | 0 false positives | tests still 0/10 — per-test skip granularity is the open sub-item | ~5.5 min generation + suite | Deterministic repro from the **exact live pool** (`scratch/b096_live_pool.json`) — the pipeline's emit-time descriptions differ from the goldens, so the static sweep and the journey log both mislead. Also **B-094 fixed** (per-story test filenames; `eval_runs` already keys on `story_id`, no schema change). **Full held-out re-run (all 9 stories): 82/113 → 86/113 (76.1%)** — six sites byte-identical, gain = lv +3 and ecommerce +1; gate 2 unchanged at 16 false greens; tests 43/62 (the old 63 was the duplicated banking execution). Still FAIL on both gates. Gates: 3454 pytest / 1 skipped, smoke 39/39, eval static 97.9% (0.0pp drift), ruff + mypy clean. Records: `docs/sessions/2026-09-25_b095_b096_pass1_twins.md` |

---

## 8. Part D — AXI.md research (2026-09-18)

> **Source:** https://axi.md/ — *AXI: Agent eXperience Interface*, 10 design principles for agent-ergonomic CLI.
> **Benchmark:** 490 browser runs + 425 GitHub runs. AXI achieves **100% task success at $0.074/task, 21.5s, 4.5 turns** — the only condition leading on all four metrics.
> **Key finding:** A principled CLI beats both raw CLI and MCP. MCP uses 2.3× more input tokens (185K vs 79K per task). The gap is not protocol choice — it is design.

### D1. The 10 AXI principles (condensed)

| # | Principle | One-line |
|---|-----------|----------|
| 1 | Token-efficient output | TOON format → ~40% savings vs JSON |
| 2 | Minimal default schemas | 3–4 fields per item, not 10+ |
| 3 | Content truncation | Truncate with size hints + `--full` escape hatch |
| 4 | Pre-computed aggregates | Include `totalCount`, CI summaries inline |
| 5 | Definitive empty states | Explicit "0 results", never ambiguous empty |
| 6 | Structured errors & exit codes | Idempotent mutations, no prompts, fail loud on unknown flags |
| 7 | Ambient context | Session hooks/skills load relevant state before the agent acts |
| 8 | Content first | No args → live data, not help text |
| 9 | Contextual disclosure | Next-step suggestions after each output |
| 10 | Consistent help | Concise `--help` per subcommand |

### D2. Direct opportunities for TanCat

**A. Extend the eval harness with AXI-style metrics** — → **B-073**

Today the harness tracks only resolution accuracy. AXI benchmarked cost, duration, and turns. We should add:
- **Cost per task:** token count per story→test generation (equivalent to AXI's $/task)
- **Success rate:** resolution accuracy per story type (not just overall)
- **Duration:** wall-clock per criterion count
- **Turns:** LLM calls per story decomposition

This gives us a commercial story: AXI proved CLI beats MCP at lower cost — we can prove our tool beats raw LLM+Playwright at lower cost per test.

**B. Make `tancat` CLI AXI-compliant** — → **B-074**

| Principle | Current gap | Action |
|-----------|-------------|--------|
| 8 (Content first) | Bare `tancat` shows help, not live state | Show last-run status on bare invocation |
| 5 (Definitive empty states) | Empty test runs can be ambiguous | Always show explicit counts: "0 tests generated", "0 failures" |
| 9 (Contextual disclosure) | No next-step suggestions after generation | Suggest: "run pytest --generated", "review evidence", "self-heal" |
| 10 (Help) | CLI help may be verbose per subcommand | Add concise `--help` per subcommand |
| 2 (Minimal schemas) | Evidence sidecars carry excess data | Provide `--fields` / `--compact` option on evidence output |
| 4 (Pre-computed aggregates) | Reports lack totals upfront | Add summary line: `Tests: 48 (43 passed, 3 failed, 2 unverified)` |

**C. Agent-to-agent pipeline (longer term)** — → **B-075**

| Principle | Application | Action |
|-----------|-------------|--------|
| 6 (Structured errors) | Pipeline errors opaque between Planner→Generator→Validator | Standardise error codes |
| 2 (Minimal schemas) | Inter-agent messages carry full context | Pass only required fields between stages |
| 7 (Ambient context) | No session-wide state at start | Expose `tancat` as MCP server: `generate_test(story=...)`, `self_heal(test_path=...)` |

### D3. AXI lens on existing backlog items

| Backlog | AXI Principle | Connection |
|---------|--------------|------------|
| B-069 (False greens) | 5 (Definitive empty states) | False greens = ambiguous "success" — make passing definitive |
| B-068 (Self-heal no data) | 4 (Pre-computed aggregates) | Scrape manifest is pre-computed data not being passed in |
| B-065 (Selector builders) | 2 (Minimal schemas) | Correct minimal selectors vs over-fetching |
| B-062/B-063 (Parsing) | 3 (Content truncation) | Stories with headings = un-truncated context needed |
| B-071 (Streamlit spam) | 6 (Structured errors) | Torchvision noise = unstructured error output |

### D4. Recommendation

AXI validates that principled CLI design beats both raw CLI and MCP. Our product is a CLI+UI that generates tests for agents (and for humans). The biggest takeaways:

1. **Measure cost-per-task like AXI did** — extend eval harness with token/cost metrics (B-073)
2. **Apply AXI principles to `tancat` CLI** — content-first, definitive states, contextual help (B-074)
3. **Fix B-069/B-068 through AXI lens** — definitive pass/fail, pre-computed context
4. **Consider MCP server** — ambient context principle (B-075, longer term)

---

## 7. Appendix B — BACKLOG references

| Id | Item | Status at time of writing |
|---|---|---|
| B-062 | Prose story collapses to one test | ✅ fixed 2026-09-21 |
| B-063 | Numbered criteria truncated at the first heading | ✅ fixed 2026-09-21 |
| B-064 | Flat 600s pytest ceiling killed healthy suites | ✅ fixed |
| B-065 | Selector builders emit unmatchable selectors (Tailwind variants, href host) | ✅ fixed 2026-09-17 (re-run verified; ship pending) |
| B-066 | Bare `uv sync` / `uv run` strips optional extras | open |
| B-067 | Self-healing no-op on `[chromium]` node ids | ✅ fixed |
| B-068 | Self-heal reviewer given no page elements | ✅ fixed 2026-09-20 |
| B-069 | False passes — 17 tests assert the same element | ✅ complete 2026-09-19 (a: f324b39 · b: attribute predicates + page-level count checks; full-LLM re-run pending model health) |
| B-070 | Self-heal re-runs the whole suite when it fixes nothing | ✅ fixed 2026-09-20 |
| B-071 | Streamlit watcher `torchvision` traceback spam | open |
| B-072 | `target="_blank"` link tests fail post-click navigation check | ✅ fixed 2026-09-21 (found 2026-09-17 by the B-065 re-run) |
| B-060 / B-061 | Mock page scoping / eval-harness `Tests executed: 0` | fixed / open |

---

*Written 2026-09-15. Status of every item above lives in `BACKLOG.md` — this document points at
it, and does not restate status.*
