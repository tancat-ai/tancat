# Session 8 — B-088 closed + B-087 + the generation-speed fix (record)

**Date:** 2026-09-24 · **Branch:** `fix/b088-page-section-scoping`
**Story:** the same 35-criterion landing-page story as Session 7 (`scratch/landing_page_story.md`)
**Target:** local serve of `landing/` on `:8079`
**Model:** Qwen3.8-27B-UD-Q4_K_XL_v2, LM Studio `:8080`

---

## 1. Headline

| Measure | Session 7 (before) | **Session 8 (after)** |
|---|---|---|
| Generation wall-clock | 3356s (thinking **on**) | **631s** (thinking **off**) |
| Criteria → tests | 34 | **35** |
| Result | 8 failed / 26 passed | **2 failed / 31 passed / 2 skipped** |
| Suite wall-clock | 210s | 245s |
| Wrong-element mappings | 7 | **0** |
| False greens in the B-086/87/88 classes | ≥3 | **0** |

The two reds are criteria 13 and 14 — both stale by design since Session 6 replaced the
purchase links with a request-a-licence route (`#contact`). The two skips are criteria 16
and 17 — the named "Walkthrough" links no longer exist on the page. Neither is a resolver
defect.

## 2. What was fixed

| Item | Defect | Fix |
|---|---|---|
| **B-088 c24** | "no TBD in hrefs" / "no TBD in visible copy" never reached the count classifier; the resolver picked the hero paragraph and asserted `href` on it | `count_assertion_from_description` now maps "no X in hrefs" → `[href]` scan, "no X in visible copy" → `body` text scan, and the combined criterion → one multi-token scan of `a, button, h1–h6` over **both** href and text. `assert_no_forbidden` accepts a token tuple + `also_text`. |
| **B-088 c22** | "Security Policy link resolves" resolved to a `<span>` that names the link (no href) | `src/link_scoping.py` narrows a link criterion to anchors before any pass runs |
| **B-088 c16** | "Watch 3-Min Walkthrough …" resolved to the nav-logo anchor when the named link no longer exists | the same scoping plus a name guard; a pick sharing no distinctive token with the named link → honest skip |
| **B-088 c27** | two unrelated heading-visibility asserts passed for "a contact link appears inside the Air-Gap tier" | skeleton prompt keeps compound checks in one assert; new `assert_contains(<section heading>, <child selector>)` checks the child **inside** the section |
| **B-087 c26** | "the hello@tancat.dev link is a mailto link" emitted `must_be_url=True` and failed a correct page | `attribute_scheme()` + `assert_attribute(required_scheme='mailto:')` |
| **B-091** | the per-condition fragment path called `client.generate(prompt)` with no `enable_thinking`, so the model default (thinking **on**) governed | `TestOrchestrator` stores the resolved switch and passes it on all four fragment calls |

Page-level families also no longer trigger the journey-level consolidated skip when the
resolver returns nothing (`_is_page_level_assert`) — the emitter owns their check, so the
test runs the real scan instead of skipping.

## 3. Verification

- **Offline, with teeth** (`scratch/b088_live_replay.py`, real page + mutated copies): every
  new check passes on the clean page and **FAILS when the thing it checks is removed** —
  TBD injected into an href, lorem into visible copy, the mailto link removed, both tier
  contact links removed.
- **Prompt probe** (real LLM, 2 calls): criterion 26 → `{ASSERT:hello@tancat.dev mailto link}`,
  criterion 27 → `{ASSERT:contact link inside Air-Gap tier}`.
- **End-to-end re-run**: 2 failed / 31 passed / 2 skipped (numbers above).
- **Gates**: 3376 pytest passed / 1 skipped, smoke 39/39, ruff + mypy clean, eval static
  97.9% (0.0pp drift).

## 4. Residual (not B-088)

- **Criteria 13 and 14** need a story update (the page design changed on purpose).
- **B-090** (new) files the *geometric/asset* false-green class the re-run exposed:
  criteria 3 ("at least four capability cards"), 6 (natural width > 0), 7 (no broken
  images), 35 (no horizontal scroll at 375px) still emit `assert_visible` on one element.
  Different root cause, different assertion family.
- **B-091 follow-up**: the fragment loop is still sequential; re-measure a batch/parallel
  call once the server can serve more than one request at a time.
