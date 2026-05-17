# Resolver Restructure Plan
## AI Playwright Test Generator — Placeholder Resolution Overhaul

**Purpose**: Clean up dead code in the resolver layer, restructure resolution to use an LLM-first priority chain, and put process guardrails in place to prevent zombie code recurring.

**Golden rule for this work**: Each phase must be fully verified before the next begins. No phase is "mostly done". Green gate means `bash fix.sh` clean + `pytest tests/ -v` passing + `uat_full_pipeline.py` passing.

---

## Phase 0 — Audit (no code changes)

**Goal**: Know exactly what is live, what is dead, and what the current resolution path actually is before touching anything.

**Do this with Claude, not Cline.**

### Step 0.1 — Run vulture
```bash
pip install vulture --break-system-packages
vulture src/ --min-confidence 80 > vulture_report.txt
cat vulture_report.txt
```
Share the output with Claude. Do not act on it yet — just collect it.

### Step 0.2 — Trace the live call graph manually
Share these files with Claude one session and trace the actual execution path from pipeline entry to resolved selector:
- `src/orchestrator.py`
- `src/semantic_candidate_ranker.py`
- `src/intent_matcher.py`
- `src/locator_builder.py`

From the two files already reviewed, the suspected dead methods are:

| Method | File | Status | Evidence |
|--------|------|---------|----------|
| `find_best_match()` | `placeholder_resolver.py` | Suspected dead | Orchestrator calls `rank_candidates()` directly; comment at line 579 confirms bypass |
| `find_best_element()` | `placeholder_resolver.py` | Suspected dead | Only callable via `find_best_match()` |
| `resolve_all()` | `placeholder_resolver.py` | Suspected dead | Not called from orchestrator path |
| `_disambiguate_with_llm()` | `placeholder_resolver.py` | Suspected dead | Lives in resolver path; orchestrator uses `semantic_ranker` instead |

These need confirming against `orchestrator.py` before deletion.

### Step 0.3 — Document findings
Add a **Live Call Graph** section to `PROJECT_KNOWLEDGE.md` in this format:

```
## Live Call Graph (Resolution Path)

Entry: orchestrator.py → PlaceholderOrchestrator.resolve_placeholders()
  → _replace_placeholders_sequentially()
    → _resolve_placeholder_for_page()
      → _find_best_element_for_current_page()
        → PlaceholderResolver.rank_candidates()
        → SemanticCandidateRanker.choose_best_candidate()  [if shortlist > 1]
      → _validate_text_match()
      → build_robust_locator()

## Dead Code (confirmed, do not resurrect)
- PlaceholderResolver.find_best_match() — bypassed, see commit [hash]
- PlaceholderResolver.find_best_element() — bypassed, see commit [hash]
- PlaceholderResolver.resolve_all() — bypassed, see commit [hash]
- PlaceholderResolver._disambiguate_with_llm() — superseded by SemanticCandidateRanker
```

This section is the source of truth Cline must read before any resolver work.

### Step 0.4 — Run audit_3d_map.py
```bash
python scripts/audit_3d_map.py
```
Note dead nodes and dead links. These will be cleaned up after dead code deletion (Phase 2 end).

**Phase 0 exit criteria**: Live call graph documented in `PROJECT_KNOWLEDGE.md`. Dead method list confirmed. No code changed.

**Status (2026-05-17):** ✅ Complete

---

## Phase 1 — Dead Code Deletion

**Goal**: Remove confirmed dead methods so Cline cannot rediscover and reactivate them.

**Do this with Cline, one session per file, with explicit dead method lists.**

### Rules for each deletion session
- Share only the file being modified
- Tell Cline exactly which methods to delete by name
- Tell Cline exactly which imports become unused after deletion (remove those too)
- No other changes — no refactoring, no renames, no "while I'm here" edits
- Run green gate after each session before starting the next

### Session 1.1 — placeholder_resolver.py dead method removal
**Cline prompt template**:
```
In src/placeholder_resolver.py, delete the following methods entirely:
- find_best_match()
- find_best_element()  
- resolve_all()
- _disambiguate_with_llm()

Also remove any imports that become unused after these deletions.
Do not modify any other methods. Do not refactor. Stop after the deletions.
Verify: grep -n "find_best_match\|find_best_element\|resolve_all\|_disambiguate_with_llm" src/ -r
should return zero results outside of test files.
```

**After session**: Check if any unit tests in `tests/test_placeholder_resolver.py` test the deleted methods. If so, delete those test cases too (they were testing dead code). Green gate.

### Session 1.2 — Any other dead files/methods surfaced by vulture
One Cline session per file. Same template as above.

### Session 1.3 — Update 3D map
```bash
python scripts/generate_3d_map.py
python scripts/audit_3d_map.py
```
Remove any IMPORT_LINKS entries in `generate_3d_map.py` that referenced deleted methods' modules.

**Phase 1 exit criteria**: `vulture src/ --min-confidence 80` shows no methods from the confirmed dead list. Green gate passing. 3D map regenerated. Commit: `chore: remove dead resolver methods`.

**Status (2026-05-17):** ✅ Complete — methods deleted; tests use `tests/resolver_test_helpers.py`; `test_placeholder_resolver_disambiguation.py` removed.

---

## Phase 2 — LLM-First Resolution Restructure

**Goal**: Replace the complex unified scoring system with a transparent priority chain. Design with Claude, implement with Cline.

### The new resolution priority chain

```
Given: action, description, scraped candidates for current page

Pass 1 — Exact text match
  For each candidate:
    if candidate.text is contained in description (or vice versa, normalised):
      return candidate
  → If match found: done. No LLM needed.

Pass 2 — Structural attribute match  
  For each candidate:
    if data-test or id or aria-label keywords overlap strongly with description:
      return candidate
  → If match found: done. No LLM needed.

Pass 3 — LLM arbitration
  Take top N candidates by existing word-overlap score (keep rank_candidates() for this)
  Send to LLM: "Given action=CLICK, description='products link in header navigation',
    which of these N elements is the correct match? Return index only."
  → LLM returns winner. Log which pass fired.

Pass 4 — Skip
  emit pytest.skip() with URL and description
```

**Key principles**:
- Pass 1 and 2 are deterministic and fast — no LLM cost
- LLM is called only when genuinely ambiguous (multiple plausible candidates)
- `rank_candidates()` is kept as a utility to produce the shortlist for Pass 3, not as the decision-maker
- Every resolution logs which pass fired — gives you the verbose output you wanted without a separate flag
- ASSERT tokens get a modified Pass 1 that looks at text-bearing elements (p, h*, span, div with text) not just interactive ones

### What changes vs what stays

**Stays**:
- `rank_candidates()` — used to produce shortlist for Pass 3 only
- `SemanticCandidateRanker.choose_best_candidate()` — becomes the Pass 3 LLM call
- `build_robust_locator()` — unchanged
- `_validate_text_match()` — logic moves into Pass 1, method deleted

**Changes**:
- `_find_best_element_for_current_page()` — rewritten as priority chain
- `_validate_text_match()` — absorbed into Pass 1 logic, method removed
- Shortlist `[:4]` cap — removed (no longer needed; LLM shortlist is explicit)
- `global_top_score - 2` threshold — removed (Pass 1 and 2 don't use scoring)

**New**:
- Resolution pass logged per token: `[RESOLVE] Token: X | Pass: 1 (text match) | Winner: selector`
- ASSERT-specific path in Pass 1 that filters for text-bearing elements

### Design session (with Claude before Cline)
Before writing the Cline spec, share:
- `src/semantic_candidate_ranker.py` — to confirm it can be reused as Pass 3 as-is
- `src/locator_builder.py` — to confirm build_robust_locator() interface is unchanged

Then write a precise spec with before/after code blocks for `_find_best_element_for_current_page()` before handing to Cline.

### Cline session structure for Phase 2
Split into three sessions:

**Session 2.1**: Rewrite `_find_best_element_for_current_page()` in `placeholder_orchestrator.py` only. Green gate.

**Session 2.2**: Add resolution pass logging. Green gate.

**Session 2.3**: ASSERT-specific Pass 1 path. Green gate.

One UAT run after all three sessions before commit.

**Phase 2 exit criteria**: UAT passing. Resolution pass visible in output. `tests/uat_full_pipeline.py` green. Commit: `feat: LLM-first priority chain resolver`.

**Status (2026-05-17):** 🟡 Partial — Sessions 2.1–2.2 done (Pass 1 CLICK/FILL + ASSERT text, Pass 2 structural, `[RESOLVE]` logging). Pass 3 still uses legacy shortlist/threshold + `SemanticCandidateRanker`. Session 2.3 / full UAT pending.

---

## Phase 3 — Process Guardrails

**Goal**: Make it structurally harder for Cline to resurrect dead code or drift into wrong files.

### 3.1 — PROJECT_KNOWLEDGE.md additions
- Live call graph section (from Phase 0)
- Dead code section with commit hashes (from Phase 1)
- A "Resolver architecture" section describing the priority chain and naming the three passes

### 3.2 — .clinerules additions
Add these rules:
```
## Resolver Work
- Before any change to placeholder_resolver.py or placeholder_orchestrator.py,
  read the "Live Call Graph" section of PROJECT_KNOWLEDGE.md.
- Do not call or reference any method listed in the "Dead Code" section of
  PROJECT_KNOWLEDGE.md without explicit approval from the user.
- The live resolution entry point is _find_best_element_for_current_page() in
  placeholder_orchestrator.py. Do not route resolution through find_best_match(),
  find_best_element(), or resolve_all() — these are deleted.

## Green Gate
- uat_full_pipeline.py must pass before any pipeline fix is declared complete.
  Unit tests with mocked dependencies do not satisfy this requirement.

## Session Discipline  
- Stop after completing the explicitly named task.
- Do not refactor, rename, or modify files not named in the prompt.
```

### 3.3 — BACKLOG.md
Add a standing item: "After any resolver session, run vulture src/ --min-confidence 80 and check for new dead methods."

### 3.4 — generate_3d_map.py
After Phase 1 deletions, update IMPORT_LINKS to reflect the actual post-deletion import graph. Run the audit script and verify zero dead links in the resolver/orchestrator cluster.

**Phase 3 exit criteria**: .clinerules committed. PROJECT_KNOWLEDGE.md updated. 3D map regenerated and audit clean.

---

## Sequencing Summary

| Phase | What | Who | Verifier |
|-------|------|-----|----------|
| 0 | Audit — trace live path, run vulture | Claude + Louis | PROJECT_KNOWLEDGE.md updated |
| 1.1 | Delete dead resolver methods | Cline | Green gate + vulture clean |
| 1.2 | Delete any other vulture findings | Cline | Green gate |
| 1.3 | Regenerate 3D map | Louis | audit_3d_map.py clean |
| 2.A | Design session — confirm ranker/locator interfaces | Claude + Louis | Spec written |
| 2.1 | Rewrite _find_best_element_for_current_page() | Cline | Green gate |
| 2.2 | Add resolution pass logging | Cline | Green gate |
| 2.3 | ASSERT-specific Pass 1 path | Cline | Green gate |
| 2.UAT | Full UAT run | Louis | uat_full_pipeline.py green |
| 3 | .clinerules + PROJECT_KNOWLEDGE.md + 3D map | Louis + Cline | Committed |

---

## What Not To Do

- Do not start Phase 2 before Phase 1 is complete — restructuring around dead code will replicate the confusion
- Do not let Cline combine phases — "clean up and restructure" in one session is how things go wrong
- Do not skip the design session before 2.1 — `_find_best_element_for_current_page()` is the core of the live path and needs precise before/after code blocks before Cline touches it
- Do not declare UAT passing based on unit tests — `uat_full_pipeline.py` on SauceDemo (Docker) is the bar
