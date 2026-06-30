# llm_providers/__init__.py

## Overview

This module provides a unified interface for interacting with different LLM backends in the AI-Playwright-Test-Generator project. It implements a provider abstraction pattern that supports multiple LLM services through a common interface.

**Supported Providers:**
- Ollama (native API)
- LM Studio (OpenAI-compatible API)
- OpenAI (cloud and local modes)
- Any OpenAI-compatible local server

## Architecture

The module follows an **Abstract Factory pattern** with the following components:

1. **Data Models**: `ChatMessage` and `ChatCompletion` dataclasses for type-safe message handling
2. **Abstract Base Class**: `LLMProvider` defines the contract all providers must implement
3. **Concrete Implementations**: Provider-specific classes that handle API communication
4. **Factory Functions**: Helper functions for provider instantiation and auto-detection

## Data Models

### ChatMessage
```python
@dataclass
class ChatMessage:
    role: str  # 'system', 'user', or 'assistant'
    content: str
```

Represents a single message in a chat conversation.

### ChatCompletion
```python
@dataclass
class ChatCompletion:
    content: str
    model: str
    usage: dict[str, int] | None = None  # {'prompt_tokens': int, 'completion_tokens': int}
```

Represents the response from an LLM completion request, including token usage metadata.

## Abstract Base Class

### LLMProvider
```python
class LLMProvider(ABC):
```

Abstract base class that defines the interface all LLM providers must implement.

**Properties:**
- `provider_name(self) -> str`: Returns the provider identifier (e.g., 'ollama', 'lm-studio')
- `base_url(self) -> str`: Returns the configured API base URL

**Methods:**
- `complete(self, messages: list[ChatMessage], model: str | None = None, timeout: int = 300) -> ChatCompletion`: Send a chat completion request
- `list_models(self, timeout: int = 30) -> list[str]`: List available models on the provider

## Provider Implementations

### OllamaProvider
```python
class OllamaProvider(LLMProvider):
    DEFAULT_BASE_URL = "http://localhost:11434"
    PROVIDER_NAME = "ollama"
    
    def __init__(self, base_url: str | None = None, **kwargs: Any) -> None
```

Native Ollama API provider implementation.

**Key Features:**
- Uses Ollama's native `/api/chat` endpoint
- Default model: `qwen2.5:7b` (configurable via `OLLAMA_MODEL` env var)
- Timeout configurable via `OLLAMA_TIMEOUT` env var (default: 300s)
- Token counting via `eval_count` field in response

**Environment Variables:**
- `OLLAMA_BASE_URL`: Override default base URL
- `OLLAMA_MODEL`: Override default model
- `OLLAMA_TIMEOUT`: Override request timeout

### LMStudioProvider
```python
class LMStudioProvider(LLMProvider):
    DEFAULT_BASE_URL = "http://localhost:1234"
    PROVIDER_NAME = "lm-studio"
    
    def __init__(self, base_url: str | None = None, **kwargs: Any) -> None
```

LM Studio provider implementation using OpenAI-compatible API.

**Key Features:**
- Uses OpenAI-compatible `/v1/chat/completions` endpoint
- Default model: `lmstudio-community/Qwen2.5-7B-Instruct-GGUF`
- Additional method: `get_loaded_model()` to query currently loaded model
- Native API endpoint at `/api/v0/models` for model state detection

**Environment Variables:**
- `LM_STUDIO_BASE_URL`: Override default base URL
- `LM_STUDIO_MODEL`: Override default model

### OpenAIProvider
```python
class OpenAIProvider(LLMProvider):
    PROVIDER_NAME = "openai"
    LOCAL_PROVIDER_NAME = "openai-local"
    LOCAL_DEFAULT_PORTS = [8080, 8000, 5000]  # llama.cpp, vLLM, text-gen-webui
    
    def __init__(self, api_key: str | None = None, base_url: str | None = None, is_local: bool = False)
```

OpenAI API provider supporting both cloud and local modes.

**Key Features:**
- **Cloud mode** (default): Requires API key, targets `api.openai.com`
- **Local mode** (`is_local=True`): No API key required, auto-detects local servers
- Auto-detection probes ports: 8080 (llama.cpp), 8000 (vLLM), 5000 (text-gen-webui)
- Default cloud model: `gpt-4o`
- Default local model: `llama`
- API key masking for security in logs

**Environment Variables:**
- `OPENAI_API_KEY`: Required for cloud mode
- `OPENAI_BASE_URL`: Override default base URL
- `OPENAI_MODEL`: Override default model

**Special Methods:**
- `get_loaded_model(timeout: int = 5) -> str | None`: Returns first available model from `/v1/models`
- `api_key(self) -> str | None`: Returns masked API key for logging

## Factory Functions

### auto_detect_provider()
```python
def auto_detect_provider() -> LLMProvider
```

Automatically detects and returns the first active local LLM provider.

**Detection Order:**
1. LM Studio (http://localhost:1234/v1/models)
2. Ollama (http://localhost:11434/api/tags)
3. OpenAI-compatible local servers (ports 8080, 8000, 5000)

**Raises:**
- `ConnectionError`: If no local providers are active

### get_provider()
```python
def get_provider(provider_name: str, **kwargs: Any) -> LLMProvider
```

Factory function to create a provider instance by name.

**Parameters:**
- `provider_name`: One of 'ollama', 'lm-studio', 'openai', 'openai-local'
- `**kwargs`: Additional arguments passed to provider constructor

**Raises:**
- `ValueError`: If provider name is unknown

### create_provider_from_env()
```python
def create_provider_from_env() -> LLMProvider
```

Creates a provider instance based on environment variables.

**Environment Variables:**
- `LLM_PROVIDER`: Provider name (default: 'ollama')
- Provider-specific variables (see individual provider sections)

**Raises:**
- `ValueError`: If required environment variables are missing or provider is unknown

## Design Patterns

### Provider Abstraction
All providers implement the same interface, allowing the rest of the application to work with any LLM backend without changing code.

### Environment-Based Configuration
Providers read configuration from environment variables, supporting the 12-factor app methodology.

### Auto-Detection
The `auto_detect_provider()` function enables zero-configuration startup by probing common local ports.

### Graceful Degradation
Local mode providers handle missing endpoints gracefully, falling back to defaults rather than crashing.

## Usage Example

```python
from src.llm_providers import get_provider, ChatMessage

# Create a provider
provider = get_provider("ollama")

# Send a completion request
messages = [
    ChatMessage(role="system", content="You are a helpful assistant."),
    ChatMessage(role="user", content="Generate a Playwright test.")
]
response = provider.complete(messages, model="qwen2.5:7b")
print(response.content)

# List available models
models = provider.list_models()
print(models)
```

## Exported Symbols

```python
__all__ = [
    "ChatMessage",
    "ChatCompletion",
    "LLMProvider",
    "OllamaProvider",
    "LMStudioProvider",
    "OpenAIProvider",
    "get_provider",
    "create_provider_from_env",
    "auto_detect_provider",
]
```

## Dependencies

- `abc`: Abstract base class support
- `dataclasses`: Data model definitions
- `httpx`: HTTP client for API communication (imported per-provider to minimize startup overhead)

## Notes

- All HTTP clients use a 300-second default timeout unless overridden
- Token usage tracking is optional and depends on provider response format
- Local OpenAI-compatible servers may return 401 for `/v1/models` (treated as success in local mode)
- Provider auto-detection uses 2-second timeouts for fast failure