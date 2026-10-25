# Contributing to AI Playwright Test Generator

Thank you for your interest in contributing! This document explains how to get involved, what we expect from contributors, and how to get your changes accepted.

---

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [How to Report a Bug](#how-to-report-a-bug)
- [How to Request a Feature](#how-to-request-a-feature)
- [Security](#security)
- [Development Setup](#development-setup)
- [Making a Pull Request](#making-a-pull-request)
- [Coding Standards](#coding-standards)
- [Commit Message Format](#commit-message-format)

---

## Code of Conduct

This project follows the [Contributor Covenant Code of Conduct](https://www.contributor-covenant.org/version/2/1/code_of_conduct/).
By participating you agree to abide by its terms. Please be respectful and constructive in all interactions.

---

## How to Report a Bug

1. **Search existing issues first** — your bug may already be reported.
2. If not, open a [Bug Report issue](https://github.com/lacattano/tancat-ai/tancat/issues/new?template=bug_report.md).
3. Include:
   - A clear, descriptive title
   - Steps to reproduce the problem
   - What you expected to happen vs. what actually happened
   - Your OS, Python version, and Ollama model in use
   - Any relevant error output or screenshots

---

## How to Request a Feature

1. Open a [Feature Request issue](https://github.com/lacattano/tancat-ai/tancat/issues/new?template=feature_request.md).
2. Describe the problem you are trying to solve, not just the solution you have in mind.
3. If you plan to implement it yourself, say so — we will prioritise reviewing it.

---

## Security

If you discover a security vulnerability, please do **not** open a public issue. See [SECURITY.md](SECURITY.md) for responsible disclosure guidelines.

---

## Public-repo safety

This repository is public until release. A blocking CI job, **Private Content
Guard**, runs:

```bash
python scripts/maintenance/kanban.py --check-private
```

It reads the committed public artefacts, never `docs/private/`, and fails with
the file, line and match when it finds:

- content from `docs/private/` in `kanban.html`;
- an absolute Windows, macOS or Linux home path in a tracked fixture, evidence
  file or committed run output (`fixtures/`, `docs/`, `exported_tests/`,
  `generated_tests/`, `screenshots/`, `evidence/`, `training_data/`,
  `scripts/archive/`);
- an XML/HTML `hostname` attribute;
- the current user's name (derived from the environment at check time) or the
  current machine name in run output;
- an absolute citation to a gitignored path that names a file, such as a local
  `scratch/` or `docs/private/` path. The published relative form used by the
  committed evidence (`scratch/gate1_out_.../test.py:44`) is allowed and
  documented in `fixtures/heldout_runs/2026-10-24/README.md`.

It cannot see:

- text inside images, screenshots, PDFs or other binaries, for example a photo
  of a desktop or a terminal;
- untracked or gitignored files - they are not published;
- secrets in source comments, root-level notes, or files outside the scanned
  roots - the secret-scan and gitleaks jobs cover credentials;
- a plain user or machine name written in prose under `docs/`. The hostname is
  also the public handle, so those words are not flagged there; a home path in
  the same docs is still caught.

Run it locally before a release-shaped change:

```bash
python scripts/maintenance/kanban.py --check-private
```

`--check` keeps the board-only private check and the freshness comparison; it
does not run the machine scan, so a pre-commit hook is not blocked by the
historical findings the CI guard is there to surface.

---

## Development Setup

**Requirements:** Python 3.14+, [uv](https://github.com/astral-sh/uv), Git, Ollama

```bash
# 1. Fork and clone
git clone https://github.com/<your-username>/tancat-ai/tancat
cd tancat-ai/tancat

# 2. Install dependencies (do NOT use pip)
uv sync

# 3. Activate virtual environment
source .venv/Scripts/activate   # Windows (Git Bash)
source .venv/bin/activate        # macOS / Linux

# 4. Install Playwright browsers
playwright install chromium

# 5. Configure environment
cp .env.example .env
# Edit .env — set OLLAMA_TIMEOUT=300 and your preferred OLLAMA_MODEL
```

> ⚠️ **Always use `uv add <package>` to add dependencies. Never use `pip install` directly** —
> `pip` is not on PATH in this project's virtual environment.

---

## Making a Pull Request

1. **Create a branch** from `main` with a descriptive name:
   ```bash
   git checkout -b feat/your-feature-name
   # or
   git checkout -b fix/the-bug-you-are-fixing
   ```

2. **Write your code** following the standards below.

3. **Run the quality checks** before pushing:
   ```bash
   bash fix.sh          # ruff lint + ruff format + mypy
   pytest tests/ -v     # unit tests — must be green
   ```

4. **Stage and review your changes:**
   ```bash
   git add -A
   git diff --staged --stat
   ```

5. **Commit** with a clear message (see format below).

6. **Open a Pull Request** against `main`. Fill in the PR template completely.
   A reviewer will respond within a few business days.

### What makes a PR likely to be accepted

- It solves one clearly defined problem
- All new functions have full type annotations
- New behaviour is covered by unit tests in `tests/`
- `bash fix.sh` and `pytest tests/ -v` both pass cleanly
- It does not modify [protected files](AGENTS.md#3-protected-files--do-not-modify-without-explicit-instruction) without prior discussion

---

## Coding Standards

This project enforces the following non-negotiable rules:

| Rule | Detail |
|------|--------|
| **Package manager** | `uv add` only — never `pip install` |
| **Type hints** | All functions must have full type annotations — no exceptions |
| **Test format** | Generated tests use pytest sync format (`def test_...`) — never `async def` |
| **Testable helpers** | Logic goes in `src/<module>.py` — never directly in `streamlit_app.py` |
| **Linting** | `ruff check` must pass cleanly |
| **Type checking** | `mypy` must pass cleanly |
| **Tests** | `pytest tests/ -v` must be green before any commit |

Run all checks at once:
```bash
bash fix.sh && pytest tests/ -v
```

### New module checklist

If you are adding a new `src/` module:

1. Create `src/<module_name>.py` with full type annotations
2. Create `tests/test_<module_name>.py` with unit tests
3. Import into `streamlit_app.py` if needed — never define logic there directly
4. Run `ruff check src/<module_name>.py` and `mypy src/<module_name>.py`
5. Ensure all Playwright imports are at module level (not inside function bodies)

---

## Commit Message Format

Use plain, descriptive imperative sentences. No backticks in commit messages.

```
Add evidence tracker module with sidecar JSON output
Fix scraper failing silently when URL has no scheme
Update prompt rules to require evidence_tracker methods
```

Do not use:
- Conventional Commits format (`feat:`, `fix:` prefixes) — not required here
- Backtick characters in the message — they cause rendering issues
- Generic messages like "fix bug" or "update code"

---

## Questions?

Open a [Discussion](https://github.com/lacattano/tancat-ai/tancat/discussions) 
for anything that does not fit a bug report or feature request.
