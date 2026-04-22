# AI-Playwright-Test-Generator

An AI-powered tool that generates Playwright Python test scripts from user stories using local LLM models via Ollama.

| Metric | Status |
|--------|--------|
| CI/CD Pipeline | [![CI](https://github.com/lacattano/AI-Playwright-Test-Generator/actions/workflows/ci.yml/badge.svg)](https://github.com/lacattano/AI-Playwright-Test-Generator/actions) |
| Python Version | ![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg) |
| License | ![License](https://img.shields.io/badge/license-MIT-green.svg) |
| Code Quality | [![ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff) |

## What It Does

Paste a user story → get back executable Playwright pytest tests with real DOM selectors.

## Key Features

- **AI-Powered Generation** — Natural language stories → pytest sync tests
- **Local LLM** — Runs entirely locally via Ollama (no API costs)
- **Real Selectors** — Scrapes actual DOM elements, never injects selectors into LLM prompts
- **Skeleton-First Pipeline** — Two-phase: placeholders → resolution (eliminates selector hallucination)
- **Page Object Model** — Generated tests follow POM pattern
- **Streamlit UI** — Primary interface for non-technical QA testers
- **CLI Tool** — Command-line interface for CI/CD integration
- **Multi-Format Reports** — Local markdown, Jira, HTML with base64-embedded screenshots
- **Evidence Tracking** — Annotated screenshots, Gantt timelines, heat maps
- **Pre-commit Hooks** — Automated linting and formatting with ruff

## Quick Start

```bash
# 1. Install dependencies
uv sync
playwright install chromium

# 2. Configure environment
cp .env.example .env
# Edit .env — set OLLAMA_MODEL and OLLAMA_TIMEOUT=300

# 3. Start Ollama (if not running)
ollama serve
ollama pull qwen3.5:35b

# 4. Launch UI
bash launch_ui.sh
# Then open http://localhost:8501
```

## Prerequisites

- **Python 3.13+**
- **Ollama** with a model (recommended: `qwen3.5:35b`)
- **Docker** (optional — for containerized runs)

## Architecture

```
streamlit_app.py (UI) ─→ cli/main.py (CLI)
        │
        ▼
  src/orchestrator.py (pipeline brain)
        │
   ┌────┼─────────┬──────────┬──────────┐
   ▼    ▼         ▼          ▼          ▼
spec    test    scraper  LLM       placeholder
analyzer generator  (DOM)  client    resolver
                          │
                    src/pipeline_writer.py → generated_tests/
```

## Documentation

| Doc | Purpose |
|-----|---------|
| [ARCHITECTURE.md](docs/ARCHITECTURE.md) | System architecture, data flows, dependency graph |
| [PROJECT_KNOWLEDGE.md](docs/PROJECT_KNOWLEDGE.md) | Architecture decisions, gotchas, recurring bugs |
| [DEMO_GUIDE.md](docs/DEMO_GUIDE.md) | Step-by-step demo script for stakeholders |
| [PROMPT_EXAMPLES.md](docs/PROMPT_EXAMPLES.md) | LLM prompt templates |
| [BACKLOG.md](BACKLOG.md) | Feature backlog, bug tracker |
| [AGENTS.md](AGENTS.md) | AI coding agent conventions (read before writing code) |
| [specs/](docs/specs/) | Feature specification documents |

## License

This project is provided as-is for personal and educational use.