# `src/settings_store.py` — Persisted Application Settings

## High-Level Purpose

**Consumer-grade settings that survive app restarts** (B-036 Phase 4). The
product's feature toggles must not require `.env` edits — this module is the
persistence layer that replaces dev-era env-var gates with a persisted,
encrypted store on the same pattern as `src/secure_config.py` (Fernet,
machine-derived key, corruption-tolerant).

```
Streamlit sidebar / CLI menu (user sets a value)
    └─ save_setting(key, value)
        └─ _load_settings() + update + _save_settings()
            └─ Fernet-encrypt → ~/.ai-test-gen/settings.enc
    └─ load_setting(key, default)   # decrypts fresh on every read
        └─ Streamlit sidebar init / CLI Session seeding / OCR backend / Jira key
```

Settings live in **their own file** (`settings.enc`) rather than inside
`config.enc` — both modules persist the whole dict they loaded, so sharing one
file would silently drop whichever was written second.

**Migration targets:** `pom_mode`, `consent_mode`, `provider`/`model_name`,
`workspace`, `ocr_backend`, `jira_project_key`.

## Module Metadata

- **Lines:** ~190
- **Imports:** `json`, `logging`, `os`, `pathlib.Path`, `typing.Any`, `src.secure_config`
- **Spec:** `docs/specs/FEATURE_SPEC_B036_consumer_config.md` §6 (Change 4) / §7 removal matrix
- **Shipped:** 2026-08-03 (B-036 Phase 4)

## Constants

### `DEFAULT_SETTINGS: dict[str, Any]`
Documented defaults for every migrated setting (`pom_mode=False`,
`consent_mode="auto-dismiss"`, `provider=""`, `model_name=""`,
`workspace="default"`, `ocr_backend="pymupdf"`, `jira_project_key="TEST"`).
Used by the UI as fallbacks — **not merged into the stored dict**, so callers
can distinguish "never set" from "set to the default" (that distinction powers
the `OCR_BACKEND` env fallback during the transition window).

## Class

### `SettingsStore`
Encrypted, persisted key-value store. Stateless — every read decrypts the file
fresh (tiny), so tests and callers can monkeypatch `_settings_path` and see
live results.

| Method | Behaviour |
|--------|-----------|
| `get(key, default=None)` | Saved value, or `default` when never saved |
| `set(key, value)` | Persist one key/value pair (best-effort, logs + swallows write failures) |
| `update(mapping)` | Persist several pairs in one write |
| `delete(key)` | Remove a saved setting (no-op when absent) |
| `get_all()` | All saved settings (never-saved keys omitted) |
| `reset()` | Delete the settings file — next read returns defaults |

## Module-level functions (mirror `secure_config.save_key`/`load_key`)

- `load_setting(key, default=None)` — read one setting (never raises; missing/
  corrupt file ⇒ `default`)
- `save_setting(key, value)` — persist one setting
- `save_settings(mapping)` — persist several settings in one encrypted write
- `get_all_settings()` — all persisted settings
- `reset_settings()` — delete the store (tests / "reset to defaults")

## Internal helpers

- `_settings_path()` — `~/.ai-test-gen/settings.enc` (creates the config dir;
  monkeypatch target for tests)
- `_load_settings()` — decrypt + parse; `{}` on missing file, undecryptable
  content (e.g. key derivation changed), or non-dict JSON
- `_save_settings(data)` — encrypt + write; `chmod 600` on Unix

## Depended On By

- `src/ocr_backends.py` — `get_ocr_backend()` reads the persisted
  `ocr_backend` setting first; env is now a fallback
- `src/ui/ui_sidebar.py` — `SidebarConfig.render()` persists `provider`/
  `pom_mode`; `render_settings()` edits `ocr_backend`/`workspace` and shows RAG
  store stats
- `streamlit_app.py` — workspace init, consent-mode persistence, export-panel
  Jira project key field
- `src/cli/session.py` — `create_session()` seeds provider/model/consent/POM/
  Jira key from the store (settings win, env is fallback)
- `src/cli/main.py` — Consent/POM/Jira menu items persist to the store

## Notes

- Settings are **not secrets** — they're encrypted for consistency with
  `secure_config`, not because they need hiding.
- Write failures (e.g. `cryptography` unavailable, disk error) are logged and
  swallowed: the in-session value still applies, mirroring B-036's graceful
  degradation philosophy.
- `JIRA_PROJECT_KEY` env read was removed from `src/config.py` (constant
  default `TEST`); `LANGGRAPH_ENABLED` was removed outright (dead flag).
