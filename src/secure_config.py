"""Encrypted API key storage for the AI Playwright Test Generator.

Stores provider API keys in an encrypted config file at
``~/.ai-test-gen/config.enc`` using Fernet symmetric encryption.

The encryption key comes from one of:

1. ``AITEST_CONFIG_KEY`` in the environment (a passphrase, hashed with
   SHA-256) - use this for headless and CI deployments.
2. ``~/.ai-test-gen/config.key`` - a random 32-byte key created on first
   use, readable only by the owner (0600 on POSIX, an owner-only ACL on
   Windows).

It is deliberately NOT derived from machine identifiers such as the MAC
address, hostname or CPU architecture: those are guessable, so the old
scheme was obfuscation rather than encryption.

Product deployments should prefer environment injection from the
customer's own secret store; the local key file is the air-gapped
fallback.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import subprocess
from pathlib import Path
from typing import Any


def _config_dir() -> Path:
    """Return the config directory, creating it owner-only if needed."""
    home = Path.home()
    config_dir = home / ".ai-test-gen"
    # exist_ok=True is race-safe: on a fresh machine several workers create
    # the directory at once, and a plain mkdir raises FileExistsError for all
    # but one. _restrict_to_owner is idempotent and best-effort, so it also
    # covers a directory created by a racing worker (or one that already
    # existed with the wrong permissions).
    config_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    _restrict_to_owner(config_dir)
    return config_dir


def _config_path() -> Path:
    """Return the path to the encrypted config file."""
    return _config_dir() / "config.enc"


def _key_path() -> Path:
    """Return the path to the local master-key file."""
    return _config_dir() / "config.key"


def _restrict_to_owner(path: Path) -> None:
    """Restrict *path* to the current user, best effort.

    POSIX: mode 0600 for a file, 0700 for a directory.
    Windows: replace inherited ACLs with a single grant to the current
    user (``os.chmod`` on Windows only changes the read-only flag, so it
    cannot express owner-only). A permission failure is ignored: it must
    never break the save.
    """
    try:
        if os.name == "nt":
            user = os.environ.get("USERNAME", "").strip()
            if not user:
                return
            subprocess.run(
                [
                    "icacls",
                    str(path),
                    "/inheritance:r",
                    "/grant:r",
                    f"{user}:F",
                    "SYSTEM:F",
                ],
                check=False,
                capture_output=True,
            )
        else:
            os.chmod(path, 0o600 if path.is_file() else 0o700)
    except OSError:
        return


def _derive_key() -> bytes:
    """Return the 32-byte Fernet key.

    Priority:

    1. ``AITEST_CONFIG_KEY`` when set (a passphrase, hashed with SHA-256).
    2. ``~/.ai-test-gen/config.key`` - a random 32-byte key created on
       first use.

    It is NOT derived from machine identifiers (MAC address, hostname,
    CPU architecture). Those are guessable, so the old scheme was
    obfuscation rather than encryption.
    """
    passphrase = os.environ.get("AITEST_CONFIG_KEY", "").strip()
    if passphrase:
        return hashlib.sha256(passphrase.encode()).digest()

    key_path = _key_path()
    if key_path.exists():
        try:
            raw = base64.urlsafe_b64decode(key_path.read_bytes().strip())
            if len(raw) == 32:
                return raw
        except ValueError, OSError:
            pass

    key = os.urandom(32)
    key_path.write_bytes(base64.urlsafe_b64encode(key))
    _restrict_to_owner(key_path)
    return key


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
        "azure-openai": "AZURE_OPENAI_API_KEY",
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
    _restrict_to_owner(path)
