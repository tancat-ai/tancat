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

    def selectbox(self, *args: Any, **kwargs: Any) -> str:
        self.sidebar.calls.append(("selectbox", args[0] if args else ""))
        options = args[1] if len(args) > 1 else kwargs.get("options", [])
        return options[kwargs.get("index", 0)]

    def caption(self, text: str) -> None:
        self.sidebar.calls.append(("caption", text))

    def error(self, text: str) -> None:
        self.sidebar.calls.append(("error", text))

    def warning(self, text: str) -> None:
        self.sidebar.calls.append(("warning", text))


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

    # run 1: the refusal is recorded and a rerun is requested.
    SidebarConfig._render_license_entry(LicenseResult(status=LicenseStatus.UNLICENSED))
    assert fake.session_state["license_entry_flash"] == (
        "error",
        "That licence token was refused: Token malformed: bad",
    )
    assert fake.session_state["license_entry_open"] is True

    # run 2 (the rerun): the reason is shown in the panel.
    fake.sidebar._submitted = False
    SidebarConfig._render_license_entry(LicenseResult(status=LicenseStatus.UNLICENSED))
    errors = [text for kind, text in fake.sidebar.calls if kind == "error"]
    assert errors
    assert "refused" in errors[0]
    assert "Token malformed" in errors[0]


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


def test_render_license_entry_clears_token_after_success(monkeypatch: Any) -> None:
    """The paste field is empty after a successful save."""
    from src.licensing.license import LicenseResult, LicenseStatus

    fake = _FakeSt(submitted=True, token="a-token")
    fake.session_state["license_entry_open"] = True
    fake.session_state["license_entry_token"] = "a-token"
    monkeypatch.setattr("src.ui.ui_sidebar.st", fake)
    monkeypatch.setattr(
        "src.licensing.license.save_license_key",
        lambda token: LicenseResult(LicenseStatus.VALID, tier="pro", deployment_id="deploy-42"),
    )

    SidebarConfig._render_license_entry(LicenseResult(status=LicenseStatus.UNLICENSED))
    assert fake.session_state["license_entry_open"] is False

    # run 2 (the rerun): the flash is consumed and the field is cleared.
    SidebarConfig._render_license_entry(
        LicenseResult(status=LicenseStatus.VALID, tier="pro", deployment_id="deploy-42")
    )
    assert fake.session_state["license_entry_token"] == ""


def test_render_license_entry_clears_token_after_refusal(monkeypatch: Any) -> None:
    """The paste field is empty after a refused token."""
    from src.licensing.license import LicenseResult, LicenseStatus

    fake = _FakeSt(submitted=True, token="garbage")
    fake.session_state["license_entry_open"] = True
    fake.session_state["license_entry_token"] = "garbage"
    monkeypatch.setattr("src.ui.ui_sidebar.st", fake)
    monkeypatch.setattr(
        "src.licensing.license.save_license_key",
        lambda token: LicenseResult(LicenseStatus.INVALID, reason="Token malformed: bad"),
    )

    SidebarConfig._render_license_entry(LicenseResult(status=LicenseStatus.UNLICENSED))

    # run 2 (the rerun): the field is cleared even though the panel stays open.
    fake.sidebar._submitted = False
    SidebarConfig._render_license_entry(LicenseResult(status=LicenseStatus.UNLICENSED))
    assert fake.session_state["license_entry_open"] is True
    assert fake.session_state["license_entry_token"] == ""


def test_render_license_entry_save_error_shows_a_line(monkeypatch: Any) -> None:
    """A save error is caught and shown as a line, not raised."""
    from src.licensing.license import LicenseResult, LicenseStatus

    fake = _FakeSt(submitted=True, token="a-token")
    fake.session_state["license_entry_open"] = True
    monkeypatch.setattr("src.ui.ui_sidebar.st", fake)

    def _boom(token: str) -> Any:
        raise PermissionError("read-only file system")

    monkeypatch.setattr("src.licensing.license.save_license_key", _boom)

    # run 1 must not raise.
    SidebarConfig._render_license_entry(LicenseResult(status=LicenseStatus.UNLICENSED))
    assert fake.session_state["license_entry_flash"] == (
        "error",
        "Could not save the licence: read-only file system",
    )

    # run 2 (the rerun): the error is shown as a line in the panel.
    fake.sidebar._submitted = False
    SidebarConfig._render_license_entry(LicenseResult(status=LicenseStatus.UNLICENSED))
    errors = [text for kind, text in fake.sidebar.calls if kind == "error"]
    assert errors
    assert "Could not save the licence" in errors[0]


# ---------------------------------------------------------------------------
# OCR backend picker (job j-0039): offer only what this build can run
# ---------------------------------------------------------------------------


def test_ocr_choices_hide_gpu_without_a_gpu(monkeypatch: Any) -> None:
    """A GPU-less build offers the CPU tier and hides the GPU choice."""
    from src.ui.ui_sidebar import _ocr_backend_choices

    monkeypatch.setattr("src.ocr_backends.PyMuPDFBackend.available", True)
    monkeypatch.setattr("src.ocr_backends.RapidOCRBackend.engine_available", True)
    monkeypatch.setattr("src.ocr_backends.UnlimitedOCRBackend.engine_available", False)

    choices, notes = _ocr_backend_choices()

    assert choices == ["auto", "cpu"]
    assert any("GPU OCR option is hidden" in n for n in notes)
    assert not any("uv sync" in n for n in notes)


def test_ocr_choices_expose_gpu_when_the_build_has_one(monkeypatch: Any) -> None:
    """A build with PyMuPDF, CPU OCR and a GPU offers all three tiers."""
    from src.ui.ui_sidebar import _ocr_backend_choices

    monkeypatch.setattr("src.ocr_backends.PyMuPDFBackend.available", True)
    monkeypatch.setattr("src.ocr_backends.RapidOCRBackend.engine_available", True)
    monkeypatch.setattr("src.ocr_backends.UnlimitedOCRBackend.engine_available", True)

    choices, notes = _ocr_backend_choices()

    assert choices == ["auto", "cpu", "power"]
    assert notes == []


def test_ocr_choices_name_what_to_install_when_missing(monkeypatch: Any) -> None:
    """The shipped build has no PyMuPDF, no CPU OCR, no GPU - it offers nothing and says why."""
    from src.ui.ui_sidebar import _ocr_backend_choices

    monkeypatch.setattr("src.ocr_backends.PyMuPDFBackend.available", False)
    monkeypatch.setattr("src.ocr_backends.RapidOCRBackend.engine_available", False)
    monkeypatch.setattr("src.ocr_backends.UnlimitedOCRBackend.engine_available", False)

    choices, notes = _ocr_backend_choices()

    assert choices == []
    assert any("uv sync --extra pdf" in n for n in notes)
    assert any("uv sync --extra ocr" in n for n in notes)


def test_render_ocr_backend_migrates_an_unavailable_saved_choice(monkeypatch: Any) -> None:
    """A saved GPU choice on a GPU-less build is named and replaced with Automatic."""
    fake = _FakeSt()
    saved: list[tuple[str, Any]] = []
    monkeypatch.setattr("src.ui.ui_sidebar.st", fake)
    monkeypatch.setattr("src.ocr_backends.PyMuPDFBackend.available", True)
    monkeypatch.setattr("src.ocr_backends.RapidOCRBackend.engine_available", True)
    monkeypatch.setattr("src.ocr_backends.UnlimitedOCRBackend.engine_available", False)
    monkeypatch.setattr("src.ui.ui_sidebar.load_setting", lambda _key, _default=None: "unlimited-ocr")
    monkeypatch.setattr("src.ui.ui_sidebar.save_setting", lambda key, value: saved.append((key, value)))

    result = SidebarConfig._render_ocr_backend()

    assert result == "auto"
    assert ("ocr_backend", "auto") in saved
    captions = [t for kind, t in fake.sidebar.calls if kind == "caption"]
    assert any("cannot run on this build" in c for c in captions)


def test_render_ocr_backend_warns_instead_of_offering_a_dead_choice(monkeypatch: Any) -> None:
    """With nothing installable, the panel warns, renders no dropdown, and the store matches it."""
    fake = _FakeSt()
    saved: list[tuple[str, Any]] = []
    monkeypatch.setattr("src.ui.ui_sidebar.st", fake)
    monkeypatch.setattr("src.ocr_backends.PyMuPDFBackend.available", False)
    monkeypatch.setattr("src.ocr_backends.RapidOCRBackend.engine_available", False)
    monkeypatch.setattr("src.ocr_backends.UnlimitedOCRBackend.engine_available", False)
    monkeypatch.setattr("src.ui.ui_sidebar.load_setting", lambda _key, _default=None: "unlimited-ocr")
    monkeypatch.setattr("src.ui.ui_sidebar.save_setting", lambda key, value: saved.append((key, value)))

    result = SidebarConfig._render_ocr_backend()

    assert result == "auto"
    assert ("ocr_backend", "auto") in saved
    assert any(kind == "warning" for kind, _ in fake.sidebar.calls)
    assert not any(kind == "selectbox" for kind, _ in fake.sidebar.calls)


def test_gpu_note_names_no_gpu_when_that_is_the_cause(monkeypatch: Any) -> None:
    """A genuinely GPU-less machine gets the no-GPU message."""
    from src.ui.ui_sidebar import _gpu_unavailable_reason

    monkeypatch.setattr("src.ui.ui_sidebar._module_available", lambda _name: True)
    monkeypatch.setattr("torch.cuda.is_available", lambda: False)

    reason = _gpu_unavailable_reason()

    assert reason is not None
    assert "no CUDA/ROCm GPU" in reason


def test_gpu_note_names_transformers_when_that_is_the_cause(monkeypatch: Any) -> None:
    """A GPU machine missing transformers is told so, not told it has no GPU."""
    from src.ui.ui_sidebar import _gpu_unavailable_reason

    monkeypatch.setattr("src.ui.ui_sidebar._module_available", lambda name: name == "torch")
    monkeypatch.setattr("torch.cuda.is_available", lambda: True)

    reason = _gpu_unavailable_reason()

    assert reason is not None
    assert "transformers" in reason
    assert "no CUDA/ROCm GPU" not in reason


def test_gpu_note_names_torch_when_it_is_missing(monkeypatch: Any) -> None:
    """A build without PyTorch is told to install it."""
    from src.ui.ui_sidebar import _gpu_unavailable_reason

    monkeypatch.setattr("src.ui.ui_sidebar._module_available", lambda _name: False)

    reason = _gpu_unavailable_reason()

    assert reason is not None
    assert "PyTorch" in reason


def test_ocr_choices_gpu_note_names_the_true_cause(monkeypatch: Any) -> None:
    """The picker's GPU note names the missing package, not a phantom missing GPU."""
    from src.ui.ui_sidebar import _ocr_backend_choices

    monkeypatch.setattr("src.ui.ui_sidebar._module_available", lambda name: name == "torch")
    monkeypatch.setattr("src.ocr_backends.PyMuPDFBackend.available", True)
    monkeypatch.setattr("src.ocr_backends.RapidOCRBackend.engine_available", False)
    monkeypatch.setattr("src.ocr_backends.UnlimitedOCRBackend.engine_available", False)
    monkeypatch.setattr("torch.cuda.is_available", lambda: True)

    _, notes = _ocr_backend_choices()

    assert any("transformers" in n for n in notes)
    assert not any("no CUDA/ROCm GPU" in n for n in notes)


def test_ocr_choices_hide_everything_when_the_backend_cannot_run(monkeypatch: Any) -> None:
    """When the backend reports the PDF library missing, the picker offers no PDF tier."""
    from src.ui.ui_sidebar import _ocr_backend_choices

    monkeypatch.setattr("src.ocr_backends.PyMuPDFBackend.available", False)
    monkeypatch.setattr("src.ocr_backends.RapidOCRBackend.engine_available", True)
    monkeypatch.setattr("src.ocr_backends.UnlimitedOCRBackend.engine_available", True)

    choices, notes = _ocr_backend_choices()

    assert choices == []
    assert any("--extra pdf" in n for n in notes)


def test_ocr_choices_offer_all_tiers_when_the_backend_reports_them(monkeypatch: Any) -> None:
    """The picker agrees with the backend's availability in the positive case too."""
    from src.ui.ui_sidebar import _ocr_backend_choices

    monkeypatch.setattr("src.ocr_backends.PyMuPDFBackend.available", True)
    monkeypatch.setattr("src.ocr_backends.RapidOCRBackend.engine_available", True)
    monkeypatch.setattr("src.ocr_backends.UnlimitedOCRBackend.engine_available", True)

    choices, notes = _ocr_backend_choices()

    assert choices == ["auto", "cpu", "power"]
    assert notes == []


# ---------------------------------------------------------------------------
# OCR refusal + engine in use (job t-0183): no silent downgrade from the env
# ---------------------------------------------------------------------------


def test_render_ocr_refusal_is_shown_at_the_top_of_settings(monkeypatch: Any) -> None:
    """A configured backend that cannot run is refused visibly, not inside the expander."""
    fake = _FakeSt()
    monkeypatch.setattr("src.ui.ui_sidebar.st", fake)
    monkeypatch.setattr(
        "src.ocr_backends.configured_ocr_backend_error",
        lambda: "REFUSED: OCR_BACKEND=power cannot run here",
    )

    SidebarConfig._render_ocr_refusal()

    errors = [t for kind, t in fake.sidebar.calls if kind == "error"]
    assert errors and "REFUSED" in errors[0]


def test_render_ocr_backend_shows_the_engine_in_use(monkeypatch: Any) -> None:
    """The panel names the engine actually in use, so a downgrade is not silent."""
    fake = _FakeSt()
    monkeypatch.setattr("src.ui.ui_sidebar.st", fake)
    monkeypatch.setattr("src.ocr_backends.PyMuPDFBackend.available", True)
    monkeypatch.setattr("src.ocr_backends.RapidOCRBackend.engine_available", True)
    monkeypatch.setattr("src.ocr_backends.UnlimitedOCRBackend.engine_available", True)
    monkeypatch.setattr("src.ui.ui_sidebar.load_setting", lambda _key, _default=None: "auto")
    monkeypatch.setattr("src.ui.ui_sidebar.save_setting", lambda _key, _value: None)

    SidebarConfig._render_ocr_backend()

    captions = [t for kind, t in fake.sidebar.calls if kind == "caption"]
    assert any("Engine in use" in c for c in captions)


# ---------------------------------------------------------------------------
# PDF reader notice (document mode has no reader when the [pdf] extra is absent)
# ---------------------------------------------------------------------------


def test_settings_warn_when_the_pdf_reader_is_missing(monkeypatch: Any) -> None:
    """A build with no reader says so in Settings, where document mode is named."""
    fake = _FakeSt()
    monkeypatch.setattr("src.ui.ui_sidebar.st", fake)
    monkeypatch.setattr("src.pdf_ingest.pdf_reader_available", lambda: False)

    SidebarConfig._render_pdf_reader_notice()

    warnings = [t for kind, t in fake.sidebar.calls if kind == "warning"]
    assert any("--extra pdf" in w for w in warnings)


def test_settings_are_quiet_when_the_pdf_reader_is_present(monkeypatch: Any) -> None:
    fake = _FakeSt()
    monkeypatch.setattr("src.ui.ui_sidebar.st", fake)
    monkeypatch.setattr("src.pdf_ingest.pdf_reader_available", lambda: True)

    SidebarConfig._render_pdf_reader_notice()

    assert not [t for kind, t in fake.sidebar.calls if kind == "warning"]
