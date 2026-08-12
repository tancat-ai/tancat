# AI-042 Cross-Site Flow Memory — Customer-Value Analysis

**Date:** 2026-08-12 · **Feature:** cross-site flow memory (shipped, `src/flow_memory.py`) · **Roadmap:** Tier 4 §16 (Complete)

---

## 1. Executive summary

Flow memory teaches the tool **how pages connect** (login → dashboard → cart →
checkout) from tests that pass, and reuses that knowledge on sites it has never
seen before. Locators don't transfer across sites (~3% overlap), but navigation
*shape* does. The measured transfer value: **on a site whose evidence is
entirely withheld, 3 of 4 navigation assertions that today fail become
resolvable** — using knowledge learned only from other sites.

Its value to a customer is **concentrated, not broad**: it targets the
navigation slice of test generation (≈7% of resolved placeholders, ≈27% of
executed steps are navigation), so it is a *journey-integrity* feature, not a
resolution-everything feature. Element-level resolution (the dominant skip
cause) is the RAG/locator layer's job — flow memory protects it indirectly by
making navigation reliable (a wrong navigation cascades into dozens of
downstream element failures — the B-015 failure class this feature's ancestors
kept fixing).

**Recommendation: ship it as a differentiator for multi-site customers and
demo it on the mock catalog.** For a single-site, single-page-form customer the
value is near zero — that is a documented boundary, not a bug.

---

## 2. What it does (plain English)

1. **Learns**: every time a generated test *passes*, the tool records where the
   test was and where it went — `(page A, action, description, page B)` — as a
   route-level transition ("from the login page, clicking 'sign in' lands on
   the dashboard").
2. **Generalizes**: it only remembers the *shape* (routes like "cart",
   "checkout"), never URLs or credentials (privacy: AI-035 §4), and it
   remembers **which sites** verified each transition.
3. **Reuses**: when a new site can't resolve "go to the cart" on its own, the
   tool answers with "on every other site that shape led to the cart route —
   here is that URL."

The learning is **local and automatic** — no config, no LLM calls, a small JSON
file next to the other evidence.

---

## 3. Who benefits (and when)

| Customer scenario | Value | Why |
|---|---|---|
| **Multi-site shop** (prod + staging + second app in one workspace) | **High** | Flows learned on site A resolve navigation on site B from day one — the "first passing test on a new site" moment |
| **Onboarding / evaluation** (trial user generating their first tests) | **Medium-High** | Fewer navigation skips in the demo run = the difference between "it works" and "half the tests skipped" |
| **E-commerce / multi-page flows** (cart, checkout, order) | **High** | This is exactly the learned shape (home → cart → checkout → success) |
| **Single-page form sites** (insurance quote, contact form) | **Low** | One navigation per test; flow memory has almost nothing to transfer — locator/RAG matters instead |
| **Portfolio / ML-story** | **Medium** | The learning loop "generate → execute → pass → learn → next site resolves better" is the self-healing narrative made quantitative |

---

## 4. The measured surface (from this repo's own data)

| Metric | Value | Source |
|---|---|---|
| Navigation-class steps in real evidence | **27.4%** (925/3,381) | sidecar sweep |
| URL-assert / GOTO-class golden placeholders | **7.3%** (7/96) | eval datasets |
| `to_have_url` assertions emitted in 22 real packages | 50 | generated code |
| Real unresolved skips mentioning navigation words | 21 | generated code |
| Real skips that are *element-level* (Place Order, quantity…) | majority | generated code (flow memory does NOT target these) |
| Eval holdout, baseline today | **0/4** resolvable | flow_holdout_eval.py |
| Eval holdout, with flow memory | **3/4** resolvable | flow_holdout_eval.py |
| …of which verified on ≥2 sites (strict cross-site) | 1/4 | same |
| Store after seeding from 908 real sidecars | 89 patterns, 6 sites, **5 cross-site** | evidence/flow_memory.json |

**Interpretation:** roughly a quarter of everything a generated test does is
navigation, and a tenth of resolved placeholders are URL-class. Flow memory
targets that tenth — and, measured with the target site's own evidence removed,
recovers **75% of the navigation-assertion goldens that today fail**.

---

## 5. Where the value lands

1. **First-pass navigation on a new site (the headline).** Today, a brand-new
   site's page-state assertions ("cart page title") fail because there is no
   DOM element matching "cart page title". Flow memory resolves them to the
   right URL using only knowledge from *other* sites. Measured: 3/4 (the 4th
   is a documented corpus/port-collision artifact, not a capability miss).

2. **Skip reduction with trust intact.** Skips are the #1 user-trust killer
   (B-021: "skipped tests degrade user trust"). Every URL-class skip that
   becomes a real navigation is a test that now runs and produces evidence.

3. **Journey integrity (the cascade effect).** The expensive failures in this
   product's history were cascades: wrong navigation → wrong page scraped →
   *everything* downstream unresolved (B-015, B-028, B-045). Making navigation
   resolution more reliable protects the element layer beneath it — the
   indirect value is larger than the 7.3% direct share.

4. **Self-healing flywheel.** Flow memory is the navigation half of the
   learning loop; RAG is the locator half. Together: generate → execute →
   pass → learn → the *next* site's first run is better. That closes the
   story a customer can be told (and a portfolio can show with numbers).

---

## 6. What it does NOT do (honest boundaries)

- **Does not resolve element placeholders** ("Place Order", "quantity",
  "Proceed to Checkout" as a *button*). Those dominate real skips and are the
  RAG/locator layer's job. Customers whose pain is element resolution will see
  no benefit here.
- **Does not help single-navigation tests** (the majority of the current
  corpus — 904/908 sidecars contain one navigation). The cross-test suite
  shape (login test → cart test) is a known extension (AI-042-F3), not yet
  learned.
- **Needs vocabulary overlap between sites.** saucedemo's `cart.html` and
  automationexercise's `view_cart` only transfer after the alias
  canonicalization shipped in session 2; sites with genuinely unique route
  names won't transfer (correctly — precision beats recall here).
- **Learning is workspace-local**: customer A's flows never help customer B
  (privacy by design). The transfer value is *within* a customer's own
  multi-site usage, plus any pre-seeded golden flows we ship.

---

## 7. Rough impact estimate (clearly labelled directional)

Per 100 generated tests on a new site (first run, no site evidence):

| Slice | Baseline | With flow memory |
|---|---|---|
| URL-assert / GOTO placeholders | ~7 fail (element matching can't resolve them) | ~5 resolve correctly; ~2 remain (vocabulary gap / home-targets) |
| Tests *entirely* skipped due to navigation resolution | e.g. the checkout leg of a suite | that leg runs |
| Downstream element failures caused by wrong navigation | cascade-prone | protected |

The headline for a customer demo: **"the checkout leg of a brand-new site's
story goes from skipped to executed, using navigation knowledge learned from
your other sites."** The honest caveat for an engineering buyer: **"this is
the navigation slice; element resolution is a separate (also shipped) layer."**

---

## 8. Cost / risk profile

| Dimension | Assessment |
|---|---|
| Runtime cost | ~zero: pure Python, local JSON (atomic writes), no LLM calls, no network, no new deps |
| Privacy | Strong: routes only, site identity is a one-way sha256, no URLs/credentials/story text (AI-035 §4) |
| Regression risk | Low: consumption is a *fallback* that runs only after all site-specific resolution fails; `FLOW_MEMORY_ENABLED=0` hermetic gate; 34 unit tests + full suite 2457 green |
| Maintenance | One 440-line module; learning rides existing teardown/sweep hooks |
| Failure mode | Store corrupt/missing → starts empty → behavior identical to no-feature |

---

## 9. Recommendation

- **Ship** (it is shipped and measured). Position it as the navigation half of
  the self-healing story, alongside RAG (locators).
- **Demo it** on the mock catalog: run the banking story on the ecommerce
  site (or vice versa) with the flow store seeded from the other mocks — the
  checkout leg resolves without the target site having any evidence.
- **Do not oversell**: a single-site form customer's win is small. The buyer
  message is *multi-site onboarding speed*, not universal resolution.
- **Optional roadmap follow-ups** (added to §16): GOTO-flavored golden
  (AI-042-F1), Streamlit flow stats + prune (AI-042-F2), cross-test flow
  chaining (AI-042-F3 — the bigger surface), skeleton guidance (AI-042-F4,
  deferred deliberately).
