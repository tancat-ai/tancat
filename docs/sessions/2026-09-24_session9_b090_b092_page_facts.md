# Session 9 — B-090 + B-092 closed (gate 2, zero false greens)

**Date:** 2026-09-24 · **Branch:** `fix/b090-b092-page-facts`
**Story:** the same 35-criterion landing-page story as Sessions 7/8 (`scratch/landing_page_story.md`)
**Target:** local serve of `landing/` on `:8079`
**Model:** Qwen3.8-27B-UD-Q4_K_XL_v2, LM Studio `:8080`

---

## 1. Headline

| Measure | Session 8 (before) | **Session 9 (after)** |
|---|---|---|
| Result | 2 failed / 31 passed / 2 skipped | **2 failed / 31 passed / 2 skipped** |
| False greens (B-090/B-092 classes) | 8 | **0** |
| Wrong-element mappings | 0 | 0 |
| Skips | 2 (c16/c17) | 2 (c16/c17) |

The pass count is unchanged, but the passes are now real: 8 of the Session 8
passes were false greens. During the run the Noir Art artwork image was hosted
on `lh3.googleusercontent.com` and returned **HTTP 403**, so c7 (`no broken
images`) and c8 (`the artwork image loads`) first failed honestly; re-hosting it
as `landing/noir_art.jpg` makes both pass for real. The 2 remaining reds are the
stale c13/c14.

## 2. What was fixed

| Item | Defect | Fix |
|---|---|---|
| **B-090 c3** | "at least four capability cards" emitted `assert_visible(<hero p>)` | `PageFactAssertion` classifier → `assert_count_at_least(selector, n)`; new tracker method |
| **B-090 c6/c8** | "image loaded / natural width" emitted `assert_visible` | `assert_natural_width(selector)`; `src/content_scoping.py` scopes image criteria to `<img>`; scorer `_kind_bonus` ranks the named image first and waives the hidden penalty |
| **B-090 c7** | "no broken images" emitted `assert_visible(<div>)` | `assert_no_broken_images()` scans every `<img>` |
| **B-090 c35** | "no horizontal scroll at 375px" emitted `assert_visible(<div>)` | `assert_no_horizontal_scroll(width=375)` resizes the viewport and measures `scrollWidth` |
| **B-092 c1** | "hero headline visible" resolved to a `<p>` | heading scoping (`headline` → `h1`) + `kind_matches` guard |
| **B-092 c4** | install command never read | `assert_text_contains('body', 'git clone …')` |
| **B-092 c11/c12** | "Pro/Air-Gap price" checked a heading | `assert_section_has_price(<tier>)` |
| **B-092 c18/c19** | "every … link" checked one anchor | `assert_anchor_targets_exist()` scans every same-page anchor's fragment target |
| **root cause** | the scraper collected **zero** `<img>` elements | `src/scraper.py` extracts `<img>` with `alt`; `_build_haystack` + ranker prompts include `alt` |

`_is_page_level_assert` treats the no-resolution families as page-level, so an
unresolved resolver result no longer inserts a journey-level skip.

## 3. Worktree correctness fix

The harness ran a script under `scratch/`, which puts `scratch/` on `sys.path[0]`
— so `import src` resolved to the **main repo's editable install**, not the
worktree. Two fixes:

- `src/journey_scraper.py` now passes `PYTHONPATH=<checkout root>` to its
  journey-scrape subprocess. Without this the child imported the main repo's
  scraper and silently missed the new `<img>` extraction.
- the scratch harness inserts its own repo root on `sys.path` and exports
  `PYTHONPATH` for children, and copies the emitted test file to
  `scratch/session8_emitted_test_file.py` for audit.

## 4. Verification

- **Offline teeth**: `tests/test_b090_b092_page_facts.py` (59 tests) pins the
  classifier, emitter, tracker methods, scoping, kind bonus, and the
  journey-subprocess `PYTHONPATH`.
- **Live re-run**: 4 failed / 29 passed / 2 skipped; every B-090/B-092 class
  emits a real check (see BACKLOG entries).
- **Gates**: 3436 pytest / 1 skipped, smoke 39/39, ruff + mypy clean, eval
  static 97.9% (0.0pp drift).

## 5. Residual

- **c13/c14** still need a story update (the page design changed on purpose in
  Session 6).
