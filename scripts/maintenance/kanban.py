#!/usr/bin/env python3
"""Generate kanban.html from BACKLOG.md + ROADMAP_ROADTO_PRODUCTION.md.

BACKLOG.md  -> bugs, issues found, unplanned changes
ROADMAP.md  -> planned features and milestones

Both are merged into a single kanban view. Items sharing an ID are deduplicated;
the roadmap status wins for column assignment.
"""

from __future__ import annotations

import re
import sys
from datetime import UTC, datetime
from html import escape as html_escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
BACKLOG_PATH = ROOT / "BACKLOG.md"
ROADMAP_PATH = ROOT / "docs" / "plans" / "ROADMAP_ROADTO_PRODUCTION.md"
KANBAN_PATH = ROOT / "kanban.html"

# ── Column mapping ──────────────────────────────────────────────────────────

TODO_EMOJIS = {"\U0001f195", "\U0001f534", "\u2753"}  # new, red, ?
PROGRESS_EMOJIS = {"\U0001f7e1", "\U0001f527"}  # yellow, wrench
DONE_EMOJIS = {"\u2705"}  # checkmark

TODO_LABEL = "To Do"
PROGRESS_LABEL = "In Progress"
DONE_LABEL = "Done"

# Standard issue ID patterns
_STD_ID_PAT = r"(?:AI|B|CI|REF|BREAK|FC)-\d+"

# Leading dash strip pattern (em-dash, en-dash, plain hyphen)
_LEADING_DASH_RE = re.compile(r"^[\u2014\u2013-]\s*")


# ── Backlog parser ──────────────────────────────────────────────────────────


def parse_backlog(path: Path) -> list[dict]:
    """Parse BACKLOG.md into structured items with status, id, title."""
    text = path.read_text(encoding="utf-8")

    # Match section headers: ## or ###, optional emoji, optional ID, dash, title
    header_re = re.compile(
        r"^(#{2,3})\s*"  # ## or ###
        r"([\u2705\U0001f195\U0001f7e1\U0001f534\u2753]?)\s*"  # optional emoji
        r"([A-Z]+-\d+\s+)?\s*"  # optional ID
        r"(?:[\u2014\u2013-]\s*)?"  # optional dash
        r"(.+)$",  # rest is title
    )

    status_override_re = re.compile(r"\*\*Status:\*\*\s*([\u2705\U0001f7e1\U0001f534\u2753])\s*(.*)")

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
                if item_id:
                    current = _make_item(emoji or "\U0001f195", item_id, title, lineno, "BACKLOG.md")
                    section_emoji = None
                else:
                    section_emoji = emoji or "\U0001f195"
                    current = None
            elif level == 3:
                if item_id:
                    sub_emoji = emoji or section_emoji or "\U0001f195"
                    current = _make_item(sub_emoji, item_id, title, lineno, "BACKLOG.md")
        elif current is not None:
            current["content"].append(line)
            sm = status_override_re.search(line)
            if sm:
                current["status_override"] = sm.group(1)

    if current is not None:
        items.append(current)

    return items


# ── Roadmap parser ──────────────────────────────────────────────────────────


def parse_roadmap(path: Path) -> list[dict]:
    """Parse ROADMAP_ROADTO_PRODUCTION.md items from Tier 1-5 sections.

    Skips the summary checklist table, session tracking, and rules.
    """
    text = path.read_text(encoding="utf-8")

    # Match ### headers, capturing ID and title separately
    item_header_re = re.compile(
        r"^###\s+"
        r"(?:\d+[a-z]?\.\s+)?"  # optional number (12b.)
        r"(" + _STD_ID_PAT + r")?\s*"  # optional standard ID (group 1)
        r"(.+)$"  # rest = title (group 2)
    )

    status_re = re.compile(r"\*\*Status[:*]{1,3}\s*`\[([x~SR\s])\]`")

    items: list[dict] = []
    current: dict | None = None
    in_tier = False
    in_checklist = False
    relative_path = _relative_path(path)

    for lineno, line in enumerate(text.split("\n"), start=1):
        # Track tier sections
        if re.match(r"^## Tier \d", line):
            in_tier = True
            in_checklist = False
            continue

        # Stop parsing at these sections
        if re.match(
            r"^(## (?:Summary Checklist|Future Considerations|Session Tracking|Rules for Implementation))",
            line,
        ):
            in_tier = False
            continue

        # Skip the summary checklist table
        if in_checklist:
            if line.startswith("|"):
                continue
            in_checklist = False

        if re.match(r"^\| # \| Item \| Tier \| Status", line):
            in_checklist = True
            continue

        if not in_tier or in_checklist:
            continue

        # Match item headers
        m = item_header_re.match(line)
        if m:
            if current:
                items.append(current)

            raw_id = (m.group(1) or "").strip()
            raw_title = (m.group(2) or "").strip()
            # Strip leading dash (em-dash, en-dash, hyphen)
            title = _LEADING_DASH_RE.sub("", raw_title).strip()

            item_id = raw_id if raw_id else _generate_roadmap_id(title)
            current = _make_item("", item_id, title, lineno, relative_path)
            current["roadmap_status"] = "[ ]"  # default until we find status line

        elif current is not None:
            current["content"].append(line)
            sm = status_re.search(line)
            if sm:
                current["roadmap_status"] = f"[{sm.group(1)}]"

    if current is not None:
        items.append(current)

    return items


def _generate_roadmap_id(title: str) -> str:
    """Generate a readable ID for roadmap items without standard IDs."""
    # Extract phase number
    pm = re.match(r"Phase\s+(\d+[a-z]?)", title)
    if pm:
        return f"PHASE-{pm.group(1)}"

    # Use first significant words from title
    words = [w for w in title.split() if w not in ("the", "a", "an", "for", "of")]
    if words:
        prefix = "-".join(w.upper()[:8] for w in words[:2])
        return f"RD-{prefix}"

    return f"RD-{abs(hash(title)) % 10000:04d}"


# ── Item helpers ────────────────────────────────────────────────────────────


def _make_item(emoji: str, item_id: str, title: str, lineno: int, source_path: str) -> dict:
    # Clean common suffixes: "(2026-...)", "(COMPLETE ...)"
    title = re.sub(r"\s*\(COMPLETE\s*[\u2014\u2013-].*?\)$", "", title).strip()
    title = re.sub(r"\s*\(\d{4}-\d{2}-\d{2}\)$", "", title).strip()
    return {
        "emoji": emoji,
        "id": item_id,
        "title": title,
        "content": [],
        "line": lineno,
        "source_path": source_path,
    }


def _column_for(item: dict) -> str:
    """Determine which column an item belongs in.

    Roadmap status markers take priority over backlog emoji status.
    """
    # Roadmap status wins
    rs = item.get("roadmap_status")
    if rs:
        if rs in ("[x]", "[S]"):
            return DONE_LABEL
        if rs == "[~]":
            return PROGRESS_LABEL
        return TODO_LABEL

    # Backlog status override (from **Status:** line)
    override = item.get("status_override")
    if override == "\u2705":
        return DONE_LABEL
    if override == "\U0001f7e1":
        return PROGRESS_LABEL

    # Backlog emoji
    emoji = item["emoji"]
    if emoji in DONE_EMOJIS:
        return DONE_LABEL
    if emoji in PROGRESS_EMOJIS:
        return PROGRESS_LABEL
    return TODO_LABEL


# ── Merge logic ─────────────────────────────────────────────────────────────


def merge_items(roadmap_items: list[dict], backlog_items: list[dict]) -> list[dict]:
    """Merge roadmap and backlog items, deduplicating by ID.

    Roadmap items are added first (features). Backlog items merge in by ID.
    For shared IDs, roadmap status wins for column assignment.
    """
    merged: dict[str, dict] = {}

    # Roadmap first
    for item in roadmap_items:
        rs = item.get("roadmap_status", "")
        if rs == "[R]":
            continue  # skip removed items
        merged[item["id"]] = item

    # Backlog second
    for item in backlog_items:
        bid = item["id"]
        if bid in merged:
            existing = merged[bid]
            existing["content"].extend(item.get("content", []))
            existing["backlog_line"] = item.get("line", 0)
            if "roadmap_status" not in existing:
                existing["emoji"] = item.get("emoji", "")
                existing["status_override"] = item.get("status_override")
        else:
            merged[bid] = item

    return list(merged.values())


# ── HTML generator ──────────────────────────────────────────────────────────


def generate_html(items: list[dict], source_updated: str) -> str:
    """Generate a self-contained kanban HTML page."""
    columns: dict[str, list[dict]] = {
        TODO_LABEL: [],
        PROGRESS_LABEL: [],
        DONE_LABEL: [],
    }
    for item in items:
        col = _column_for(item)
        columns[col].append(item)

    done_count = str(len(columns[DONE_LABEL]))
    roadmap_count = sum(1 for it in items if "ROADMAP" in it.get("source_path", ""))
    backlog_count = len(items) - roadmap_count
    src_time = html_escape(source_updated)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Kanban \u2014 tancat-ai/tancat</title>
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
    flex-wrap: wrap;
    gap: 4px;
}}
.card-link {{
    color: #58a6ff;
    text-decoration: none;
    font-size: 0.7rem;
}}
.card-link:hover {{ text-decoration: underline; }}
.source-badge {{
    font-size: 0.6rem;
    padding: 1px 5px;
    border-radius: 3px;
    background: #1a3a5c;
    color: #58a6ff;
    text-transform: uppercase;
    letter-spacing: 0.05em;
}}
.source-badge.roadmap {{ background: #2d1a3c; color: #bc8cff; }}
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
    <h1>\U0001f4cb Kanban Board</h1>
    <p>Generated from <code>BACKLOG.md</code> ({backlog_count}) + <code>ROADMAP_ROADTO_PRODUCTION.md</code> ({roadmap_count}) &mdash; {src_time}</p>
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
    source_path = item.get("source_path", "BACKLOG.md")

    # Priority / additional info from content
    extra = ""
    for cline in item.get("content", [])[:3]:
        pm = re.match(r"\*\*Priority:\*\*\s*(.*)", cline)
        if pm:
            extra = pm.group(1).strip()
            break

    # Source badge
    is_roadmap = source_path != "BACKLOG.md"
    badge_cls = "roadmap" if is_roadmap else ""
    badge_label = "ROADMAP" if is_roadmap else "BACKLOG"
    source_badge = f'<span class="source-badge {badge_cls}">{badge_label}</span>'

    meta_parts = []
    if extra:
        meta_parts.append(f"<span>{html_escape(extra)}</span>")
    meta_parts.append(source_badge)

    # Link to source file
    source_label = source_path.split("/")[-1] if "/" in source_path else source_path
    if line:
        meta_parts.append(
            f'<a class="card-link" href="{source_path}#L{line}" target="_blank">{source_label}:{line}</a>'
        )

    # Also show backlog link for merged items
    bline = item.get("backlog_line", 0)
    if bline and is_roadmap:
        meta_parts.append(f'<a class="card-link" href="BACKLOG.md#L{bline}" target="_blank">BACKLOG.md:{bline}</a>')

    meta = "\n".join(meta_parts)

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

    items = _load_all_items()
    new_html = generate_html(items, _source_timestamp())
    existing = KANBAN_PATH.read_text(encoding="utf-8")

    # Normalize the "Generated from ... <timestamp></p>" line before comparing.
    # Strip the whole line to a canonical form so a wall-clock/min-advance in the
    # embedded timestamp (source-file mtime or regen time) can never make the check
    # flaky — only the item content (counts + rows) is compared.
    _norm = re.compile(r"Generated from.*?</p>", re.DOTALL)
    new_normalized = _norm.sub("Generated from BACKLOG.md</p>", new_html)
    existing_normalized = _norm.sub("Generated from BACKLOG.md</p>", existing)

    if new_normalized.strip() != existing_normalized.strip():
        print("ERROR: kanban.html is stale. Run: python scripts/maintenance/kanban.py")
        return 1

    print("OK: kanban.html is up to date")
    return 0


# ── Main ─────────────────────────────────────────────────────────────────────


def _source_timestamp() -> str:
    """Human-readable timestamp for the newest source file's modification."""
    mtime = max(
        BACKLOG_PATH.stat().st_mtime if BACKLOG_PATH.exists() else 0,
        ROADMAP_PATH.stat().st_mtime if ROADMAP_PATH.exists() else 0,
    )
    dt = datetime.fromtimestamp(mtime, tz=UTC)
    return dt.strftime("%Y-%m-%d %H:%M UTC")


def _relative_path(path: Path) -> str:
    """Get the path relative to ROOT, falling back to absolute."""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _load_all_items() -> list[dict]:
    """Parse both sources and return merged items."""
    roadmap_items: list[dict] = []
    if ROADMAP_PATH.exists():
        roadmap_items = parse_roadmap(ROADMAP_PATH)

    backlog_items: list[dict] = []
    if BACKLOG_PATH.exists():
        backlog_items = parse_backlog(BACKLOG_PATH)

    return merge_items(roadmap_items, backlog_items)


def main() -> None:
    if "--check" in sys.argv:
        sys.exit(check_mode())

    items = _load_all_items()
    roadmap_count = sum(1 for it in items if "ROADMAP" in it.get("source_path", ""))
    backlog_count = len(items) - roadmap_count

    html = generate_html(items, _source_timestamp())
    KANBAN_PATH.write_text(html, encoding="utf-8")
    print(f"OK: generated kanban.html ({roadmap_count} from roadmap, {backlog_count} from backlog)")


if __name__ == "__main__":
    main()
