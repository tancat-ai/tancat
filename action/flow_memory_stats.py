#!/usr/bin/env python3
"""Flow-memory store stats for the Phase 7 CI action (spec §3 goal 13, ``learn: true``).

Loads the workspace flow-memory store (``<workspace>/evidence/flow_memory.json``
— written by the generated package's conftest teardown during pytest) and
prints its stats as JSON. The entrypoint consumes these as the "learned
count" it logs and emits as ``flow_*`` outputs after a green generate-and-run
with ``learn: true``.

Contracts:

- **A missing store is not an error** (no fully-passing tests → nothing
  learned) — prints zeros and exits 0, so the entrypoint never fails a
  green run on learning bookkeeping.
- **A corrupt store is not an error either** — ``FlowMemoryStore`` starts
  empty on unreadable files (its "never break the run" contract), so stats
  read as zeros with a ``corrupt`` flag for diagnostics.
- **Platform-neutral** — no GitHub/GitLab imports; the store path is passed
  explicitly (the entrypoint already resolved it from ``$WORKSPACE_ROOT`` +
  ``$WS_NAME``). Runs under the action image's venv python.

Usage::

    python action/flow_memory_stats.py --store ai-test-workspace/evidence/flow_memory.json --json
    # {"patterns": 7, "sites": 1, "cross_site": 0, "suite_chains": 3, ...}
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from src.flow_memory import FlowMemoryStore


def flow_memory_stats(store_path: str | Path) -> dict[str, Any]:
    """Stats dict for the store at *store_path* — zeros when missing/corrupt.

    ``patterns`` / ``sites`` / ``cross_site`` / ``suite_chains`` /
    ``within_test`` come from :meth:`FlowMemoryStore.stats`; ``corrupt``
    flags a file that existed but could not be parsed (the store's load
    falls back to empty — learning is best-effort, never fatal).
    """
    path = Path(store_path)
    base: dict[str, Any] = {
        "patterns": 0,
        "sites": 0,
        "cross_site": 0,
        "suite_chains": 0,
        "within_test": 0,
        "last_learned_at": None,
        "path": str(path),
        "corrupt": False,
    }
    if not path.exists():
        return base
    # FlowMemoryStore.load() swallows parse errors and starts empty (its
    # "never break the run" contract) — validate the raw file so the
    # corrupt flag is truthful for diagnostics.
    try:
        json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        base["corrupt"] = True
        return base
    try:
        store = FlowMemoryStore(path)
        base.update(store.stats())
    except Exception:
        base["corrupt"] = True
    base["path"] = str(path)
    return base


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="flow_memory_stats",
        description="Print flow-memory store stats (learn: true reporting).",
    )
    parser.add_argument("--store", required=True, help="Path to flow_memory.json")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON on stdout")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    stats = flow_memory_stats(args.store)
    if args.json:
        print(json.dumps(stats))
    else:
        print(
            f"flow memory: {stats['patterns']} patterns, {stats['sites']} sites, "
            f"{stats['cross_site']} cross-site, {stats['suite_chains']} suite chains"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
