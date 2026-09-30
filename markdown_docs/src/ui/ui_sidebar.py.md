# `src/ui/ui_sidebar.py` — Sidebar Configuration Panel

## Purpose

Streamlit sidebar for LLM provider selection and test structure configuration.

## Class: `SidebarConfig`

### `render() -> dict[str, Any]` (static)

Renders the configuration sidebar:

| Widget | Key | Description |
|--------|-----|-------------|
| Selectbox | `provider` | LLM provider (`SUPPORTED_PROVIDERS` with labels from `PROVIDER_LABELS`) |
| Toggle | `pom_mode` | Page Object Model generation (`False` default) |

**Provider options** (from `src.provider_config`):
- Ollama (local)
- LM Studio (local)
- OpenAI-Compatible (local)
- OpenAI (cloud)

**Returns:** `{"provider": str, "pom_mode": bool}`

**POM Mode:** When enabled, generates tests using Page Object Model classes with evidence-aware locators. Stored in `st.session_state.pom_mode`.

### `render_license_usage()` (static)

Renders the one-line licence state, then a small action (`Enter a licence` / `Replace licence`)
and a hidden paste panel. The panel is not permanently visible: it opens on the action and
closes after a successful save; a refused token or a save error shows its reason in the panel.
The token field is cleared after every outcome, so reopening it never prefills the previous
token. Saving calls `save_license_key` and writes `~/.ai-test-gen/license.key`.

## How It Works (Internals)

Private `_`-helpers — the module's real logic (1 item). Grouped under the public function that uses them:

### `SidebarConfig`
- `_saved_index(options: tuple[str, ...], stored_value: str, default: str) -> int` (function) — Return the selectbox index for *stored_value* (falling back to *default*).
