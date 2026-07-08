# `src/ui/ui_requirements.py` — Requirements Input Panel

## Purpose

Streamlit component for entering user story requirements via text paste or file upload.

## Class: `RequirementsInput`

### Constants

| Constant | Description |
|----------|-------------|
| `BASELINE_STARTING_URL` | `"https://automationexercise.com/"` |
| `BASELINE_ADDITIONAL_URLS` | `""` |
| `BASELINE_REQUIREMENTS` | Pre-defined automationexercise.com user story with 8 acceptance criteria |

### `render(base_url, urls_input) -> tuple[str, str, str, str]` (static)

Renders requirements input with two modes:

| Mode | Widget | Description |
|------|--------|-------------|
| Paste Text | `st.text_area` | Free-form requirements input with placeholder example |
| Upload File | `st.file_uploader` | Upload `.md` or `.txt` file, displayed in read-only text area |

Returns `(input_mode, raw_text, base_url, urls_input)`.
