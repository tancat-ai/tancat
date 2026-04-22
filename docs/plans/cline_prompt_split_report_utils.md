# Cline Task: Split src/report_utils.py into focused modules

## Context
`src/report_utils.py` is 1,262 lines with three distinct concerns mixed together:
data preparation, standard report rendering, and evidence/annotated report generation.
This task separates them. **No logic must change — mechanical move only.**

---

## What you will create

### 1. `src/report_builder.py` — NEW FILE
Data preparation functions that convert coverage analysis and run results into the
`list[dict]` format consumed by the renderers. Also contains shared private helpers.

Extract these functions exactly as-is:
- `escape_html(text)`
- `_normalise_test_name(name)` — keep leading underscore, module-private
- `_find_matching_run_result(run_map, test_name)` — keep leading underscore, module-private
- `build_report_dicts(coverage_analysis, run_result)`
- `_status_summary(coverage)` — keep leading underscore, module-private
- `_status_icon(status)` — keep leading underscore, module-private

Required imports for `src/report_builder.py`:
```python
from __future__ import annotations
import html as _html
from typing import Any
from src.pytest_output_parser import RunResult, TestResult
```

---

### 2. `src/report_formatters.py` — NEW FILE
The three standard report format renderers. Each takes a `list[dict]` and returns
a string. They depend on `_status_summary` and `_status_icon` from `report_builder`.

Extract these functions exactly as-is:
- `generate_local_report(coverage)`
- `generate_jira_report(coverage, test_execution_date)`
- `generate_html_report(coverage, screenshots_dir)` — keep `embed_screenshot`
  as an inner function inside `generate_html_report`, do not extract it

Required imports for `src/report_formatters.py`:
```python
from __future__ import annotations
import base64
from datetime import datetime
from pathlib import Path
from typing import Any
from src.report_builder import _status_summary, _status_icon
```

---

### 3. `src/evidence_report.py` — NEW FILE
The annotated screenshot, journey, and heatmap generators. These read `.evidence.json`
sidecar files from disk and produce HTML strings. Entirely independent of the standard
report renderers.

Move the colour constant first, then extract these functions exactly as-is:
- `_EVIDENCE_STEP_COLORS` dict — move here as a module-level constant
- `_safe_read_json(path)`
- `_safe_embed_image_data_uri(image_path)`
- `_normalise_url(url)`
- `_clean_evidence_label(label)`
- `_prepare_steps_for_display(steps)`
- `_extract_step_points_by_url(sidecar)` — keep `is_meaningful_screenshot` and
  `flush_segment` as inner functions
- `generate_suite_heatmap(*, evidence_dir, page_url)`
- `generate_annotated_screenshot(*, evidence_dir, test_name, page_url)`
- `generate_annotated_journey(*, evidence_dir, test_name)` — keep `flush` as
  an inner function

Required imports for `src/evidence_report.py`:
```python
from __future__ import annotations
import base64
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit, urlunsplit
```

---

## What you will modify

### `src/report_utils.py`
Replace the entire file contents with a backwards-compatible re-export shim so that
all existing callers continue to work without any changes:

```python
"""Backwards-compatible re-exports. Import from specific modules in new code."""
from src.report_builder import build_report_dicts, escape_html
from src.report_formatters import (
    generate_html_report,
    generate_jira_report,
    generate_local_report,
)
from src.evidence_report import (
    generate_annotated_journey,
    generate_annotated_screenshot,
    generate_suite_heatmap,
)

__all__ = [
    "build_report_dicts",
    "escape_html",
    "generate_annotated_journey",
    "generate_annotated_screenshot",
    "generate_html_report",
    "generate_jira_report",
    "generate_local_report",
    "generate_suite_heatmap",
]
```

This means `streamlit_app.py` and all test files need NO changes.
Verify this is the case before touching any other file.

---

## What you must NOT touch
- `src/llm_client.py`
- `src/llm_providers/__init__.py`
- `src/pipeline_models.py`
- `src/orchestrator.py`
- `streamlit_app.py`
- `tests/test_report_utils.py`
- Any file not listed in "What you will modify" above

---

## Verification steps — ALL must pass before declaring done

### Step 1: Syntax check
```bash
python -c "from src.report_builder import build_report_dicts, escape_html"
python -c "from src.report_formatters import generate_html_report, generate_local_report, generate_jira_report"
python -c "from src.evidence_report import generate_suite_heatmap, generate_annotated_screenshot"
python -c "from src.report_utils import build_report_dicts, generate_html_report, generate_suite_heatmap"
```
All four must complete without error. The fourth confirms the shim works.

### Step 2: Linting
```bash
bash fix.sh
```
Must complete with no errors.

### Step 3: Unit tests
```bash
pytest tests/test_report_utils.py -v --tb=short
```
Run report tests first to confirm the shim works. Then run the full suite:
```bash
pytest tests/ -v --tb=short
```
Count passing tests before you begin. Must match after.

### Step 4: UAT — mandatory, unit tests alone are not sufficient
```bash
python uat_full_pipeline.py
```
Must complete without error. If a live LLM is required and unavailable, say so
explicitly — do NOT skip and declare done.

---

## Stop conditions
- Stop after Step 4
- Do not fix unrelated issues discovered during this task
- If you find a bug in a file you are not supposed to touch, document it in
  BACKLOG.md and stop
- If any verification step fails, diagnose and fix within the scope of this
  split only, then re-run from Step 1

---

## Key rules (from AGENTS.md)
- Use `uv add` for any new dependencies — never pip
- All functions must retain full type annotations
- Commit only after all four verification steps pass
- Commit message must not contain backticks
