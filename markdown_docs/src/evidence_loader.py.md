# `src/evidence_loader.py`

## Purpose
Loads evidence JSON from generated test packages. Evidence files are written by EvidenceTracker at runtime containing diagnostic context for failed steps.

## Metadata
- **Lines:** ~183
- **Imports:** json, logging, pathlib.Path, typing

## Functions
| Function | Description |
|----------|-------------|
| `load_evidence_for_package(package_dir)` | Scans `<package_dir>/evidence/` for `*.evidence.json`; returns dict mapping test name → evidence |
| `get_failure_diagnostics(evidence)` | Extracts failure diagnostics: failed steps, page URL, title, duration |
| `get_screenshot_paths(evidence)` | Returns screenshot paths from failed steps |
| `match_evidence_to_test(evidence_map, test_name)` | Finds matching evidence via exact, prefix, and parameterized name matching |

## Key Logic
- Evidence files keyed by filename stem
- Failed steps filtered by result status
- Matching tries: exact name → test name prefix → parameterized pattern
- Returns None gracefully when no evidence found