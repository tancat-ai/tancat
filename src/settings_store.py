"""Persisted application settings store (B-036 Phase 4).

Consumer-grade settings that survive app restarts — no ``.env`` edits.

Mirrors ``src/secure_config.py`` (Fernet-encrypted, machine-keyed,
corruption-tolerant) but for *non-secret* application settings such as
POM mode, consent mode, LLM provider/model, workspace, OCR backend and
the Jira project key used at export time.

Settings live in their own file (``~/.ai-test-gen/settings.enc``) rather
than inside ``config.enc`` so API-key storage and settings storage never
clobber each other's writes (both modules persist the whole dict they
loaded; sharing one file would drop whichever was written second).

Usage::

    from src.settings_store import load_setting, save_setting

    save_setting("pom_mode", True)
    pom_mode = load_setting("pom_mode", False)

Values are only persisted when explicitly saved; ``load_setting`` returns
its ``default`` for never-saved keys, so callers keep applying their own
fallback chains (e.g. ``OCR_BACKEND`` env var during the transition
window).
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from src.secure_config import _config_dir, _get_fernet

logger = logging.getLogger(__name__)

# Documented defaults — used by the UI as fallbacks when a setting has
# never been saved. Not merged into the stored dict: the store holds only
# what the user explicitly set, so callers can distinguish "never set"
# from "set to the default" (important for the OCR_BACKEND env fallback).
DEFAULT_SETTINGS: dict[str, Any] = {
    "pom_mode": False,
    "consent_mode": "auto-dismiss",
    "provider": "",
    "model_name": "",
    "workspace": "default",
    "ocr_backend": "pymupdf",
    "jira_project_key": "TEST",
}


def _settings_path() -> Path:
    """Return the encrypted settings file path (creates the config dir)."""
    return _config_dir() / "settings.enc"


def _load_settings() -> dict[str, Any]:
    """Load the decrypted settings dict; empty dict when unset/corrupt.

    Mirrors ``secure_config._load_config``: a missing file, undecryptable
    content (e.g. key derivation changed) or malformed JSON all degrade to
    an empty dict — never an exception.
    """
    path = _settings_path()
    if not path.exists():
        return {}
    try:
        fernet = _get_fernet()
        decrypted = fernet.decrypt(path.read_bytes())
        data = json.loads(decrypted.decode())
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save_settings(data: dict[str, Any]) -> None:
    """Encrypt and write the settings dict to disk."""
    fernet = _get_fernet()
    encrypted = fernet.encrypt(json.dumps(data, indent=2).encode())
    path = _settings_path()
    path.write_bytes(encrypted)
    # Restrict permissions on Unix
    if os.name != "nt":
        os.chmod(path, 0o600)


class SettingsStore:
    """Encrypted, persisted key-value settings (secure_config pattern).

    Stateless: every read decrypts the file fresh (tiny), so tests and
    callers can monkeypatch :func:`_settings_path` and see live results.
    """

    def get(self, key: str, default: Any = None) -> Any:
        """Return *key*'s saved value, or *default* when never saved."""
        return _load_settings().get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Persist a single key/value pair (best-effort, never crashes)."""
        try:
            data = _load_settings()
            data[key] = value
            _save_settings(data)
        except Exception as exc:
            logger.warning("Failed to persist setting '%s': %s", key, exc)

    def update(self, mapping: dict[str, Any]) -> None:
        """Persist several key/value pairs in one write."""
        try:
            data = _load_settings()
            data.update(mapping)
            _save_settings(data)
        except Exception as exc:
            logger.warning("Failed to persist %d setting(s): %s", len(mapping), exc)

    def delete(self, key: str) -> None:
        """Remove a saved setting (no-op when absent)."""
        try:
            data = _load_settings()
            data.pop(key, None)
            _save_settings(data)
        except Exception as exc:
            logger.warning("Failed to delete setting '%s': %s", key, exc)

    def get_all(self) -> dict[str, Any]:
        """Return every saved setting (never-saved keys omitted)."""
        return _load_settings()

    def reset(self) -> None:
        """Delete the settings file — next read returns defaults."""
        _settings_path().unlink(missing_ok=True)


_STORE = SettingsStore()


# ── Module-level convenience API (mirrors secure_config.load_key/save_key) ─


def load_setting(key: str, default: Any = None) -> Any:
    """Return a persisted setting, or *default* when never saved."""
    return _STORE.get(key, default)


def save_setting(key: str, value: Any) -> None:
    """Persist a single setting."""
    _STORE.set(key, value)


def save_settings(mapping: dict[str, Any]) -> None:
    """Persist several settings in one encrypted write."""
    _STORE.update(mapping)


def get_all_settings() -> dict[str, Any]:
    """Return all persisted settings (empty dict when none saved yet)."""
    return _STORE.get_all()


def reset_settings() -> None:
    """Delete the settings store (used by tests / "reset to defaults")."""
    _STORE.reset()
