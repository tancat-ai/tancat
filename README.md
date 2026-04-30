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

## Usage

### Quick Launchers

```bash
# Launch the Streamlit UI
bash launch_ui.sh

# Launch the interactive CLI
bash launch_cli.sh
```
### Interactive CLI (Recommended)

The CLI launches an interactive, menu-driven session that guides you through the full pipeline:

```bash
# Activate virtual environment first
uv sync
.venv\Scripts\activate   # Windows
source .venv/bin/activate   # macOS/Linux

# Launch interactive CLI
python -m cli.main
```

**Interactive menu flow:**
1. **Configure LLM** — Select provider (ollama/lm-studio) and model
2. **Enter User Story** — Paste text or upload a `.md`/`.txt` file
3. **Enter Target URLs** — Starting URL + additional pages to scrape
4. **Consent Mode** — How to handle cookie/consent banners
5. **Build Living Test Plan** — AI derives conditions for your review and sign-off
6. **Run Intelligent Pipeline** — Generates skeleton → scrapes pages → resolves placeholders
7. **View Generated Code** — Inspect the final pytest script
8. **Run Generated Tests** — Execute tests with pytest
9. **Generate/View Reports** — Local markdown, Jira, or HTML reports

### Legacy Parameter-Based CLI

```bash
# Generate from a string
python -m cli.main generate --input "As a user, I want to login"

# Generate from a file
python -m cli.main generate --file user_stories.md

# With full options
python -m cli.main generate \
  --input "Add items to cart" \
  --output generated_tests \
  --url https://example.com \
  --format user_story
```

**Available options:**

| Option | Default | Description |
|--------|---------|-------------|
| `--input`, `-i` | | Raw test case input string |
| `--file`, `-f` | | Input file (text or JSON) |
| `--generate`, `-g` | | Generate test case from prompt |
| `--format` | `user_story` | Format: `user_story`, `gherkin`, `auto` |
| `--output`, `-o` | `generated_tests` | Output directory |
| `--url` | | Target URL for page context |
| `--help` | | Show help message |

### Help

```bash
python -m cli.main --help
python -m cli.main generate --help
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