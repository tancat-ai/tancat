# `src/ui/ui_journey.py` — Credential Profiles and Journey Builder UI

## Purpose

Streamlit components for authentication credential profiles and journey step builder. Used for navigating dynamic or authenticated pages during scraping.

## Type Aliases

| Alias | Description |
|-------|-------------|
| `_CredentialProfileDict` | `dict[str, str]` with keys: `label`, `username`, `password` |
| `_JourneyStepDict` | `dict[str, str]` with keys: `action`, `url`, `selector`, `text`, `label`, `description` |

## Functions

### `render_credential_profiles() -> CredentialProfile | None`

Renders the authentication section (expander) with:
- Toggle to enable/disable authentication
- Dynamic profile list (add/remove)
- Per-profile fields: label, username, password (masked)
- Active profile selector (dropdown)
- Returns `CredentialProfile` for the active profile, or `None` if disabled

Credentials stored in `st.session_state` only — never persisted to disk.

### `render_journey_builder(additional_urls: list[str]) -> list[JourneyStep] | None`

Renders the journey builder section with:
- "Build from URL list" button (auto-populates goto+capture steps)
- Toggle to enable/disable journey builder
- Dynamic step list with add/remove
- Returns list of `JourneyStep` objects, or `None` if disabled

**Step types:**
- `goto`: URL + description
- `click`: selector + description
- `fill`: selector + value (supports `{{username}}`/`{{password}}` templates)
- `capture`: label + description (marks a page for DOM scraping)
- `wait`: selector (optional) + duration in seconds

### `_render_single_step(idx, step) -> _JourneyStepDict`

Renders a single journey step row with action selector and contextual fields.

### `_urls_to_journey_step_dicts(urls) -> list[_JourneyStepDict]`

Converts a URL list into `goto` + `capture` step pairs.

### `_dict_to_journey_step(d) -> JourneyStep`

Converts a session state dict to `JourneyStep`. Maps UI action names: `goto` → `navigate`.
