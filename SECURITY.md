# Security Policy

## Supported Versions

The following versions currently receive security updates:

| Version | Supported |
|---------|-----------|
| `main` branch (latest) | ✅ Yes |
| Older tagged releases | ❌ No — please upgrade to latest |

---

## Reporting a Vulnerability

**Please do not report security vulnerabilities through public GitHub Issues.**

If you discover a security vulnerability, report it privately so it can be assessed
and patched before public disclosure. This protects users who may be running the tool.

### How to report

**Option 1 — GitHub Private Vulnerability Reporting (preferred)**

Use GitHub's built-in private reporting:
[Report a vulnerability](https://github.com/lacattano/AI-Playwright-Test-Generator/security/advisories/new)

**Option 2 — Email**

Send details to the repository maintainer directly. Find contact details on the
[GitHub profile](https://github.com/lacattano).

### What to include in your report

- A description of the vulnerability and where it exists in the codebase
- Steps to reproduce or a proof-of-concept (if safe to share)
- The potential impact — what could an attacker do?
- Your name / handle if you would like to be credited in the fix

---

## What to Expect

- **Acknowledgement:** Within 48 hours of receipt
- **Initial assessment:** Within 5 business days
- **Fix timeline:** Dependent on severity — critical issues are prioritised immediately
- **Disclosure:** We will notify you before publishing a fix and credit you in the release
  notes unless you prefer to remain anonymous

---

## Scope

Vulnerabilities that are in scope for this policy:

- **Prompt injection** — LLM prompt manipulation that causes unintended code execution
- **Path traversal** — File read/write outside intended directories (e.g. `generated_tests/`, `screenshots/`)
- **Secret exposure** — Leaking API keys, `.env` contents, or credentials through logs or UI
- **Subprocess injection** — Malicious input reaching the Playwright subprocess or `pytest` runner
- **Dependency vulnerabilities** — Critical CVEs in pinned dependencies in `pyproject.toml`

Out of scope:

- Vulnerabilities in third-party services (Ollama, OpenAI, Anthropic, Streamlit hosting)
- Issues only reproducible with full access to the host machine
- Social engineering attacks

---

## Security Design Notes

For contributors and security researchers, the following design decisions are relevant:

- **Subprocess isolation:** The Playwright scraper runs in a subprocess to isolate it from
  Streamlit's event loop. This also limits the blast radius of any scraper-level exploit.
- **No credentials stored server-side:** API keys are stored in `.env` (gitignored) or passed
  as session-state values — they are never persisted to disk or transmitted to third parties
  by this tool.
- **Generated test files:** Tests are written to `generated_tests/` and must be reviewed
  before execution. This tool does not auto-execute generated code without user action.
- **LLM output validation:** Generated test code is validated with `ast.parse()` before being
  written to disk (`src/code_validator.py`) to prevent malformed or injected code from being saved.

---

## Dependency Management

Dependencies are managed with [uv](https://github.com/astral-sh/uv) and pinned in `uv.lock`.
To check for known vulnerabilities in current dependencies:

```bash
uvx pip-audit
```

We recommend running `uvx pip-audit` as part of your local review before submitting a PR that
updates dependencies.
