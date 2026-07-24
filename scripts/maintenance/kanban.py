#!/usr/bin/env python3
"""Generate kanban.html from BACKLOG.md — a visual board, not a source of truth.

Usage:
    python scripts/maintenance/kanban.py              # generate kanban.html
    python scripts/maintenance/kanban.py --check      # exit 1 if kanban.html is stale
"""

from __future__ import annotations

import re
import sys
from datetime import UTC, datetime
from html import escape as html_escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
BACKLOG_PATH = ROOT / "BACKLOG.md"
KANBAN_PATH = ROOT / "kanban.html"

# ── Column mapping ──────────────────────────────────────────────────────────

TODO_EMOJIS = {"🆕", "🔴", "❓"}
PROGRESS_EMOJIS = {"🟡", "🔧"}
DONE_EMOJIS = {"✅"}

TODO_LABEL = "To Do"
PROGRESS_LABEL = "In Progress"
DONE_LABEL = "Done"


# ── Parser ───────────────────────────────────────────────────────────────────


def parse_backlog(path: Path) -> list[dict]:
    """Parse BACKLOG.md into structured items with status, id, title."""
    text = path.read_text(encoding="utf-8")

    # Match section headers: ## or ###, optional emoji, optional ID, dash, title
    header_re = re.compile(
        r"^(#{2,3})\s*"  # ## or ###
        r"([✅🆕🟡🔴❓]?)\s*"  # optional emoji
        r"([A-Z]+-\d+\s+)?\s*"  # optional ID (AI-XXX, B-XXX, REF-XXX, CI-XXX)
        r"(?:[—–-]\s*)?"  # optional dash
        r"(.+)$",  # rest is title
    )

    status_override_re = re.compile(r"\*\*Status:\*\*\s*([✅🟡🔴❓])\s*(.*)")

    items: list[dict] = []
    current: dict | None = None
    section_emoji: str | None = None

    for lineno, line in enumerate(text.split("\n"), start=1):
        m = header_re.match(line)
        if m:
            level = len(m.group(1))
            emoji = m.group(2) or ""
            item_id = (m.group(3) or "").strip()
            title = (m.group(4) or "").strip()

            # Save previous item
            if current:
                items.append(current)
                current = None

            if level == 2:
                # Top-level: could be a standalone item or a section
                if item_id:
                    current = _make_item(emoji or "🆕", item_id, title, lineno)
                    section_emoji = None
                else:
                    # Section header (e.g. "## 🟡 Active Improvements", "## 🔴 Open Bugs")
                    section_emoji = emoji or "🆕"
                    current = None
            elif level == 3:
                # Sub-item — belongs to current section; skip if no ID
                if item_id:
                    sub_emoji = emoji or section_emoji or "🆕"
                    current = _make_item(sub_emoji, item_id, title, lineno)
        elif current is not None:
            # Accumulate content for the current item
            current["content"].append(line)
            sm = status_override_re.search(line)
            if sm:
                current["status_override"] = sm.group(1)

    if current is not None:
        items.append(current)

    return items


def _make_item(emoji: str, item_id: str, title: str, lineno: int) -> dict:
    # Clean common suffixes: "(2026-...)", "(COMPLETE — ...)"
    title = re.sub(r"\s*\(COMPLETE\s*[—–-].*?\)$", "", title).strip()
    title = re.sub(r"\s*\(\d{4}-\d{2}-\d{2}\)$", "", title).strip()
    return {
        "emoji": emoji,
        "id": item_id,
        "title": title,
        "content": [],
        "line": lineno,
    }


def _column_for(item: dict) -> str:
    """Determine which column an item belongs in."""
    # Status override (from **Status:** line) wins
    override = item.get("status_override")
    if override == "✅":
        return DONE_LABEL
    if override == "🟡":
        return PROGRESS_LABEL

    emoji = item["emoji"]
    if emoji in DONE_EMOJIS:
        return DONE_LABEL
    if emoji in PROGRESS_EMOJIS:
        return PROGRESS_LABEL
    return TODO_LABEL


# ── HTML generator ──────────────────────────────────────────────────────────


def generate_html(items: list[dict], source_updated: str) -> str:
    """Generate a self-contained kanban HTML page."""
    # Group items by column
    columns: dict[str, list[dict]] = {
        TODO_LABEL: [],
        PROGRESS_LABEL: [],
        DONE_LABEL: [],
    }
    for item in items:
        col = _column_for(item)
        columns[col].append(item)

    done_count = str(len(columns[DONE_LABEL]))
    src_time = html_escape(source_updated)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Kanban — AI-Playwright-Test-Generator</title>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: #0d1117;
    color: #c9d1d9;
    padding: 20px;
}}
header {{
    margin-bottom: 24px;
}}
header h1 {{ font-size: 1.4rem; color: #58a6ff; }}
header p {{ font-size: 0.8rem; color: #8b949e; margin-top: 4px; }}
.board {{
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    gap: 16px;
    align-items: start;
}}
@media (max-width: 900px) {{
    .board {{ grid-template-columns: 1fr; }}
}}
.column {{
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 6px;
    padding: 12px;
    min-height: 200px;
}}
.column h2 {{
    font-size: 0.9rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    padding-bottom: 8px;
    margin-bottom: 8px;
    border-bottom: 1px solid #30363d;
}}
.column.todo h2 {{ color: #f0883e; }}
.column.progress h2 {{ color: #d29922; }}
.column.done h2 {{ color: #3fb950; }}
.done-section {{ display: none; }}
.done-section.open {{ display: block; }}
.toggle-done {{
    background: none;
    border: 1px solid #30363d;
    color: #8b949e;
    padding: 4px 12px;
    border-radius: 4px;
    cursor: pointer;
    font-size: 0.75rem;
    margin-bottom: 8px;
}}
.toggle-done:hover {{ color: #c9d1d9; background: #21262d; }}
.card {{
    background: #21262d;
    border: 1px solid #30363d;
    border-radius: 4px;
    padding: 10px;
    margin-bottom: 8px;
    transition: border-color 0.15s;
}}
.card:hover {{ border-color: #58a6ff; }}
.card-id {{
    font-size: 0.7rem;
    font-weight: 700;
    color: #58a6ff;
    margin-bottom: 4px;
}}
.card-title {{
    font-size: 0.85rem;
    line-height: 1.35;
    margin-bottom: 6px;
}}
.card-meta {{
    font-size: 0.7rem;
    color: #8b949e;
    display: flex;
    justify-content: space-between;
    align-items: center;
}}
.card-link {{
    color: #58a6ff;
    text-decoration: none;
    font-size: 0.7rem;
}}
.card-link:hover {{ text-decoration: underline; }}
.empty {{
    color: #484f58;
    font-size: 0.8rem;
    font-style: italic;
    padding: 16px 0;
    text-align: center;
}}
</style>
</head>
<body>
<header>
    <h1>📋 Kanban Board</h1>
    <p>Generated from <code>BACKLOG.md</code> &mdash; {src_time}</p>
</header>
<div class="board">
    {_render_column(TODO_LABEL, "todo", columns[TODO_LABEL])}
    {_render_column(PROGRESS_LABEL, "progress", columns[PROGRESS_LABEL])}
    {_render_column(DONE_LABEL, "done", columns[DONE_LABEL], done_count)}
</div>
<script>
(function() {{
    var btn = document.getElementById('toggle-done-btn');
    var section = document.getElementById('done-section');
    var count = "{done_count}";
    if (btn && section) {{
        btn.addEventListener('click', function() {{
            section.classList.toggle('open');
            btn.textContent = section.classList.contains('open')
                ? 'Hide completed (' + count + ')' : 'Show completed (' + count + ')';
        }});
    }}
}})();
</script>
</body>
</html>"""


def _render_column(label: str, css_class: str, items: list[dict], done_count: str = "0") -> str:
    """Render a single kanban column as HTML."""
    if label == DONE_LABEL:
        count = len(items)
        toggle = f'<button id="toggle-done-btn" class="toggle-done">Show completed ({count})</button>'
        section_open = " done-section"
        section_id = ' id="done-section"'
    else:
        toggle = ""
        section_open = ""
        section_id = ""

    if not items and label != DONE_LABEL:
        cards = '<div class="empty">No items</div>'
    elif not items:
        cards = '<div class="empty">No completed items</div>'
    else:
        cards = "\n".join(_render_card(item) for item in items)

    return f"""<div class="column {css_class}">
    <h2>{label} ({len(items)})</h2>
    {toggle}
    <div{section_id} class="{section_open.strip()}">
    {cards}
    </div>
</div>"""


def _render_card(item: dict) -> str:
    """Render a single card as HTML."""
    item_id = html_escape(item["id"])
    title = html_escape(item.get("title", ""))
    line = item.get("line", 0)

    # Priority / additional info from content
    extra = ""
    for cline in item.get("content", [])[:3]:
        pm = re.match(r"\*\*Priority:\*\*\s*(.*)", cline)
        if pm:
            extra = pm.group(1).strip()
            break

    meta = ""
    if extra:
        meta = f"<span>{html_escape(extra)}</span>"

    if line:
        meta += f'<a class="card-link" href="BACKLOG.md#L{line}" target="_blank">BACKLOG.md:{line}</a>'

    return f"""<div class="card">
    <div class="card-id">{item_id}</div>
    <div class="card-title">{title}</div>
    <div class="card-meta">{meta}</div>
</div>"""


# ── Check mode ───────────────────────────────────────────────────────────────


def check_mode() -> int:
    """Exit 0 if kanban.html is up to date, 1 if stale."""
    if not KANBAN_PATH.exists():
        print("ERROR: kanban.html does not exist. Run kanban.py without --check to generate it.")
        return 1

    items = parse_backlog(BACKLOG_PATH)
    new_html = generate_html(items, _source_timestamp())
    existing = KANBAN_PATH.read_text(encoding="utf-8")

    # Normalize timestamps before comparing (ignore the source_updated line)
    new_normalized = re.sub(r"Generated from.*?</p>", "Generated from BACKLOG.md</p>", new_html)
    existing_normalized = re.sub(r"Generated from.*?</p>", "Generated from BACKLOG.md</p>", existing)

    if new_normalized.strip() != existing_normalized.strip():
        print("ERROR: kanban.html is stale. Run: python scripts/maintenance/kanban.py")
        return 1

    print("OK: kanban.html is up to date")
    return 0


# ── Main ─────────────────────────────────────────────────────────────────────


def _source_timestamp() -> str:
    """Human-readable timestamp for the source file's last modification."""
    mtime = BACKLOG_PATH.stat().st_mtime
    dt = datetime.fromtimestamp(mtime, tz=UTC)
    return dt.strftime("%Y-%m-%d %H:%M UTC")


def main() -> None:
    if "--check" in sys.argv:
        sys.exit(check_mode())

    items = parse_backlog(BACKLOG_PATH)
    html = generate_html(items, _source_timestamp())
    KANBAN_PATH.write_text(html, encoding="utf-8")
    print(f"OK: generated kanban.html ({len(items)} items from BACKLOG.md)")


if __name__ == "__main__":
    main()
