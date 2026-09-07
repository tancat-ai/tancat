# Feature Spec — TanCat Landing Page (tancat.dev) — Phase 8 GTM

**Feature ID:** Phase 8 GTM (landing page)
**Created:** 2026-09-07
**Status:** WRITTEN — ready to build. Not started.
**Priority:** High — the "in market" surface. Customers land here before they buy.
**Estimated sessions:** 1–2 (copy + build + screenshots + demo video link).
**Roadmap ref:** `docs/plans/ROADMAP_ROADTO_PRODUCTION.md` §15 (Phase 8 GTM Assets).
**Predecessor:** AI-039 brand rename (SHIPPED 2026-09-07) — the landing page uses the settled TanCat name + live `tancat-ai/tancat` repo.

---

## 1. Problem Statement

The product (TanCat) is built, renamed, and gated, but there is **no place a prospective customer goes to learn what it is, why it's different, and how to start.** Phase 8 GTM's first asset is the landing page on **tancat.dev** (domain already acquired). It must convert a visitor into a "Get Started" action honestly — no false claims, no broken "pip install" (that's deferred, see §7).

## 2. Positioning (the one-line pitch — verified in research)

> **"The AI test generator that never touches your data."**

This is the defensible differentiator (`RESEARCH_COMPETITIVE_LANDSCAPE.md`): every incumbent (testRigor, Mabl, QA Wolf, Functionize, Keploy) is **cloud SaaS** that routes your app's DOM/test data through *their* servers. **Nobody sells BYO-LLM, no-egress test generation.** TanCat deploys on *your* infra, pointed at *your* LLM, handling *your* data — the LLM calls go to your endpoint and nothing else (the no-egress claim is literally true, proven by the egress audit, `docs/security/egress-audit.md`).

**The buyer (optimise for first):** the **air-gap / regulated** team — "we could not use Mabl/testRigor because of data residency." Per-deployment, per-company (D2). Pricing is per-deployment, not per-seat (research §4.2).

## 3. What the page must contain

1. **Hero** — the one-line pitch + a sub-line ("Paste a user story → get executable Playwright pytest tests with real DOM selectors, on your own LLM, on your own infra.") + the **primary CTA: "Get Started."**
2. **How it works** — the 3-step value moment: **story → generate → run → evidence → export** (the value moment the free-tier research said must *complete*).
3. **Features** — the differentiators: BYO-LLM (llama.cpp / Ollama / LM Studio, local or cloud-API), no-egress / air-gap, evidence + reports (HTML/CSV/NDJSON/JUnit), CI/CD (GitHub/GitLab Action), self-healing, RAG learning, POM mode.
4. **The no-egress trust section** — the headline claim + "data never leaves your deployment" + link to the published egress audit. This is the *reason* the regulated buyer exists.
5. **Pricing tiers** — per-deployment: **Free** (25 runs / 10 exports per 30 days) → **Pro** (POM, multi-site, CI Action) → **Air-gap / Enterprise** (private-network, support). **Numbers are a placeholder pending your pricing decision** (see §8) — the page structure is ready; the actual prices are yours to lock.
6. **Get Started** — the real, working onboarding flow (see §7). **Lead with `uv`** (user preference + matches existing docs which use `uv sync`).
7. **Footer** — **`© TanCat`** (NOT "© Cat Tan Operations Ltd" — the company is not yet incorporated, see §8). Links: GitHub, egress audit, security.
8. **Demo video** — a 2–3 min real session (story → generate → HTML evidence). The Loom link placeholder is already in the README; the page links to the finished video (recorded as a follow-on).

## 4. Tech approach (recommended)

- **Static site** (no backend needed): **MkDocs Material** or a plain static HTML page on tancat.dev. MkDocs is the lower-effort choice and also becomes the **docs site** (Phase 8 also needs a docs site — quickstart, API, deployment guides). One MkDocs build can serve *both* the landing page (home) and the docs.
- **Host:** tancat.dev (you own it). Deploy via a static host (Netlify/Vercel/Cloudflare Pages/GitHub Pages) — all have free tiers. The exact host is a follow-on decision (no funds constraint — free tiers are fine).
- **Screenshots:** capture the real Streamlit app (the "TanCat" heading is now live) + a CLI banner + an evidence report. Real screenshots, not mocks (the product is real).
- **Copy:** plain, benefit-led, no jargon dumps. The regulated buyer is technical but the *pitch* is about data residency, not architecture.

## 5. "Get Started" — the working flow (Option A: clone + uv + run)

PyPI publish is **deferred** (no entry point yet — see §7), so the landing page's Get Started is the **clone + `uv sync` + run** flow, which **already works and is tested** (it's what the README, Streamlit app, and CI Action all use):

```bash
# 1. Prerequisites: Python 3.14+, uv, a local LLM server (llama.cpp :8080 / Ollama / LM Studio)
# 2. Clone + set up
git clone https://github.com/tancat-ai/tancat
cd tancat
uv sync
playwright install chromium
# 3. Launch the UI
bash launch_ui.sh        # → http://localhost:8501
#    (or the CLI: bash launch_cli.sh)
```

**Lead with `uv`** (not `pip`). The page can show the uv commands as primary; `pip` is not needed in this flow at all.

## 6. Out of Scope (this spec)

- **PyPI publish** — deferred until the entry point exists (see §7). The Get Started uses clone+run, not `pip install`.
- **The docs site's full content** — MkDocs can host the landing page (home) + a docs section; the full API/deployment docs are a follow-on (Phase 8 also lists a docs site). The landing page *links* to docs; it doesn't need to contain the full API reference.
- **Interactive sandbox** ("try in-browser, 3 generations") — Phase 8 lists it; it depends on Phase 6 Part 2 (multi-tenant), which is deferred. **Not on the landing page now.**
- **Demo video recording** — a follow-on (the page links to it; the video is recorded separately).
- **Marketplace listings** (GitHub/AWS) — Phase 8, follow-on. The GitHub Marketplace Action listing needs the thin public Action repo + semver tags (a later step).
- **Payment processing** — Phase 8 GTM is *after* pricing is validated by pilots; the landing page shows tiers, not a checkout.

## 7. The PyPI entry-point gap (why publish is deferred — tracked)

The package builds (`uv build` → `tancat-0.1.0`) and is named `tancat`, but **`pyproject.toml` has no `[project.scripts]` console entry point**, so `pip install tancat` (or `uv tool install tancat`) would install the code but give **no runnable command**. The code imports as `src`/`cli` (not `tancat`), and the CLI's `main` is async (needs an `asyncio.run` wrapper for a console script). **So `pip install` is not yet a working "Get Started."**

**This is the reason PyPI publish is deferred** (agreed with user 2026-09-07). The follow-up (tracked, not in this spec):
- Add a `[project.scripts]` entry point, e.g. `tancat = "cli.main:run"` where `cli.main` gains a small sync `run()` that does `asyncio.run(main())`.
- Verify `uv tool install tancat` → `tancat` works, then publish to PyPI.
- Until then, the landing page uses the clone+run flow (§5).

**uv vs pip note (user preference, 2026-09-07):** there is no "pip vs uv" decision — both read from PyPI. The customer-facing commands **lead with `uv`** (user preference + the existing docs already use `uv sync`). For the future pip-install story, the customer command for "run the TanCat tool" is **`uv tool install tancat`** (or `uvx tancat`), not a bare `pip install`.

## 8. Decisions the user must make (before/during build)

1. **Pricing numbers** — the tiers structure is ready (Free / Pro / Air-gap), but the **actual prices** are yours to lock. Research band (per-deployment, `RESEARCH_COMPETITIVE_LANDSCAPE.md` §4.2): Free / ~$299–499 (Pro) / ~$1–3k (air-gap premium). The air-gap tier is the *differentiated* revenue. **The page can build with placeholder prices and you fill them in** — or hold the pricing section until you've decided.
2. **Landing-page host** — Netlify/Vercel/Cloudflare Pages/GitHub Pages (all free tiers). No funds constraint. Your pick.
3. **Companies House / legal line** — **`© TanCat`** on the page (NOT "© Cat Tan Operations Ltd" — not yet incorporated; no funds this month). The company name becomes real (and the proper legal line) only once incorporated.
4. **Demo video** — record a 2–3 min real session (follow-on); the page links to it.
5. **GitHub org / repo** — already done: `tancat-ai/tancat` (live, CI green). The page links to it.

## 9. Acceptance Criteria

- [ ] tancat.dev resolves and serves the landing page.
- [ ] Hero shows the one-line pitch ("…never touches your data") + "Get Started" CTA.
- [ ] The no-egress trust section is present + links the published egress audit.
- [ ] Features section covers BYO-LLM, air-gap, evidence, CI/CD, self-healing, RAG, POM.
- [ ] Pricing tiers (Free / Pro / Air-gap) present (real numbers once locked; placeholder otherwise).
- [ ] **Get Started shows the working clone + `uv sync` + run flow** (uv-led, not `pip`).
- [ ] Footer is **`© TanCat`** (no "Ltd"), with GitHub + egress-audit + security links.
- [ ] Real screenshots of the Streamlit app (TanCat heading), CLI banner, and an evidence report.
- [ ] Demo video link present (video recorded as follow-on).
- [ ] Page is honest — no "pip install tancat" claim (deferred), no false company legal line.
- [ ] Responsive (mobile) + reasonable load (static site).

## 10. Follow-ons (tracked, not this spec)

- **PyPI entry point + publish** (§7) — `uv tool install tancat` story.
- **Full docs site** (quickstart, API ref, deployment guides) — MkDocs can host both; the docs content is a follow-on.
- **Demo video recording.**
- **GitHub Marketplace Action listing** (thin public Action repo + semver tags).
- **Pilot + case study** — one real user → testimonial (closes the GTM loop).
- **Companies House incorporation** — when funds allow (legal line, invoicing, trademark applicant).

---

*Supersedes:* nothing (new spec). *Feeds:* Phase 8 GTM (docs site, demo video, marketplace listings, pilot). *Depends on:* AI-039 rename (SHIPPED), egress audit (SHIPPED), `tancat-ai/tancat` repo (LIVE).
