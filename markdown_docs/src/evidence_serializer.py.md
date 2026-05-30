# `src/evidence_serializer.py`

## Purpose
Serialization utilities for evidence sidecar JSON files. Handles writing and reading the structured evidence format used by EvidenceTracker.

## Metadata
- **Lines:** 64
- **Imports:** json, pathlib.Path, typing.Any

## Class
| Class | Description |
|-------|-------------|
| `EvidenceSerializer` | Static methods for reading/writing evidence JSON sidecar files |

## Methods
| Method | Description |
|--------|-------------|
| `serialize(test_name, condition_ref, story_ref, status, page_url, run_history, steps)` | Returns JSON string for evidence sidecar with schema version |
| `load(sidecar_path)` | Loads and returns sidecar contents as dict |
| `load_run_history(sidecar_path)` | Extracts run history dict from sidecar |
| `load_steps(sidecar_path)` | Extracts steps list from sidecar |
| `validate(payload)` | Checks required keys: schema_version, test, steps |

## Key Logic
- Schema version tracked as constant ("1.0")
- All methods are @staticmethod — no instance state needed
- JSON output uses 2-space indent, UTF-8 encoding
- Validates presence of schema_version, test, and steps keys