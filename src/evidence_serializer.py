"""Serialization utilities for evidence sidecar files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "1.0"


class EvidenceSerializer:
    """Read and write evidence JSON sidecar files."""

    @staticmethod
    def serialize(
        *,
        test_name: str,
        condition_ref: str,
        story_ref: str,
        status: str,
        page_url: str,
        run_history: dict[str, int],
        steps: list[dict[str, Any]],
    ) -> str:
        """Return JSON payload for an evidence sidecar."""
        return json.dumps(
            {
                "schema_version": SCHEMA_VERSION,
                "test": {
                    "name": test_name,
                    "condition_ref": condition_ref,
                    "story_ref": story_ref,
                    "status": status,
                },
                "page": {"url": page_url},
                "run_history": run_history,
                "steps": steps,
            },
            indent=2,
            ensure_ascii=False,
        )

    @staticmethod
    def load(sidecar_path: Path) -> dict[str, Any]:
        """Load and return sidecar contents."""
        return json.loads(sidecar_path.read_text(encoding="utf-8"))

    @staticmethod
    def load_run_history(sidecar_path: Path) -> dict[str, int]:
        """Extract run history from a sidecar file."""
        data = EvidenceSerializer.load(sidecar_path)
        return data.get("run_history", {"total_runs": 0, "passed_runs": 0, "failed_runs": 0})

    @staticmethod
    def load_steps(sidecar_path: Path) -> list[dict[str, Any]]:
        """Extract steps from a sidecar file."""
        data = EvidenceSerializer.load(sidecar_path)
        return data.get("steps", [])

    @staticmethod
    def validate(payload: dict[str, Any]) -> bool:
        """Check that required keys are present."""
        return all(k in payload for k in ("schema_version", "test", "steps"))
