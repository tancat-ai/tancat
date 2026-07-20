"""Encrypted API key storage for the AI Playwright Test Generator.

Stores provider API keys in an encrypted config file at
``~/.ai-test-gen/config.enc`` using Fernet symmetric encryption.
The encryption key is derived from the machine's unique identifier,
providing local-only access without requiring a master password.

Also supports cloud deployment scenarios where keys are injected
via environment variables (Azure Key Vault, AWS Secrets Manager).
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import platform
import uuid
from pathlib import Path
from typing import Any


def _config_dir() -> Path:
    """Return the config directory, creating it if needed."""
    home = Path.home()
    config_dir = home / ".ai-test-gen"
    config_dir.mkdir(mode=0o700, exist_ok=True)
    return config_dir


def _config_path() -> Path:
    """Return the path to the encrypted config file."""
    return _config_dir() / "config.enc"


def _derive_key() -> bytes:
    """Derive an encryption key from machine-specific identifiers.

    Uses the machine's UUID (platform-independent) and hostname to
    produce a stable 32-byte key.  This means the config file can only
    be decrypted on the same machine that created it.

    On cloud VMs the machine UUID may change across reprovisioning,
    which would orphan existing encrypted configs.  In those environments
    prefer environment-variable injection (Azure Key Vault / AWS Secrets
    Manager) over local encrypted storage.
    """
    identifiers = [
        str(uuid.getnode()),  # MAC-based node ID
        platform.node(),  # hostname
        platform.machine(),  # e.g. 'AMD64'
        "ai-playwright-test-gen-v1",  # namespace salt
    ]
    combined = "|".join(identifiers)
    return hashlib.sha256(combined.encode()).digest()


try:
    from cryptography.fernet import Fernet

    _HAS_CRYPTO = True
except ImportError:
    _HAS_CRYPTO = False


def _get_fernet() -> Any:
    """Return a Fernet instance for encryption/decryption.

    Raises ImportError if cryptography is not installed.
    """
    if not _HAS_CRYPTO:
        raise ImportError(
            "The 'cryptography' package is required for encrypted key storage. Install it with: uv add cryptography"
        )
    key = base64.urlsafe_b64encode(_derive_key())
    return Fernet(key)


# ── Public API ────────────────────────────────────────────────────────────


def save_key(provider: str, key: str) -> None:
    """Save an API key for *provider* to encrypted local storage.

    Args:
        provider: Provider key name (e.g. 'openai', 'ollama').
        key: The API key / secret to store.
    """
    fernet = _get_fernet()
    config = _load_config()
    config["keys"][provider] = fernet.encrypt(key.encode()).decode()
    _save_config(config)


def load_key(provider: str) -> str | None:
    """Load an API key for *provider* from encrypted local storage.

    Returns:
        The decrypted key, or None if not found or decryption fails.
    """
    try:
        fernet = _get_fernet()
        config = _load_config()
        encrypted = config.get("keys", {}).get(provider)
        if not encrypted:
            return None
        return fernet.decrypt(encrypted.encode()).decode()
    except Exception:
        return None


def delete_key(provider: str) -> None:
    """Delete a stored API key for *provider*."""
    config = _load_config()
    config["keys"].pop(provider, None)
    _save_config(config)


def list_stored_providers() -> list[str]:
    """Return a list of provider keys that have stored API keys."""
    config = _load_config()
    return list(config.get("keys", {}).keys())


def resolve_key(provider: str) -> str | None:
    """Resolve an API key by checking (in priority order):

    1. Process environment variable (provider-specific, e.g. OPENAI_API_KEY)
    2. Encrypted local config file (~/.ai-test-gen/config.enc)
    3. None — caller must prompt the user

    Args:
        provider: Provider key name (e.g. 'openai').

    Returns:
        The resolved key, or None if no key is available.
    """
    # 1. Environment variable (cloud injection / user preference)
    env_var_map: dict[str, str] = {
        "openai": "OPENAI_API_KEY",
        "ollama": "OLLAMA_API_KEY",
        "lm-studio": "LM_STUDIO_API_KEY",
        "openai-local": "OPENAI_API_KEY",
    }
    env_var = env_var_map.get(provider, "")
    if env_var:
        env_val = os.environ.get(env_var, "").strip()
        if env_val:
            return env_val

    # 2. Encrypted local config
    stored = load_key(provider)
    if stored:
        return stored

    return None


# ── Internal helpers ──────────────────────────────────────────────────────


def _load_config() -> dict[str, Any]:
    """Load the decrypted config dictionary from disk."""
    path = _config_path()
    if not path.exists():
        return {"version": 1, "keys": {}}

    fernet = _get_fernet()
    try:
        encrypted_data = path.read_bytes()
        decrypted = fernet.decrypt(encrypted_data)
        return json.loads(decrypted.decode())
    except Exception:
        # If decryption fails (e.g. machine changed), start fresh
        return {"version": 1, "keys": {}}


def _save_config(config: dict[str, Any]) -> None:
    """Encrypt and write the config dictionary to disk."""
    fernet = _get_fernet()
    plaintext = json.dumps(config, indent=2).encode()
    encrypted = fernet.encrypt(plaintext)
    path = _config_path()
    path.write_bytes(encrypted)
    # Restrict permissions on Unix
    if os.name != "nt":
        os.chmod(path, 0o600)
