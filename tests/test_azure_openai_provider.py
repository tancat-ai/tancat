"""Azure OpenAI is first-class, not a plain OpenAI-compatible endpoint.

Azure differs in three load-bearing ways: the deployment name is in the request
path, every request carries an ``api-version`` query parameter, and
authentication uses the ``api-key`` header (not ``Authorization: Bearer``).
These tests pin selectability, the required key, the URL/payload shape, and the
Bedrock-gateway documentation.
"""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.cli.session import _session_defaults
from src.llm_providers import (
    AzureOpenAIProvider,
    ChatMessage,
    create_provider_from_env,
    get_provider,
)
from src.provider_config import (
    SUPPORTED_PROVIDERS,
    api_key_env_var,
    get_provider_defaults,
    provider_requires_openai_api_key,
    resolve_openai_api_key,
    sync_openai_api_key_to_env,
)

ENDPOINT = "https://my-resource.openai.azure.com"
DEPLOYMENT = "my-gpt4o-deployment"


def _provider(api_version: str | None = None) -> AzureOpenAIProvider:
    return AzureOpenAIProvider(api_key="az-key", base_url=ENDPOINT, api_version=api_version)


class TestSelectable:
    def test_azure_is_in_the_supported_list(self) -> None:
        assert "azure-openai" in SUPPORTED_PROVIDERS

    def test_factory_returns_the_azure_provider(self) -> None:
        provider = get_provider("azure-openai", api_key="az-key", base_url=ENDPOINT)
        assert isinstance(provider, AzureOpenAIProvider)
        assert provider.provider_name == "azure-openai"

    def test_env_factory_constructs_azure(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LLM_PROVIDER", "azure-openai")
        monkeypatch.setenv("AZURE_OPENAI_API_KEY", "az-key")
        monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", ENDPOINT)
        provider = create_provider_from_env()
        assert isinstance(provider, AzureOpenAIProvider)
        assert provider.base_url == ENDPOINT

    def test_key_env_var_is_the_azure_variable(self) -> None:
        assert api_key_env_var("azure-openai") == "AZURE_OPENAI_API_KEY"

    def test_no_default_endpoint_or_deployment(self) -> None:
        # Both are resource-specific, so the user must name them.
        assert get_provider_defaults("azure-openai") == ("", "")


class TestKeyRequired:
    def test_azure_requires_a_key(self) -> None:
        assert provider_requires_openai_api_key("azure-openai") is True

    def test_missing_key_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
        with pytest.raises(ValueError, match="API key is required"):
            AzureOpenAIProvider(base_url=ENDPOINT)

    def test_missing_endpoint_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("AZURE_OPENAI_ENDPOINT", raising=False)
        with pytest.raises(ValueError, match="resource endpoint"):
            AzureOpenAIProvider(api_key="az-key")

    def test_resolve_reads_the_azure_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.setenv("AZURE_OPENAI_API_KEY", "env-az-key")
        assert resolve_openai_api_key(provider="azure-openai", user_api_key=None) == "env-az-key"

    def test_sync_writes_the_azure_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
        sync_openai_api_key_to_env("azure-openai", "session-key")
        assert os.environ["AZURE_OPENAI_API_KEY"] == "session-key"
        assert os.environ.get("OPENAI_API_KEY") is None


class TestDeploymentPath:
    @staticmethod
    def _post(provider: AzureOpenAIProvider) -> tuple[str, dict[str, object]]:
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {
            "choices": [{"message": {"content": "ok"}}],
            "model": DEPLOYMENT,
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        }
        with patch.object(provider, "_client") as mock_client:
            mock_client.post.return_value = mock_resp
            mock_post = mock_client.post
            provider.complete([ChatMessage(role="user", content="hi")], model=DEPLOYMENT)
        return mock_post.call_args[0][0], mock_post.call_args[1]["json"]

    def test_builds_the_deployment_path_and_api_version(self) -> None:
        path, _payload = self._post(_provider())
        assert path == f"/openai/deployments/{DEPLOYMENT}/chat/completions?api-version=2024-10-21"

    def test_custom_api_version_is_used(self) -> None:
        path, _payload = self._post(_provider(api_version="2025-01-01-preview"))
        assert "api-version=2025-01-01-preview" in path

    def test_api_version_comes_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AZURE_OPENAI_API_VERSION", "2024-06-01")
        provider = _provider()
        assert provider.api_version == "2024-06-01"

    def test_body_has_no_model_field(self) -> None:
        # The deployment in the URL selects the model; a body "model" is wrong.
        _path, payload = self._post(_provider())
        assert "model" not in payload
        assert payload["messages"] == [{"role": "user", "content": "hi"}]

    def test_client_sends_api_key_header_not_bearer(self) -> None:
        provider = _provider()
        assert provider._client.headers.get("api-key") == "az-key"
        assert "authorization" not in provider._client.headers

    def test_missing_deployment_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("AZURE_OPENAI_DEPLOYMENT", raising=False)
        provider = _provider()
        with pytest.raises(ValueError, match="No deployment configured"):
            provider.complete([ChatMessage(role="user", content="hi")], model="")

    def test_list_models_reads_deployments(self) -> None:
        provider = _provider()
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_resp = MagicMock()
        mock_resp.raise_for_status.return_value = None
        mock_resp.json.return_value = {"data": [{"id": "dep-a"}, {"id": "dep-b"}]}
        mock_client.get.return_value = mock_resp
        with patch("httpx.Client", return_value=mock_client):
            models = provider.list_models(timeout=5)
        assert models == ["dep-a", "dep-b"]
        assert mock_client.get.call_args[0][0] == "/openai/deployments?api-version=2024-10-21"


class TestCliSession:
    def test_session_defaults_honour_azure_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("LLM_PROVIDER", "azure-openai")
        monkeypatch.setenv("AZURE_OPENAI_ENDPOINT", ENDPOINT)
        monkeypatch.setenv("AZURE_OPENAI_DEPLOYMENT", DEPLOYMENT)
        defaults = _session_defaults()
        assert defaults["provider"] == "azure-openai"
        assert defaults["provider_base_url"] == ENDPOINT
        assert defaults["model_name"] == DEPLOYMENT


class TestBedrockGatewayDocumented:
    """The Bedrock path is documented, not built as a provider adapter."""

    @staticmethod
    def _repo_text(name: str) -> str:
        repo_root = Path(__file__).resolve().parents[1]
        return (repo_root / name).read_text(encoding="utf-8")

    def test_env_example_names_the_bedrock_gateway(self) -> None:
        text = self._repo_text(".env.example")
        assert "Bedrock Access Gateway" in text
        assert "execute-api" in text
        assert "/api/v1" in text

    def test_readme_names_the_bedrock_gateway(self) -> None:
        text = self._repo_text("README.md")
        assert "Bedrock Access Gateway" in text
        assert "execute-api" in text
        assert "/api/v1" in text

    def test_bedrock_is_not_built_as_a_provider(self) -> None:
        # The brief says route Bedrock through the gateway, never build it.
        assert "bedrock" not in SUPPORTED_PROVIDERS
