# Cline Task: Refactor CLI to be a thin front-end over src/

## Context

The CLI module (`cli/`) has ~2,877 lines across 7 files with significant duplication of functionality already in `src/`. The goal is to make CLI a thin coordination layer (like `streamlit_app.py`) that delegates to `src/` modules, while keeping CLI-specific logic (argparse, format detection) in CLI.

**Architecture goal:**
```
CLI (front-end, ~400 lines) → src/ (brain, ~2,400+ lines) → LLM/external
```

---

## Files to DELETE (CLI routes to src/)

### 1. `cli/test_orchestrator.py` (402 lines) → DELETE

This file's `TestCaseOrchestrator` duplicates `src/orchestrator.TestOrchestrator`.

**Replacement:**
- `cli/main.py` line 109: `from cli.test_orchestrator import TestCaseOrchestrator` → `from src.orchestrator import TestOrchestrator`
- Replace `TestCaseOrchestrator().process(...)` with `TestOrchestrator().generate_tests_from_story(...)`
- Check what methods `TestCaseOrchestrator` calls and ensure `TestOrchestrator` has equivalent API

**Impact:** -402 lines in CLI, zero lines added in src/

### 2. `cli/story_analyzer.py` (443 lines) → DELETE

This provides keyword-based analysis that overlaps with `src/spec_analyzer.py` (LLM-based).

**Replacement:**
- Create lightweight `src/analyzer.py` with a `KeywordAnalyzer` class (can be extracted from `cli/story_analyzer.py`)
- OR: Have CLI call `src/spec_analyzer.py` directly for LLM-based analysis
- The keyword analyzer is fast and doesn't need LLM — best to keep as a thin src/ module

**Impact:** -443 lines in CLI, ~50 lines added in src/ (if extracting KeywordAnalyzer)

---

## Files to MODIFY (CLI-specific logic, keep but clean up)

### 3. `cli/config.py` (158 lines) → MODIFY

**Action:** Consolidate enums into `src/config.py`, have `cli/config.py` re-export.

**Create `src/config.py`:**
```python
"""Centralized configuration for AI Playwright Test Generator."""
from __future__ import annotations
import os
from enum import Enum

class AnalysisMode(Enum):
    FAST = "fast"
    THOROUGH = "thorough"
    AUTO = "auto"

class ReportFormat(Enum):
    CONFLUENCE = "confluence"
    JIRA_XML = "jira_xml"
    JSON = "json"
    MARKDOWN = "markdown"
    LOCAL = "local"
    JIRA = "jira"
    SHAREABLE = "shareable"

class DetectionMode(Enum):
    AUTO = "auto"
    EXPLICIT = "explicit"
    FAST = "fast"
    THOROUGH = "thorough"

class CaptureLevel(Enum):
    BASIC = "basic"
    STANDARD = "standard"
    THOROUGH = "thorough"

class ScreenshotNaming(Enum):
    SEQUENTIAL = "sequential"
    DESCRIPTIVE = "descriptive"
    HYBRID = "hybrid"

# Global defaults
JIRA_PROJECT_KEY: str = os.getenv("JIRA_PROJECT_KEY", "TEST")
```

**Update `cli/config.py` to re-export:**
```python
"""Backwards-compatible re-exports for CLI."""
from src.config import (
    AnalysisMode,
    CaptureLevel,
    DetectionMode,
    JIRA_PROJECT_KEY,
    ReportFormat,
    ScreenshotNaming,
)

# CLI-specific AppConfig dataclass can stay here or move to src/
```

**Impact:** -108 lines in CLI, +60 lines in src/

### 4. `cli/input_parser.py` (581 lines) → MODIFY

**Action:** Keep format detection logic (Jira/Gherkin/bullets parsers) — this is CLI-specific user input handling. But have it import from `src/user_story_parser.py` for actual user story extraction.

**Changes:**
- Keep `FormatDetector`, `JiraParser`, `GherkinParser`, `BulletParser`, `PlainTextParser`
- Replace internal parsing calls with `from src.user_story_parser import parse_user_story`
- Keep `TestCase`, `ParsedInput` dataclasses (or import from src/)

**Impact:** -100 lines in CLI (clean up internal calls), zero in src/

### 5. `cli/evidence_generator.py` (424 lines) → MODIFY

**Action:** Keep screenshot capture logic (CLI-specific). Route report generation to `src/report_formatters.py`.

**Changes:**
- Keep `ScreenshotCapturer`, `EvidenceCollection`
- Replace HTML report generation with calls to `src/report_formatters.generate_local_report`
- Keep `BugEvidenceGenerator` as-is

**Impact:** -80 lines in CLI, zero in src/

### 6. `cli/report_generator.py` (425 lines) → MODIFY

**Action:** This generates Jira test case entries from analyzed data. Different from `src/report_formatters.py` which generates coverage reports. Keep but simplify.

**Changes:**
- Keep `JiraTestCase`, `TestExecutionResult`, `JiraReportGenerator`
- Replace HTML report generation with calls to `src/report_formatters`
- Import report rendering from src/

**Impact:** -60 lines in CLI, zero in src/

### 7. `cli/main.py` (218 lines) → MODIFY

**Action:** Update imports to use new src/ modules.

**Changes:**
- Line 14: `from cli.story_analyzer` → `from src.analyzer import KeywordAnalyzer` (or similar)
- Line 109: `from cli.test_orchestrator` → `from src.orchestrator import TestOrchestrator`
- Line 121: `from cli.evidence_generator` → keep but call src/ report functions
- Line 129: `from cli.report_generator` → keep but call src/ report functions

**Impact:** ~20 lines changed, zero added

---

## Files to CREATE in src/

### 1. `src/config.py` — NEW FILE

Consolidated enums and defaults. See section "Files to MODIFY" #3 above.

### 2. `src/analyzer.py` — NEW FILE (OPTIONAL)

Thin wrapper around keyword-based analysis extracted from `cli/story_analyzer.py`.

```python
"""Keyword-based test case analyzer (fast, no LLM required)."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

@dataclass
class AnalyzedTestCase:
    title: str
    description: str
    identified_actions: list[str] = field(default_factory=list)
    identified_expectations: list[str] = field(default_factory=list)
    suggested_data: dict[str, Any] = field(default_factory=dict)
    estimated_complexity: str = "low"

class KeywordAnalyzer:
    @classmethod
    def analyze(cls, title: str, description: str) -> AnalyzedTestCase:
        ...
```

**Impact:** ~80 lines in src/

---

## What you will NOT touch
- `src/orchestrator.py` — already split, stable
- `src/url_utils.py` — already created
- `src/code_postprocessor.py` — already created
- `src/report_builder.py` — already created
- `src/report_formatters.py` — already created
- `src/evidence_report.py` — already created
- `src/scraper.py` — stable
- `src/test_generator.py` — PROTECTED
- `src/llm_client.py` — PROTECTED
- `streamlit_app.py` — out of scope
- `tests/` — update imports only, don't add new tests

---

## Verification steps — ALL must pass before declaring done

### Step 1: Syntax check
```bash
python -c "from src.config import AnalysisMode, ReportFormat"
python -c "from src.analyzer import KeywordAnalyzer"
python -c "from src.orchestrator import TestOrchestrator"
python -c "from cli.main import main"
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
Count passing tests before you begin. Must match after.

### Step 4: CLI smoke test
```bash
python -m cli.main --help
```
Must display help text without error.

### Step 5: UAT — mandatory
```bash
python scripts/uat_full_pipeline.py
```
Must complete without error. If a live LLM is required and unavailable, say so explicitly — do NOT skip and declare done.

---

## Stop conditions
- Stop after Step 5
- Do not fix unrelated issues discovered during this task
- If you find a bug in a file you are not supposed to touch, document it in BACKLOG.md and stop
- If any verification step fails, diagnose and fix within the scope of this refactor only, then re-run from Step 1

---

## Key rules (from AGENTS.md)
- Use `uv add` for any new dependencies — never pip
- All functions must retain full type annotations
- Commit only after all five verification steps pass
- Commit message must not contain backticks