# AI-054 — Pipeline consolidation & testing-strategy review

> **Date:** 2026-08-23
> **Backlog:** AI-054 (📋 review)
> **Trigger:** post-ship test-coverage audit after AI-051/052/053 closed (both live sites fully green).

---

## Why this exists

After shipping AI-051/052/053, we audited **what we actually tested vs what we
didn't** (unit, UAT, eval static/full, RAG, LangGraph, linear, flat,
code-postprocessor/export, flakiness). The honest gaps consolidated into six
related facets of one question: *"what do we maintain, and when do we test it?"*
Recorded as a single backlog item (AI-054) rather than six scattered entries.
No code changes implied yet — this is a decision + test-strategy record; fixes
are added here as they get scoped.

## The six facets (summary — full detail in BACKLOG.md)

1. **One pipeline? (linear vs LangGraph)** — ⏸️ **UNDECIDED, pending research.**
   Linear is the production default; the graph path is built + unit-tested but
   dormant (never default — eval was worse: linear 88.1% vs graph 32.8%).
   Recorded diagnosis (`2026-07-29_eval_baseline_restoration.md`): the gap is the
   **scraper**, not the architecture — graph generates broader skeletons the
   scraper can't keep up with. The user wants to research the two pipelines'
   real tradeoffs + **market direction** before deciding. Candidate outcomes:
   keep-dormant / invest-in-scraper-then-reactivate / delete.

2. **RAG** — already settled in code: **always-on by default** (B-036), graceful
   degradation, `RAG_ENABLED=0` opts out (hermetic tests + CI). The real gap:
   this session's verify/uat/eval ran **RAG-off**, so RAG + the trail fix were
   never seen composing live. Test trigger: one RAG-ON verify.

3. **thinking=ON** — switch shipped (AI-050), but a valid verdict is **model-
   gated** by AI-046 (the 3.8 GGUF is Q2_K-heavy, so the earlier thinking-ON A/B
   is a quantization confound). Test trigger: matched-precision re-test, paired
   with flakiness.

4. **Flat (non-POM) mode** — keep; it's mode parity, not a feature. Test trigger:
   one flat UAT after structural pipeline changes. (All this session's runs were POM.)

5. **Export / code-postprocessor** — the one buildable piece: bring export
   quality to a bar we're happy with, then add a **regression gate** so pipeline
   changes are checked against evidence export.

6. **Flakiness** — don't chase constantly; measure it **during the thinking
   re-test** (#3). Known candidate: the `--all-sites` UAT saucedemo leg that
   timed out under GPU contention.

## Test cadence rollup

| Trigger | Run |
|---------|-----|
| Structural pipeline change | eval static (gate) + one flat UAT + one RAG-ON verify |
| Thinking re-test / model change | thinking-ON A/B + GSM8K + flakiness/determinism |
| Export / code_postprocessor touch | export-quality pass + evidence-export regression gate |
| Before any ship | smoke → pytest → verify_production (both sites) → eval static → ruff/mypy → CI |

## What was NOT done here

No code changes, no re-running of the skipped layers (eval full, slow/integration
markers, RAG-ON, graph E2E, flat) — those are the *triggers* above, to be run
when their condition occurs. This session only **recorded** the strategy.
