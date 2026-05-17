"""
LLM Provider implementations for AI-Playwright-Test-Generator.

This module provides a unified interface for interacting with different LLM backends:
- Ollama (native API)
- LM Studio (Open/AI-compatible API)
- Any OpenAI-compatible server

All providers implement the LLMProvider abstract base class.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class ChatMessage:
    """Represents a single chat message in a conversation."""

    role: str  # 'system', 'user', or 'assistant'
    content: str


@dataclass
class ChatCompletion:
    """Represents an LLM completion response."""

    content: str
    model: str
    usage: dict[str, int] | None = None  # {'prompt_tokens': int, 'completion_tokens': int}


class LLMProvider(ABC):
    """Abstract base class for all LLM providers.

    All provider implementations must implement these methods to ensure
    a consistent interface across different backends.
    """

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Returns the name of this provider (e.g., 'ollama', 'lm-studio')."""
        pass

    @property
    @abstractmethod
    def base_url(self) -> str:
        """Returns the configured provider base URL."""
        pass

    @abstractmethod
    def complete(self, messages: list[ChatMessage], model: str | None = None, timeout: int = 300) -> ChatCompletion:
        """Send a chat completion request to the LLM.

        Args:
            messages: List of chat messages in conversation order.
            model: Optional model override (uses provider default if not provided).
            timeout: Request timeout in seconds.

        Returns:
            ChatCompletion with the assistant's response.

        Raises:
            TimeoutError: If the request exceeds the timeout.
            ConnectionError: If the provider is unreachable.
            ValueError: If the model is invalid or not available.
        """
        pass

    @abstractmethod
    def list_models(self, timeout: int = 30) -> list[str]:
        """List available models on this provider.

        Args:
            timeout: Request timeout in seconds for listing models.

        Returns:
            List of model names (e.g., ['qwen2.5:7b', 'llama2:latest']).

        Raises:
            ConnectionError: If the provider is unreachable.
        """
        pass


class OllamaProvider(LLMProvider):
    """Ollama native API provider implementation."""

    DEFAULT_BASE_URL = "http://localhost:11434"
    PROVIDER_NAME = "ollama"

    def __init__(self, base_url: str | None = None, **kwargs: Any) -> None:
        import os

        import httpx

        self._base_url = base_url or self.DEFAULT_BASE_URL.rstrip("/")
        timeout_value = int(os.environ.get("OLLAMA_TIMEOUT", "300"))

        self._client = httpx.Client(
            base_url=self._base_url,
            timeout=timeout_value if timeout_value else 300,
        )

    @property
    def provider_name(self) -> str:
        return self.PROVIDER_NAME

    @property
    def base_url(self) -> str:
        """Returns the configured Ollama API base URL."""
        import os

        return os.environ.get("OLLAMA_BASE_URL", self.DEFAULT_BASE_URL).rstrip("/")

    def complete(self, messages: list[ChatMessage], model: str | None = None, timeout: int = 300) -> ChatCompletion:
        import os

        model = model or os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")

        # Ollama expects messages in its native format
        ollama_messages = [{"role": msg.role, "content": msg.content} for msg in messages]

        response = self._client.post(
            "/api/chat", json={"model": model, "messages": ollama_messages, "stream": False}, timeout=timeout
        )

        response.raise_for_status()
        data = response.json()

        return ChatCompletion(
            content=data["message"]["content"],
            model=data.get("model", model),
            usage={"prompt_tokens": data.get("eval_count", 0), "completion_tokens": data.get("eval_count", 0)}
            if "eval_count" in data
            else None,
        )

    def list_models(self, timeout: int = 30) -> list[str]:
        response = self._client.get("/api/tags", timeout=timeout)
        response.raise_for_status()

        return [m["name"] for m in response.json().get("models", [])]


class LMStudioProvider(LLMProvider):
    """LM Studio (OpenAI-compatible API) provider implementation."""

    DEFAULT_BASE_URL = "http://localhost:1234"
    PROVIDER_NAME = "lm-studio"

    def __init__(self, base_url: str | None = None, **kwargs: Any) -> None:
        self._base_url = base_url or self.DEFAULT_BASE_URL.rstrip("/")
        import httpx

        self._client = httpx.Client(base_url=f"{self._base_url}/v1", timeout=300)

    @property
    def provider_name(self) -> str:
        return self.PROVIDER_NAME

    @property
    def base_url(self) -> str:
        """Returns the configured LM Studio API base URL."""
        import os

        return os.environ.get("LM_STUDIO_BASE_URL", self.DEFAULT_BASE_URL).rstrip("/")

    def complete(self, messages: list[ChatMessage], model: str | None = None, timeout: int = 300) -> ChatCompletion:
        import os

        model = model or os.environ.get("LM_STUDIO_MODEL", "lmstudio-community/Qwen2.5-7B-Instruct-GGUF")

        # Normalize messages to OpenAI format (LM Studio expects this)
        openai_messages = [{"role": msg.role, "content": msg.content} for msg in messages]

        response = self._client.post(
            "/chat/completions", json={"model": model, "messages": openai_messages, "stream": False}, timeout=timeout
        )

        response.raise_for_status()
        data = response.json()

        return ChatCompletion(
            content=data["choices"][0]["message"]["content"],
            model=data.get("model", model),
            usage={
                "prompt_tokens": data.get("usage", {}).get("prompt_tokens", 0),
                "completion_tokens": data.get("usage", {}).get("completion_tokens", 0),
            }
            if "usage" in data
            else None,
        )

    def get_loaded_model(self, timeout: int = 5) -> str | None:
        """Return the model ID that is currently loaded in LM Studio memory.

        Queries LM Studio's native API endpoint which exposes model state.
        Returns the first LLM-type model whose state is 'loaded', or None
        if no model is currently loaded (e.g. JIT-loading mode).
        """
        try:
            # /api/v0/models is LM Studio's native endpoint (not OpenAI-compatible)
            # so hit the base URL directly, not the /v1 proxy
            response = self._client.get(f"{self._base_url}/api/v0/models", timeout=timeout)
            response.raise_for_status()
            for model in response.json().get("data", []):
                if model.get("state") == "loaded" and model.get("type") in ("llm", "vlm"):
                    return model["id"]
        except Exception:
            # If the endpoint is unavailable, fall back gracefully
            pass
        return None

    def list_models(self, timeout: int = 30) -> list[str]:
        response = self._client.get("/models", timeout=timeout)
        response.raise_for_status()

        return [m["id"] for m in response.json().get("data", [])]


class OpenAIProvider(LLMProvider):
    """OpenAI API provider implementation."""

    PROVIDER_NAME = "openai"

    def __init__(self, api_key: str | None = None, base_url: str | None = None):
        import os

        self._api_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not self._api_key:
            raise ValueError("OPENAI_API_KEY environment variable is required")

        self._base_url = base_url or "https://api.openai.com/v1"

        import httpx

        self._client = httpx.Client(
            base_url=self._base_url, timeout=300, headers={"Authorization": f"Bearer {self._api_key}"}
        )

    @property
    def provider_name(self) -> str:
        return self.PROVIDER_NAME

    @property
    def base_url(self) -> str:
        """Returns the configured OpenAI API base URL."""
        return self._base_url

    @property
    def api_key(self) -> str | None:
        """Returns the configured OpenAI API key (masked)."""
        if not self._api_key:
            return None
        return f"{self._api_key[:4]}...{self._api_key[-4:]}" if len(self._api_key) > 8 else "***"

    def complete(self, messages: list[ChatMessage], model: str | None = None, timeout: int = 300) -> ChatCompletion:
        import os

        model = model or os.environ.get("OPENAI_MODEL", "gpt-4o")

        openai_messages = [{"role": msg.role, "content": msg.content} for msg in messages]

        response = self._client.post(
            "/chat/completions", json={"model": model, "messages": openai_messages, "stream": False}, timeout=timeout
        )

        response.raise_for_status()
        data = response.json()

        return ChatCompletion(
            content=data["choices"][0]["message"]["content"],
            model=data.get("model", model),
            usage={
                "prompt_tokens": data.get("usage", {}).get("prompt_tokens", 0),
                "completion_tokens": data.get("usage", {}).get("completion_tokens", 0),
            }
            if "usage" in data
            else None,
        )

    def list_models(self, timeout: int = 30) -> list[str]:
        response = self._client.get("/models", timeout=timeout)
        response.raise_for_status()

        return [m["id"] for m in response.json().get("data", []) if not m.get("owned_by", "").startswith("system")]


# Exported symbols
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


def auto_detect_provider() -> LLMProvider:
    """Probe local ports to find an active LLM provider.

    Checks:
    1. LM Studio (http://localhost:1234/v1)
    2. Ollama (http://localhost:11434)

    Returns:
        The first active LLMProvider found.

    Raises:
        ConnectionError: If no local providers are active.
    """
    import httpx

    # 1. Try LM Studio
    try:
        lm_url = "http://localhost:1234/v1/models"
        resp = httpx.get(lm_url, timeout=2.0)
        if resp.status_code == 200:
            return LMStudioProvider()
    except httpx.ConnectError, httpx.TimeoutException:
        pass

    # 2. Try Ollama
    try:
        ollama_url = "http://localhost:11434/api/tags"
        resp = httpx.get(ollama_url, timeout=2.0)
        if resp.status_code == 200:
            return OllamaProvider()
    except httpx.ConnectError, httpx.TimeoutException:
        pass

    raise ConnectionError("No local LLM providers (LM Studio or Ollama) are currently active.")


def get_provider(provider_name: str, **kwargs: Any) -> LLMProvider:
    """Factory function to create an LLM provider instance.

    Args:
        provider_name: Name of the provider ('ollama', 'lm-studio', or 'openai').
        **kwargs: Additional keyword arguments passed to the provider constructor.

    Returns:
        An instantiated LLMProvider subclass.

    Raises:
        ValueError: If an unknown provider name is provided.
    """
    providers: dict[str, type[LLMProvider]] = {
        "ollama": OllamaProvider,
        "lm-studio": LMStudioProvider,
        "openai": OpenAIProvider,
    }

    if provider_name not in providers:
        raise ValueError(f"Unknown provider '{provider_name}'. Available providers: {list(providers.keys())}")

    return providers[provider_name](**kwargs)


def create_provider_from_env() -> LLMProvider:
    """Create an LLM provider instance from environment variables.

    This function reads the following env vars to determine which provider to use:
    - LLM_PROVIDER: 'ollama', 'lm-studio', or 'openai' (default: 'ollama')

    Each provider has its own required environment variables:
    - ollama: OLLAMA_BASE_URL, OLLAMA_MODEL, OLLAMA_TIMEOUT
    - lm-studio: LM_STUDIO_BASE_URL, LM_STUDIO_MODEL
    - openai: OPENAI_API_KEY, OPENAI_MODEL

    Returns:
        An instantiated LLMProvider subclass.

    Raises:
        ValueError: If required environment variables are missing or invalid.
    """
    import os

    provider_name = os.environ.get("LLM_PROVIDER", "ollama").lower()

    if provider_name == "ollama":
        return OllamaProvider(base_url=os.environ.get("OLLAMA_BASE_URL"))
    elif provider_name == "lm-studio":
        return LMStudioProvider(base_url=os.environ.get("LM_STUDIO_BASE_URL"))
    elif provider_name == "openai":
        return OpenAIProvider(api_key=os.environ.get("OPENAI_API_KEY"), base_url=os.environ.get("OPENAI_BASE_URL"))
    else:
        raise ValueError(f"Unknown LLM_PROVIDER '{provider_name}'. Must be one of: ollama, lm-studio, openai")
