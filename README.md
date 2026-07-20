# AI-Playwright-Test-Generator

Paste a user story → get executable Playwright pytest tests with real DOM selectors.

Powered by local LLMs — no cloud API keys needed.

| Metric | Status |
|--------|--------|
| CI/CD Pipeline | [![CI](https://github.com/lacattano/AI-Playwright-Test-Generator/actions/workflows/ci.yml/badge.svg)](https://github.com/lacattano/AI-Playwright-Test-Generator/actions) |
| Python Version | ![Python 3.14+](https://img.shields.io/badge/python-3.14+-blue.svg) |
| License | ![License](https://img.shields.io/badge/license-Apache_2.0-green.svg) |
| Code Quality | [![Ruff](https://img.shields.io/badge/linter-ruff-261230.svg)](https://github.com/astral-sh/ruff) |

## How It Works

```
User story (natural language)
    ↓
Skeleton generation — LLM produces test structure with placeholders
    ↓
DOM scraping — real page structure captured, never injected into prompts
    ↓
Placeholder resolution — placeholders replaced with actual selectors
    ↓
Executable pytest file (sync format, ready to run)
```

## Key Features

- **AI-Powered Generation** — Natural language stories → pytest sync tests
- **Local LLMs** — Runs entirely offline via llama.cpp, Ollama, or LM Studio
- **Real Selectors** — Scrapes actual DOM; no selector hallucination
- **Skeleton-First Pipeline** — Two-phase generation eliminates bad selectors
- **Page Object Models** — Optional POM output for scalable test suites
- **Streamlit UI** — Primary interface for non-technical QA testers
- **CLI** — Command-line mode for CI/CD integration
- **Evidence Tracking** — Annotated screenshots, Gantt timelines, heat maps
- **Multi-Format Reports** — Markdown, Jira, or standalone HTML

## Quick Start

### Prerequisites

- Python 3.14+
- [uv](https://github.com/astral-sh/uv) (package manager)
- A local LLM server — llama.cpp on `:8080` (default), Ollama, or LM Studio

### Install & Run

```bash
# 1. Install dependencies
uv sync
playwright install chromium

# 2. Configure (optional — prompts at runtime)
cp .env.example .env

# 3. Launch the UI
bash launch_ui.sh
# → http://localhost:8501
```

Or use the CLI:

```bash
bash launch_cli.sh
```

For a full walkthrough of the CLI interactive menu, see [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

## Architecture

```
Phase 1: SKELETON GENERATION (LLM)
────────────────────────────────────
streamlit_app.py / cli/main.py
        │
        ▼
  orchestrator.py ──┐
        │            │
   ┌────┼────┬──────┴──────────────┐
   ▼    ▼     ▼                    ▼
 spec  test  scraper              LLM
 analyzer generator (scraper)    client
          │                        │
          ▼                        ▼
      skeleton with           prompt_utils.py
      placeholders ←───────── prompt template

Phase 2: PLACEHOLDER RESOLUTION (DOM Data)
────────────────────────────────────────────
        │
        ▼
placeholder_orchestrator.py (coordinates per-page resolution)
   │            │              │
   ▼            ▼              ▼
journey_    stateful_    semantic_
scraper     scraper      candidate_ranker
                            │
                            ▼
                placeholder_resolver
                (semantic_matcher + intent_matcher)
                            │
                            ▼
                locator_builder → code_postprocessor

Phase 3: PERSISTENCE + REPORTING
─────────────────────────────────
        │
        ▼
  pipeline_writer.py ──→ generated_tests/
        │
   evidence_tracker.py → .evidence.json sidecars
        │
   report_builder ←──┐
        │            │
        ▼            ▼
  failure_reporter  evidence_loader
        │
        ▼
  report_formatters → markdown / jira / html
```

For a full module map and dependency graph, see [ARCHITECTURE.md](docs/ARCHITECTURE.md).
- [Interactive call-flow diagram](graphify-out/callflow.html) — generated from live code, 10 700+ nodes

## Documentation

| Doc | Purpose |
|-----|---------|
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | System architecture, data flows, dependency graph |
| [PROJECT_KNOWLEDGE.md](docs/PROJECT_KNOWLEDGE.md) | Decisions, gotchas, recurring bugs |
| [DEMO_GUIDE.md](docs/DEMO_GUIDE.md) | Step-by-step demo for stakeholders |
| [BACKLOG.md](BACKLOG.md) | Feature backlog and bug tracker |
| [AGENTS.md](AGENTS.md) | AI coding agent conventions |
| [CONTEXT.md](CONTEXT.md) | Single-page project context |

## For Contributors

See [CONTRIBUTING.md](CONTRIBUTING.md) and [AGENTS.md](AGENTS.md).

Pre-commit checklist: `smoke.py` (offline import/resolver check) → `ruff` → `mypy` → `pytest`.

## License

Apache 2.0 — see [LICENSE](LICENSE).
