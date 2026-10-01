"""Guard: the committed kanban board must not carry private content.

``kanban.html`` is a committed, generated artefact. Its sources are BACKLOG.md
(public) and the roadmap, which now lives under the ignored ``docs/private/``.
The generator is public-only by default; ``--with-private`` adds the roadmap for
a local view, and a board built that way must not be committed. These tests pin
the guard that catches private bleed, and pin that the generator degrades when
the roadmap is absent.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
KANBAN_SCRIPT = PROJECT_ROOT / "scripts" / "maintenance" / "kanban.py"


def _load_kanban() -> Any:
    spec = importlib.util.spec_from_file_location("kanban_maintenance", KANBAN_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_generator_runs_with_roadmap_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    kanban = _load_kanban()
    monkeypatch.setattr(kanban, "ROADMAP_PUBLIC_PATH", Path("does/not/exist.md"))
    monkeypatch.setattr(kanban, "ROADMAP_PRIVATE_PATH", Path("also/missing.md"))
    items = kanban._load_all_items()
    assert items
    assert all(item.get("source_path") == "BACKLOG.md" for item in items)


def test_committed_board_carries_no_private_content() -> None:
    kanban = _load_kanban()
    text = (PROJECT_ROOT / "kanban.html").read_text(encoding="utf-8")
    assert kanban.private_content_bleed(text) == []


def test_guard_flags_roadmap_content_placed_in_the_board() -> None:
    kanban = _load_kanban()
    text = (PROJECT_ROOT / "kanban.html").read_text(encoding="utf-8")
    poisoned = text.replace("</header>", '<p class="source-badge roadmap">ROADMAP</p></header>')
    assert kanban.private_content_bleed(poisoned)


def test_guard_flags_a_private_phrase(tmp_path: Path) -> None:
    kanban = _load_kanban()
    private = tmp_path / "private"
    private.mkdir()
    phrase = "A private roadmap title that must never leak"
    (private / "PLAN.md").write_text(f"# Plan\n\n- {phrase}\n", encoding="utf-8")
    clean = kanban.private_content_bleed("<div>clean</div>", private_dir=private, public_text="")
    assert clean == []
    poisoned = f"<div>{phrase}</div>"
    assert phrase in kanban.private_content_bleed(poisoned, private_dir=private, public_text="")


def test_guard_ignores_content_shared_with_public_inputs(tmp_path: Path) -> None:
    kanban = _load_kanban()
    private = tmp_path / "private"
    private.mkdir()
    shared = "A backlog title that is also public"
    (private / "PLAN.md").write_text(f"# Plan\n\n- {shared}\n", encoding="utf-8")
    artifact = f"<div>{shared}</div>"
    assert kanban.private_content_bleed(artifact, private_dir=private, public_text=shared) == []
