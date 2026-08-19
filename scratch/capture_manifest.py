"""Capture the pre-leg manifest: /v1/models + /slots + /props.

Usage: python scratch/capture_manifest.py scratch/manifest_36.json
Per the 2026-08-18 doc rules: captured BEFORE every eval leg, and /slots is
the serving truth (never trust /props alone).
"""

import json
import sys
from datetime import UTC, datetime
from typing import Any

import httpx

BASE = "http://localhost:8080"
out_path = sys.argv[1] if len(sys.argv) > 1 else "scratch/manifest.json"

manifest: dict[str, Any] = {"captured_at": datetime.now(UTC).isoformat()}
manifest["models"] = httpx.get(f"{BASE}/v1/models", timeout=5).json()
manifest["slots"] = httpx.get(f"{BASE}/slots", timeout=5).json()
try:
    manifest["props"] = httpx.get(f"{BASE}/props", timeout=5).json()
except Exception as exc:
    manifest["props_error"] = str(exc)

with open(out_path, "w", encoding="utf-8") as fh:
    json.dump(manifest, fh, indent=2)

slots = manifest["slots"]
slot0: dict[str, Any] = slots[0] if slots else {}
model_id = manifest["models"]["data"][0]["id"]
print(f"model={model_id}")
print(f"slot0: n_ctx={slot0.get('n_ctx')} speculative={slot0.get('speculative')}")
print(f"wrote {out_path}")
