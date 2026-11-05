"""Which report formats each local surface writes, in one place (j-0286).

The owner's rule, 2026-11-05: parity of facts, not coverage. Wherever a format
is offered the facts must agree, and every difference must carry a reason that
is written down here - a surface that silently drops HTML or JSON leaves a run
with nothing to check, which is the hole this table exists to catch.

The CI surface is deliberately NOT listed: its schema is a separate job. Its
report.py writes report.json and report.md today, and that gap is recorded, not
decided here.
"""

from __future__ import annotations

#: Every report format the package can actually write, and its human label.
REPORT_FORMATS: dict[str, str] = {
    "markdown": "Markdown (local)",
    "json": "JSON",
    "html": "HTML",
    "jira": "Jira",
    "csv": "CSV",
    "ndjson": "NDJSON",
    "junit": "JUnit XML",
}

#: Which formats each local surface writes. A surface may offer MORE than the
#: required pair; it may not offer fewer.
SURFACE_FORMATS: dict[str, tuple[str, ...]] = {
    # Streamlit: the report service (markdown, JSON, HTML, Jira) plus the three
    # evidence exports on the Evidence & Reports page.
    "streamlit": ("markdown", "json", "html", "jira", "csv", "ndjson", "junit"),
    # The interactive menu: the same set, from the same writers (j-0286).
    "cli_menu": ("markdown", "json", "html", "jira", "csv", "ndjson", "junit"),
    # 'tancat run': the report service only. No evidence index is built on this
    # path, so the three evidence exports are not written - a recorded
    # difference, and the reason is that a headless run writes files and a
    # summary, not a browsable evidence store.
    "headless": ("markdown", "json", "html", "jira"),
    # The evidence CLI exports the index only; it has no reports to make.
    "evidence_cli": ("csv", "ndjson", "junit"),
}

#: The pair a run cannot be checked without. Every local surface must carry it.
PARITY_REQUIRED: tuple[str, ...] = ("json", "html")

#: Surfaces the parity test holds to the rule above. The CI surface is out of
#: scope until its own job settles it, and its current gap is named here so it
#: cannot be forgotten.
OUT_OF_SCOPE_SURFACES: dict[str, str] = {
    "ci_action": "writes report.json + report.md only; schema is a separate job (j-0286 F2)",
}
