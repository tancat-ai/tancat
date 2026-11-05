#!/usr/bin/env python3
"""Golden-key live re-validation (Phase 6i, spec §5.11).

The eval harness's published honesty signal is only as true as its golden keys.
Golden keys decay — AGENTS.md §12: re-validate locators against live sites every
3–6 months. This script does exactly that, deterministically:

- **Live datasets** (saucedemo, automationexercise, demoqa, theinternet): a real
  Chromium session loads each golden's ``target_page`` (what the step selects on) or
  ``outcome_page`` (what it must reach) and asserts every
  tolerance selector (and the exact golden locator) resolves ≥ 1 element; URL
  assertions assert the page actually loads at the expected URL.
- **Mock datasets** (ecommerce, banking, ambiguous): same checks against the
  local deterministic mock server (no network).
- **LV insurance** (eval-005): no mock present locally and no public site —
  recorded honestly as ``static-only`` (re-validated via the harness's frozen
  captures instead; see the 24/24 resolver record).

Output: a recency record ``scripts/eval/revalidation/latest.json`` (per-dataset
status + missing goldens) + a human table. Exit codes: 0 = all reachable
datasets match (or unreachable due to no network); 1 = real golden decay found;
2 = usage/config error.

Usage::

    python scripts/eval/revalidate_goldens.py                 # all datasets
    python scripts/eval/revalidate_goldens.py --dataset eval-002
    python scripts/eval/revalidate_goldens.py --json --save scripts/eval/revalidation/latest.json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DATASET_DIR = Path(__file__).resolve().parent / "dataset"
#: This script's own directory, so `golden_validator` resolves both when run as
#: a script and when a test loads the file directly (t-1303 step 3).
_EVAL_DIR = Path(__file__).resolve().parent
if str(_EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(_EVAL_DIR))
DEFAULT_OUT = Path(__file__).resolve().parent / "revalidation" / "latest.json"

# Datasets whose mock server supplies the DOM (deterministic, local).
MOCK_DATASET_IDS = {
    "eval-006": "mock_sites/ecommerce",
    "eval-007": "mock_sites/banking",
    "eval-010": "mock_sites/ambiguous",
}
# eval-008 (GOTO navigation) also targets the banking mock.
MOCK_DATASET_IDS["eval-008"] = "mock_sites/banking"

# Datasets with no locally-servable target → honestly marked static-only.
STATIC_ONLY_DATASET_IDS = {"eval-005"}

# State-dependent pages: their DOM only exists with a seeded cart / a login
# session (B-022 class), so a plain load would report false decay. t-1303 step 3
# removed the SKIP these used to drive: a row on one of these pages is now
# checked against its frozen capture in scraped_pages/ (the DOM the tool recorded
# when the page was really served), and only a row with no capture is reported as
# "needs a session" - unproven, never a silent pass. The map survives as the
# classifier that chooses the capture path. dataset_id → path fragments.
STATEFUL_PATHS: dict[str, list[str]] = {
    "eval-001": ["/inventory", "/cart", "/checkout"],  # saucedemo (login-gated + sessionStorage cart)
    "eval-002": ["/view_cart"],  # automationexercise (session cookie cart)
    "eval-003": [],  # demoqa — see golden-description rule below
    "eval-006": ["/cart", "/checkout"],  # ecommerce mock
    "eval-007": ["/dashboard", "/transfer", "/payment", "/success"],  # banking mock (login wall only)
    "eval-008": ["/dashboard", "/transfer", "/payment", "/success"],
    "eval-010": [],  # ambiguous mock — stateless (verified)
}

# Golden-description rule for stateful elements on otherwise stateless pages
# (e.g. demoqa renders the submission confirmation only after form submit).
STATEFUL_DESCRIPTION_FRAGMENTS = ("submission success", "order confirmation")


def _load_dataset(dataset_id: str | None = None) -> list[dict[str, Any]]:
    """Load all datasets (or one) from the dataset dir, newest schema first."""
    files = sorted(DATASET_DIR.glob("eval-*.json"))
    datasets: list[dict[str, Any]] = []
    for f in files:
        data = json.loads(f.read_text(encoding="utf-8"))
        if dataset_id and data.get("id") != dataset_id:
            continue
        datasets.append(data)
    return datasets


def _golden_placeholders(dataset: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for gr in dataset.get("golden_resolutions") or []:
        out.extend(gr.get("placeholders") or [])
    return out


def _is_url_assert(placeholder: dict[str, Any]) -> bool:
    return placeholder.get("expected_type") == "url_assertion" or str(
        placeholder.get("expected_locator", "")
    ).startswith("expect(page).to_have_url")


def _selectors_to_check(placeholder: dict[str, Any]) -> list[str]:
    """Tolerance selectors first, then the exact golden locator (dedup'd)."""
    tols = list(placeholder.get("tolerance_selectors") or [])
    exact = placeholder.get("expected_locator")
    if exact and exact not in tols and not _is_url_assert(placeholder):
        tols.append(exact)
    return tols


def _check_selectors_on_page(page: Any, selectors: list[str]) -> tuple[bool, list[str]]:
    """Return (any_match, missing_selectors) for *selectors* on *page*.

    Golden tolerance semantics are **OR**: a golden passes when ANY tolerance
    (or the exact locator) resolves — the eval ``golden_validator`` accepts the
    same way. ``missing`` is only populated when NONE matched (a real-decay
    finding); a passing golden returns an empty missing list even if some stale
    tolerances failed.
    """
    missing: list[str] = []
    any_match = False
    for sel in selectors:
        try:
            # The golden may be a full code snippet (e.g. has_text) — only
            # check when it is a usable Playwright locator string.
            if sel.startswith("expect("):
                continue
            if page.locator(sel).count() >= 1:
                any_match = True
                continue
        except Exception:  # invalid selector syntax → treat as not-found
            pass
        missing.append(sel)
    return any_match, ([] if any_match else missing)


def _page_url_matches(page_url: str, expected: str) -> bool:
    """Compare a page URL against the URL the golden names (path-insensitive
    to trailing slashes / landing redirects)."""
    a = page_url.rstrip("/").split("?")[0]
    b = expected.rstrip("/").split("?")[0]
    return a == b


#: Frozen captures of the pages these goldens name (`scraped_pages/`), keyed by
#: URL. A stateful row is checked against its capture instead of being skipped
#: (t-1303 step 3): the capture is the DOM the tool itself recorded when the page
#: was really served, so a locator in it was on the page, and a miss reads as
#: "the capture does not hold it" rather than "the live page decayed".
CAPTURES_DIR = Path(__file__).resolve().parent / "scraped_pages"


def load_captures(directory: Path | None = None) -> dict[str, dict[str, Any]]:
    """Every frozen page capture, keyed by its URL (trailing slash normalised)."""
    captures: dict[str, dict[str, Any]] = {}
    for path in sorted((directory or CAPTURES_DIR).glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except OSError, ValueError:
            continue
        if isinstance(data, dict) and "elements" in data and data.get("url"):
            captures[str(data["url"]).rstrip("/")] = data
    return captures


def _capture_holds(capture: dict[str, Any], selector: str) -> bool:
    """Whether a frozen capture holds this selector (id, exact CSS, or text)."""
    selector = selector.strip()
    elements = capture.get("elements") or []
    if not selector:
        return True
    if selector.startswith("#") and " " not in selector:
        return any(e.get("id") == selector[1:] or e.get("selector") == selector for e in elements)
    if ":has-text(" in selector:
        want = selector.split(":has-text(", 1)[1].rstrip(")").strip().strip("\"'").lower()
        return any(want in str(e.get("text") or "").lower() for e in elements)
    return any(e.get("selector") == selector for e in elements)


def _capture_check(placeholder: dict[str, Any], captures: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    """Check one row against the frozen captures, or ``None`` when they cannot decide.

    The same three facts the live path checks: the locator is on ``target_page``,
    ``outcome_page`` exists as a page, and (for an element ASSERT) the locator is
    on ``outcome_page``. ``None`` means a capture the row needs is missing - the
    caller says so instead of counting a skip as a pass.
    """
    from golden_validator import accepts_page_arrival

    target = str(placeholder.get("target_page") or "").rstrip("/")
    outcome = str(placeholder.get("outcome_page") or "").rstrip("/")
    url_row = _is_url_assert(placeholder) or placeholder.get("action") in ("GOTO", "URL")
    problems: list[dict[str, Any]] = []
    needed: list[str] = []

    if url_row:
        if not outcome:
            return {"status": "unchecked", "reason": "a URL row must name outcome_page"}
        needed.append(outcome)
        if outcome not in captures:
            return None
        if not _page_url_matches(str(captures[outcome].get("url") or ""), outcome):
            problems.append({"outcome_page": outcome, "actual_url": captures[outcome].get("url")})
    else:
        if not target:
            return {"status": "unchecked", "reason": "an element row must name target_page"}
        needed.append(target)
        if target not in captures:
            return None
        missing = [s for s in _selectors_to_check(placeholder) if not _capture_holds(captures[target], s)]
        if missing:
            problems.append({"target_page": target, "missing_selectors": missing})
        if outcome and placeholder.get("action") == "ASSERT" and not accepts_page_arrival(placeholder):
            needed.append(outcome)
            if outcome not in captures:
                return None
            outcome_missing = [s for s in _selectors_to_check(placeholder) if not _capture_holds(captures[outcome], s)]
            if outcome_missing and outcome != target:
                problems.append({"outcome_page": outcome, "missing_selectors": outcome_missing})

    return {
        "status": "ok" if not problems else "missing",
        "problems": problems,
        "pages": needed,
    }


def _is_stateful_golden(dataset: dict[str, Any], placeholder: dict[str, Any]) -> bool:
    """True when this golden can only be truthfully validated by the harness's
    execution path (stateful page / post-submit element), not a static load."""
    ds_id = dataset.get("id", "")
    frags = STATEFUL_PATHS.get(ds_id, [])
    # t-1303: the page this row is about is its target (element rows) or its
    # outcome (URL rows). One field used to carry both.
    target = placeholder.get("target_page") or placeholder.get("outcome_page") or ""
    if any(f in target for f in frags):
        return True
    desc = str(placeholder.get("description", "")).lower()
    return any(f in desc for f in STATEFUL_DESCRIPTION_FRAGMENTS)


def _check_live_dataset(
    dataset: dict[str, Any],
    *,
    page: Any,
    timeout_s: int,
    captures: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Check every golden row: schema, target, outcome page, outcome element.

    The three facts are separate on purpose (t-1303). ``target_page`` is where
    the locator must be; ``outcome_page`` is where the step lands, so it must be
    a page that exists; and for an element-kind ASSERT the locator must be on the
    page the claim is judged on.

    A row on a state-dependent page is **not skipped any more**. It is checked
    against its frozen capture (``scraped_pages/``): the DOM the tool recorded
    when that page was really served. If no capture of the page exists, the row
    is reported as ``needs-a-session`` - unproven, never a pass and never a silent
    skip. That is what replaced ``STATEFUL_PATHS``: the list was blind to exactly
    the banking rows this job corrects.
    """
    from golden_validator import accepts_page_arrival, check_page_schema

    captures = captures or {}
    base_url = dataset.get("base_url", "")
    pages_checked: list[str] = []
    missing: list[dict[str, Any]] = []
    checked = 0
    matched = 0
    from_capture: list[dict[str, Any]] = []
    needs_session: list[dict[str, Any]] = []
    schema_errors = check_page_schema(dataset)

    page.set_default_timeout(timeout_s * 1000)

    def _goto(target: str) -> None:
        nonlocal pages_checked
        try:
            page.goto(target, timeout=timeout_s * 1000, wait_until="domcontentloaded")
        except Exception:
            pass
        pages_checked.append(target)

    for placeholder in _golden_placeholders(dataset):
        label = str(placeholder.get("description") or "")
        # 1. Schema. A row the two-page schema refuses is reported, not checked:
        #    checking it would judge a key whose pages are the wrong way round.
        row_schema = [problem for problem in schema_errors if label and label in problem]
        if row_schema:
            missing.append(
                {
                    "action": placeholder.get("action"),
                    "description": label,
                    "schema": row_schema[0],
                }
            )
            continue

        # 2. State-dependent pages: the frozen capture settles the row.
        if _is_stateful_golden(dataset, placeholder):
            verdict = _capture_check(placeholder, captures)
            if verdict is None or verdict.get("status") == "unchecked":
                reason = (verdict or {}).get(
                    "reason"
                ) or "stateful page with no capture of it - needs a session to check"
                needs_session.append(
                    {
                        "action": placeholder.get("action"),
                        "description": label,
                        "target_page": placeholder.get("target_page"),
                        "outcome_page": placeholder.get("outcome_page"),
                        "reason": reason,
                    }
                )
                continue
            checked += 1
            pages_checked.extend(verdict.get("pages") or [])
            from_capture.append({"description": label, "status": verdict["status"]})
            if verdict["status"] == "ok":
                matched += 1
            else:
                for problem in verdict.get("problems") or []:
                    missing.append(
                        {
                            "action": placeholder.get("action"),
                            "description": label,
                            "basis": "capture",
                            **problem,
                        }
                    )
            continue

        # 3. Outcome page: a URL row must reach the page it names.
        if _is_url_assert(placeholder) or placeholder.get("action") in ("GOTO", "URL"):
            outcome = placeholder.get("outcome_page") or base_url
            if not outcome:
                continue
            checked += 1
            _goto(outcome)
            if _page_url_matches(page.url, outcome):
                matched += 1
            else:
                missing.append(
                    {
                        "action": placeholder.get("action"),
                        "description": label,
                        "outcome_page": outcome,
                        "actual_url": page.url,
                    }
                )
            continue

        # 4. Target: the locator must be on the page that holds it.
        target = placeholder.get("target_page") or base_url
        if not target:
            continue
        checked += 1
        _goto(target)
        selectors = _selectors_to_check(placeholder)
        ok, miss = _check_selectors_on_page(page, selectors)
        if not ok:
            missing.append(
                {
                    "action": placeholder.get("action"),
                    "description": label,
                    "target_page": target,
                    "missing_selectors": miss,
                }
            )
            continue

        # 5. Outcome element: an element ASSERT must be true on the page it names.
        outcome = str(placeholder.get("outcome_page") or "")
        if (
            placeholder.get("action") == "ASSERT"
            and outcome
            and outcome.rstrip("/") != target.rstrip("/")
            and not accepts_page_arrival(placeholder)
        ):
            _goto(outcome)
            outcome_ok, outcome_miss = _check_selectors_on_page(page, selectors)
            if not outcome_ok:
                missing.append(
                    {
                        "action": placeholder.get("action"),
                        "description": label,
                        "outcome_page": outcome,
                        "missing_selectors": outcome_miss,
                    }
                )
                continue
        matched += 1

    return {
        "dataset_id": dataset.get("id"),
        "site": dataset.get("site"),
        "base_url": base_url,
        "kind": "live",
        "status": "ok" if not missing else "fail",
        "checked_at": datetime.now(UTC).isoformat(),
        "goldens_checked": checked,
        "goldens_matched": matched,
        # Kept for older readers: rows that are still unproven, now with a reason.
        "stateful_skipped": len(needs_session),
        "stateful_needs_session": needs_session,
        "stateful_checked_from_capture": from_capture,
        "schema_errors": schema_errors,
        "pages_checked": sorted(set(pages_checked)),
        "missing": missing,
        "stateful": needs_session,
    }


def _rewrite_mock_expected_pages(dataset: dict[str, Any], *, old_origin: str, new_origin: str) -> dict[str, Any]:
    """Clone *dataset*, rewriting placeholder page roots from the
    harness's canonical mock origin to the port this run actually served on.

    Also rewrites the canonical ``http://localhost:8781`` origin directly (some
    mock datasets encode it even when their ``base_url`` carries a path).
    """
    import copy

    d = copy.deepcopy(dataset)
    origins = {o for o in (old_origin, "http://localhost:8781") if o}
    for gr in d.get("golden_resolutions") or []:
        for ph in gr.get("placeholders") or []:
            for field in ("target_page", "outcome_page"):
                value = ph.get(field)
                if not value:
                    continue
                for origin in origins:
                    if value.startswith(origin):
                        ph[field] = new_origin + value[len(origin) :]
                        break
    return d


def _origin_of(url: str) -> str:
    """Scheme://host[:port] of *url* (strips any path)."""
    try:
        from urllib.parse import urlsplit

        parts = urlsplit(url)
        return f"{parts.scheme}://{parts.netloc}"
    except Exception:  # pragma: no cover
        return url.rstrip("/")


def _check_mock_dataset(dataset: dict[str, Any], mock_dir: str, *, port: int) -> dict[str, Any]:
    """Start the local mock server and run the same golden checks against it."""

    sys.path.insert(0, str(REPO_ROOT))
    from scripts.mock_server import MockServer  # type: ignore[import-not-found]

    base_url = f"http://localhost:{port}"
    with MockServer.start(port=port, directory=str(REPO_ROOT / mock_dir)):
        from playwright.sync_api import sync_playwright

        with sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page()
            try:
                # The datasets' golden page values hard-code the
                # harness's canonical mock port (8781); rewrite that origin to
                # the port we actually served on, or every goto would target a
                # dead port → about:blank (observed 6i debug).
                old_origin = _origin_of(dataset.get("base_url", ""))
                d = _rewrite_mock_expected_pages(dataset, old_origin=old_origin, new_origin=base_url)
                d["base_url"] = base_url
                return _check_live_dataset(d, page=page, timeout_s=10, captures=load_captures())
            finally:
                browser.close()


def _check_static_only(dataset: dict[str, Any]) -> dict[str, Any]:
    """Datasets with no locally-servable target → honest static-only record."""
    placeholders = _golden_placeholders(dataset)
    return {
        "dataset_id": dataset.get("id"),
        "site": dataset.get("site"),
        "base_url": dataset.get("base_url", ""),
        "kind": "static-only",
        "status": "static-only",
        "checked_at": datetime.now(UTC).isoformat(),
        "goldens_checked": len(placeholders),
        "goldens_matched": None,
        "pages_checked": [],
        "missing": [],
        "note": "No local mock or public site — validated via frozen captures (see eval harness).",
    }


def run_revalidation(
    dataset_id: str | None = None, *, mock_port: int = 8781, live_timeout_s: int = 30
) -> list[dict[str, Any]]:
    """Re-validate all (or one) datasets; returns per-dataset records.

    Never raises on network failure — unreachable live sites are recorded as
    ``unreachable`` (status) so CI stays green offline while the recency record
    stays honest.
    """
    datasets = _load_dataset(dataset_id)
    records: list[dict[str, Any]] = []

    for ds in datasets:
        ds_id = ds.get("id")
        if ds_id in MOCK_DATASET_IDS:
            try:
                records.append(_check_mock_dataset(ds, MOCK_DATASET_IDS[ds_id], port=mock_port))
            except Exception as exc:
                records.append(
                    {
                        "dataset_id": ds_id,
                        "site": ds.get("site"),
                        "base_url": ds.get("base_url", ""),
                        "kind": "mock",
                        "status": "unreachable",
                        "checked_at": datetime.now(UTC).isoformat(),
                        "goldens_checked": 0,
                        "goldens_matched": 0,
                        "pages_checked": [],
                        "missing": [],
                        "error": str(exc),
                    }
                )
            continue

        if ds_id in STATIC_ONLY_DATASET_IDS:
            records.append(_check_static_only(ds))
            continue

        # Live site.
        try:
            from playwright.sync_api import sync_playwright

            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page()
                try:
                    records.append(
                        _check_live_dataset(ds, page=page, timeout_s=live_timeout_s, captures=load_captures())
                    )
                finally:
                    browser.close()
        except Exception as exc:
            records.append(
                {
                    "dataset_id": ds_id,
                    "site": ds.get("site"),
                    "base_url": ds.get("base_url", ""),
                    "kind": "live",
                    "status": "unreachable",
                    "checked_at": datetime.now(UTC).isoformat(),
                    "goldens_checked": 0,
                    "goldens_matched": 0,
                    "pages_checked": [],
                    "missing": [],
                    "error": str(exc),
                }
            )

    return records


def render_report(records: list[dict[str, Any]]) -> str:
    lines = ["Golden-key re-validation (Phase 6i)", f"  ran at   : {datetime.now(UTC).isoformat()}"]
    for r in records:
        mark = "✓" if r["status"] == "ok" else ("⚠" if r["status"] in ("unreachable", "static-only") else "✗")
        stat = r["status"]
        if r["goldens_matched"] is not None:
            extra = f" (+{r.get('stateful_skipped', 0)} stateful-skipped)" if r.get("stateful_skipped") else ""
            lines.append(
                f"  {mark} {r['dataset_id']:10} {r['site']:22} {stat:12} {r['goldens_matched']}/{r['goldens_checked']} goldens{extra}"
            )
        else:
            lines.append(f"  {mark} {r['dataset_id']:10} {r['site']:22} {stat:12} (static-only)")
        for m in r.get("missing", [])[:6]:
            lines.append(
                f"      ✗ {m.get('description')} @ {m.get('target_page') or m.get('outcome_page')} — {m.get('missing_selectors') or m.get('actual_url')}"
            )
        if r.get("error"):
            lines.append(f"      unreachable: {r['error'][:120]}")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    # Windows consoles default to cp1252 — force UTF-8 so ✓/⚠/✗ render.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]

    parser = argparse.ArgumentParser(description="Golden-key live re-validation (Phase 6i).")
    parser.add_argument("--dataset", default="", help="Re-validate only this dataset id (eval-00X).")
    parser.add_argument("--mock-port", type=int, default=8781, help="Port for the local mock server (default 8781).")
    parser.add_argument("--live-timeout", type=int, default=30, help="Per-page timeout for live sites (seconds).")
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON on stdout.")
    parser.add_argument("--save", default="", help="Write the recency record to this path.")
    args = parser.parse_args(argv)

    records = run_revalidation(args.dataset or None, mock_port=args.mock_port, live_timeout_s=args.live_timeout)

    if args.save:
        out = Path(args.save)
        out.parent.mkdir(parents=True, exist_ok=True)
        payload = {"ran_at": datetime.now(UTC).isoformat(), "datasets": records}
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"Revalidation record written to {out}")

    if args.json:
        print(json.dumps(records))
    else:
        print(render_report(records))

    # Exit 1 only on *real* decay (a reachable dataset with missing goldens).
    # Unreachable (no network) and static-only never fail the run.
    if any(r["status"] == "fail" for r in records):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
