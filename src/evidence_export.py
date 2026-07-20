"""Evidence export — CSV, NDJSON, and JUnit XML exporters.

All exporters consume the same filter parameters as
:class:`EvidenceIndex.search` so every format respects the same search
and facet constraints.  Designed to bridge the gap between the tool's
internal evidence format and external toolchains (Excel, Tableau, Splunk,
pandas, Jenkins, GitHub Actions, TestRail).

Typical usage::

    from src.evidence_export import export_csv
    from src.evidence_index import EvidenceIndex

    index = EvidenceIndex()
    csv_path = export_csv(index, status="failed", output="evidence_failed.csv")
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import TYPE_CHECKING
from xml.etree.ElementTree import Element, SubElement, tostring

if TYPE_CHECKING:
    from src.evidence_index import EvidenceIndex


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------


def export_csv(
    index: EvidenceIndex,
    *,
    query: str = "",
    status: str | None = None,
    url_domain: str | None = None,
    condition_prefix: str | None = None,
    story_ref: str | None = None,
    step_type: str | None = None,
    output: str | Path | None = None,
) -> str:
    """Export evidence metadata as a flat CSV table.

    One row per evidence sidecar.  Columns::

        test_name, condition_ref, story_ref, status, page_url,
        step_count, step_types, step_labels, duration_s,
        test_package, sidecar_path

    Parameters
    ----------
    index:
        A populated :class:`EvidenceIndex`.
    query / status / url_domain / condition_prefix / story_ref / step_type:
        Same filter semantics as :meth:`EvidenceIndex.search`.
    output:
        If provided, write CSV to this path.  Otherwise return the CSV
        as a string.

    Returns
    -------
    str
        CSV content (or written-to path if *output* was provided).
    """
    results = index.search(
        query=query,
        status=status,
        url_domain=url_domain,
        condition_prefix=condition_prefix,
        story_ref=story_ref,
        step_type=step_type,
        limit=100_000,  # effectively unlimited for export
    )

    buf = io.StringIO()
    buf.write("\ufeff")  # BOM for Excel UTF‑8 detection

    writer = csv.writer(buf)
    writer.writerow(
        [
            "test_name",
            "condition_ref",
            "story_ref",
            "status",
            "page_url",
            "step_count",
            "step_types",
            "step_labels",
            "duration_s",
            "test_package",
            "sidecar_path",
        ]
    )

    for r in results:
        sidecar = _load_sidecar(index, r.sidecar_path)
        steps = sidecar.get("steps", []) if sidecar else []
        writer.writerow(
            [
                r.test_name,
                r.condition_ref,
                r.story_ref,
                r.status,
                r.page_url,
                len(steps),
                "|".join(s.get("type", "") for s in steps),
                "|".join(s.get("label", "") for s in steps),
                sidecar.get("test", {}).get("duration_s", 0.0) if sidecar else 0.0,
                r.test_package,
                r.sidecar_path,
            ]
        )

    csv_text = buf.getvalue()
    if output is not None:
        Path(output).write_text(csv_text, encoding="utf-8-sig")
        return str(output)

    return csv_text


# ---------------------------------------------------------------------------
# NDJSON (newline-delimited JSON)
# ---------------------------------------------------------------------------


def export_ndjson(
    index: EvidenceIndex,
    *,
    query: str = "",
    status: str | None = None,
    url_domain: str | None = None,
    condition_prefix: str | None = None,
    story_ref: str | None = None,
    step_type: str | None = None,
    output: str | Path | None = None,
) -> str:
    """Export evidence as newline-delimited JSON (NDJSON / JSON Lines).

    One JSON object per line — the full sidecar data.  Ready for
    ``jq``, ``pandas.read_json(lines=True)``, Splunk, or Elasticsearch.

    Parameters
    ----------
    index:
        A populated :class:`EvidenceIndex`.
    query / status / url_domain / condition_prefix / story_ref / step_type:
        Same filter semantics as :meth:`EvidenceIndex.search`.
    output:
        If provided, write NDJSON to this path.  Otherwise return the
        content as a string.

    Returns
    -------
    str
        NDJSON content (or written-to path if *output* was provided).
    """
    results = index.search(
        query=query,
        status=status,
        url_domain=url_domain,
        condition_prefix=condition_prefix,
        story_ref=story_ref,
        step_type=step_type,
        limit=100_000,
    )

    lines: list[str] = []
    for r in results:
        sidecar = _load_sidecar(index, r.sidecar_path)
        if sidecar is None:
            continue
        lines.append(json.dumps(sidecar, ensure_ascii=False))

    ndjson_text = "\n".join(lines)
    if lines:
        ndjson_text += "\n"

    if output is not None:
        Path(output).write_text(ndjson_text, encoding="utf-8")
        return str(output)

    return ndjson_text


# ---------------------------------------------------------------------------
# JUnit XML
# ---------------------------------------------------------------------------


def export_junit_xml(
    index: EvidenceIndex,
    *,
    query: str = "",
    status: str | None = None,
    url_domain: str | None = None,
    condition_prefix: str | None = None,
    story_ref: str | None = None,
    step_type: str | None = None,
    output: str | Path | None = None,
    suite_name: str = "evidence_export",
) -> str:
    """Export evidence as a JUnit XML test report.

    One ``<testcase>`` per evidence sidecar.  Failed sidecars get a
    ``<failure>`` child containing the first step error message.

    Parameters
    ----------
    index:
        A populated :class:`EvidenceIndex`.
    query / status / url_domain / condition_prefix / story_ref / step_type:
        Same filter semantics as :meth:`EvidenceIndex.search`.
    output:
        If provided, write XML to this path.  Otherwise return the XML
        as a string.
    suite_name:
        Value for the ``<testsuite name="...">`` attribute.

    Returns
    -------
    str
        JUnit XML content (or written-to path if *output* was provided).
    """
    results = index.search(
        query=query,
        status=status,
        url_domain=url_domain,
        condition_prefix=condition_prefix,
        story_ref=story_ref,
        step_type=step_type,
        limit=100_000,
    )

    total = len(results)
    failures = sum(1 for r in results if r.status == "failed")
    errors = sum(1 for r in results if r.status == "error")
    skipped = sum(1 for r in results if r.status == "skipped")
    total_time = 0.0

    testsuites = Element("testsuites")
    suite = SubElement(
        testsuites,
        "testsuite",
        {
            "name": suite_name,
            "tests": str(total),
            "failures": str(failures),
            "errors": str(errors),
            "skipped": str(skipped),
        },
    )

    for r in results:
        sidecar = _load_sidecar(index, r.sidecar_path)
        duration = sidecar.get("test", {}).get("duration_s", 0.0) if sidecar else 0.0
        total_time += float(duration)

        classname = _classname_from_url(r.page_url)

        testcase = SubElement(
            suite,
            "testcase",
            {
                "classname": classname,
                "name": f"{r.condition_ref}_{_slug(r.test_name)}",
                "time": f"{duration:.3f}",
            },
        )

        if r.status in ("failed", "error"):
            failure_msg = _first_step_error(sidecar) if sidecar else ""
            SubElement(
                testcase,
                "failure",
                {"message": failure_msg[:200] if failure_msg else "Test failed"},
            )
            if failure_msg:
                failure_elem = testcase.find("failure")
                if failure_elem is not None:
                    failure_elem.text = failure_msg

        elif r.status == "skipped":
            SubElement(testcase, "skipped")

    suite.set("time", f"{total_time:.3f}")

    xml_text = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml_text += tostring(testsuites, encoding="unicode")

    if output is not None:
        Path(output).write_text(xml_text, encoding="utf-8")
        return str(output)

    return xml_text


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_sidecar(index: EvidenceIndex, sidecar_path: str) -> dict | None:
    """Load the full sidecar JSON from disk."""
    try:
        abs_path = index.get_test_package_path(sidecar_path)
        with open(abs_path, encoding="utf-8") as fh:
            return json.load(fh)  # type: ignore[no-any-return]
    except OSError, json.JSONDecodeError:
        return None


def _classname_from_url(url: str) -> str:
    """Derive a JUnit ``classname`` from a page URL.

    ``https://automationexercise.com/view_cart`` → ``automationexercise.view_cart``
    """
    if not url:
        return "unknown"
    try:
        from urllib.parse import urlparse

        parsed = urlparse(url if "://" in url else f"https://{url}")
        domain = parsed.netloc.replace("www.", "").split(".")[0]
        path = parsed.path.strip("/").replace("/", ".") or "root"
        # Strip common file extensions
        for ext in (".html", ".php", ".asp", ".aspx"):
            if path.endswith(ext):
                path = path[: -len(ext)]
        return f"{domain}.{path}"
    except Exception:
        return url.replace("://", "_").replace("/", ".")


def _slug(text: str) -> str:
    """Create a filename-safe, XML-attribute-safe slug."""
    return text.replace("[", "_").replace("]", "_").replace(" ", "_").replace("/", "_").replace("\\", "_").rstrip("_")


def _first_step_error(sidecar: dict | None) -> str:
    """Extract the first step error message from a sidecar."""
    if not sidecar:
        return ""
    for step in sidecar.get("steps", []):
        result = step.get("result", {})
        error = result.get("error")
        if error:
            return str(error)
        failure_note = result.get("failure_note")
        if failure_note:
            return str(failure_note)
    return ""
