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
import ast
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
_HTTP_PRIMITIVES: frozenset[str] = frozenset(
    {
        "httpx.get",
        "httpx.post",
        "httpx.put",
        "httpx.patch",
        "httpx.delete",
        "httpx.head",
        "httpx.stream",
        "httpx.Client",
        "httpx.AsyncClient",
        "httpx.request",
        "requests.get",
        "requests.post",
        "requests.put",
        "requests.patch",
        "requests.delete",
        "requests.head",
        "requests.stream",
        "requests.request",
        "urllib3.request",
        "aiohttp.request",
        "aiohttp.ClientSession",
        "urllib.request.urlopen",
        "urllib.request.Request",
        "urllib.request.build_opener",
    }
)


#: Fixed destinations we own, allowed one CALL at a time: the enclosing function, the
#: exact primitive, and a token the arguments must name. Not a whole function - a
#: second call added beside an allow-listed one is a finding (t-1521, closing the hole
#: the reviewer found in t-1511), and never by a comment in the call's own text
#: (t-1478: a '# noqa: S310 - fixed https URL' used to be enough).
@dataclass(frozen=True)
class AllowedSite:
    primitive: str
    argument_token: str
    reason: str
    #: The function must make exactly this many calls of the primitive. One, always:
    #: a second call beside an allow-listed one is a finding (t-1521).
    exact_calls: int = 1


ALLOWED_CALL_SITES: dict[str, dict[str, AllowedSite]] = {
    "src/version_check.py": {
        "_fetch": AllowedSite(
            primitive="urllib.request.urlopen",
            # _fetch takes the address as a parameter; its only caller passes
            # FEED_URL, and a test in tests/test_audit_egress.py holds that.
            argument_token="url",
            reason="PyPI's JSON for this package (the daily update check); sends nothing about the customer",
        ),
    },
    "src/licensing/activation.py": {
        "_post": AllowedSite(
            primitive="urllib.request.urlopen",
            argument_token="relay_url",
            reason="our licence relay: activation once and the update check once per version; never the store",
        ),
    },
}

#: HTTP verbs an alias or a dynamic call could hide behind.
_HTTP_VERBS: frozenset[str] = frozenset({"get", "post", "put", "patch", "delete", "head", "request", "stream"})

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
            "statement": " ".join(self.statement.split()),
            "classification": self.classification,
            "reason": self.reason,
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


def _aliases(tree: ast.Module) -> dict[str, str]:
    """Local names bound to an imported module or function.

    ``import httpx as hx`` -> ``{"hx": "httpx"}``; ``from urllib.request import
    urlopen as open_url`` -> ``{"open_url": "urllib.request.urlopen"}``. Without this
    an aliased call is invisible to the scan (t-1521).
    """
    found: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                local = alias.asname or alias.name.split(".")[0]
                found[local] = alias.name if alias.asname else alias.name.split(".")[0]
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            for alias in node.names:
                local = alias.asname or alias.name
                found[local] = f"{module}.{alias.name}" if module else alias.name
    return found


def _resolve(name: str, aliases: dict[str, str]) -> str:
    """Rewrite a call name through the alias map: 'hx.get' -> 'httpx.get'."""
    head, _, rest = name.partition(".")
    target = aliases.get(head)
    if target is None:
        return name
    return f"{target}.{rest}" if rest else target


def _is_dynamic_http_call(node: ast.Call) -> bool:
    """``getattr(x, 'get')(...)`` and friends: a verb reached without an attribute.

    The AST cannot see the target, and neither can a reader. Flagged always, because
    "we could not tell" is not a classification (t-1521).
    """
    func = node.func
    if not isinstance(func, ast.Call):
        return False
    name = _call_name(func)
    if name not in ("getattr", "builtins.getattr"):
        return False
    if len(func.args) < 2:
        return False
    verb = func.args[1]
    return isinstance(verb, ast.Constant) and isinstance(verb.value, str) and verb.value in _HTTP_VERBS


def _call_name(node: ast.Call) -> str:
    """'httpx.get(...)' -> 'httpx.get'."""
    func = node.func
    parts: list[str] = []
    while isinstance(func, ast.Attribute):
        parts.append(func.attr)
        func = func.value
    if isinstance(func, ast.Name):
        parts.append(func.id)
    return ".".join(reversed(parts))


def _enclosing_function(tree: ast.Module, node: ast.Call) -> str:
    for candidate in ast.walk(tree):
        if isinstance(candidate, (ast.FunctionDef, ast.AsyncFunctionDef)):
            end = getattr(candidate, "end_lineno", candidate.lineno)
            if candidate.lineno <= node.lineno <= end:
                return candidate.name
    return ""


def _argument_text(text: str, node: ast.Call) -> str:
    """The call's ARGUMENTS, not its function name.

    t-1478: 'urllib.request.urlopen(FEED)' used to match the URL token through the
    word 'urlopen' in its own name, so any urllib call was allowed. The target is
    what the call is given: a literal here is a hardcoded destination.
    """
    parts: list[str] = []
    for arg in [*node.args, *(kw.value for kw in node.keywords)]:
        parts.append(ast.get_source_segment(text, arg) or "")
    return " ".join(parts)


def _inside_repo(path: Path) -> bool:
    try:
        path.resolve().relative_to(REPO_ROOT.resolve())
        return True
    except ValueError:
        return False


def _allow_list_for(display_path: str, path: Path) -> dict[str, AllowedSite]:
    """The allow-list entry for this file: exact key, a path ending in it, or the name.

    The name match lets the tests plant the fixture in a temp directory and still find
    the entry. It must not depend on the separator or on the depth of that directory:
    an earlier version counted "/" in the path, which passed on Windows (a temp path
    with backslashes) and failed on CI's Linux (any temp path is several levels deep)
    - t-1532.
    """
    for key, entry in ALLOWED_CALL_SITES.items():
        if display_path == key or Path(display_path).as_posix().endswith("/" + key):
            return entry
        if path.as_posix().endswith("/" + key):
            return entry
        if path.name == Path(key).name and not _inside_repo(path):
            return entry
    return {}


def _function_source(text: str, tree: ast.Module, function: str) -> str:
    """The source of the named function, or "" when it is not a def."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function:
            return ast.get_source_segment(text, node) or ""
    return ""


def _primitive_calls_in(text: str, tree: ast.Module, function: str, primitive: str, aliases: dict[str, str]) -> int:
    """How many calls of *primitive* the named function makes."""
    body = _function_source(text, tree, function)
    if not body:
        return 0
    try:
        inner = ast.parse(textwrap_dedent(body))
    except SyntaxError:  # pragma: no cover - a def always parses
        return 0
    return sum(
        1 for node in ast.walk(inner) if isinstance(node, ast.Call) and _resolve(_call_name(node), aliases) == primitive
    )


def textwrap_dedent(source: str) -> str:
    import textwrap

    return textwrap.dedent(source)


def audit_file(path: Path, sites: list[CallSite]) -> int:
    """Find outbound calls by AST; classify by allow-list or a user-config target."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(text)
    except (OSError, SyntaxError) as exc:
        sites.append(CallSite(str(path), 0, "read-error", "", "FLAGGED", str(exc)))
        return 0
    try:
        display_path = str(path.relative_to(REPO_ROOT)).replace("\\", "/")
    except ValueError:
        display_path = str(path)

    aliases = _aliases(tree)
    seen: set[tuple[int, str]] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if _is_dynamic_http_call(node):
            verb = node.func.args[1].value  # type: ignore[attr-defined]
            sites.append(
                CallSite(
                    display_path,
                    node.lineno,
                    f"getattr({verb})",
                    ast.get_source_segment(text, node) or "",
                    "FLAGGED",
                    "dynamic HTTP call: the target cannot be read from the code",
                )
            )
            continue
        primitive = _resolve(_call_name(node), aliases)
        if primitive not in _HTTP_PRIMITIVES:
            continue
        key = (node.lineno, primitive)
        if key in seen:
            continue
        seen.add(key)
        statement = ast.get_source_segment(text, node) or ""
        function = _enclosing_function(tree, node)
        allowed = _allow_list_for(display_path, path)
        entry = allowed.get(function)
        arguments = _argument_text(text, node)
        function_body = _function_source(text, tree, function)
        calls_here = _primitive_calls_in(text, tree, function, entry.primitive, aliases) if entry is not None else 0
        if (
            entry is not None
            and entry.primitive == primitive
            and entry.argument_token in function_body
            and calls_here == entry.exact_calls
        ):
            sites.append(CallSite(display_path, node.lineno, primitive, statement, "ALLOW-LISTED", entry.reason))
        elif entry is not None and entry.primitive == primitive and calls_here > entry.exact_calls:
            sites.append(
                CallSite(
                    display_path,
                    node.lineno,
                    primitive,
                    statement,
                    "FLAGGED",
                    f"a second call of {primitive} inside the allow-listed function {function}()",
                )
            )
        elif _ALLOWED_TOKEN.search(arguments):
            sites.append(
                CallSite(
                    display_path,
                    node.lineno,
                    primitive,
                    statement,
                    "USER-CONFIGURED",
                    "target derived from user config / guarded target site",
                )
            )
        else:
            sites.append(CallSite(display_path, node.lineno, primitive, statement))
    return len(seen)


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


def _render_table(result: AuditResult) -> str:
    """The markdown table for docs/security/egress-audit.md, from this scan."""
    pipe = chr(92) + "|"  # an escaped pipe, so a call containing one keeps the table intact
    lines = [
        "| File | Line | Call | Classification | Reason |",
        "|------|------|------|----------------|--------|",
    ]
    for site in sorted(result.sites, key=lambda s: (s.file, s.line)):
        call = " ".join(site.statement.split()).replace("|", pipe)[:90]
        reason = site.reason.replace("|", pipe)
        lines.append(f"| `{site.file}` | {site.line} | `{call}` | {site.classification} | {reason} |")
    return chr(10).join(lines)


def _render_human(result: AuditResult) -> str:
    lines = [
        f"Egress audit — {result.scanned_files} product-runtime files scanned, "
        f"{len(result.sites)} outbound-HTTP call site(s).",
        "",
    ]
    # t-1485: the marker must agree with the verdict. ALLOW-LISTED and
    # USER-CONFIGURED are both allowed - only FLAGGED is a finding.
    for site in sorted(result.sites, key=lambda s: (s.classification == "FLAGGED", s.file, s.line)):
        status = "FLAG" if site.classification == "FLAGGED" else "OK "
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
    parser.add_argument("--table", action="store_true", help="Print the markdown table for the egress doc")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON manifest on stdout")
    parser.add_argument(
        "--scope", nargs="+", default=DEFAULT_SCOPE, help="Files/dirs to scan (default: product runtime)"
    )
    args = parser.parse_args(argv)

    result = run_audit(args.scope)
    if args.table:
        print(_render_table(result))
        return 0 if not result.flagged else 1
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
