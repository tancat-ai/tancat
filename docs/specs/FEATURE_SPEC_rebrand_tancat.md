# Feature Spec — Brand Rename to TanCat + GitHub org (AI-039)

**Feature ID:** AI-039 (brand rename)
**Created:** 2026-09-06
**Status:** **BUILD DONE 2026-09-06** (distribution name + all active display strings renamed to tancat / tancat-ai; uv.lock regenerated; smoke 39/39, ruff clean, product entrypoints import cleanly) — **NOT COMMITTED** (user reviews the diff per AGENTS.md §11). **GitHub org/repo rename is a git-remote action** (create org `tancat-ai` + rename repo on GitHub) — not part of the working-tree diff. Companies House **deferred** (no funds; income/projections first).
**Priority:** High — GTM / Phase 8 launch prerequisite (must precede first PyPI publish).
**Estimated sessions:** 0.5
**Roadmap ref:** `docs/plans/ROADMAP_ROADTO_PRODUCTION.md` §15 (Phase 8 GTM) + §13 prerequisite line.
**Backlog ref:** `BACKLOG.md` → AI-039.

---

## 1. Problem Statement

The product is named and branded "TanCat" in the research and the roadmap, but the **code and distribution surface still carry the old working name** (`playwright-test-generator` in `pyproject.toml`, repo `AI-Playwright-Test-Generator`, docs headers, CI badge). The Phase 8 GTM surface (PyPI publish, GitHub Marketplace Action listing, landing page, docs site) all assume the TanCat name. Renaming must happen **before the first PyPI publish** — the package name locks in once published, and the GitHub org/repo/Action owner reference must be a stable post-rename constant.

The 2026-08-01 decision deferred the rename ("no functional value pre-launch"). **That decision is now superseded**: the launch window (1 month) makes the rename the Week-1 build, because it gates PyPI publish + Marketplace listing + the landing page.

## 2. Name Layers (keep separate — do not conflate)

| Layer | Name | Status | Notes |
|-------|------|--------|-------|
| **Legal entity** | Cat Tan Operations Ltd | **To be incorporated** (Companies House) | Holding company; NOT yet registered (verified 2026-09-06). Trademark applicant + invoicing + GitHub-org ownership flow from it. Landing page "© Cat Tan Operations Ltd" must be true → incorporate before launch. |
| **Product** | TanCat | Confirmed | `pip install tancat`, `tancat.dev`, UI, GitHub org, trademark. |
| **GitHub account** | `tancat-ai` (org) + product repo | Pending handle confirmation | Org handle `tancat` is taken (dormant squatter); use `tancat-ai` (verified free) or another. Product repo name may be `tancat` (repo names don't collide with usernames). |

## 3. Live Name-Check Results (2026-09-06 — verified via Companies House + PyPI + GitHub)

- **Companies House:** **Cat Tan Operations Ltd is NOT registered.** No exact "CAT TAN OPERATIONS LTD" in the register (only fuzzy matches: TANDB OPERATIONS, THE TAN STATION, BIG CAT OPERATIONS, …). The roadmap's "registered holding company" line was inaccurate → corrected.
- **PyPI `tancat`:** **available** (404). **PyPI `tancat-ai`:** available (404).
- **GitHub user/org `tancat`:** **taken** — a dormant squatter account (user id 14859968; 0 public repos, 1 star, 0 followers, no activity in the last year). Use a variant for the **org handle**.
- **GitHub `tancat-ai`:** **available** (404).
- **UK IPO trademark "TanCat":** search is **bot-gated for automation** (Cloudflare) — **user must run manually** at `trademarks.ipo.gov.uk/ipo-tmtext` (keyword "TanCat"). If clear, file UK trademark class 9/42 (~£205+, 3–4 months to grant); applicant = the incorporated entity.

## 4. What Changes (build checklist)

> Parameterised on the two pending confirmations. Default picks shown in **bold** (my recommendations, both verified free).

1. **`pyproject.toml`** — `name = "playwright-test-generator"` → `name = "**tancat**"`. (PyPI normalises dashes/dots/case to lowercase; `tancat` is the clean form.)
   - **Note (CORRECTED 2026-09-06 — no import-path rename needed for PyPI, but customer-facing banners DID need updating):** the code does **NOT** import via `playwright_test_generator.…`. The packages are `src` and `cli` (`packages = ["src", "cli"]` in `pyproject.toml`), imported as `from src.…` / `from cli.…` (e.g. `from src.orchestrator import …`, `from src.cli.main import main`). `git grep` confirmed **0** `playwright_test_generator` import paths in the codebase — so **no import sed** for the distribution name. **However**, the **customer-facing banner titles** were written as "AI Playwright Test Generator" (no hyphens), which the exact-string `AI-Playwright-Test-Generator` pass did **not** match, so they needed separate updating (done): Streamlit `<h1>`/`st.title`/browser-tab title, CLI `print_header` + `menu_renderer` header comparison + subtitle, HTML report footer. The customer story is "pip install tancat" + the UI/CLI say **TanCat**; the code's internal imports stay `src`/`cli` (not customer-facing).
2. **GitHub org** — create org `**tancat-ai**` (or confirmed handle) under the user's account (or the incorporated entity's account — user's call, #5).
3. **Product repo** — rename `AI-Playwright-Test-Generator` → `tancat` **under the new org** (e.g. `tancat-ai/tancat`). Repo name `tancat` is fine even though the *username* `tancat` is taken.
4. **Thin public Action repo** — `tancat-ai/ai-test-generator` (`action.yml` + `entrypoint.sh` + `Dockerfile`) whose image installs the product **from PyPI** (`tancat`). The product repo stays private. (This is the Phase 7 CI/CD extraction — see spec `FEATURE_SPEC_phase7_ci_cd_integration.md` §Q4.)
5. **Action owner reference** — update all docs/CI references from `…/ai-test-generator@v1` → `tancat-ai/ai-test-generator@v1`.
6. **README + docs headers + script docstrings** — old name → TanCat / `tancat`.
7. **CI badge URL** — update to the new org/repo.
8. **Regenerate graphify** — `graphify update .` + regenerate `graphify-out/callflow.html` (gitignored).
9. **`AGENTS.md` / `CONTEXT.md` / `docs/ARCHITECTURE.md`** — name references.

## 5. Touch-Surface Audit (run before the mechanical rename)

```
rg -n "playwright-test-generator|playwright_test_generator|AI-Playwright-Test-Generator" \
   --glob '!graphify-out/**' --glob '!.git/**' --glob '!generated_tests/**'
```
- Categorise hits: distribution name (`pyproject.toml`) vs import paths (`import`/`from`) vs display strings (README/docs) vs repo/CI references (badge, Action ref, workflow paths).
- **Do NOT rename `generated_tests/`** (output artifact, gitignored) — only the *generator* that writes it.
- Keep `ci_generate.py` imports consistent with the chosen import name so the thin-repo extraction stays copy-paste.

## 6. Decision Gates (user — before build)

1. **Incorporate Cat Tan Operations Ltd** with Companies House — now or later? (Trademark applicant, invoicing, GitHub-org ownership, landing-page legal line all depend on it. Recommend **now** for a commercial launch.)
2. **GitHub org handle** — `tancat-ai` (my pick, verified free) or another?
3. **PyPI name** — `tancat` (free, verified) or `tancat-ai`?
4. **Import name** — rename to `tancat` (my pick, full consistency) or keep `playwright_test_generator` (smaller diff)?
5. **GitHub org owner** — user's personal account or the incorporated entity's account?
6. **Trademark** — user runs the IPO search (bot-gated for me); if clear, file.

## 7. Acceptance Criteria

- [ ] `pip install tancat` resolves to the published package (post-publish); `import tancat` (or chosen import) works.
- [ ] GitHub org `tancat-ai` exists; product repo `tancat-ai/tancat` (or confirmed handle/repo); thin Action repo `tancat-ai/ai-test-generator` installs the product from PyPI.
- [ ] `rg` audit returns **zero** stale `playwright-test-generator` / `playwright_test_generator` / `AI-Playwright-Test-Generator` hits in tracked source (excl. `generated_tests/`, `graphify-out/`, `.git/`).
- [ ] CI badge + Action owner reference point at the new org.
- [ ] README/docs/AGENTS/CONTEXT/ARCHITECTURE carry the TanCat name.
- [ ] Gates green: `smoke` → `ruff` → `mypy` → `pytest` (rename is mechanical; full suite must pass unchanged).
- [ ] graphify regenerated.
- [ ] Cat Tan Operations Ltd incorporated (CH) — so the product's legal owner is real and the landing page legal line is true.

## 8. Out of Scope

- **PyPI publish** itself (a follow-on action once the rename is merged — needs the PyPI account + token; not part of the rename diff).
- **Landing page / docs site / demo video / pricing page** (Phase 8 GTM surface — separate build, consumes the TanCat name).
- **Trademark filing** (user action, IPO).
- **Incorporation** (user action, Companies House) — the rename spec *depends on* it for the legal line but doesn't perform it.
- **TanCat Cloud** (post-launch, separate product — AGENTS.md §FC-05).

## 9. Decisions Taken (2026-09-06, recorded — reversible)

- **Rename is approved** — the 2026-08-01 "defer to launch readiness" is superseded by the 1-month launch window; the rename is Week 1, not deferred.
- **GitHub org handle = `tancat-ai`** (CONFIRMED by user 2026-09-06) — `tancat` is a dormant squatter; the handle is cosmetic, PyPI + domain + product name are the real customer-facing surface and all stay clean. Product repo = `tancat-ai/tancat` (repo name may be `tancat`; only the username `tancat` is taken).
- **PyPI name = `tancat`** (CONFIRMED by user 2026-09-06).
- **Import name = `tancat`** (recommended; mechanical sed with a flagged touch surface) — unless user prefers to keep `playwright_test_generator` for a smaller diff.
- **Companies House incorporation = DEFERRED (no funds this month; user unemployed 18 months — ~£150 yr-1 is a large investment).** Incorporate once there's income or solid projections. **Consequences (recorded so the build stays honest):**
  - Landing page / all customer-facing surface uses the **product brand "TanCat"** only (footer = **"© TanCat"**). "Cat Tan Operations" is **not prohibited** (it's a name, not a legal status) but is **not the customer-facing brand** — it's the (future) owning company, relevant only once incorporated (contracts, invoices, footer, trademark applicant). The **"Ltd"** is the only part that is prohibited now (phantom limited-company status for an unregistered entity).
  - GitHub org created under the user's **personal** account (not the entity's) for now.
  - Trademark can be filed by the **user personally** (assign to the company later if incorporated) — or deferred. Not a launch blocker (3–4 months to grant regardless).
  - **Nothing in the product surface (org, PyPI publish, domain, rename build) requires the company** — only invoicing/taking money does, which is gated on the incorporation anyway.
- **The "registered holding company" claim is retracted** — Cat Tan Operations Ltd is a *planned* company, not registered; incorporation is deferred (no funds), tracked here, not a done fact.

---

*Supersedes:* the 2026-08-01 deferral decision (AI-039) and the roadmap's "registered holding company" line (2026-07-31 entry, corrected 2026-09-06).
*Feeds:* Phase 8 GTM (landing page, docs, Marketplace listing), Phase 7 CI/CD thin-repo extraction.
