"""Tests for the Streamlit sidebar panel (AI-042-F2 flow-memory section)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.flow_memory import FlowMemoryStore, FlowTransition
from src.ui.ui_sidebar import SidebarConfig


class _FakeSidebar:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []

    def subheader(self, text: str) -> None:
        self.calls.append(("subheader", text))

    def caption(self, text: str) -> None:
        self.calls.append(("caption", text))

    def button(self, *args: Any, **kwargs: Any) -> bool:  # noqa: ARG002
        self.calls.append(("button", args[0] if args else ""))
        return False  # never trigger the confirm flow in these tests

    def success(self, text: str) -> None:
        self.calls.append(("success", text))

    def error(self, text: str) -> None:
        self.calls.append(("error", text))


class _FakeSt:
    def __init__(self) -> None:
        self.sidebar = _FakeSidebar()
        self.session_state: dict[str, Any] = {}


def _seeded_store(path: Path) -> FlowMemoryStore:
    store = FlowMemoryStore(path)
    store.upsert_flow(FlowTransition("login", "CLICK", "sign in", "dashboard"), "site-a.com")
    store.upsert_flow(FlowTransition("login", "CLICK", "sign in", "dashboard"), "site-b.com")
    store.upsert_flow(FlowTransition("cart", "GOTO", "checkout", "checkout"), "site-a.com", source="suite_chain")
    return store


def test_render_flow_memory_shows_stats(monkeypatch: Any, tmp_path: Path) -> None:
    """With learned flows, the sidebar shows the stats caption + prune button."""
    store = _seeded_store(tmp_path / "fm.json")
    fake = _FakeSt()
    monkeypatch.setattr("src.ui.ui_sidebar.st", fake)
    monkeypatch.setattr("src.flow_memory.FlowMemoryStore", lambda: store)

    SidebarConfig._render_flow_memory()

    captions = [t for kind, t in fake.sidebar.calls if kind == "caption"]
    assert any("**Patterns:** 2" in c for c in captions)
    assert any("**Sites:** 2" in c for c in captions)
    assert any("**Cross-site:** 1" in c for c in captions)
    assert any("**Suite chains:** 1" in c for c in captions)
    assert any(kind == "subheader" and text == "Flow Memory" for kind, text in fake.sidebar.calls)
    assert any(kind == "button" and "Prune learned flows" in text for kind, text in fake.sidebar.calls)


def test_render_flow_memory_degrades_when_empty(monkeypatch: Any, tmp_path: Path) -> None:
    """An empty store shows a hint, not a stats block or prune button."""
    store = FlowMemoryStore(tmp_path / "empty.json")
    fake = _FakeSt()
    monkeypatch.setattr("src.ui.ui_sidebar.st", fake)
    monkeypatch.setattr("src.flow_memory.FlowMemoryStore", lambda: store)

    SidebarConfig._render_flow_memory()

    captions = [t for kind, t in fake.sidebar.calls if kind == "caption"]
    assert any("no flows learned yet" in c for c in captions)
    assert not any(kind == "subheader" for kind, _ in fake.sidebar.calls)
    assert not any(kind == "button" for kind, _ in fake.sidebar.calls)
