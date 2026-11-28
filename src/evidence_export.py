"""Evidence export — CSV, NDJSON, and JUnit XML exporters.

All exporters consume the same filter parameters as
:class:`EvidenceIndex.search` so every format respects the same search
and facet constraints.  Designed to bridge the gap between the tool's
internal evidence format and external toolchains (Excel, Tableau, Splunk,
pandas, Jenkins, GitHub Actions, TestRail).

**One path (t-1488).** :func:`export_evidence` checks the Free-tier cap, builds the
bytes, charges the meter and then writes a file or returns the text. No other public
function here produces export bytes - the per-format builders are private - so a
caller cannot obtain an export without the check.

Typical usage::

    from src.evidence_export import export_evidence
    from src.evidence_index import EvidenceIndex

    index = EvidenceIndex()
    csv_path = export_evidence(index, "csv", status="failed", output="evidence_failed.csv")
    browser_csv = export_evidence(index, "csv", status="failed")
"""

from __future__ import annotations

import csv
import io
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING
from xml.etree.ElementTree import Element, SubElement, tostring

if TYPE_CHECKING:
    from src.evidence_index import EvidenceIndex


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------


def _in_package(result: object, package: str | None) -> bool:
    """True when *result* belongs to *package* (a directory name), else True.

    j-0286: the CLI menu writes these exports into a run's package, so it must
    not write every run's evidence into one file. The comparison is on the sidecar
    path's OWN package folder - the same rule for all three writers - and a
    result with no package recorded is kept, because dropping it silently would
    shrink an export for a reason the reader cannot see. The filter changes which
    rows are written, never what a row holds.
    """
    if not package:
        return True
    value = str(getattr(result, "sidecar_path", "") or "").replace(chr(92), "/").rstrip("/")
    return f"/{package}/" in f"/{value}/"


def _csv_text(
    index: EvidenceIndex,
    *,
    query: str = "",
    status: str | None = None,
    url_domain: str | None = None,
    condition_prefix: str | None = None,
    story_ref: str | None = None,
    step_type: str | None = None,
    test_package: str | None = None,
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
    results = [r for r in results if _in_package(r, test_package)]

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
                # POSIX separators: the index stores OS-native paths (backslashes
                # on Windows), but consumers (pandas/Splunk/Excel on any OS) get
                # one portable form.
                str(r.sidecar_path).replace("\\", "/"),
            ]
        )

    return buf.getvalue()


# ---------------------------------------------------------------------------
# NDJSON (newline-delimited JSON)
# ---------------------------------------------------------------------------


def _ndjson_text(
    index: EvidenceIndex,
    *,
    query: str = "",
    status: str | None = None,
    url_domain: str | None = None,
    condition_prefix: str | None = None,
    story_ref: str | None = None,
    step_type: str | None = None,
    test_package: str | None = None,
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
    results = [r for r in results if _in_package(r, test_package)]

    lines: list[str] = []
    for r in results:
        sidecar = _load_sidecar(index, r.sidecar_path)
        if sidecar is None:
            continue
        lines.append(json.dumps(sidecar, ensure_ascii=False))

    ndjson_text = "\n".join(lines)
    if lines:
        ndjson_text += "\n"

    return ndjson_text


# ---------------------------------------------------------------------------
# JUnit XML
# ---------------------------------------------------------------------------


def _junit_text(
    index: EvidenceIndex,
    *,
    query: str = "",
    status: str | None = None,
    url_domain: str | None = None,
    condition_prefix: str | None = None,
    story_ref: str | None = None,
    step_type: str | None = None,
    test_package: str | None = None,
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
    results = [r for r in results if _in_package(r, test_package)]

    total = len(results)
    # partial_pass is a test whose assertion was resolved by a fallback: it did
    # not verify its condition. Counting it as a pass would be a false green in
    # CI, so it is reported as a failure like any other non-verification.
    failures = sum(1 for r in results if r.status in ("failed", "partial_pass"))
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

        if r.status in ("failed", "error", "partial_pass"):
            failure_msg = _first_step_error(sidecar) if sidecar else ""
            if not failure_msg and r.status == "partial_pass":
                failure_msg = "Partial verification: the assertion was resolved by a fallback, not by its condition"
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

    return xml_text


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


#: The formats this module can produce, by the name the meter and the CLI use.
EXPORT_FORMATS: tuple[str, ...] = ("csv", "ndjson", "junit")


def export_evidence(
    index: EvidenceIndex,
    format_name: str,
    *,
    output: str | Path | None = None,
    charge_meter: bool = True,
    enforce_cap: bool = True,
    **filters: object,
) -> str:
    """**The one export path.** Every surface that exports evidence goes through here.

    Order, and it is deliberate (j-0311/t-1488):

    1. **check the cap** - the Free tier's monthly limit is asked first, so no caller
       can obtain export bytes without it;
    2. **build the bytes**;
    3. **charge the meter** - one export recorded, unless the caller is the UI (see
       ``charge_meter``) or the tooling bypass below;
    4. **write to a path, or return the text** for the browser.

    ``output`` is where the CLI and the Action write; the UI passes no output and
    returns the text to a download button. ``charge_meter=False`` exists for one
    reason: Streamlit re-runs the whole script on every interaction, so the UI charges
    on the button's click instead - otherwise opening the page would count as an
    export. ``enforce_cap=False`` exists for one caller: ``scripts/parity_check.py``,
    our own CI tooling, which exports a throwaway index and must not be affected by a
    developer machine's export history. Both flags are named in
    ``tests/test_export_single_path.py`` so a new caller cannot quietly use them.

    Raises :class:`src.usage_meter.FreeTierLimitError` when the cap is spent.
    """
    if format_name not in EXPORT_FORMATS:
        raise ValueError(f"unknown export format {format_name!r}; expected one of {EXPORT_FORMATS}")
    if enforce_cap:
        _meter_check(format_name)

    builders = {"csv": _csv_text, "ndjson": _ndjson_text, "junit": _junit_text}
    text = builders[format_name](index, **filters)  # type: ignore[arg-type]

    if charge_meter:
        _meter_record(format_name, output or "")
    if output is not None:
        Path(output).write_text(text, encoding="utf-8")
        return str(output)
    return text


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


def _meter_check(format_name: str) -> None:
    """Refuse an export the deployment's tier does not allow (j-0311).

    The cap is enforced here, at the one place every evidence export passes, so the
    sentence on the pricing page and the behaviour agree. A metering fault never
    blocks an export; only a real tier refusal does.
    """
    try:
        from src.usage_meter import FreeTierLimitError, UsageMeter

        UsageMeter().assert_export_allowed(format_name)
    except FreeTierLimitError:
        raise
    except Exception:  # pragma: no cover - a broken meter must not break exports
        return


def _meter_record(format_name: str, output: str | Path) -> None:
    """Best-effort record of one evidence export in the usage ledger.

    Phase 6e — metering must never break an export: any failure here is
    swallowed (a log line at most). The ledger lives inside the storage
    evidence dir; reads/writes are local, no network.
    """
    try:
        from src.usage_meter import UsageMeter

        UsageMeter().record_export(format_name, str(output))
    except Exception as exc:  # pragma: no cover - defensive
        logging.getLogger(__name__).warning("Usage meter could not record export: %s", exc)
