# Feature Spec: Multi-Provider LLM Support (AI-010)

> **Status:** Proposed  
> **Created:** 2026-04-03  
> **Priority:** High  
> **Related:** AI-009 (Run Results), multi-page scraping features

---

## 1. Problem Statement

The current test generator is hardcoded to work only with Ollama's API format. This limits:
- **User flexibility**: Users of LM Studio, OpenAI-compatible servers, or future API key providers cannot use the tool
- **Market reach**: Many developers prefer LM Studio (GUI-based model management) over running a separate Ollama server
- **Future extensibility**: Adding support for Claude, ChatGPT, or other paid APIs requires refactoring existing code

---

## 2. Goals

1. **Support multiple LLM providers** through a unified interface
2. **Keep Ollama as the default** (safest option for most users, no API key required)
3. **Add LM Studio support** (OpenAI-compatible endpoint at `localhost:1234`)
4. **Future-proof for API key providers** (Claude, ChatGPT, etc.) without breaking changes
5. **Auto-discover available models** from the connected server
6. **Maintain backward compatibility** with existing `.env` configuration

---

## 3. Non-Goals

- ❌ Re-implementing LLM chat completions (we use providers' APIs)
- ❌ Caching model responses (out of scope for this feature)
- ❌ Supporting paid API providers in this iteration (prepared for, but not implemented yet)
- ❌ Model fine-tuning or training capabilities

---

## 4. Provider Support Matrix

| Provider | Endpoint Format | Default URL | API Key Required | Status |
|----------|----------------|-------------|------------------|--------|
| **Ollama** | Custom `/api/generate` | `http://localhost:11434` | No | ✅ Primary |
| **LM Studio** | OpenAI-compatible `/v1/chat/completions` | `http://localhost:1234` | Optional (reserved) | ✅ Secondary |
| **OpenAI-Compatible** | Configurable `/v1/chat/completions` | User-defined | Yes (future) | ⏳ Future-proofed |

---

## 5. Architecture Design

### 5.1 Provider Abstraction Layer

```python
# src/llm_providers/__init__.py

from abc import ABC, abstractmethod
from typing import List, Protocol

class LLMProvider(ABC):
    """Abstract base class for all LLM providers."""
    
    def __init__(self, base_url: str, model: str, api_key: str | None = None):
        self.base_url = base_url
        self.model = model
        self.api_key = api_key
    
    @abstractmethod
    async def generate(self, prompt: str) -> str:
        """Generate test code from the given prompt."""
        pass
    
    @abstractmethod
    async def validate_connection(self) -> bool:
        """Verify connectivity to the provider's server."""
        pass
    
    @abstractmethod
    async def list_available_models(self) -> List[str]:
        """Fetch and return list of available model names from the server."""
        pass


class OllamaProvider(LLMProvider):
    """Ollama-specific implementation using /api/generate endpoint."""
    
    async def generate(self, prompt: str) -> str:
        # Uses Ollama's custom format
        ...
    
    async def list_available_models(self) -> List[str]:
        # GET /api/tags → extract name field from each model
        ...


class LMStudioProvider(LLMProvider):
    """LM Studio implementation using OpenAI-compatible endpoint."""
    
    async def generate(self, prompt: str) -> str:
        # Uses /v1/chat/completions with OpenAI format
        ...
    
    async def list_available_models(self) -> List[str]:
        # GET /v1/models → extract id field from data[].models
        ...


class ProviderFactory:
    """Factory for creating provider instances based on configuration."""
    
    @staticmethod
    def create_provider(provider_type: str, config: dict) -> LLMProvider:
        providers = {
            "ollama": OllamaProvider,
            "lm-studio": LMStudioProvider,
            # "openai-compatible": OpenAICompatibleProvider  # Future
        }
        
        if provider_type not in providers:
            raise ValueError(f"Unknown provider: {provider_type}")
        
        return providers[provider_type](**config)
```

### 5.2 Refactored LLM Client

```python
# src/llm_client.py (refactored)

from .llm_providers import ProviderFactory, LLMProvider

class LLMClient:
    """Facade for LLM operations — delegates to provider."""
    
    def __init__(self, config: dict):
        self.provider = ProviderFactory.create_provider(
            provider_type=config["provider"],
            config={
                "base_url": config["base_url"],
                "model": config["model"],
                "api_key": config.get("api_key"),
            }
        )
    
    async def generate(self, prompt: str) -> str:
        """Generate test code from the given prompt."""
        return await self.provider.generate(prompt)
    
    async def validate_connection(self) -> bool:
        """Verify connectivity to the provider's server."""
        return await self.provider.validate_connection()
    
    async def list_available_models(self) -> List[str]:
        """Fetch available models from the connected server."""
        return await self.provider.list_available_models()
```

---

## 6. Environment Variables

### Current (Backward Compatible)

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_MODEL` | `qwen3.5:35b` | Model name for Ollama |
| `OLLAMA_TIMEOUT` | `300` | Request timeout in seconds |
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |

### New (Added)

| Variable | Default | Description | When Used |
|----------|---------|-------------|-----------|
| `LLM_PROVIDER` | `ollama` | Provider type: `ollama`, `lm-studio`, or `openai-compatible` | All cases |
| `LLM_BASE_URL` | `http://localhost:11434` | Base URL for the provider | All cases |
| `LLM_API_KEY` | *(empty)* | API key for authentication | Future providers only |

### Migration Strategy

- If `LLM_PROVIDER` is not set, default to `ollama` and use existing `OLLAMA_*` variables
- If `LLM_BASE_URL` is set but `OLLAMA_BASE_URL` exists, prefer `LLM_BASE_URL` (new takes precedence)
- Old `.env` files continue working without modification

---

## 7. UI Changes in Streamlit App

### 7.1 Provider Selection Dropdown

```python
# New section at top of LLM configuration panel

import streamlit as st

st.sidebar.subheader("🤖 LLM Provider")

provider = st.sidebar.selectbox(
    "Select Provider",
    options=["Ollama", "LM Studio"],  # Future: "OpenAI-Compatible"
    index=0 if current_provider == "ollama" else 1,
    help="Choose which LLM server to connect to"
)

# Show/hide fields based on selection
if provider == "Ollama":
    base_url = st.sidebar.text_input(
        "Base URL", 
        value=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    )
elif provider == "LM Studio":
    base_url = st.sidebar.text_input(
        "Base URL", 
        value=os.getenv("LLM_BASE_URL", "http://localhost:1234"),
        help="Default LM Studio OpenAI-compatible server port is 1234"
    )

# Model name input (same for both providers)
model = st.sidebar.text_input(
    "Model Name", 
    value=os.getenv("OLLAMA_MODEL", os.getenv("LLM_MODEL", "qwen3.5:35b")),
    help="Enter model name or use 'Refresh Models' to auto-discover"
)

# New: Refresh Models button
col1, col2 = st.sidebar.columns([1, 4])
with col1:
    if st.sidebar.button("🔄 Refresh Models"):
        # Trigger model discovery
        models = llm_client.list_available_models()
        st.session_state.available_models = models

# New: Model dropdown (replaces text input when models are available)
if st.session_state.get("available_models"):
    selected_model = st.sidebar.selectbox(
        "Select Model",
        options=st.session_state.available_models,
        index=0  # or calculate based on current model
    )
```

### 7.2 Connection Validation

When user changes provider or base URL:
1. Show "Testing connection..." indicator
2. Call `validate_connection()` method
3. Display success/failure message
4. If failed, suggest troubleshooting steps

---

## 8. Error Handling

| Scenario | Error Type | User Message | Recovery Action |
|----------|------------|--------------|-----------------|
| Provider connection timeout | `ConnectionTimeoutError` | "Connection to LLM server timed out after {timeout}s" | Increase timeout or check server status |
| Invalid base URL | `ConfigurationError` | "Invalid base URL format. Expected: http://localhost:XXXX" | Correct the URL and retry |
| Model not found on server | `ModelNotFoundError` | "Model '{model}' not found on {provider}" | Use dropdown to select available model |
| API key missing (future) | `AuthenticationError` | "API key required for this provider. Please enter your key." | Enter valid API key |

---

## 9. Testing Strategy

### Unit Tests

| Test File | What to Test | Mock Target |
|-----------|--------------|-------------|
| `tests/test_llm_providers/__init__.py` | Provider base class instantiation | N/A |
| `tests/test_ollama_provider.py` | OllamaProvider.generate() | HTTPX mock for `/api/generate` |
| `tests/test_ollama_provider.py` | OllamaProvider.list_available_models() | HTTPX mock for `/api/tags` |
| `tests/test_lmstudio_provider.py` | LMStudioProvider.generate() | HTTPX mock for `/v1/chat/completions` |
| `tests/test_lmstudio_provider.py` | LMStudioProvider.list_available_models() | HTTPX mock for `/v1/models` |
| `tests/test_provider_factory.py` | Factory returns correct instance based on type | N/A |

### Integration Tests

```python
# tests/integration/test_multi_provider_llm.py

@pytest.mark.integration
class TestMultiProviderLLM:
    @pytest.fixture
    def ollama_client(self, monkeypatch):
        # Set up Ollama environment
        monkeypatch.setenv("LLM_PROVIDER", "ollama")
        monkeypatch.setenv("OLLAMA_BASE_URL", "http://localhost:11434")
        return LLMClient()
    
    @pytest.fixture
    def lmstudio_client(self, monkeypatch):
        # Set up LM Studio environment  
        monkeypatch.setenv("LLM_PROVIDER", "lm-studio")
        monkeypatch.setenv("LLM_BASE_URL", "http://localhost:1234")
        return LLMClient()
    
    def test_ollama_provider_generation(self, ollama_client):
        """Generate tests using Ollama provider."""
        prompt = "Generate a test for login page"
        result = await ollama_client.generate(prompt)
        assert "def test_" in result
    
    def test_lmstudio_provider_generation(self, lmstudio_client):
        """Generate tests using LM Studio provider."""
        prompt = "Generate a test for login page"
        result = await lmstudio_client.generate(prompt)
        assert "def test_" in result
```

---

## 10. Backward Compatibility

### Guarantees

- ✅ Existing `.env` files work without modification
- ✅ CLI interface remains unchanged (`--provider` flag optional, defaults to `ollama`)
- ✅ Streamlit app loads with default Ollama configuration
- ✅ Generated test format is identical regardless of provider

### Migration Path for Users

1. **No action required** — existing users continue using Ollama as before
2. To switch to LM Studio: Update `.env` or use UI dropdown
3. To add new provider in future: No code changes needed, just configuration

---

## 11. Security Considerations

### API Key Handling (Future-Proofing)

| Risk | Mitigation |
|------|------------|
| Keys stored in `.env` committed to Git | ✅ Covered by existing `.gitignore` rule for `.env` |
| Keys exposed in logs | ⚠️ Implement log sanitization for `api_key` fields |
| Keys displayed in UI | ❌ Never display API keys; use password-style input field |
| Keys persisted beyond session | ✅ Read from environment only, never save to disk |

### Future Implementation (API Key Providers)

When adding Claude/ChatGPT support:
1. Add "OpenAI-Compatible" provider option
2. Show API key input field (password type, masked display)
3. Validate key format before making any requests
4. Store in `session_state` only (cleared on browser close)
5. Write to `.env` only if user explicitly clicks "Save to .env"

---

## 12. Implementation Checklist

- [ ] Create `src/llm_providers/__init__.py` with base class and providers
- [ ] Implement `OllamaProvider.generate()` (adapt from current LLMClient)
- [ ] Implement `OllamaProvider.list_available_models()` using `/api/tags`
- [ ] Implement `LMStudioProvider.generate()` (OpenAI format)
- [ ] Implement `LMStudioProvider.list_available_models()` using `/v1/models`
- [ ] Create `ProviderFactory` for instantiation based on config
- [ ] Refactor `src/llm_client.py` to delegate to provider instances
- [ ] Update `.env.example` with new variables
- [ ] Add environment variable loading logic (new > old precedence)
- [ ] Update Streamlit UI with provider dropdown and model discovery
- [ ] Write unit tests for each provider class
- [ ] Write integration tests for multi-provider scenarios
- [ ] Test end-to-end with Ollama running locally
- [ ] Test end-to-end with LM Studio running locally
- [ ] Document changes in README.md

---

## 13. Open Questions

1. **Model naming conventions:** Should we normalize model names across providers (e.g., `qwen3.5:35b` vs `Qwen3.5-35B`)?
2. **Timeout handling:** Should each provider have its own timeout setting, or share the global `OLLAMA_TIMEOUT`?
3. **Streaming responses:** Should we support streaming for long-running generations (future enhancement)?
4. **Provider-specific parameters:** Should users be able to set temperature/top_p per-provider, or keep it centralized?

---

## 14. Related Documentation

- [`src/llm_client.py`](src/llm_client.py) — Current Ollama-only implementation
- [`.env.example`](.env.example) — Environment variable template
- [`streamlit_app.py`](streamlit_app.py) — UI where changes will be made
- [APIs/Providers (AI-010)](FEATURE_SPEC_multi_provider_llm.md) — This document

---

*Last updated: 2026-04-03*