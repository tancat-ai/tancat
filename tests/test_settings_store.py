"""Tests for src/settings_store.py — persisted app settings (B-036 Phase 4)."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.settings_store import (
    DEFAULT_SETTINGS,
    SettingsStore,
    _load_settings,
    _save_settings,
    get_all_settings,
    load_setting,
    reset_settings,
    save_setting,
    save_settings,
)


@pytest.fixture(autouse=True)
def _isolate_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Redirect the settings file to a temp path for every test."""
    settings_file = tmp_path / "settings.enc"
    monkeypatch.setattr("src.settings_store._settings_path", lambda: settings_file)
    if settings_file.exists():
        settings_file.unlink()


class TestDefaults:
    """Documented defaults exist for every migrated setting."""

    def test_defaults_cover_migrated_settings(self) -> None:
        for key in (
            "pom_mode",
            "consent_mode",
            "provider",
            "model_name",
            "workspace",
            "ocr_backend",
            "jira_project_key",
        ):
            assert key in DEFAULT_SETTINGS

    def test_default_ocr_backend_is_pymupdf(self) -> None:
        assert DEFAULT_SETTINGS["ocr_backend"] == "pymupdf"

    def test_default_jira_project_key_is_test(self) -> None:
        assert DEFAULT_SETTINGS["jira_project_key"] == "TEST"


class TestLoadSave:
    """Round-trip through the encrypted store."""

    def test_load_returns_empty_when_no_file(self) -> None:
        assert _load_settings() == {}

    def test_save_and_load_roundtrip(self) -> None:
        _save_settings({"pom_mode": True, "ocr_backend": "unlimited-ocr"})
        assert _load_settings() == {"pom_mode": True, "ocr_backend": "unlimited-ocr"}

    def test_load_handles_corrupt_file(self) -> None:
        from src.settings_store import _settings_path

        _settings_path().write_bytes(b"not-valid-encrypted-data")
        assert _load_settings() == {}

    def test_load_handles_non_dict_json(self) -> None:
        # Fernet-encrypt a JSON array (not a dict) — must degrade to {}.
        from src.secure_config import _get_fernet
        from src.settings_store import _settings_path

        _settings_path().write_bytes(_get_fernet().encrypt(b"[1, 2, 3]"))
        assert _load_settings() == {}

    def test_never_saved_key_returns_default(self) -> None:
        assert load_setting("pom_mode", False) is False
        assert load_setting("nope", "x") == "x"

    def test_save_setting_then_load(self) -> None:
        save_setting("pom_mode", True)
        assert load_setting("pom_mode", False) is True

    def test_save_settings_batch(self) -> None:
        save_settings({"provider": "lm-studio", "model_name": "qwen", "pom_mode": True})
        assert load_setting("provider") == "lm-studio"
        assert load_setting("model_name") == "qwen"
        assert load_setting("pom_mode") is True

    def test_overwrite_existing(self) -> None:
        save_setting("workspace", "proj-a")
        save_setting("workspace", "proj-b")
        assert load_setting("workspace") == "proj-b"

    def test_special_characters_roundtrip(self) -> None:
        value = "TEST-123 !@#$%^&*()_+"
        save_setting("jira_project_key", value)
        assert load_setting("jira_project_key") == value

    def test_get_all_returns_only_saved(self) -> None:
        save_setting("pom_mode", True)
        assert get_all_settings() == {"pom_mode": True}


class TestSettingsStoreClass:
    """The class API mirrors the module-level functions."""

    def test_get_set_delete(self) -> None:
        store = SettingsStore()
        assert store.get("consent_mode", "auto-dismiss") == "auto-dismiss"
        store.set("consent_mode", "leave-as-is")
        assert store.get("consent_mode") == "leave-as-is"
        store.delete("consent_mode")
        assert store.get("consent_mode", "auto-dismiss") == "auto-dismiss"

    def test_update(self) -> None:
        store = SettingsStore()
        store.update({"a": 1, "b": 2})
        assert store.get_all() == {"a": 1, "b": 2}

    def test_reset_removes_file(self) -> None:
        from src.settings_store import _settings_path

        save_setting("pom_mode", True)
        assert _settings_path().exists()
        reset_settings()
        assert not _settings_path().exists()
        assert load_setting("pom_mode", False) is False

    def test_delete_missing_key_does_not_raise(self) -> None:
        SettingsStore().delete("never-saved")

    def test_delete_keeps_other_keys(self) -> None:
        store = SettingsStore()
        store.update({"a": 1, "b": 2})
        store.delete("a")
        assert store.get_all() == {"b": 2}


class TestOcrBackendIntegration:
    """ocr_backend setting resolves through the store (see test_ocr_backends.py)."""

    def test_settings_wins_over_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from unittest.mock import patch

        import src.ocr_backends as ocr

        # The autouse fixture keeps the settings file empty for this test.
        monkeypatch.setenv("OCR_BACKEND", "pymupdf")
        save_setting("ocr_backend", "unlimited-ocr")
        with (
            patch("torch.cuda.is_available", return_value=True),
            patch("torch.cuda.is_bf16_supported", return_value=True),
            patch("torch.cuda.get_device_name", return_value="Test GPU"),
            patch("transformers.AutoTokenizer.from_pretrained") as tok,
            patch("transformers.AutoModel.from_pretrained") as model,
        ):
            tok.return_value = object()
            model.return_value = object()
            backend = ocr.get_ocr_backend()
        assert isinstance(backend, ocr.UnlimitedOCRBackend)

    def test_env_fallback_when_setting_never_saved(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import src.ocr_backends as ocr

        # Autouse fixture guarantees no settings file — env is the fallback.
        # AI-055: ``pymupdf`` (the legacy default) now resolves to the ``auto``
        # tier (tier-0 whole-doc + tier-1 CPU OCR for image-only pages).
        monkeypatch.setenv("OCR_BACKEND", "pymupdf")
        backend = ocr.get_ocr_backend()
        assert isinstance(backend, ocr.AutoOcrBackend)


class TestSessionSeeding:
    """CLI ``create_session`` seeds from the settings store (B-036 Phase 4)."""

    def test_create_session_uses_persisted_values(self) -> None:
        from src.cli.session import create_session

        save_settings(
            {
                "provider": "lm-studio",
                "model_name": "persisted-model",
                "consent_mode": "leave-as-is",
                "pom_mode": True,
                "jira_project_key": "PAYMENTS",
            }
        )
        session = create_session()
        assert session.provider == "lm-studio"
        assert session.model_name == "persisted-model"
        assert session.consent_mode == "leave-as-is"
        assert session.pom_mode is True
        assert session.jira_project_key == "PAYMENTS"

    def test_create_session_defaults_without_settings(self) -> None:
        from src.cli.session import create_session

        session = create_session()
        assert session.consent_mode == "auto-dismiss"
        assert session.pom_mode is False
        assert session.jira_project_key == "TEST"


class TestJiraProjectKeyNoEnv:
    """src.config.JIRA_PROJECT_KEY is a constant — env read removed."""

    def test_constant_ignores_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        import importlib

        monkeypatch.setenv("JIRA_PROJECT_KEY", "SHOULD-BE-IGNORED")
        from src import config as src_config

        importlib.reload(src_config)
        assert src_config.JIRA_PROJECT_KEY == "TEST"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
