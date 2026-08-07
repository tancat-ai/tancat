# `cli/evidence_cli.py` — Evidence CLI (AI-028)

## Purpose
Command-line interface for evidence search, inspection, rerun, and export. Lets users find evidence files (by query/status), drill into a result's details, rerun the matching tests, and export to CSV/JUnit XML/NDJSON.

## Usage
```bash
python -m cli.evidence_cli search --query "cart" --status failed --verbose
python -m cli.evidence_cli detail 3                      # drill into result #3 from last search
python -m cli.evidence_cli search --query "cart" --status failed --rerun
python -m cli.evidence_cli export --format csv --status failed -o evidence.csv
```

## Commands
| Command | Description |
|---------|-------------|
| `search` | Query the evidence index (`src.evidence_index.EvidenceIndex`) with `--query`, `--status`, `--condition`, `--story` filters; `--verbose` shows timestamps; `--rerun` re-executes the matching tests |
| `detail <n>` | Show full step details for result #N from the last search (locator, assertion type, timing, screenshots) |
| `export` | Export filtered results via `src.evidence_export` (`csv` / `junit-xml` / `ndjson`) |

## Key Logic
- Index built/refreshed on demand via `EvidenceIndex.build_or_refresh()`
- Search results persisted to a temp sidecar so `detail` can drill into the last search
- `--rerun` executes the source test files with pytest in a subprocess
- Timestamp formatting for human-readable output

## Related
- `src/evidence_index.py` — evidence index
- `src/evidence_export.py` — export formats

## How It Works (Internals)

Private `_`-helpers — the module's real logic (9 items). Grouped under the public function that uses them:

### `main`
- `_cmd_detail(args: argparse.Namespace) -> None` (function) — Show detailed evidence for a result from the last search.
- `_cmd_export(args: argparse.Namespace) -> None` (function) — Export evidence to CSV, NDJSON, or JUnit XML.
- `_cmd_search(args: argparse.Namespace) -> None` (function) — Search evidence sidecars and print results as a table.

### Internal utilities
- `_build_index() -> EvidenceIndex` (function) — Build or refresh the evidence index.
- `_format_timestamp(iso_str: str) -> str` (function) — Convert ISO-8601 to a human-readable local timestamp.
- `_load_last_results() -> list[dict]` (function) — Load the last search results from the temp file.
- `_print_search_table(results: list, verbose: bool = False) -> None` (function) — Print search results as a numbered table.
- `_rerun_tests(results: list) -> None` (function) — Rerun pytest on the test packages that produced the search results.
- `_save_last_results(results: list) -> None` (function) — Save search results to a temp file for cross-command reference.
