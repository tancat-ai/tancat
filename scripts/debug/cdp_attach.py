"""Attach to the user's Chrome via CDP (remote-debugging-port=9222) and dump
the accessibility tree of the Streamlit tab — real co-working view.

Usage:
    python scripts/debug/cdp_attach.py tabs            # list tabs
    python scripts/debug/cdp_attach.py ax              # AX tree of localhost:8501 tab
    python scripts/debug/cdp_attach.py ax --max-depth 8
    python scripts/debug/cdp_attach.py eval "1+1"      # run JS in the 8501 tab
"""

from __future__ import annotations

import argparse
import json
import sys

from playwright.sync_api import sync_playwright

CDP_URL = "http://localhost:9222"


def _find_app_tab(pages) -> object | None:
    for pg in pages:
        if "8501" in pg.url:
            return pg
    return None


def dump_ax(max_depth: int | None = None) -> str:
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(CDP_URL)
        ctx = browser.contexts[0]
        app = _find_app_tab(ctx.pages)
        if app is None:
            return "APP TAB NOT FOUND — tabs: " + ", ".join(pg.url for pg in ctx.pages)
        cdp = ctx.new_cdp_session(app)
        res = cdp.send("Accessibility.getFullAXTree")
        nodes = res.get("nodes", [])

        by_id: dict[str, dict] = {n["nodeId"]: n for n in nodes}
        children_map: dict[str, list[str]] = {}
        for n in nodes:
            children_map.setdefault(n.get("parentId", ""), []).append(n["nodeId"])

        def role_name(n: dict) -> tuple[str, str]:
            role = n.get("role", {}).get("value", "generic")
            name = n.get("name", {}).get("value", "")
            return role, name

        def _props(n: dict) -> str:
            bits = []
            for prop in n.get("properties", []):
                if prop["name"] in ("level", "checked", "selected", "expanded", "pressed"):
                    bits.append(f"{prop['name']}={prop.get('value', {}).get('value', prop.get('value'))}")
            return " ".join(bits)

        lines: list[str] = []

        def walk(node_id: str, depth: int) -> None:
            if max_depth is not None and depth > max_depth:
                return
            n = by_id.get(node_id)
            if n is None:
                return
            role, name = role_name(n)
            if role in ("generic", "none", "Unknown") and not name:
                pass  # still recurse
            props = _props(n)
            indent = "  " * depth
            label = f"{indent}- {role}"
            if name:
                label += f" \"{name}\""
            if props:
                label += f" [{props}]"
            lines.append(label)
            for child in children_map.get(node_id, []):
                walk(child, depth + 1)

        roots = [nid for nid, n in by_id.items() if not n.get("parentId") or n.get("parentId") == "0"]
        for rid in roots:
            walk(rid, 0)
        return "\n".join(lines)


def run_js(expr: str) -> str:
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(CDP_URL)
        ctx = browser.contexts[0]
        app = _find_app_tab(ctx.pages)
        if app is None:
            return "APP TAB NOT FOUND"
        return str(app.evaluate(expr))


def list_tabs() -> str:
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(CDP_URL)
        out = []
        for i, pg in enumerate(browser.contexts[0].pages):
            out.append(f"[{i}] {pg.title()} | {pg.url}")
        return "\n".join(out)


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("tabs")
    p_ax = sub.add_parser("ax")
    p_ax.add_argument("--max-depth", type=int, default=None)
    p_eval = sub.add_parser("eval")
    p_eval.add_argument("expr")
    args = parser.parse_args()

    if args.cmd == "tabs":
        print(list_tabs())
    elif args.cmd == "ax":
        print(dump_ax(args.max_depth))
    elif args.cmd == "eval":
        print(run_js(args.expr))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
