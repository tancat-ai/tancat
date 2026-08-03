# Mock Site Catalog

Local, deterministic test targets for the AI-Playwright-Test-Generator pipeline.
Each mock is a self-contained site we own — **no ads, no consent dialogs, no
third-party dependency, no decay** — and each covers a distinct *product shape*
so the pipeline (scraper → resolver → generator → executor → evidence) is
exercised across as much product range as possible.

> Rationale: real demo sites (automationexercise, saucedemo…) are covered in
> Google consent/ad overlays and change under us. A real user runs this tool
> against **their own site** — clean, deterministic, local. The mocks are that.

## Why mocks are better test targets than prod demo sites

| | Third-party demo site | Our mock |
|---|---|---|
| Determinism | Random ad/consent overlay timing → flaky | Fully controlled |
| Overlay race (B-029) | Untestable (random timing) | **Injectable overlay on demand** |
| Golden keys | Decay every 3–6 months | Never decay (versioned in-repo) |
| CI | Needs internet | localhost, CI-capable |
| Coverage of product types | Fixed set, unknown maintenance | Curated, grows with us |

## Catalog (build order)

| # | Product type | Status | Path | Key flows to exercise |
|---|---|---|---|---|
| 0 | Insurance (multi-step form) | ✅ have | `generated_tests/mock_insurance_site.html` | multi-step form, validation |
| 1 | E-commerce (multi-page) | 🆕 build first | `mock_sites/ecommerce/` | home → category → product → add-to-cart **modal** → cart → checkout; **injectable consent/ad overlay** for the B-029 race |
| 2 | Banking / fintech | 🆕 | `mock_sites/banking/` | login, accounts, transfers, payments, multi-user |
| 3 | Booking / travel | 🆕 | `mock_sites/booking/` | search, date pickers, booking lifecycle |
| 4 | Healthcare | 🆕 | `mock_sites/healthcare/` | patient intake forms, appointment CRUD |
| 5 | Enterprise / HR | 🆕 | `mock_sites/hr/` | org hierarchy, multi-role, admin |
| 6 | Element / widgets | 🆕 | `mock_sites/widgets/` | auth, alerts, frames, drag-drop, shadow DOM |
| 7 | Robustness / security | 🆕 | `mock_sites/security/` | auth, admin, tricky forms |
| 8 | API (non-DOM shape) | 🆕 future (FC-02) | `mock_sites/api/` | OpenAPI stub — endpoints, payloads, auth, status codes; same story→skeleton→evidence loop, no browser |

Reference repos researched 2026-08-03 (sources of inspiration, **not** dependencies):

- E-commerce: automationexercise.com; Potion Shop; Practice Software Testing
- Banking: `cypress-io/cypress-realworld-app` (5.9k★, React+Express+SQLite)
- Booking: Restful-Booker; Sunny Meadows B&B
- Healthcare: Spring PetClinic (too heavy — prefer our own static)
- Enterprise: OrangeHRM (too heavy — prefer our own static)
- Widgets: `saucelabs/the-internet`; LetCode; DemoQA
- Security: OWASP Juice Shop

## How to add a mock

1. One directory per product type under `mock_sites/`.
2. Self-contained: static HTML/JS single-file or a tiny stdlib server (no build step).
   Follow the `mock_insurance_site.html` / `scripts/mock_server.py` pattern.
3. **Every mock must support an optional injected consent/ad overlay**
   (`?overlay=consent` query param or server toggle) so the B-029-class race is
   testable deterministically (clean path AND overlay path).
4. Ship with a user story + golden-key eval dataset
   (`scripts/eval/dataset/eval-NNN_<mock>_<flow>.json`) so the harness runs
   against it.
5. Register in `scripts/README.md` and this table.

## Serving

- `python scripts/mock_server.py` — stdlib ThreadingHTTPServer (port 8781).
- `bash launch_dev.sh` — mock + Streamlit UI.
- Eval runner auto-starts the server for mock datasets.
