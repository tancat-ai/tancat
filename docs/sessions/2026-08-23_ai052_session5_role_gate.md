# AI-052 — Observed Transitions — Session 5

> **Session 5 of 6** — ARIA role-aware candidate collection (optional defence).
> Plan: `docs/plans/AI-052_observed_transitions_plan.md` (read §0 + this session).
> Date: 2026-08-23

---

## What was built

**Penalty-first role gate in the element matcher's fast passes** (`src/element_matcher.py`).

### The gap

Passes 0/D/1/2 return their first match outright. A heading or text field
sharing words with the description could win a CLICK **before** the
role-aware scoring pass (Pass 3, with its `_click_role_bonus` /
B-045 fillable penalties) ever ran — a second, independent line of defence
for the day scoping is ever empty again.

### The mechanism

- `ElementMatcher.role_contradicts_click(element)` — True when the element's
  **effective ARIA role** (`computed_role` authoritative, falling back to
  `role`) is a heading / status / banner-class region, or a text-entry role
  (`textbox`, `searchbox`, `combobox`, …), or the element is structurally
  fillable (`_is_fillable`). Deliberately conservative: generic `div`/`span`
  containers stay fully eligible (B-025 clickable containers depend on them).
- In `find_best_element_for_current_page` (and `find_best_elements_batch`),
  a fast-pass CLICK match that contradicts is **deferred**, not dropped:
  deeper role-aware passes compete, and the first deferred candidate is
  returned as a **last resort** if every pass fails. Excluded (B-014)
  candidates never enter the deferred slot.
- FILL and ASSERT are untouched (FILL has its own fillability gate; ASSERT
  keeps B-016 display-role preference).

## Gate results

| Gate | Result |
|---|---|
| `scripts/smoke.py --json` | ✅ 39/39 |
| `ruff` / `mypy src/ cli/` | ✅ |
| `pytest tests/ -n 3` | ✅ **2735 passed**, 1 skipped (+9 S5 tests) |
| eval static | ✅ 97.9% (unchanged) |
| **eval full `--mode full --regenerate`** | ✅ 58/109 = **53.2%** resolution; FP rate **26.7%** — identical to the historical same-model leg (qwen3.8, leg G: 26.7%) |
| **eval resolver-mode A/B (S5 on vs off)** | ✅ **97.9% = 97.9%** — deterministic, zero golden regressions from the gate |
| `verify_production` | not re-run — resolver A/B proves no resolution change on goldens; S3/S4 site profiles stand (0 different-page errors both sites) |

## Reading the eval-full number honestly

Full-mode resolution accuracy (53.2%) is below the pre-AI-052 historical leg
(62.4%, qwen3.8) — **by design, and not attributable to S5**:

- S3/S4 convert wrong-page resolutions into honest skips, which the metric
  scores as "unresolved" (the plan explicitly accepted this: "a shorter
  journey is better than a complete-but-wrong one").
- The resolver-mode A/B (identical golden skeletons, gate on vs off) is
  byte-for-byte equal at 97.9% — the role gate changed nothing on golden
  resolutions, deterministically, without LLM regeneration noise.
- False-positive rate matches the historical leg exactly (26.7% vs 26.7%).

## Files changed

| File | Change |
|---|---|
| `src/element_matcher.py` | `_CLICK_CONTRADICTORY_ROLES` + `_CLICK_FILLABLE_ARIA_ROLES`, `role_contradicts_click`, penalty-first deferral in both resolution entry points |
| `tests/test_element_matcher_role_gate.py` | **new** — 9 tests (deferral, last-resort fallback, computed_role precedence, FILL/ASSERT isolation, batch gate, exclusion safety) |

## Next

**Session 6** — regression sweep (`uat.py --all-sites`), docs sync, BACKLOG/ROADMAP
status flip to ✅, ship.
