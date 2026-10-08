# tancat-ai/tancat

Paste a user story → get executable Playwright pytest tests with real DOM selectors.

Powered by local LLMs — no cloud API keys needed.

| Metric | Status |
|--------|--------|
| CI/CD Pipeline | [![CI](https://github.com/tancat-ai/tancat/actions/workflows/ci.yml/badge.svg)](https://github.com/tancat-ai/tancat/actions) |
| Python Version | ![Python 3.14+](https://img.shields.io/badge/python-3.14+-blue.svg) |
| License | ![License](https://img.shields.io/badge/license-Apache_2.0-green.svg) |
| Code Quality | [![Ruff](https://img.shields.io/badge/linter-ruff-261230.svg)](https://github.com/astral-sh/ruff) |

## Demo

A short walkthrough video is planned. Until it is recorded, the
[Your first run](docs/user/getting-started/first-run.md) page in the user docs
specifies exactly what the video will show, and walks the same story end to end
with real expected output.

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
- **Self-Learning RAG** — the resolver improves with use: passing runs and self-healed locators teach a local, site-scoped store (no telemetry, no cloud)
- **Self-Healing** — failed locators are reviewed and repaired automatically, then written back so the next generation resolves correctly
- **Local LLMs** — Runs entirely offline via llama.cpp, Ollama, or LM Studio
- **Semantic Scraper** — Three-layer extraction (BS4 + CDP accessibility tree + ARIA snapshot) captures computed accessible names, placeholder text, and container elements that CSS-only scrapers miss
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

For the CLI, run `bash launch_cli.sh`. It starts an interactive menu; the
[Install](docs/user/getting-started/install.md) page covers the launch options,
and `tancat --help` prints the usage text.

## Connect your LLM

Pick the provider in the Streamlit sidebar or the CLI "Configure LLM" menu. The
supported providers are: Ollama, LM Studio, OpenAI-compatible (local),
OpenAI (cloud), **Azure OpenAI**, OpenAI-compatible (cloud), and OpenRouter.
Local providers need no key. Cloud providers need a key; the app stores it in
memory for the session unless you save it encrypted.

Every provider is configured with **base URL + model + key**. For a generic
endpoint the model is whatever the endpoint serves; for Azure OpenAI the "model"
is your deployment name.

### Azure OpenAI (first-class)

Azure is not a plain OpenAI-compatible endpoint: the deployment name is in the
request path, `api-version` is a query parameter, and the key goes in the
`api-key` header. The app builds:

```
POST https://<resource>.openai.azure.com/openai/deployments/<deployment>/chat/completions?api-version=2024-10-21
api-key: <AZURE_OPENAI_API_KEY>
```

Set these in `.env` (or inject them from your platform's secret store):

```
LLM_PROVIDER=azure-openai
AZURE_OPENAI_ENDPOINT=https://my-resource.openai.azure.com
AZURE_OPENAI_DEPLOYMENT=my-gpt4o-deployment
AZURE_OPENAI_API_KEY=...
# AZURE_OPENAI_API_VERSION=2024-10-21   # optional; this is the default
```

### AWS Bedrock (via the Bedrock Access Gateway)

Do **not** point TanCat at `bedrock-runtime` directly. AWS ships the
[Bedrock Access Gateway](https://github.com/aws-samples/bedrock-access-gateway),
an OpenAI-compatible API in front of Bedrock. Use the generic compatible
provider --- no adapter needed:

```
LLM_PROVIDER=openai-compatible
OPENAI_COMPATIBLE_BASE_URL=https://<api-id>.execute-api.<region>.amazonaws.com/api/v1
OPENAI_COMPATIBLE_API_KEY=<bedrock-gateway-api-key>
OPENAI_COMPATIBLE_MODEL=anthropic.claude-3-5-sonnet-20241022-v2:0
```

The base URL shape is the API Gateway invoke URL with a trailing `/api/v1`
(add the stage if you deployed one):
`https://<api-id>.execute-api.<region>.amazonaws.com/<stage>/api/v1`.
The gateway speaks `/chat/completions` with `Authorization: Bearer`, which is
exactly what the compatible provider sends.

### Any other gateway

The same compatible path covers LiteLLM, Portkey, Azure API Management,
self-hosted vLLM/SGLang/TGI, Together, Groq, and DeepSeek: set the provider to
OpenAI-compatible, paste the gateway's `/v1` base URL and key, and name the
model. See [.env.example](.env.example) for the full list of variables.

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
- Interactive call-flow diagram: generated locally with `graphify update .` (not committed to the repo).

## Documentation

| Doc | Purpose |
|-----|---------|
| [docs/user/](docs/user/index.md) | User documentation - install, configure your LLM, first run, guides, licensing |
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
