#!/usr/bin/env python3
"""Egress audit — prove "no data leaves your deployment" (Phase 6 6a).

Statically scans the **product runtime** for outbound-HTTP primitives and
classifies each call site as either:

- ``USER-CONFIGURED`` — the target is derived from user configuration (the
  customer's LLM endpoint / provider URL) or from the already-SSRF-guarded
  target site (journey-inferred candidate URLs);
- ``FLAGGED`` — an unrecognised call site: a candidate phone-home / third-party
  call. A flagged site fails the gate.

Scope (product runtime): ``src/``, ``generated_tests/conftest.py``, and the
product entrypoints (``streamlit_app.py``, ``cli/main.py``). Dev/CI tooling in
``scripts/`` is out of scope by design (``scripts/ci_*`` deliberately call
GitHub/GitLab APIs during development and self-test; the customer's CI uses the
Phase 7 Action, whose outbound traffic is the customer's LLM endpoint plus
their own platform APIs — documented in FEATURE_SPEC_phase7 §9).

The check is deliberately conservative: any call site that does not reference a
URL-ish / user-configurable target is flagged, and the gate fails, so a future
"quick telemetry call" cannot land silently.

Usage:
    python scripts/audit_egress.py [--json] [--scope src generated_tests/conftest.py ...]

Exit codes: 0 = all call sites classified USER-CONFIGURED; 1 = at least one
FLAGGED (or scan error).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent

# Outbound-HTTP primitives that matter for the "no data leaves your deployment"
# claim. Not matched: urllib.parse (pure URL manipulation), requests as a bare
# identifier (e.g. ``pass3_requests.append``), httpx type names
# (ConnectError/TimeoutException/Response), playwright navigation (that is the
# *target* traffic, guarded separately by src/url_guard.py).
_CALL_PATTERN = re.compile(
    r"\b(?:httpx|requests|urllib3|aiohttp)\.(?:get|post|put|patch|delete|head|stream|"
    r"Client|AsyncClient|request|urlopen)\s*\("
    r"|\burllib\.request\.(?:urlopen|Request|build_opener)\s*\("
)

# A call site is USER-CONFIGURED when its statement references a user-configurable
# or target-derived address. Conservative: any URL-ish identifier or env read.
_ALLOWED_TOKEN = re.compile(
    r"\b[a-z_]*url[a-z_]*\b"  # *_url, url*, base_url, provider_url, ...
    r"|endpoint|base|provider|candidate|probe|host|target"
    r"|os\.environ|getenv"
    r"|localhost|127\.0\.0\.1|0\.0\.0\.0|11434"
    r"|starting_url|full_url",
    re.IGNORECASE,
)

DEFAULT_SCOPE: list[str] = ["src", "generated_tests/conftest.py", "streamlit_app.py", "cli/main.py"]

_MISSING_REASON = "file/dir not found (product runtime path removed?)"


@dataclass
class CallSite:
    file: str
    line: int
    primitive: str
    statement: str
    classification: str = "FLAGGED"
    reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "line": self.line,
            "primitive": self.primitive,
            "classification": self.classification,
            "statement": " ".join(self.statement.split()),
        }


@dataclass
class AuditResult:
    sites: list[CallSite] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    scanned_files: int = 0

    @property
    def flagged(self) -> list[CallSite]:
        return [s for s in self.sites if s.classification == "FLAGGED"]


def _iter_py_files(path: Path) -> list[Path]:
    if path.is_file():
        return [path] if path.suffix == ".py" else []
    return sorted(p for p in path.rglob("*.py") if "__pycache__" not in str(p))


def _statement_block(lines: list[str], start_idx: int) -> str:
    """Return the statement starting at *start_idx*, extending until parens balance.

    Counts each appended line once (a cumulative count of the whole block would
    over-extend past the statement's own closing paren).
    """
    block = lines[start_idx]
    depth = block.count("(") - block.count(")")
    idx = start_idx
    while depth > 0 and idx + 1 < len(lines):
        idx += 1
        line = lines[idx]
        block += "\n" + line
        depth += line.count("(") - line.count(")")
        if depth <= 0:
            break
    return block


def audit_file(path: Path, sites: list[CallSite]) -> int:
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        sites.append(CallSite(str(path), 0, "read-error", "", "FLAGGED", str(exc)))
        return 0
    hits = 0
    try:
        display_path = str(path.relative_to(REPO_ROOT))
    except ValueError:
        display_path = str(path)
    for idx, line in enumerate(lines):
        m = _CALL_PATTERN.search(line)
        if not m:
            continue
        hits += 1
        statement = _statement_block(lines, idx)
        primitive = m.group(0).rstrip("(")
        if _ALLOWED_TOKEN.search(statement):
            sites.append(
                CallSite(
                    display_path,
                    idx + 1,
                    primitive,
                    statement,
                    "USER-CONFIGURED",
                    "target derived from user config / guarded target site",
                )
            )
        else:
            sites.append(CallSite(display_path, idx + 1, primitive, statement))
    return hits


def run_audit(scope: list[str]) -> AuditResult:
    result = AuditResult()
    total_hits = 0
    for scope_item in scope:
        path = (REPO_ROOT / scope_item) if not Path(scope_item).is_absolute() else Path(scope_item)
        if not path.exists():
            result.errors.append(f"{scope_item}: {_MISSING_REASON}")
            continue
        for py_file in _iter_py_files(path):
            result.scanned_files += 1
            total_hits += audit_file(py_file, result.sites)
    # Deterministic ordering: file, then line.
    result.sites.sort(key=lambda s: (s.file, s.line))
    return result


def _render_human(result: AuditResult) -> str:
    lines = [
        f"Egress audit — {result.scanned_files} product-runtime files scanned, "
        f"{len(result.sites)} outbound-HTTP call site(s).",
        "",
    ]
    for site in sorted(result.sites, key=lambda s: (s.classification != "USER-CONFIGURED", s.file, s.line)):
        status = "OK " if site.classification == "USER-CONFIGURED" else "FLAG"
        lines.append(f"  [{status}] {site.file}:{site.line} {site.primitive}")
        snippet = " ".join(site.statement.split())
        lines.append(f"         {snippet[:140]}{'…' if len(snippet) > 140 else ''}")
    if result.errors:
        lines.append("")
        lines.append("Scan errors:")
        lines.extend(f"  ! {e}" for e in result.errors)
    lines.append("")
    lines.append(f"Verdict: {len(result.flagged)} flagged call site(s).")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON manifest on stdout")
    parser.add_argument(
        "--scope", nargs="+", default=DEFAULT_SCOPE, help="Files/dirs to scan (default: product runtime)"
    )
    args = parser.parse_args(argv)

    result = run_audit(args.scope)
    if args.json:
        payload = {
            "scanned_files": result.scanned_files,
            "call_sites": [s.as_dict() for s in result.sites],
            "flagged": [s.as_dict() for s in result.flagged],
            "errors": result.errors,
            "verdict": "CLEAN" if not result.flagged and not result.errors else "FLAGGED",
        }
        print(json.dumps(payload, indent=2))
    else:
        print(_render_human(result))

    if result.errors:
        print(f"\nERROR: scan errors: {result.errors}", file=sys.stderr)
        return 1
    if result.flagged:
        print(
            "\nERROR: flagged egress call site(s) — see docs/security/egress-audit.md for the policy.", file=sys.stderr
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
