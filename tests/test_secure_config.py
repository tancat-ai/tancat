"""Tests for src/secure_config.py — encrypted API key storage."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.secure_config import (
    _config_dir,
    _config_path,
    _derive_key,
    _get_fernet,
    _load_config,
    _save_config,
    delete_key,
    list_stored_providers,
    load_key,
    resolve_key,
    save_key,
)


class TestKeyDerivation:
    """Tests for the encryption key derivation."""

    def test_derive_key_returns_32_bytes(self) -> None:
        key = _derive_key()
        assert len(key) == 32
        assert isinstance(key, bytes)

    def test_derive_key_is_stable(self) -> None:
        """Key should be deterministic for the same machine."""
        key1 = _derive_key()
        key2 = _derive_key()
        assert key1 == key2

    def test_derive_key_is_not_empty(self) -> None:
        key = _derive_key()
        assert key != b"\x00" * 32


class TestConfigPaths:
    """Tests for config file paths."""

    def test_config_dir_is_in_home(self) -> None:
        d = _config_dir()
        assert d.name == ".ai-test-gen"
        assert d.parent == Path.home()

    def test_config_path_ends_with_config_enc(self) -> None:
        p = _config_path()
        assert p.name == "config.enc"
        assert p.parent.name == ".ai-test-gen"


class TestSaveAndLoadKey:
    """Integration tests for save_key / load_key / delete_key."""

    @pytest.fixture(autouse=True)
    def _isolate_config(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Redirect config storage to a temp directory."""
        self._tmp_config = tmp_path / "config.enc"
        monkeypatch.setattr("src.secure_config._config_path", lambda: self._tmp_config)
        monkeypatch.setattr("src.secure_config._config_dir", lambda: tmp_path)
        # Ensure clean state
        if self._tmp_config.exists():
            self._tmp_config.unlink()

    def test_save_and_load_key(self) -> None:
        save_key("openai", "sk-test-key-1234")
        result = load_key("openai")
        assert result == "sk-test-key-1234"

    def test_load_nonexistent_key_returns_none(self) -> None:
        result = load_key("nonexistent")
        assert result is None

    def test_load_key_from_empty_config_returns_none(self) -> None:
        """Even with an empty config file, loading a missing key returns None."""
        # Create empty config
        _save_config({"version": 1, "keys": {}})
        result = load_key("nonexistent")
        assert result is None

    def test_delete_key_removes_it(self) -> None:
        save_key("openai", "sk-delete-me")
        delete_key("openai")
        assert load_key("openai") is None

    def test_delete_nonexistent_key_does_not_raise(self) -> None:
        delete_key("nonexistent")  # Should not raise

    def test_list_stored_providers(self) -> None:
        save_key("openai", "key1")
        save_key("ollama", "key2")
        providers = list_stored_providers()
        assert sorted(providers) == ["ollama", "openai"]

    def test_list_empty_when_no_keys(self) -> None:
        assert list_stored_providers() == []

    def test_overwrite_existing_key(self) -> None:
        save_key("openai", "original")
        save_key("openai", "updated")
        assert load_key("openai") == "updated"

    def test_key_not_readable_on_different_machine(self) -> None:
        """If decryption fails (e.g. key derivation changes), load should return None."""
        save_key("openai", "secret")
        # Corrupt the file
        self._tmp_config.write_bytes(b"garbage-data")
        result = load_key("openai")
        assert result is None

    def test_multiple_providers_independent(self) -> None:
        save_key("openai", "openai-key")
        save_key("ollama", "ollama-key")
        assert load_key("openai") == "openai-key"
        assert load_key("ollama") == "ollama-key"
        delete_key("openai")
        assert load_key("openai") is None
        assert load_key("ollama") == "ollama-key"

    def test_special_characters_in_key(self) -> None:
        key = "sk-!@#$%^&*()_+-=[]{}|;':\",./<>?`~"
        save_key("openai", key)
        assert load_key("openai") == key

    def test_empty_key_is_stored_and_retrieved(self) -> None:
        save_key("openai", "")
        assert load_key("openai") == ""


class TestResolveKey:
    """Tests for the resolve_key priority chain."""

    @pytest.fixture(autouse=True)
    def _isolate(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self._tmp_config = tmp_path / "config.enc"
        monkeypatch.setattr("src.secure_config._config_path", lambda: self._tmp_config)
        monkeypatch.setattr("src.secure_config._config_dir", lambda: tmp_path)
        if self._tmp_config.exists():
            self._tmp_config.unlink()
        # Clear any env var interference
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        monkeypatch.delenv("OLLAMA_API_KEY", raising=False)

    def test_resolve_from_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "env-key-123")
        result = resolve_key("openai")
        assert result == "env-key-123"

    def test_resolve_from_encrypted_storage_fallback(self) -> None:
        save_key("openai", "stored-key-456")
        result = resolve_key("openai")
        assert result == "stored-key-456"

    def test_env_takes_priority_over_stored(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "env-priority")
        save_key("openai", "stored-ignored")
        result = resolve_key("openai")
        assert result == "env-priority"

    def test_resolve_returns_none_when_no_source(self) -> None:
        result = resolve_key("openai")
        assert result is None

    def test_resolve_unknown_provider_returns_none(self) -> None:
        """Providers without mapped env vars still check storage."""
        result = resolve_key("unknown-provider")
        assert result is None

    def test_openai_local_uses_same_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("OPENAI_API_KEY", "shared-key")
        assert resolve_key("openai-local") == "shared-key"


class TestFernetHelper:
    """Tests for the Fernet helper functions."""

    def test_get_fernet_returns_fernet_instance(self) -> None:
        fernet = _get_fernet()
        assert fernet is not None
        # Verify it can encrypt/decrypt
        encrypted = fernet.encrypt(b"test")
        decrypted = fernet.decrypt(encrypted)
        assert decrypted == b"test"


class TestLoadSaveConfigInternals:
    """Tests for the internal _load_config / _save_config functions."""

    @pytest.fixture(autouse=True)
    def _isolate(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self._tmp_config = tmp_path / "config.enc"
        monkeypatch.setattr("src.secure_config._config_path", lambda: self._tmp_config)
        monkeypatch.setattr("src.secure_config._config_dir", lambda: tmp_path)
        if self._tmp_config.exists():
            self._tmp_config.unlink()

    def test_load_returns_default_when_no_file(self) -> None:
        config = _load_config()
        assert config == {"version": 1, "keys": {}}

    def test_save_and_load_roundtrip(self) -> None:
        original = {"version": 1, "keys": {"openai": "encrypted-blob"}}
        _save_config(original)
        loaded = _load_config()
        assert loaded == original

    def test_load_handles_corrupt_file_gracefully(self) -> None:
        self._tmp_config.write_bytes(b"not-valid-encrypted-data")
        config = _load_config()
        assert config == {"version": 1, "keys": {}}
