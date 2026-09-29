"""Tests for the Streamlit sidebar panel (AI-042-F2 flow-memory section)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.flow_memory import FlowMemoryStore, FlowTransition
from src.ui.ui_sidebar import SidebarConfig


class _FakeForm:
    """Context manager returned by the fake sidebar ``form()``."""

    def __enter__(self) -> _FakeForm:
        return self

    def __exit__(self, *exc: Any) -> None:
        return None


class _FakeSidebar:
    def __init__(self, *, button_clicked: bool = False, submitted: bool = False, token: str = "") -> None:
        self.calls: list[tuple[str, Any]] = []
        self._button_clicked = button_clicked
        self._submitted = submitted
        self._token = token

    def subheader(self, text: str) -> None:
        self.calls.append(("subheader", text))

    def caption(self, text: str) -> None:
        self.calls.append(("caption", text))

    def button(self, *args: Any, **kwargs: Any) -> bool:  # noqa: ARG002
        self.calls.append(("button", args[0] if args else ""))
        return self._button_clicked

    def success(self, text: str) -> None:
        self.calls.append(("success", text))

    def warning(self, text: str) -> None:
        self.calls.append(("warning", text))

    def error(self, text: str) -> None:
        self.calls.append(("error", text))

    def form(self, *args: Any, **kwargs: Any) -> _FakeForm:  # noqa: ARG002
        self.calls.append(("form", args[0] if args else ""))
        return _FakeForm()

    def text_area(self, *args: Any, **kwargs: Any) -> str:  # noqa: ARG002
        self.calls.append(("text_area", args[0] if args else ""))
        return self._token

    def form_submit_button(self, *args: Any, **kwargs: Any) -> bool:  # noqa: ARG002
        self.calls.append(("form_submit_button", args[0] if args else ""))
        return self._submitted


class _FakeSt:
    def __init__(self, **sidebar_kwargs: Any) -> None:
        self.sidebar = _FakeSidebar(**sidebar_kwargs)
        self.session_state: dict[str, Any] = {}

    def rerun(self) -> None:
        self.sidebar.calls.append(("rerun", ""))


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


# ---------------------------------------------------------------------------
# Licence paste box (design 2026-09-29): hidden by default, closes on save
# ---------------------------------------------------------------------------


def test_render_license_entry_hidden_by_default(monkeypatch: Any) -> None:
    """A free user sees the state line and the small action, but no paste box."""
    from src.licensing.license import LicenseResult, LicenseStatus

    fake = _FakeSt()
    monkeypatch.setattr("src.ui.ui_sidebar.st", fake)

    SidebarConfig._render_license_entry(LicenseResult(status=LicenseStatus.UNLICENSED))

    assert ("button", "Enter a licence") in fake.sidebar.calls
    assert not any(kind == "text_area" for kind, _ in fake.sidebar.calls)
    assert not any(kind == "form" for kind, _ in fake.sidebar.calls)


def test_render_license_entry_says_replace_when_licensed(monkeypatch: Any) -> None:
    from src.licensing.license import LicenseResult, LicenseStatus

    fake = _FakeSt()
    monkeypatch.setattr("src.ui.ui_sidebar.st", fake)

    SidebarConfig._render_license_entry(LicenseResult(status=LicenseStatus.VALID, tier="pro", deployment_id="d1"))

    assert ("button", "Replace licence") in fake.sidebar.calls


def test_render_license_entry_refusal_is_shown_in_the_panel(monkeypatch: Any) -> None:
    """A refused token shows its reason in the panel and leaves it open."""
    from src.licensing.license import LicenseResult, LicenseStatus

    fake = _FakeSt(submitted=True, token="garbage")
    fake.session_state["license_entry_open"] = True
    monkeypatch.setattr("src.ui.ui_sidebar.st", fake)
    monkeypatch.setattr(
        "src.licensing.license.save_license_key",
        lambda token: LicenseResult(LicenseStatus.INVALID, reason="Token malformed: bad"),
    )

    SidebarConfig._render_license_entry(LicenseResult(status=LicenseStatus.UNLICENSED))

    assert any(kind == "form" for kind, _ in fake.sidebar.calls)
    errors = [text for kind, text in fake.sidebar.calls if kind == "error"]
    assert errors
    assert "refused" in errors[0]
    assert "Token malformed" in errors[0]
    assert fake.session_state["license_entry_open"] is True


def test_render_license_entry_success_closes_and_names_deployment(monkeypatch: Any) -> None:
    from src.licensing.license import LicenseResult, LicenseStatus

    fake = _FakeSt(submitted=True, token="a-token")
    fake.session_state["license_entry_open"] = True
    monkeypatch.setattr("src.ui.ui_sidebar.st", fake)
    monkeypatch.setattr(
        "src.licensing.license.save_license_key",
        lambda token: LicenseResult(LicenseStatus.VALID, tier="pro", deployment_id="deploy-42"),
    )

    SidebarConfig._render_license_entry(LicenseResult(status=LicenseStatus.UNLICENSED))

    assert fake.session_state["license_entry_open"] is False
    assert fake.session_state["license_entry_flash"] == (
        "success",
        "Licence installed. Deployment id: deploy-42.",
    )
    assert ("rerun", "") in fake.sidebar.calls
