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
