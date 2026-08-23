# AI-051 — B-021 page-state URL assertions emit the landing page, not the base URL

> **Date:** 2026-08-23
> **Backlog:** AI-051 → ✅ Fixed

---

## The bug (repro)

Generated saucedemo `test_01_login` ended with:

```python
evidence_tracker.click("#login-button", ...)
expect(page).to_have_url("https://www.saucedemo.com/")  # ← base URL, wrong
```

saucedemo redirects to `/inventory.html` post-login, so the assert always
failed (`AssertionError: Page URL expected .../ actual .../inventory.html`).

## Root cause

The **B-021** page-state ASSERT branch
(`placeholder_orchestrator.py::_replace_placeholders_sequentially`, the
`if action == "ASSERT" and self._is_page_state_assertion(description)` path)
resolved the URL by **keyword-matching the description** against scraped pages
(`self.resolver.resolve_url(...)`). For a login assertion, "inventory page
loaded" has no keyword overlap with any scraped page's *path* (the base page's
path is `/`), so `resolve_url` fell back to the base/starting URL via its
root-path guard. The post-login special-case (lines ~633) only checked the
*description* for login words ("logged", "login success", …) and searched
`scraped_data` for an `inventory`/`products` page — but `/inventory.html` was
often not a scraped *key* in that shape, so it missed.

The resolver already tracks where the browser actually went — the **observed
trail** (`ObservedTrail`, AI-052) — but the B-021 branch never consumed it.

## The fix (trail-driven, evidence-only)

In the same B-021 branch, after keyword resolution (and the legacy post-login
special-case), consult the trail:

```python
if (
    resolved_url
    and obs is not None  # this step has an observed trail step
    and not diverged  # our emitted path still matches the observed one
    and pending_evidence is None  # we didn't emit an unscraped-href navigation
    and obs.to_url  # the trail recorded where this step landed
):
    landing_key = canon(obs.to_url)  # map trail URL → scraped_data key
    if landing_key is not None and normalize_url(landing_key) != normalize_url(resolved_url):
        resolved_url = landing_key  # assert the OBSERVED landing (a browser fact)
```

When the trail says the step's page is a different, scraped page than the
keyword-inferred one, assert the observed `to_url`. This is the same
"observation over inference" principle that closed AI-052 — a browser fact
replaces a guess.

**Guards:**
- `obs is not None` — no-trail (back-compat) mode is untouched.
- `not diverged` — once our emitted path departs from the observed one, the
  trail no longer describes this test.
- `pending_evidence is None` — if *we* emitted a click to an unscraped href,
  the runtime lands on the href target, not the trail's `to_url`.
- `canon(obs.to_url) is not None` — only when the landing page is actually
  scraped (a real `scraped_data` key), so `to_have_url` can be checked.
- `normalize_url` comparison — no-op when keyword and observed already agree.

## Verification

**Unit** (`tests/test_ai051_page_state_url.py`, 4 new):
- `test_login_assert_uses_observed_landing_url` — the repro: after Login, the
  assert targets `/inventory.html`, NOT the base URL.
- `test_no_trail_keeps_legacy_keyword_resolution` — back-compat: no trail →
  base URL (unchanged).
- `test_assert_on_scraped_landing_stays_on_landing` — keyword == observed → no flip.
- `test_no_override_when_keyword_and_observed_agree` — stable when they match.

**Production** (`verify_production saucedemo`, run `verify_saucedemo_20260823_180614`):
- `test_01_login` now asserts `to_have_url("https://www.saucedemo.com/inventory.html")`.
- Execution: **5 passed / 1 honest skip / 0 failed / 0 different-page errors**
  (was 4 passed / 1 failed / 1 skipped).
- The 1 skip is `test_06_complete_checkout` — a designed honest skip (the
  checkout/finish transition is unevidenced in the scraped trail, S3/S4
  behaviour). The 2 "failed gates" are the skip-related checks
  (`Pipeline unresolved: 1`, minimal-skip), not the execution.

**Other gates:** eval static **97.9% (no regression)**; full suite **2744
passed / 1 skipped**; smoke 39/39; ruff + mypy clean.

## Notes

- The `enable_thinking` open question in the backlog is now moot — the fix is
  trail-driven, independent of how the skeleton phrases the assertion.
- Only the **immediate** B-021 path needed the change: page-state ASSERTs
  always resolve there (or skip) and never reach the deferred/batch ASSERT
  path (`_resolve_placeholder_for_page`), which has no trail access.
- Related: AI-052 (observed-trail plumbing the fix builds on), AI-053
  (uat.py save fix found during AI-052 S6).
