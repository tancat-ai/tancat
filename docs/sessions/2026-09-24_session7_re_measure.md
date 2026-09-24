# Session 7 — the re-measure (record)

**Date:** 2026-09-24 · **Run:** `test_20260924_002444_as_a_prospective_customer_i_want_to_review_the_ta`
**Story:** 35-criterion landing-page story (`scratch/landing_page_story.md`), live regeneration
**Target:** local serve of `landing/` on `:8079` — the **worktree page**, i.e. with the Session 6 fixes
**Runner:** scratch copy of the B-065 re-run harness (no-keepalive httpx + 10× retry with backoff over `LLMClient._complete_sync`)
**Model:** Qwen3.8-27B-UD-Q4_K_XL_v2, LM Studio `:8080`, thinking **on**

---

## 1. Headline

| Measure | Baseline (09-15) | 09-17 re-run | **Session 7 (09-24)** |
|---|---|---|---|
| Criteria → tests | 35 → 48 | 35 → 35 | **35 → 34** |
| Result | 23 failed / 25 passed | 4 failed / 31 passed | **8 failed / 26 passed** |
| Suite wall-clock | 673–1002s | 437s | **210s** |
| Generation wall-clock | — | — | **3356s** (63 LLM calls) |
| Page defects | 5 real | 4 (all new-tab class) | **0** |
| False greens | ~10 | 12 | **≥2** (27, 30) |
| Reds that are ours | 18 of 23 | 4 of 4 | **7 of 8** |

**Plain reading:** Session 6 fixed the page. Session 7 shows the *generator* is now the whole problem —
and it still manufactures green for criteria it never checked.

---

## 2. The 8 reds, classified

| Test | What failed | Class |
|---|---|---|
| `tc01_13_buy_pro_link_resolves` | `href='#contact'` is not an http(s) URL | **stale criterion** — Session 6 deliberately replaced the Buy URLs with a request-a-licence route |
| `tc01_16_watch_3_min_walkthrough…` | matched `a[href="#"]` (the nav logo), not the demo button | resolver wrong element → **false red** |
| `tc01_22_security_policy_link_resolves` | matched a non-anchor `:has-text("Security Policy")`, asserted `href` on it | resolver wrong element → **false red** |
| `tc01_24_no_placeholder_text` | checked `href` on a hero **paragraph** | resolver wrong element + wrong assertion kind → **false red** |
| `tc01_26_hello…_is_mailto_link` | `mailto:hello@tancat.dev` rejected by a *must-be-http(s)* predicate | **emitter bug** |
| `tc01_28` (meta description) | asserted `content` on the hero paragraph | resolver wrong element → **false red** |
| `tc01_29` (OG title/image) | matched an `<li>` about the LLM endpoint | resolver wrong element → **false red** |
| `tc01_31` (favicon) | asserted `href` on a footer div | resolver wrong element → **false red** |

**7 of 8 reds are ours.** Only `tc01_13` is a page/criterion mismatch, and even that one is a criterion
written against a page design we deliberately changed.

---

## 3. False greens (the gate-2 failure)

The assertion the generator emitted, read from the emitted test file:

| Test | Verdict | Emitted assertion | What it actually checked |
|---|---|---|---|
| `tc01_30` canonical URL | **PASSED** | `assert_visible('.border-slate-800/80.border-t.font-mono.mt-6.pt-4.text-[11px].text-amber-400/90')` | visibility of some styled div. A `<link rel="canonical">` lives in `<head>` and is **never** visible, so this cannot test the canonical URL. **False green.** |
| `tc01_27` Air-Gap contact link | **PASSED** | `assert_visible(h3 class blob)` + `assert_visible(h2 'Contact us' class blob)` | that two headings are visible — **not** that a contact link appears inside the Air-Gap tier. **False green.** |
| `tc01_29` OG image (2nd half) | failed on its 1st assert | `assert_visible(':has-text("Local OpenAI-compatible API endpoint…")')` | any visible element containing that text. Trivially satisfiable — the same wrong-element pattern. |

**Genuine passes on the Session 6 work** (these are real, and worth keeping):

- `tc01_32` — `assert_visible('a[href="privacy.html"]')` ✅
- `tc01_33` — `assert_visible('a[href="terms.html"]')` ✅
- `tc01_27`'s headings, 25/26 contact section, 20–23 links: all resolved to real elements.

So the privacy/terms/meta work is live and verified. What the tool cannot do is **check `<head>` and
attribute criteria** — it resolves "meta description tag", "canonical URL", "Open Graph title", "favicon"
onto whatever *visible* element looks textually closest, then asserts something trivially true.

---

## 4. The Part C gates, scored

| # | Gate | Today | Verdict |
|---|---|---|---|
| 1 | Live resolution accuracy ≥ 90% on a held-out set | 7 wrong-element mappings + 1 emitter bug out of 34 → ≈74% | **FAIL** |
| 2 | **Zero** false greens | ≥2 found (27, 30), with 29's second half the same pattern | **FAIL** |
| 3 | Self-healing fixes ≥ 30% of locator failures | **UNMEASURABLE on this package — 0/8 fixed, 0 LLM calls.** All 8 failures were pre-screened as `OTHER`/`ASSERTION_FAILURE` and correctly **not** sent to the reviewer. They are *assertion* failures (the element was found; the expectation did not hold), not locator failures, so the healer has no broken locator to repair. See §4b. A genuine measurement needs a package with `LOCATOR_TIMEOUT` failures — see §7 item 4. |
| 4 | Prose story + headings never truncate | not exercised (pre-written criteria) | **UNCHANGED** (passed Session 4) |
| 5 | 50-test suite ≤ 5 minutes | 34 tests in 210s = 6.2s/test → **≈310s (5.2 min)** at 50 | **BORDERLINE** (was 673–1002s) |
| 6 | A stranger can buy from the site | request-a-licence route only; checkout parked | **NO** |

**Also noted:** 35 criteria produced **34** tests — one criterion was lost or merged. Not investigated.

## 4b. Gate 3 — measured, and the result is "unmeasurable here"

Ran the production call path (`SelfHealingRunner(max_iterations=3).heal(<package dir>)`, exactly as
`src/ui/ui_run_results.py:1110` does) against this package, with the same retry hardening as the
regeneration harness. Result:

| Field | Value |
|---|---|
| total_failures | 8 |
| fixed | **0** |
| unfixable | **8** — every one "Pre-screened as unfixable (other)" |
| **llm_calls** | **0** |
| learned | 0 |
| iterations | 1 |
| wall clock | 168s |

**This is correct behaviour, not a defect.** `_pre_screen_failure` (`src/self_healing.py:446`) sends only
`LOCATOR_TIMEOUT` and `STRICT_VIOLATION` to the reviewer; it declines `ASSERTION_FAILURE`,
`NAVIGATION_ERROR` and `OTHER`. Our 8 reds are assertion failures — the element **was** found and the
assertion did not hold — so there is no broken locator to repair. Sending them to the reviewer would be
the no-guessing violation (AI-052), not a win.

**Two incidental confirmations:**
- **B-068 works**: `[heal] Loaded scraped elements for 1 page(s) for reviewer context` — the reviewer
gets real element context.
- **B-070 works**: `No patches applied → reusing last run results (no extra test pass)` — the no-op
  re-run that cost ~22 minutes is gone.

**Correction to an earlier claim in this note.** I wrote that this package "holds 7 genuine locator
failures to heal". That was wrong — they are assertion failures, not locator failures. Gate 3 cannot be
measured on any package whose reds are all assertion reds.

**Config-independence (checked, not assumed).** No model setting can fix B-086: the scraper collects only
`interactive_tags = ["button", "a", "input", "select", "textarea"]` and `display_tags`, plus elements with
an `id` (`src/scraper.py:776,780,808,825,839`). `<meta>`, `<link>` and `<title>` are **never collected**, so
head elements never enter the candidate pool — the resolver cannot pick an element it was never offered.
The defect is architectural and deterministic. Reasoning-on also did not affect any gate: it slows
*generation* (42–130s per fragment vs 17–25s with it off in the 09-16 record) and the suite time (210s)
never touches the LLM.

---

## 5. Why this matters commercially

The Part C recommendation was: *"If gates 1–2 pass on a held-out set, the air-gap/evidence positioning is
sellable. If they do not, the honest pivot is to sell the evidence and traceability layer."*

Gates 1 and 2 do **not** pass. Worse, the failure is precisely in the class the sales pitch leans on:
a buyer's first evaluation will be metadata/attribute checks, and the tool reports green for those without
checking them. That is the same "green that means nothing" defect the 09-15 audit called *more dangerous
than red*, now narrowed to a specific, fixable class instead of a general one.

**The gap narrowed in a useful way.** The 09-15 reds were page defects + selector defects. Today: 0 page
defects, 0 selector defects, 0 false-positive navigations. What remains is one root cause —
**the resolver has no concept of `<head>`/attribute-only criteria, so it falls back to a visible element
and the assertion is weakened to match.**

---

## 6. Environment note (cost a lot of time; record it)

The Session 7 first attempt looked like "the model is degenerate" — three completions of ~130 chars in
80–170s. **That reading was wrong.** Per the B-065 note, one fragment call *correctly* returns a single
skeleton function (~57–85 tokens, `finish=stop`). Two mistakes were made:

1. **Two `ci_generate` runs and three `http.server` processes were started by accident**, all sharing the
   single llama.cpp slot. A one-line probe then took **1m52s**; after killing them it took **2.1s**. Self-inflicted.
2. **The agent itself shares the same `:8080` slot.** Any agent turn can wedge an in-flight pipeline call
   until the 600s timeout. The scratch harness's 10× retry-with-backoff absorbed this — **zero wedges
   occurred across a 56-minute generation**. Use that harness, not bare `ci_generate.py`, for any run
   longer than a few minutes.

Practical numbers for the next session: with thinking **on**, each skeleton fragment took **42–130s**
(~35 fragments), 63 LLM calls total, generation **3356s**, suite **210s**.

---

## 7. What to do next

1. **Fix the head/attribute class (new, highest value).** A criterion about `<head>` content, an
   attribute-only element, or a non-`http` scheme (mailto) must either resolve to the real element
   (`meta[name=description]`, `link[rel=canonical]`, `link[rel=icon]`, `meta[property^=og:]`) or emit an
   honest `skip` — never a weakened `assert_visible`.
2. **Gate the assertion kind on the criterion wording.** `must_be_url` must not apply to a criterion that
   asks for a `mailto:` link.
3. Then re-run this same story. Gates 1–2 are the only two that decide the positioning.
4. Session 3's self-healing fix-rate measurement (gate 3) is outstanding, and this package cannot answer
   it (§4b). The honest way to measure it is a **deliberate DOM mutation**: serve the page with the
   class names / ids the emitted selectors depend on changed, run the suite so the failures are genuine
   `LOCATOR_TIMEOUT`s, then heal and count. Cheap (no regeneration needed — reuse this package) and it
   measures exactly what gate 3 asks.
