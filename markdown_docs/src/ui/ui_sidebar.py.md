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

Renders the one-line licence state, then where the licence file belongs: with no licence it
names the path the product reads (`.../licence.signed.json`) and the command that confirms it
(`tancat licence status`); with a valid licence it shows the path alone. There is nothing to
paste - the licence is a signed file, verified offline (j-0309), and the paste panel was deleted
with the token route (t-1468).

## How It Works (Internals)

Private `_`-helpers — the module's real logic (1 item). Grouped under the public function that uses them:

### `SidebarConfig`
- `_saved_index(options: tuple[str, ...], stored_value: str, default: str) -> int` (function) — Return the selectbox index for *stored_value* (falling back to *default*).

## Public API Additions

Refreshed 2026-10-02: public symbols present in the source and not listed above.

- `SidebarConfig.render_settings` (method of `SidebarConfig`): `SidebarConfig.render_settings() -> dict[str, Any]` - Render the persisted Settings panel (B-036 Phase 4). Shows app-level persisted settings (OCR backend, workspace) plus the RAG store "Learned Patterns" statistics from the B-036 Phase 3 learning loop. Returns the setti...
- `SETTING_POM_MODE` (constant): `SETTING_POM_MODE = 'pom_mode'`
- `SETTING_CONSENT_MODE` (constant): `SETTING_CONSENT_MODE = 'consent_mode'`
- `SETTING_PROVIDER` (constant): `SETTING_PROVIDER = 'provider'`
- `SETTING_MODEL_NAME` (constant): `SETTING_MODEL_NAME = 'model_name'`
- `SETTING_WORKSPACE` (constant): `SETTING_WORKSPACE = 'workspace'`
- `SETTING_LAST_PACKAGE` (constant): `SETTING_LAST_PACKAGE = 'last_package'`
- `SETTING_OCR_BACKEND` (constant): `SETTING_OCR_BACKEND = 'ocr_backend'`
- `SETTING_JIRA_PROJECT_KEY` (constant): `SETTING_JIRA_PROJECT_KEY = 'jira_project_key'`


### Additional helpers (docs refresh 2026-10-02)

Private helpers with real logic not listed above.

### `SidebarConfig.render_settings() -> dict[str, Any]` - method of `SidebarConfig`

- `_render_ocr_refusal() -> None` (method of `SidebarConfig`): Show, above the Settings expander, a configured backend that cannot run. The picker lives in a collapsed expander; a refusal must not hide there. The factory raises the same line, so the two never drift.
- `_render_ocr_backend() -> str` (method of `SidebarConfig`): Render the OCR backend picker; return the canonical value to store. Only backends this build can run are offered, and the store is kept in step with the panel in every case - including when nothing is installable and...
- `_render_pdf_reader_notice() -> None` (method of `SidebarConfig`): Say plainly when this build has no PDF reader. Separate from the OCR picker's note: that one covers the OCR tiers, while a build with no reader cannot read a PDF at all - document mode has no reader. Rendered wherever...
- `_render_learned_patterns() -> None` (method of `SidebarConfig`): Show RAG store statistics from the B-036 Phase 3 learning loop. Best-effort: a missing/unopenable store degrades to a short note instead of an error (same philosophy as always-on RAG).
- `_render_flow_memory() -> None` (method of `SidebarConfig`): AI-042-F2: flow-memory stats + prune (parity with the RAG "Learned Patterns" section above). Shows the navigation-shape memory the conftest/sweep hooks learn from passing runs: pattern count, distinct sites, cross-sit...

### `SidebarConfig.render_license_usage() -> None` - method of `SidebarConfig`

- `_render_license_entry(status: Any) -> None` (method of `SidebarConfig`): names the licence file path and the `tancat licence status` command when no licence is in force, and the path alone when one is valid. No button, form or text area - the paste flow was deleted with the token route (t-1468).

- `_module_available(name: str) -> bool` (function): Whether *name* can be imported here (used to report what this build has).
- `_gpu_unavailable_reason() -> str | None` (function): Why the GPU OCR tier is hidden, or None when it can run. Mirrors UnlimitedOCRBackend.engine_available: PyTorch -> CUDA/ROCm -> transformers. It names the true cause and how to install it, so a machine that has a G...
- `_ocr_backend_choices() -> tuple[list[str], list[str]]` (function): The OCR choices this build can run, plus honest notes on what is missing. Only backends that can actually run are offered, so the panel never advertises a choice that would silently fall back to a weaker tier. Each mi...
