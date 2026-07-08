# `src/ui/ui_downloads.py` — Report Download Buttons

## Purpose

Streamlit component that renders download buttons for all generated reports.

## Class: `RenderDownloads`

### `render() -> None` (static)

Renders a 4-column row of download buttons:

| Button | File | MIME | Data Source |
|--------|------|------|-------------|
| Download Manifest | `scrape_manifest.json` | `application/json` | Reads file from `pipeline_manifest_path` |
| Download Local Report | `report_local.md` | `text/markdown` | `pipeline_local_report` |
| Download Jira Report | `report_jira.md` | `text/markdown` | `pipeline_jira_report` |
| Download HTML Report | `report.html` | `text/html` | `pipeline_html_report` |

Buttons are disabled when the corresponding session state key is empty.

Also displays report file paths as `st.caption` when available.
