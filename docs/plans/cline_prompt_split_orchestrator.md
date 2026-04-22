# Cline Task: Split src/orchestrator.py into focused modules

## Context
`src/orchestrator.py` is 1,165 lines and contains five distinct concerns mixed together.
This task extracts three of those concerns into new modules, leaving `orchestrator.py` 
as a pure coordination layer. **No logic must change — this is a mechanical move only.**

---

## What you will create

### 1. `src/url_utils.py` — NEW FILE
A module of pure URL-manipulation helpers. All functions are currently static methods 
on `TestOrchestrator`. Extract them exactly as-is, converting from `@staticmethod` 
methods to module-level functions.

Extract these five methods:
- `_extract_seed_domain(seed_urls)`
- `_filter_urls_to_allowed_domain(urls, allowed_domains)` — keep the logger.warning call; 
  import logging at the top of the new file
- `_extract_route_concepts(texts)`
- `_build_common_path_candidates(seed_urls, concepts)`
- `_heuristic_url_from_description(current_url, description)`

Remove the leading underscore from names when making them module-level functions 
(e.g. `_extract_seed_domain` → `extract_seed_domain`). This is the public API now.

Required imports for `src/url_utils.py`:
```python
from __future__ import annotations
import logging
from urllib.parse import urljoin, urlparse

logger = logging.getLogger(__name__)
```

---

### 2. `src/code_postprocessor.py` — NEW FILE
A module of pure code-string transformation helpers. All are currently static methods 
on `TestOrchestrator`. Extract them as module-level functions.

Extract these methods:
- `_normalise_generated_code(code, consent_mode)` — note this currently calls 
  `TestOrchestrator._inject_import(...)` internally; update those calls to just 
  `_inject_import(...)` since they will be in the same module
- `_replace_token_in_line(line, action, token, resolved_value, duplicate_selectors, description)`
- `_replace_remaining_placeholders(code)`
- `_flatten_inner_functions(code)`
- `_inject_import(code, import_line)`
- `_rewrite_page_references_in_class_methods(code)`
- `_inject_consent_helper(code)`
- `_ensure_test_navigation(code)`

Remove the leading underscore from all names when making them module-level functions.

Required imports for `src/code_postprocessor.py`:
```python
from __future__ import annotations
import re
```

---

### 3. Add to `src/prompt_utils.py` — EXISTING FILE, ADD ONLY
Do NOT replace this file. Add the following three functions to the bottom of the 
existing file. They are currently static/instance methods on `TestOrchestrator`.

Extract these methods:
- `_count_conditions(conditions)` → `count_conditions(conditions)`
- `_prepare_conditions_for_generation(conditions)` → `prepare_conditions_for_generation(conditions)`
- `_build_retry_conditions(prepared_conditions, expected_test_count)` → `build_retry_conditions(prepared_conditions, expected_test_count)`

`_prepare_conditions_for_generation` currently uses `re` — check if `re` is already 
imported in `prompt_utils.py` and add it if not.

---

## What you will modify

### `src/orchestrator.py`
- Delete all nine methods listed above from the `TestOrchestrator` class
- Update all internal calls within `orchestrator.py` to use the new module-level 
  functions instead, with the new names (no leading underscores)
- Add these imports at the top of `src/orchestrator.py`:
  ```python
  from src.url_utils import (
      extract_seed_domain,
      filter_urls_to_allowed_domain,
      extract_route_concepts,
      build_common_path_candidates,
      heuristic_url_from_description,
  )
  from src.code_postprocessor import (
      normalise_generated_code,
      replace_token_in_line,
  )
  from src.prompt_utils import (
      count_conditions,
      prepare_conditions_for_generation,
      build_retry_conditions,
  )
  ```
- Note: `_replace_placeholders_sequentially` stays in `orchestrator.py` — it uses 
  `replace_token_in_line` from `code_postprocessor` but the coordination logic stays here
- Note: `_normalise_generated_code` is called as `self._normalise_generated_code(...)` 
  on line ~209 — update this call to `normalise_generated_code(...)` (no self)

### `tests/test_orchestrator.py`
- Check if any tests directly test the methods being extracted. If so, those tests 
  should move to the appropriate new test file. Do NOT delete them.
- Add import of new modules to any tests that need them

### Create `tests/test_url_utils.py` — NEW FILE
- Move any orchestrator tests that cover the extracted URL methods here
- If none exist, create a minimal smoke test that imports the module and calls 
  each function with a basic input to confirm the module loads correctly

### Create `tests/test_code_postprocessor.py` — NEW FILE
- Move any orchestrator tests that cover the extracted code postprocessor methods here
- If none exist, create a minimal smoke test as above

---

## What you must NOT touch
- `src/placeholder_resolver.py` — do not modify
- `src/llm_client.py` — do not modify
- `src/llm_providers/__init__.py` — do not modify
- `src/pipeline_models.py` — do not modify
- Any file not listed in "What you will modify" above

---

## Verification steps — ALL must pass before declaring done

### Step 1: Syntax check
```bash
python -c "from src.url_utils import extract_seed_domain"
python -c "from src.code_postprocessor import normalise_generated_code"
python -c "from src.prompt_utils import count_conditions"
python -c "from src.orchestrator import TestOrchestrator"
```
All four must complete without error.

### Step 2: Linting
```bash
bash fix.sh
```
Must complete with no errors.

### Step 3: Unit tests
```bash
pytest tests/ -v --tb=short
```
Must pass with the same number of passing tests as before this task started.
Count the passing tests before you begin and confirm the count matches after.

### Step 4: UAT — this is mandatory, unit tests alone are not sufficient
```bash
python uat_full_pipeline.py
```
This must complete without error. If it requires a live LLM and none is available, 
say so explicitly — do NOT skip this step and declare the task done.

---

## Stop conditions
- Stop after completing verification Step 4
- Do not proceed to fix any unrelated issues you discover during this task
- If you find a bug in a file you are not supposed to touch, document it in 
  BACKLOG.md and stop — do not fix it
- If any verification step fails, diagnose and fix within the scope of this 
  task only (the split itself), then re-run from Step 1

---

## Key rules (from AGENTS.md)
- Use `uv add` if any new dependency is needed — do NOT use pip
- All functions must have full type annotations
- Do not remove any existing type hints
- Commit only after all four verification steps pass
- Commit message must not contain backticks
