# Commercial surface — decisions

> **What this is.** One decision record for everything a buyer's procurement process touches:
> delivery, updates, licensing, entitlement, usage caps, security posture, and the sales motion.
> Written 2026-09-23.
>
> **Why one document.** These were five scattered conversations (licensing, updates, enforcement,
> security, pricing). Splitting them caused the drift this file exists to stop — the landing page
> currently promises things the tier table contradicts, and the in-product upsell names a company
> that was never incorporated.
>
> **Owner.** Roadmap, *"Pre-launch: payment → license fulfillment"*. That item owns the **status**;
> this file owns the **decisions and the reasoning**. Do not restate status here.
>
> **Related:** `RESEARCH_FEATURE_COMPARISON_2026-09.md` (competitive evidence),
> `docs/security/egress-audit.md` (the published egress claim),
> `RESEARCH_SAAS_AND_LAUNCH.md` (entity/tax and MoR scoping).

---

## 0. The rule

**Conform on the plumbing. Differ on the proof.**

- **Plumbing** = anything a buyer's procurement form or a competitor's docs would already expect:
  delivery, licensing mechanics, updates, entitlement, DPAs, security questionnaires, the sales
  motion. Deviating here buys nothing, costs trust, and adds friction. Copy the industry.
- **Proof** = anything the buyer cannot verify anywhere else: honest verification, evidence and
  traceability, repo-native output, a CI-enforced egress claim. This is where the invention budget
  goes.

**Test for which bucket something is in:**

| Question | Bucket |
|---|---|
| Would a buyer's procurement form expect this? | Conform |
| Could the buyer verify this claim at another vendor? | Conform |
| Can the buyer verify this claim *anywhere* else? | **Differ** |

---

## 1. Delivery and updates

**Decision — conform.** Ship versioned releases; the customer pulls them.

- Primary: a container image and/or package published to a registry. The operator runs
  `docker pull` / `uv sync` / downloads a release. **The running product never checks for updates.**
- Air-gapped customers: a signed release bundle carried in on approved media, signature verified at
  install.
- Entitlement is enforced **at the download point** (registry credentials or a licence-gated
  download), never inside the runtime.

**Why.** This is what our published egress audit already promises — *"no telemetry, no update
checks"* — and `scripts/audit_egress.py` fails CI if a new outbound call site appears in `src/`.
Keeping the runtime silent is also the single easiest security-questionnaire answer in the product.
It costs the customer nothing: they still get every improvement, they just choose when to fetch it.

**Note on a common misreading:** "no update checks" does **not** mean "no updates". The claim is
about *the running product*. The operator's tooling does the pulling. Our audit document already
scopes out dev/CI tooling for exactly this reason.

**Work.** Document the pull-based update path in the quickstart. Publish a release process. No code
change is required for the norm itself.

---

## 2. Licensing and entitlement

**Decision — conform, with one in-network option for air-gap.**

| Path | State | Use |
|---|---|---|
| Offline signed licence key (Ed25519, verified locally) | **shipped** — `src/licensing/license.py` | everyone |
| Licence server **inside the customer's network** (product talks to it on the LAN) | to build | air-gap / defence |
| Entitlement at the download point (registry credentials) | to set up | paid updates |

**Why.** The offline key is already the industry standard for self-hosted and it is the only
mechanism that works with zero connectivity. The in-network licence server is the established
air-gap pattern (Atlassian, JetBrains, SonarQube, GitLab EE all ship a version of it): the product
checks entitlement without anything crossing the perimeter. Selling it as "our licence server" is
normal, not a compromise.

**Conform/differ:** conform. Do not invent a novel licensing scheme.

**Work.** Build the in-network licence server. Wire registry credentials to paid tiers.

---

## 3. Usage caps and the enforcement stance

**Decision — caps stay local and stay a nudge. Never phone home from the runtime.**

- Free tier: monthly run and export caps, counted locally. Already implemented
  (`src/usage_meter.py`: a SQLite run count + a JSON export ledger).
- Paid tiers: caps lift.
- **Upgrade to tamper-*evident*, not tamper-proof:** hash-chain the ledger and sign the head with the
  licence key we already hold. Resetting stays possible on a machine the customer owns; it becomes
  *detectable*, and the terms say a broken chain voids the licence.

**Why.** The principle: **whoever owns the machine owns the enforcement.** If the customer owns the
hardware, no technical lock holds — they can edit the file, the env var, or the Python source, which
is Apache-2.0 and readable. So enforcement is detect-and-contract. Tamper-evident costs almost
nothing (we already have the signing code and the ledger) and it keeps the runtime silent, so the
egress claim stays true.

**Explicitly rejected:** a runtime phone-home licence check. It would not leak customer data — but it
would break the *true air-gap* use case functionally, and it would contradict a promise we already
published and gated in CI. If that trade is ever revisited, the audit document and the CI gate must
change **first**, so the published claim stays true.

**Known limitations, documented rather than hidden:** the counters are local files and
`AITEST_ENFORCE_FREE_TIER=0` disables them (tracked as B-051). The caps were never a lock.

**Work.** Tamper-evident ledger. Fix the in-product upsell text (see §7).

---

## 4. Security posture

**Decision — conform on documents, differ on the one proof we actually have.**

Conform (expected by every buyer; get the standard versions in place):

- DPA and MSA templates
- a SOC 2 Type II track (state the timeline honestly; do not claim it early)
- standard security-questionnaire answers
- a security contact and a disclosure policy (already shipped: `SECURITY.md`)

Differ (ours, and it is real):

- **the egress audit** — published, generated by inspection, and enforced by a CI gate that fails if
  an unrecognised outbound call site is added to the product runtime. No competitor in the
  comparison set publishes an equivalent check.

**Why.** Procurement teams do not reward a novel security posture; they reward a *recognisable* one
plus one thing they can verify. Our verifiable thing is the egress gate.

**Work.** DPA/MSA templates. Decide whether SOC 2 is worth the cost at this revenue level (open
question — see §9).

---

## 5. Sales motion

**Decision — free tier as the door, a self-serve trial as the step, a conversation for the big tier.**

1. **Free Community** — install and use, capped. This is also the solo/indie option (see §6).
2. **14-day Pro trial** — self-serve, no email. The standard door in this category (mabl runs a
   14-day trial to a quote request).
3. **Request a licence** — the current landing-page CTA, for Pro and Air-Gap.
4. **Design partners** — free licences in exchange for testimonials and pricing feedback (already in
   the GTM plan).

**Why.** At a per-deployment price nobody buys from a cold click. The ladder is free → trial →
conversation. We do not need a cheap paid tier to bridge it.

**Conform/differ:** conform. Trial-then-quote is the norm.

**Work.** Build the trial (a time-boxed licence key is enough — no new mechanism).

---

## 6. Tiers

**Decision — three public tiers. Delete the fourth.**

| Tier | Price | Caps | Includes |
|---|---|---|---|
| Free Community | $0 | 25 runs, 10 exports / month | the whole tool: generate, self-heal, RAG, POM, multi-site, every export format, CI Action |
| Pro Deployment | monthly, per deployment | none | + support, updates, priority security patches |
| Air-Gap / Defence | monthly, per deployment | none | + private-network entitlement, contractual egress limitation, SLA, onboarding, audit-ready evidence support |

- **`self-serve` is deleted.** It exists in `src/licensing/tiers.py` only to gate Jira export, which
  is a poor boundary and is not enforced anyway.
- **No per-seat option, on purpose.** A self-hosted tool cannot count seats, so a "1 seat" licence is
  unenforceable — five people would use it. The market agrees: mabl advertises "unlimited Participant
  licenses", Autonoma "unlimited users". Katalon's per-seat model is the outlier.
- **No cheap indie tier.** The solo dev, the contract tester and the developer testing their own
  product are served by **Free**. Their alternative is $0 (Playwright MCP + a local model), they do
  not buy support, and a $19/mo tier would anchor the product's value at $19 while adding a support
  burden. They are distribution, not revenue: they test on Free, then bring it to work.
- **Price period: monthly** (decided 2026-09-23). Note that annual billing is the norm for
  self-hosted and carries less churn; offer both, lead with monthly.
- **The numbers are not decided here.** See `RESEARCH_FEATURE_COMPARISON_2026-09.md` §9 for the
  evidence and the anchors.

**Why no feature scissors on Free:** the core is Apache-2.0, which already permits commercial use.
A fork removes any feature gate, so scissors only annoy honest users. What is sellable is support,
the SLA, onboarding and the contractual wrapper — which is what the paid tiers actually contain.

**Work.** Delete `self-serve` from the tier table (or fold it into `pro`). Decide the two numbers.

---

## 7. Landing page and in-product copy — corrections required

These are live defects, not preferences:

| Where | Problem | Fix |
|---|---|---|
| `landing/index.html` pricing cards | prints competitor prices as "anchors" ("testRigor $450/mo Pro; Mabl $499/mo"). They drift — testRigor no longer publishes a price, and 2026 estimates put it near $900–1,000/mo. They also invite comparison shopping. | Remove from the page; the research doc is their home. |
| `landing/index.html` pricing cards | prices carry no period ("~$299-499 / deployment") | State the period. |
| `landing/index.html` Pro card | lists self-healing and RAG as Pro features; the code puts both in Free | Correct to match the tier table. |
| `landing/index.html` Pro card | promises a "priority security patch queue" that is not in the tier table | Either add it to the tier table or remove the claim. |
| `src/usage_meter.py` `_UPGRADE_PROMPT` | says "see the license key from **Cat Tan Operations**" — a company that was never incorporated | Say TanCat (sole trader). |
| `src/ui/ui_sidebar.py` limit warning | tells the user how to switch the cap off — "set `AITEST_ENFORCE_FREE_TIER=0` to disable the cap (self-hosted)" | Do not advertise the bypass in the upsell. Keep it documented in the docs instead. |
| `landing/index.html` Free card | 10 exports/month is too low: an evaluator burns it in one afternoon, while teams hit the *run* cap | Raise free exports (25) or drop the export cap and keep the run cap. |

---

## 8. Where we deliberately differ (the whole list)

1. **Honest verification.** Unverified assertions are reported as skips, never as green passes.
2. **Evidence and traceability.** CSV/NDJSON/JUnit/Jira/HTML, per-step screenshots and URLs,
   role-based views, requirement → test traceability.
3. **Repo-native output.** The deliverable is pytest source in the customer's repository, so the
   suite outlives the vendor.
4. **A published, CI-enforced egress claim.**

Everything else — delivery, licensing, updates, security documents, sales motion — is
industry-standard by design.

---

## 9. Open questions

1. The two price numbers (evidence and anchors are in the research doc).
2. SOC 2: worth the cost at this revenue level, or defer until a regulated deal demands it?
3. Free export cap: raise to 25, or remove the export cap entirely?
4. Wire the feature gates (`feature_enabled` has zero call sites) or drop the pretence and sell
   entitlement + support only? **Recommendation: drop it.**
5. Annual billing alongside monthly — lead with which?
