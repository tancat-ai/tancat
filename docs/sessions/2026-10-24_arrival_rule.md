# Session - never assert an arrival the browser was not seen to make (2026-10-24, t-0890)

**The owner's rule:** *"if its not something a real user would have then its not accurate testing
behaviour."* The navigation rule decides which **addresses** may be used. This one decides which
**claims** may be made.

**Answer: a page-state arrival assertion is now only written when the observed trail shows the
step after the last interaction on a page the browser actually reached. Otherwise the step
becomes an honest skip whose reason names what was missing.** 4008 tests pass, smoke 39/39, ruff
+ mypy clean.

## 1. What went wrong (from the 2026-10-24 measurement)

On eval-002 the journey's cart click failed (`Locator.click: Timeout 5000ms exceeded` - the
element resolved and the click never completed), the browser stayed on the shop page, and the
trail held only that page. The arrival check was written anyway, naming the shop page as if the
test had arrived at the cart. eval-006 failed the same way in two tests. The emitted tests then
failed in the browser on an address-bar check that named the page they had never left.

That is the same class of claim as a guessed address: the test checks something the run never
established.

## 2. The rule, as implemented

`src/placeholder_orchestrator.py`:

- **`_arrival_refusal(description, last_interaction, obs, canon)`** (new, pure) returns the reason
  an arrival may not be asserted, or `None` when it may. It refuses when:
  - no landing was recorded after the last interaction (`no observed landing after '<step>'`), or
  - the recorded landing is the page the interaction ran on (`the browser was not seen leaving
    '<page>' after '<step>'`).
  If the interaction's own trail step carried an error, the reason appends
  `(that step failed: <error>)` - a broken click stays visible instead of being swallowed.
- **Per-journey `last_interaction`** is recorded when a CLICK/FILL is emitted, and when a GOTO is
  emitted as a proven click. Before any interaction there is nothing to evidence: the entry
  navigation is the emitter's own instruction, so a first-step page assertion is unchanged.
- **The arrival branch** calls the check before `resolve_url`, so neither keyword resolution nor
  the flow-memory fallback can name an unobserved page. On refusal it writes
  `pytest.skip("page arrival not asserted: <reason>")`, marks the token strict-skipped (it can
  never be resurrected by the batch pass) and records it as unresolved.
- **`_resolve_placeholder_for_page`** (the second place that can write `to_have_url`) gained
  `arrival_evidenced: bool = False`; its page-state branch refuses unless the caller says the
  arrival was observed. No production caller passes `True` today - the sequential branch handles
  every trail-driven page-state assertion - so the two arrival sites can no longer disagree.

## 3. The judgement call (the part that matters)

**Trailless journeys are left alone.** A journey with no observed trail has no evidence either
way; its page-state assertions come from keyword resolution and are already checked at run time
by the page-mismatch record. Applying the rule there would have turned every page-state assertion
in that mode into a skip - a wholesale behaviour change, not this rule. Two existing tests
(`test_ai051_page_state_url::test_no_trail_keeps_legacy_keyword_resolution` and
`test_orchestrator::test_run_pipeline_advances_after_login_to_resolve_saucedemo_inventory_steps`)
encode that contract and are untouched. I judged a skip there to be the *wrong* answer, and said
so rather than quietly changing the mode.

One narrower case also stays as it was: a page-state ASSERT that follows a GOTO the pipeline
emitted as its own `navigate(...)` is not treated as an interaction, because the test itself
commands the browser to go there - that is evidence, not inference.

## 3b. The cost this rule accepts (recorded, t-0903 review)

**One case that used to go RED is now a skip: an interaction that SUCCEEDED but whose landing was
never recorded.**

Before the rule, that case wrote an arrival assertion anyway. At run time the browser was on some
page and the assertion named another, so the test failed - red, loudly, for a real reason: the run
could not establish where the click landed, which is a capture defect worth seeing.

Now the arrival is refused and the step is skipped with `page arrival not asserted: no observed
landing after '<step>'`. That is the honest outcome, and it is the one the owner's rule asks for -
but it must be said out loud that **the red signal is gone**: a suite can look greener while the
journey still cannot be captured.

Why that is acceptable:

- A skip is **not** a pass. Gate 2 counts hollow passes, and a skipped step is not one, so the
  metric does not read the skip as success.
- The alternative was worse in both directions: a test that fails for the wrong reason (the
  assertion, not the capture gap) trains people to ignore it, and on a page that happens to match
  it would pass while proving nothing.
- The reason string NAMES the missing landing and the interaction, so the capture gap is visible
  in the evidence instead of being silent.
- The underlying capture defects have their own work (B-109 cart click; the journey's click
  timeouts). The rule does not hide them - it stops the test from lying about them.

The one place this could bite: a suite whose green/red is the only signal. Anyone reading a skip as
"fine" is reading it wrong; the generated evidence says `skipped` with the reason attached.

## 4. Tests (`tests/test_t0890_arrival_evidence.py`, 7 after t-0903)

| test | pins |
|---|---|
| `test_observed_landing_is_asserted` | the browser was seen to arrive -> `to_have_url(<landing>)` is written, no skip |
| `test_unobserved_landing_is_an_honest_skip` | the click resolved but the browser never left -> **no** `to_have_url`, a skip whose reason names the missing landing and the page never left |
| `test_a_missing_trail_step_is_a_skip_not_an_assertion` | no trail entry at all -> skip (`no observed landing after '<step>'`) |
| `test_a_failed_click_is_named_not_hidden` | the click failed -> the arrival skip NAMES the failure (`that step failed: locator_not_found_even_relaxed`), and no arrival is asserted |

## 5. Gates

| Gate | Result |
|---|---|
| pytest (full) | **4008 passed** |
| smoke | 39/39 |
| ruff check + format | clean |
| mypy `src/ cli/` | clean |

Both `to_have_url` writers in `src/` are now guarded (grep proof in the report). The pre-existing
Streamlit AppTest 20s flake was seen once during this work and passes serially; it also fails on
an untouched main checkout.

## 6. Not done

The guessed-URL deletion was not touched. The held-out measure was not run. Nothing pushed.
