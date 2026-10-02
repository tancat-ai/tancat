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

## Public API Additions

Refreshed 2026-10-02: public symbols present in the source and not listed above.

- `load_verification_strength` (function): `load_verification_strength(package_dir: str | Path) -> dict[str, dict[str, Any]]` - Load the emitted per-test verification verdicts (B-100). Reads <package_dir>/verification_strength.json written by PipelineArtifactWriter and returns it keyed by test name. A missing or malformed file returns...
- `match_verification_to_test` (function): `match_verification_to_test(verdicts: dict[str, dict[str, Any]], test_name: str) -> dict[str, Any] | None` - Find the verdict for a runtime test name (B-100). Mirrors :func:'match_evidence_to_test': pytest emits test_01_x[chromium] while the pipeline's verdict key is test_01_x.
- `get_verification` (function): `get_verification(evidence: dict[str, Any]) -> dict[str, Any]` - Return the B-100 verification verdict from an evidence payload. Returns {} when the sidecar predates the field, so report rendering stays backward compatible.
