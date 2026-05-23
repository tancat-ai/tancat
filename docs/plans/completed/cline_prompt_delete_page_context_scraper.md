# Cline Task: Verify and delete deprecated src/page_context_scraper.py

## Context
`src/page_context_scraper.py` is 2,023 lines and is marked DEPRECATED at line 1
with the following note:

> DEPRECATED — DO NOT USE IN NEW CODE
> This module was retired because it injected selectors directly into LLM prompts,
> causing hallucination. Replaced by the skeleton-first two-phase pipeline.
> DO NOT restore this scraper in the pipeline. Use src/scraper.py (PageScraper) only.

Before deleting it, you must verify nothing in the active pipeline still imports it.

---

## Step 1: Audit imports — do this before touching any file

Run these searches and report what you find:
```bash
grep -r "from src.page_context_scraper" src/ streamlit_app.py --include="*.py"
grep -r "import page_context_scraper" src/ streamlit_app.py --include="*.py"
grep -r "from src.page_context_scraper" tests/ --include="*.py"
```

### If the active pipeline files import it (src/ or streamlit_app.py):
Stop. Do not delete the file. Add an entry to BACKLOG.md documenting which files
still import from the deprecated module and what they use. That is a separate
remediation task. Mark this task as blocked and report to the user.

### If only tests/ or cli/ import it:
Proceed to Step 2.

### If nothing imports it:
Proceed directly to Step 3 (skip Step 2).

---

## Step 2: Handle test and cli/ imports

If `tests/test_page_context_scraper.py` imports from this module, the test file
should be deleted alongside the module — it is testing deprecated code.

If `cli/test_orchestrator.py` imports from this module, check whether `cli/` is
confirmed as legacy (no active import chain from `streamlit_app.py` or `src/`
reaches `cli/`). If confirmed legacy, it can also be removed.

For each file you intend to delete, confirm it has no active callers before deleting.

---

## Step 3: Delete the deprecated file

```bash
git rm src/page_context_scraper.py
```

If test or cli files were confirmed removable in Step 2:
```bash
git rm tests/test_page_context_scraper.py   # only if confirmed
git rm cli/test_orchestrator.py              # only if confirmed
```

---

## Verification steps — ALL must pass before declaring done

### Step 1: No import errors
```bash
python -c "import streamlit_app"
python -c "from src.orchestrator import TestOrchestrator"
```
Both must complete without error.

### Step 2: Linting
```bash
bash fix.sh
```
Must complete with no errors.

### Step 3: Unit tests
```bash
pytest tests/ -v --tb=short
```
Count passing tests before you begin. Must match after (or increase if deprecated
test files were removed — record the before/after counts explicitly).

### Step 4: UAT — mandatory
```bash
python uat_full_pipeline.py
```
Must complete without error. If a live LLM is required and unavailable, say so
explicitly — do NOT skip and declare done.

---

## Stop conditions
- If Step 1 audit reveals active pipeline imports, stop and report — do not delete
- Do not fix unrelated issues discovered during this task
- Document anything unexpected in BACKLOG.md before stopping

---

## Key rules (from AGENTS.md)
- Use `git rm` not `rm` so the deletion is tracked
- Commit only after all verification steps pass
- Commit message must not contain backticks
