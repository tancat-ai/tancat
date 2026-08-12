"""Flow-memory holdout evaluation - AI-042 (roadmap §16 evaluation item).

Measures whether cross-site flow memory, trained **without** the target site,
resolves the eval datasets' URL-assertion / GOTO golden placeholders - the
"first passing test on an unseen site" value moment.

Why these placeholders: page-state assertions ("cart page title") and GOTO
navigation are resolved as URLs (B-021). Today the resolver-only eval
(`eval_resolver.py`) treats ASSERT as element matching, so these golden keys
always fail (no DOM element matches "cart page title"). Flow memory can
rescue them when a flow verified on OTHER sites ends at the expected route
with matching vocabulary.

Holdout integrity: a flow counts only if the target site's own site hash is
NOT among the pattern's ``site_hashes``. Cross-site strictness
(``--min-sites 2``) requires >=2 verifying sites.

Context reachability: a flow is only consumable in the pipeline when the
target site actually has a page for the flow's ``from_route`` (the current
page at resolution time). The script verifies this against the dataset's own
URLs (base URL + every golden URL) and any per-site scraped pages.

Usage::

    python scripts/eval/flow_holdout_eval.py                    # default store + all datasets
    python scripts/eval/flow_holdout_eval.py --store /path/flow_memory.json
    python scripts/eval/flow_holdout_eval.py --json             # machine-readable
    python scripts/eval/flow_holdout_eval.py --min-sites 2      # cross-site verified only
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_DATASET_DIR = _PROJECT_ROOT / "scripts" / "eval" / "dataset"
_SCRAPED_DIR = _PROJECT_ROOT / "scripts" / "eval" / "scraped_pages"

sys.path.insert(0, str(_PROJECT_ROOT))

from src.flow_memory import FlowMemoryStore, _tokens, clean_description, normalize_route  # noqa: E402
from src.rag_learn import domain_from_url, site_hash  # noqa: E402


def _extract_url(exp: str) -> str:
    return exp.split('"')[1] if '"' in exp else exp


def _golden_url_asserts() -> list[dict[str, Any]]:
    """Golden placeholders resolved as URLs (page-state asserts / GOTO)."""
    found: list[dict[str, Any]] = []
    for fpath in sorted(_DATASET_DIR.glob("*.json")):
        data = json.loads(fpath.read_text(encoding="utf-8"))
        site = str(data.get("site", ""))
        base_url = str(data.get("base_url", ""))
        target_hash = site_hash(domain_from_url(base_url))
        for crit in data.get("golden_resolutions", []):
            for ph in crit.get("placeholders", []):
                exp = str(ph.get("expected_locator", "") or "")
                if "to_have_url" in exp or ph["action"] in ("GOTO", "URL"):
                    found.append(
                        {
                            "site": site,
                            "site_hash": target_hash,
                            "action": ph["action"],
                            "description": ph["description"],
                            "expected_url": _extract_url(exp),
                            "expected_route": normalize_route(_extract_url(exp)),
                            "dataset": fpath.stem,
                        }
                    )
    return found


def _site_known_urls(placeholder: dict[str, Any]) -> set[str]:
    """All URLs the target site is known to have: dataset base + golden URLs
    + scraped-page entries for the site's domain."""
    urls: set[str] = {placeholder["expected_url"]}
    for fpath in _DATASET_DIR.glob("*.json"):
        data = json.loads(fpath.read_text(encoding="utf-8"))
        if str(data.get("site", "")) != placeholder["site"]:
            continue
        urls.add(str(data.get("base_url", "")))
        for crit in data.get("golden_resolutions", []):
            for ph in crit.get("placeholders", []):
                exp = str(ph.get("expected_locator", "") or "")
                if "to_have_url" in exp:
                    urls.add(_extract_url(exp))
    # scraped-page files for this site's domain
    target_domain = domain_from_url(placeholder["expected_url"])
    for fpath in _SCRAPED_DIR.glob("*.json"):
        try:
            data = json.loads(fpath.read_text(encoding="utf-8"))
        except Exception:
            continue
        url = str(data.get("url", "") or "")
        if url and domain_from_url(url) == target_domain:
            urls.add(url)
    return urls


def _matching_flows(
    store: FlowMemoryStore,
    placeholder: dict[str, Any],
    *,
    min_sites: int,
    exclude_target: bool,
) -> list[Any]:
    """Flows ending at the expected route whose vocabulary overlaps the
    description. ``exclude_target`` enforces holdout integrity."""
    exp_route = placeholder["expected_route"]
    desc_tokens = _tokens(clean_description(placeholder["description"]))
    matches: list[Any] = []
    for pattern in store._patterns.values():  # noqa: SLF001
        if pattern.to_route != exp_route:
            continue
        if exclude_target and placeholder["site_hash"] in pattern.site_hashes:
            continue
        if pattern.site_count < min_sites:
            continue
        pat_tokens = _tokens(pattern.description) | _tokens(pattern.to_route)
        if desc_tokens and not (desc_tokens & pat_tokens):
            continue
        matches.append(pattern)
    matches.sort(key=lambda p: (-p.site_count, -p.hit_count))
    return matches


def _evaluate(store: FlowMemoryStore, placeholders: list[dict[str, Any]], *, min_sites: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for ph in placeholders:
        all_flows = _matching_flows(store, ph, min_sites=min_sites, exclude_target=False)
        holdout_flows = _matching_flows(store, ph, min_sites=min_sites, exclude_target=True)
        known_urls = _site_known_urls(ph)
        known_routes = {normalize_route(u) for u in known_urls}
        context_flows = [p for p in holdout_flows if p.from_route in known_routes]
        rows.append(
            {
                "site": ph["site"],
                "description": ph["description"],
                "action": ph["action"],
                "expected_route": ph["expected_route"],
                "expected_url": ph["expected_url"],
                "home_target": ph["expected_route"] == "home",
                "flow_supported": bool(all_flows),
                "holdout_resolvable": bool(holdout_flows),
                "context_reachable": bool(context_flows),
                "flow_count": len(all_flows),
                "holdout_count": len(holdout_flows),
                "context_count": len(context_flows),
                "cross_site": any(p.site_count >= 2 for p in holdout_flows),
                "best_flows": [
                    {
                        "from_route": p.from_route,
                        "action": p.action,
                        "label": p.description,
                        "hits": p.hit_count,
                        "sites": p.site_count,
                    }
                    for p in context_flows[:3]
                ]
                or [
                    {
                        "from_route": p.from_route,
                        "action": p.action,
                        "label": p.description,
                        "hits": p.hit_count,
                        "sites": p.site_count,
                    }
                    for p in holdout_flows[:3]
                ],
            }
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--store", type=Path, default=None, help="Flow store path (default: workspace evidence/flow_memory.json)"
    )
    parser.add_argument(
        "--min-sites", type=int, default=1, help="Minimum verifying sites (2 = cross-site verified only)"
    )
    parser.add_argument("--json", action="store_true", help="Machine-readable output")
    args = parser.parse_args()

    store = FlowMemoryStore(args.store)
    rows = _evaluate(store, _golden_url_asserts(), min_sites=args.min_sites)

    if args.json:
        print(json.dumps(rows, indent=2))
        return 0

    print(
        f"Flow-memory holdout evaluation (store: {store.path}, {store.stats()['patterns']} patterns, "
        f"min_sites={args.min_sites})"
    )
    print(f"{'site':<20}{'description':<30}{'route':<16}{'sup':>4}{'hold':>5}{'ctx':>4}{'xs':>3}  notes")
    print("-" * 104)
    for r in rows:
        notes = ""
        if r["best_flows"]:
            b = r["best_flows"][0]
            notes = f"from {b['from_route']} ({b['sites']} site{'s' if b['sites'] > 1 else ''}, {b['hits']} hits)"
        if r["home_target"]:
            notes = "home target - seed-URL fallback scope, not flow memory"
        elif r["context_reachable"]:
            notes += " [context OK]"
        elif r["holdout_resolvable"]:
            notes += " [flow ok, no matching from-context on this site]"
        print(
            f"{r['site']:<20}{r['description'][:29]:<30}{r['expected_route']:<16}"
            f"{'y' if r['flow_supported'] else '-':>4}"
            f"{'y' if r['holdout_resolvable'] else '-':>5}"
            f"{'y' if r['context_reachable'] else '-':>4}"
            f"{'y' if r['cross_site'] else '-':>3}  {notes}"
        )

    total = len(rows)
    non_home = [r for r in rows if not r["home_target"]]
    supported = sum(1 for r in rows if r["flow_supported"])
    holdout = sum(1 for r in rows if r["holdout_resolvable"])
    context = sum(1 for r in rows if r["context_reachable"])
    print("-" * 104)
    print(f"URL-assertion/GOTO golden placeholders: {total}  (non-home: {len(non_home)})")
    print(f"  any-site flow supports:                       {supported}/{total}")
    print(f"  holdout (target site excluded):               {holdout}/{total}")
    print(f"  holdout + from-context reachable:             {context}/{total}")
    print(f"  strict cross-site (>=2 sites) among holdout:  {sum(1 for r in rows if r['cross_site'])}/{total}")
    print()
    print("Baseline today: 0 (eval_resolver treats ASSERT as element matching - page-state")
    print("URL assertions never match a DOM element; GOTO goldens are absent from the sets).")
    print("Flow memory is a *fallback*: it fills gaps site-specific resolution leaves; the")
    print("delta above is the transfer value on these golden sets with the current corpus.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
