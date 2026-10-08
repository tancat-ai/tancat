# Configure your LLM

TanCat does not ship a model. You point it at one. Everything else - generation,
resolution, self-healing - runs through that endpoint.

The default provider is **`openai-local`**: an OpenAI-compatible server on
`http://127.0.0.1:8080/v1`, which is what llama.cpp serves. Set `LLM_PROVIDER`
in `.env` to use anything else.

```bash
cp .env.example .env
```

## Supported providers

| Provider | `LLM_PROVIDER` | Base URL | Model |
|---|---|---|---|
| llama.cpp / vLLM (default) | `openai-local` | `OPENAI_BASE_URL` (`http://127.0.0.1:8080/v1`) | `OPENAI_MODEL` |
| Ollama | `ollama` | `OLLAMA_BASE_URL` (`http://localhost:11434`) | `OLLAMA_MODEL` |
| LM Studio | `lm-studio` | `LM_STUDIO_BASE_URL` (`http://localhost:1234`) | `LM_STUDIO_MODEL` (optional, auto-detected) |
| OpenAI (cloud) | `openai` | `OPENAI_BASE_URL` | `OPENAI_MODEL` |
| Azure OpenAI | `azure-openai` | `AZURE_OPENAI_ENDPOINT` | `AZURE_OPENAI_DEPLOYMENT` |
| OpenRouter / Together / Groq / DeepSeek | `openai-compatible` or `openrouter` | `OPENAI_COMPATIBLE_BASE_URL` | `OPENAI_COMPATIBLE_MODEL` |

## llama.cpp (the default)

Start an OpenAI-compatible server and point TanCat at it:

```bash
llama-server -m model.gguf --host 127.0.0.1 --port 8080
```

```dotenv
LLM_PROVIDER=openai-local
OPENAI_BASE_URL=http://127.0.0.1:8080/v1
OPENAI_MODEL=Qwen/Qwen2.5-14B-Instruct
```

Keep `--host 127.0.0.1` for local-only access. A larger context window helps -
skeleton generation for a long story benefits from 32k tokens or more.

## Ollama

```bash
ollama pull qwen2.5:7b
```

```dotenv
LLM_PROVIDER=ollama
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:7b
OLLAMA_TIMEOUT=300
```

`OLLAMA_TIMEOUT=300` gives a slow first load enough time to answer.

## LM Studio

Start the local server in LM Studio, then:

```dotenv
LLM_PROVIDER=lm-studio
LM_STUDIO_BASE_URL=http://localhost:1234
# LM_STUDIO_MODEL is optional: when omitted, TanCat auto-detects the model
# currently loaded in LM Studio.
```

## Cloud providers

Cloud OpenAI:

```dotenv
LLM_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o
```

Azure OpenAI is not a plain OpenAI-compatible endpoint - the deployment name is
in the request path and the key goes in the `api-key` header. TanCat handles
that shape:

```dotenv
LLM_PROVIDER=azure-openai
AZURE_OPENAI_ENDPOINT=https://my-resource.openai.azure.com
AZURE_OPENAI_DEPLOYMENT=my-gpt4o-deployment
AZURE_OPENAI_API_KEY=...
# AZURE_OPENAI_API_VERSION=2024-10-21   # optional; this is the default
```

OpenRouter, Together, Groq, DeepSeek and any other OpenAI-compatible gateway use
the compatible path:

```dotenv
LLM_PROVIDER=openai-compatible
OPENAI_COMPATIBLE_BASE_URL=https://api.together.xyz/v1
OPENAI_COMPATIBLE_API_KEY=your_key_here
OPENAI_COMPATIBLE_MODEL=meta-llama/Llama-3.3-70B-Instruct-Turbo
```

## Check the endpoint before you write a story

Both the UI sidebar and the CLI have a **Check LLM** action. It reaches the
endpoint, verifies the key if one is needed, checks that the model is listed, and
sends one tiny completion. A healthy endpoint prints:

```
✓ LLM OK — openai-local / Qwen/Qwen2.5-14B-Instruct is reachable and responsive.
    provider : openai-local
    base_url : http://127.0.0.1:8080/v1
    model    : Qwen/Qwen2.5-14B-Instruct
    reachable: yes
    key      : ok (no key required)
    model    : listed  (1 available)
    responds : yes
    elapsed  : 0.4s
    sample   : 'ready'
```

If it fails, the report says which part failed - unreachable, invalid key,
missing model, or a broken (empty) response - so you can fix the endpoint before
the first real generation.

## Where your data goes

- **Local providers** (`openai-local`, `ollama`, `lm-studio`) - prompts stay on
  your network. Nothing is sent to a third party.
- **Cloud providers** (`openai`, `azure-openai`, `openrouter`,
  `openai-compatible` pointing at a hosted gateway) - the story, the scraped page
  content used for resolution, and the generated code are sent to that provider.

The health probe calls only the provider you configured. There is no telemetry.

## Next

- [Your first run](first-run.md)
