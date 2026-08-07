# `src/secure_config.py` — Secure Configuration

## Purpose
Secure configuration management for credentials and API keys. Provides encrypted storage and retrieval of sensitive configuration values.

## Related
- `src/config.py` — general configuration
- `src/provider_config.py` — LLM provider configuration


## Recent API Additions

Symbols present in the source but not covered above (refresh pass, 5 items):

### `save_key(provider: str, key: str) -> None` (function)

Save an API key for *provider* to encrypted local storage.

### `load_key(provider: str) -> str | None` (function)

Load an API key for *provider* from encrypted local storage.

### `delete_key(provider: str) -> None` (function)

Delete a stored API key for *provider*.

### `list_stored_providers() -> list[str]` (function)

Return a list of provider keys that have stored API keys.

### `resolve_key(provider: str) -> str | None` (function)

Resolve an API key by checking (in priority order):

## How It Works (Internals)

Private `_`-helpers — the module's real logic (5 items). Grouped under the public function that uses them:

### `save_key`
- `_get_fernet() -> Any` (function) — Return a Fernet instance for encryption/decryption.
- `_load_config() -> dict[str, Any]` (function) — Load the decrypted config dictionary from disk.
- `_save_config(config: dict[str, Any]) -> None` (function) — Encrypt and write the config dictionary to disk.

### Internal utilities
- `_config_dir() -> Path` (function) — Return the config directory, creating it if needed.
- `_derive_key() -> bytes` (function) — Derive an encryption key from machine-specific identifiers.
