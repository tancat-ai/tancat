"""Sidebar configuration panel."""

from __future__ import annotations

from typing import Any, cast

import streamlit as st

from src.provider_config import PROVIDER_LABELS, SUPPORTED_PROVIDERS
from src.settings_store import DEFAULT_SETTINGS, load_setting, save_setting

# Keys whose settings are edited from this panel — kept in one place so
# streamlit_app.py and the panel never disagree on naming.
SETTING_POM_MODE = "pom_mode"
SETTING_CONSENT_MODE = "consent_mode"
SETTING_PROVIDER = "provider"
SETTING_MODEL_NAME = "model_name"
SETTING_WORKSPACE = "workspace"
# Last package loaded via the sidebar — auto-restored on fresh sessions so a
# page reload / reconnect (or a session reset) does not blank Run & Fix.
SETTING_LAST_PACKAGE = "last_package"
SETTING_OCR_BACKEND = "ocr_backend"
SETTING_JIRA_PROJECT_KEY = "jira_project_key"


def _saved_index(options: tuple[str, ...], stored_value: str, default: str) -> int:
    """Return the selectbox index for *stored_value* (falling back to *default*)."""
    if stored_value in options:
        return options.index(stored_value)
    if default in options:
        return options.index(default)
    return 0


# Canonical OCR backend values the panel can store. Legacy names from the
# pre-AI-055 dropdown are mapped to these when read, so an old saved value is
# never lost and never silently kept as something the build cannot run.
_OCR_LABELS: dict[str, str] = {
    "auto": "Automatic - text, plus CPU OCR for scanned pages",
    "cpu": "CPU OCR - local CPU engine for scanned pages",
    "power": "GPU - Unlimited-OCR (needs a CUDA/ROCm GPU)",
}
_OCR_LEGACY_NAMES: dict[str, str] = {
    "pymupdf": "auto",
    "unlimited-ocr": "power",
    "unlimited_ocr": "power",
}


def _module_available(name: str) -> bool:
    """Whether *name* can be imported here (used to report what this build has)."""
    import importlib.util

    return importlib.util.find_spec(name) is not None


def _gpu_unavailable_reason() -> str | None:
    """Why the GPU OCR tier is hidden, or None when it can run.

    Mirrors ``UnlimitedOCRBackend.engine_available``: PyTorch -> CUDA/ROCm ->
    transformers. It names the true cause and how to install it, so a machine
    that has a GPU but is missing a package is not told it has no GPU.
    """
    torch_missing = (
        "The GPU OCR option is hidden: PyTorch is not installed. Install it with `uv sync` (or `pip install torch`)."
    )
    if not _module_available("torch"):
        return torch_missing
    try:
        import torch
    except ImportError:
        return torch_missing
    if not torch.cuda.is_available():
        return "The GPU OCR option is hidden: no CUDA/ROCm GPU is available on this machine."
    if not _module_available("transformers"):
        return (
            "The GPU OCR option is hidden: the `transformers` package is not installed. "
            'Install it with `pip install "transformers>=4.57"`.'
        )
    return None


def _format_ocr_backend(value: str) -> str:
    """Human label for a canonical OCR backend name."""
    return _OCR_LABELS.get(value, value)


def _ocr_backend_choices() -> tuple[list[str], list[str]]:
    """The OCR choices this build can run, plus honest notes on what is missing.

    Only backends that can actually run are offered, so the panel never
    advertises a choice that would silently fall back to a weaker tier. Each
    missing piece gets a note naming how to install it. The GPU tier needs both
    the PDF reader (to rasterise the page) and a CUDA/ROCm GPU, so it is hidden
    when either is absent.
    """
    from src.ocr_backends import PyMuPDFBackend, RapidOCRBackend, UnlimitedOCRBackend
    from src.pdf_ingest import pdf_reader_missing_message

    # The backend answers the same question the PDF-reader notice does; the
    # engine-only flags let each missing piece get its own note.
    has_pdf_text = PyMuPDFBackend().available
    has_cpu_engine = RapidOCRBackend().engine_available
    has_gpu_engine = UnlimitedOCRBackend().engine_available

    choices: list[str] = []
    if has_pdf_text:
        choices.append("auto")
        if has_cpu_engine:
            choices.append("cpu")
    if has_pdf_text and has_gpu_engine:
        choices.append("power")

    notes: list[str] = []
    if not has_pdf_text:
        notes.append(pdf_reader_missing_message())
    if not has_cpu_engine:
        notes.append(
            "Scanned (image-only) pages cannot be read: the CPU OCR engine is not installed. "
            "Install it with `uv sync --extra ocr` (or `pip install rapidocr_onnxruntime`)."
        )
    if not has_gpu_engine:
        notes.append(_gpu_unavailable_reason() or "The GPU OCR option is hidden.")
    elif not has_pdf_text:
        notes.append("The GPU OCR option is hidden until the PDF reader is installed (it rasterises the page).")
    return choices, notes


class SidebarConfig:
    """Renders the configuration sidebar and returns the selected values."""

    @staticmethod
    def render() -> dict[str, Any]:
        """Render sidebar and return provider configuration.

        Returns a dict with:
        - provider: str — selected LLM provider key
        - pom_mode: bool — Page Object Model generation mode

        B-036 Phase 4: both values persist through the SettingsStore so
        choices survive app restarts.
        """
        st.sidebar.title("Configuration")
        provider_options = SUPPORTED_PROVIDERS

        def _format_provider(value: str) -> str:
            return PROVIDER_LABELS[value]

        stored_provider = cast(str, load_setting(SETTING_PROVIDER, ""))
        provider = cast(
            str,
            st.sidebar.selectbox(
                "LLM Provider",
                provider_options,
                format_func=_format_provider,
                index=_saved_index(provider_options, stored_provider, DEFAULT_SETTINGS["provider"]),
            ),
        )
        if provider != stored_provider:
            save_setting(SETTING_PROVIDER, provider)

        # AI-010 Phase 4: POM mode toggle
        if "pom_mode" not in st.session_state:
            st.session_state["pom_mode"] = bool(load_setting(SETTING_POM_MODE, False))

        st.sidebar.divider()
        st.sidebar.subheader("Test Structure")
        pom_mode = st.sidebar.toggle(
            "Page Object Model",
            value=st.session_state.pom_mode,
            help="Generate tests using Page Object Model classes with evidence-aware locators",
        )
        st.session_state.pom_mode = pom_mode
        if pom_mode != bool(load_setting(SETTING_POM_MODE, False)):
            save_setting(SETTING_POM_MODE, pom_mode)

        return {"provider": provider, "pom_mode": pom_mode}

    @staticmethod
    def render_settings() -> dict[str, Any]:
        """Render the persisted Settings panel (B-036 Phase 4).

        Shows app-level persisted settings (OCR backend, workspace) plus
        the RAG store "Learned Patterns" statistics from the B-036 Phase 3
        learning loop. Returns the settings that consumers read elsewhere:
        ocr_backend and workspace.
        """
        st.sidebar.divider()
        st.sidebar.subheader("Settings")

        # Refuse loudly at the top of Settings, not inside the collapsed
        # expander: a configured backend this build cannot run must be visible.
        SidebarConfig._render_ocr_refusal()

        with st.sidebar.expander("App Settings", expanded=False):
            ocr_backend = SidebarConfig._render_ocr_backend()

            stored_workspace = cast(str, load_setting(SETTING_WORKSPACE, "default"))
            workspace = st.text_input(
                "Workspace",
                value=stored_workspace,
                help="Isolates generated tests / evidence under a subdirectory. Applies immediately.",
                key="workspace_setting",
            )
            if workspace != stored_workspace:
                save_setting(SETTING_WORKSPACE, workspace)

        SidebarConfig._render_pdf_reader_notice()
        SidebarConfig._render_learned_patterns()
        SidebarConfig._render_flow_memory()

        return {"ocr_backend": ocr_backend, "workspace": workspace}

    @staticmethod
    def _render_ocr_refusal() -> None:
        """Show, above the Settings expander, a configured backend that cannot run.

        The picker lives in a collapsed expander; a refusal must not hide there.
        The factory raises the same line, so the two never drift.
        """
        from src.ocr_backends import configured_ocr_backend_error

        refusal = configured_ocr_backend_error()
        if refusal:
            st.sidebar.error(refusal)

    @staticmethod
    def _render_ocr_backend() -> str:
        """Render the OCR backend picker; return the canonical value to store.

        Only backends this build can run are offered, and the store is kept in
        step with the panel in every case - including when nothing is
        installable and no choice can be shown. A saved backend that cannot run
        is named and replaced with Automatic, so nothing silently falls back.
        """
        choices, notes = _ocr_backend_choices()
        stored_raw = str(load_setting(SETTING_OCR_BACKEND, "auto") or "auto")
        stored = _OCR_LEGACY_NAMES.get(stored_raw, stored_raw)

        if stored not in choices and stored_raw != "auto":
            st.caption(f"Saved OCR backend '{stored_raw}' cannot run on this build; using Automatic.")
        effective = stored if stored in choices else "auto"

        if choices:
            ocr_backend = str(
                st.selectbox(
                    "OCR Backend (document mode)",
                    choices,
                    index=choices.index(effective),
                    format_func=_format_ocr_backend,
                    help=(
                        "How PDFs in document mode are read. Automatic reads the text directly and "
                        "uses CPU OCR for scanned pages; CPU OCR forces the local CPU engine; the GPU "
                        "tier runs Unlimited-OCR (CUDA/ROCm)."
                    ),
                    key="ocr_backend_setting",
                )
            )
            for note in notes:
                st.caption(note)
        else:
            ocr_backend = "auto"
            for note in notes:
                st.warning(note)

        if ocr_backend != stored_raw:
            save_setting(SETTING_OCR_BACKEND, ocr_backend)
        # Say plainly which engine is actually in use (the owner's question 3).
        st.caption(f"Engine in use: {_format_ocr_backend(ocr_backend)}")
        return ocr_backend

    @staticmethod
    def _render_pdf_reader_notice() -> None:
        """Say plainly when this build has no PDF reader.

        Separate from the OCR picker's note: that one covers the OCR tiers,
        while a build with no reader cannot read a PDF at all - document mode
        has no reader. Rendered wherever Settings renders, so the user meets it
        without having to open a particular dropdown.
        """
        from src.pdf_ingest import pdf_reader_available, pdf_reader_missing_message

        if not pdf_reader_available():
            st.sidebar.warning(pdf_reader_missing_message())

    @staticmethod
    def _render_learned_patterns() -> None:
        """Show RAG store statistics from the B-036 Phase 3 learning loop.

        Best-effort: a missing/unopenable store degrades to a short note
        instead of an error (same philosophy as always-on RAG).
        """
        try:
            from src.rag_bundled import store_stats

            stats = store_stats()
        except Exception:
            st.sidebar.caption("Learned Patterns: store unavailable (RAG off or not yet initialised).")
            return

        if not stats:
            st.sidebar.caption("Learned Patterns: no RAG store yet.")
            return

        learned = int(stats.get("learned", 0))
        golden = int(stats.get("golden", 0))
        docs = int(stats.get("doc", 0))
        total = int(stats.get("total", learned + golden + docs))

        st.sidebar.subheader("RAG Store")
        st.sidebar.caption(f"**Learned:** {learned} · **Golden:** {golden} · **Docs:** {docs} · **Total:** {total}")

        prune_key = "prune_learned_confirm"
        if learned and st.sidebar.button(
            "Prune learned patterns",
            type="secondary",
            help="Delete patterns learned from your own runs; golden patterns and docs stay.",
            key="prune_learned_button",
        ):
            st.session_state[prune_key] = True
        if st.session_state.get(prune_key, False):
            st.sidebar.caption("Click again to confirm pruning all learned patterns.")
            if st.sidebar.button("Yes — prune learned patterns", type="primary", key="prune_learned_confirm_btn"):
                try:
                    from src.rag_bundled import prune_learned

                    pruned = prune_learned()
                    st.sidebar.success(f"Pruned {pruned} learned pattern(s).")
                except Exception as exc:
                    st.sidebar.error(f"Prune failed: {exc}")
                st.session_state[prune_key] = False

    @staticmethod
    def _render_flow_memory() -> None:
        """AI-042-F2: flow-memory stats + prune (parity with the RAG "Learned
        Patterns" section above).

        Shows the navigation-shape memory the conftest/sweep hooks learn from
        passing runs: pattern count, distinct sites, cross-site (>=2 sites)
        and suite-chain patterns, plus a two-step prune that clears the whole
        flow store (all flows are learned — there is no golden/docs tier to
        keep, unlike RAG). Best-effort: a missing store degrades to a note.
        """
        try:
            from src.flow_memory import FlowMemoryStore, format_flow_stats_summary

            store = FlowMemoryStore()
            stats = store.stats()
        except Exception:
            st.sidebar.caption("Flow Memory: store unavailable.")
            return

        if int(stats.get("patterns", 0)) == 0:
            st.sidebar.caption("Flow Memory: no flows learned yet — run a passing suite to learn navigation shape.")
            return

        st.sidebar.subheader("Flow Memory")
        st.sidebar.caption(format_flow_stats_summary(stats))

        prune_key = "prune_flows_confirm"
        if st.sidebar.button(
            "Prune learned flows",
            type="secondary",
            help=(
                "Delete flows learned from your runs (navigation-shape memory). "
                "RAG learned patterns, golden patterns and docs stay."
            ),
            key="prune_flows_button",
        ):
            st.session_state[prune_key] = True
        if st.session_state.get(prune_key, False):
            st.sidebar.caption("Click again to confirm pruning all learned flows.")
            if st.sidebar.button("Yes — prune learned flows", type="primary", key="prune_flows_confirm_btn"):
                try:
                    store.clear()
                    st.sidebar.success("Pruned all learned flows.")
                except Exception as exc:
                    st.sidebar.error(f"Prune failed: {exc}")
                st.session_state[prune_key] = False

    @staticmethod
    def render_license_usage() -> None:
        """Phase 6e — license status banner + Usage panel (sidebar).

        Purely local: reads the offline license state and the local usage
        meter. Never blocks the OSS core — it informs (and nudges).
        """
        try:
            from src.licensing.license import license_status
            from src.usage_meter import UsageMeter

            status = license_status()
            meter = UsageMeter()
            summary = meter.summary()
        except Exception:  # pragma: no cover - defensive
            return

        st.sidebar.divider()
        st.sidebar.subheader("License & Usage")

        if status.status in ("valid",):
            st.sidebar.success(status.headline)
        elif status.status in ("expired_grace",):
            st.sidebar.warning(status.headline)
        elif status.status in ("expired_blocked", "invalid"):
            st.sidebar.error(status.headline)
        else:
            st.sidebar.info(status.headline)

        # Small action + hidden paste panel (design 2026-09-29, owner's
        # amendment: the box is not permanently visible).
        SidebarConfig._render_license_entry(status)

        runs = summary.runs_used
        runs_limit = summary.runs_limit
        exports = summary.exports_used
        exports_limit = summary.exports_limit

        def _line(label: str, used: int, limit: int | None) -> str:
            if limit is None:
                return f"{label}: {used} (unlimited)"
            return f"{label}: {used}/{limit} this month"

        st.sidebar.caption(_line("Runs", runs, runs_limit))
        st.sidebar.caption(_line("Evidence exports", exports, exports_limit))
        if summary.storage_bytes:
            mb = summary.storage_bytes / (1024 * 1024)
            st.sidebar.caption(f"Storage: {mb:.1f} MB")
        if summary.enforcement_on and (summary.runs_remaining == 0 or summary.exports_remaining == 0):
            st.sidebar.warning("Free-tier limit reached. Request a license for unlimited runs and exports.")

    @staticmethod
    def _render_license_entry(status: Any) -> None:
        """Small licence action plus a hidden paste panel (design 2026-09-29).

        The one-line state is rendered above, unchanged. This adds one small
        action next to it: "Enter a licence" when none is installed, "Replace
        licence" once one is. The paste field + Save only appear after the
        action is clicked and close after a successful save, so the box is
        never permanently visible. The field is cleared after every outcome,
        so it never prefills the previous token, and a refused token or a save
        error shows a line here in the panel, not only in the state line.
        """
        from src.licensing.license import LicenseStatus, save_license_key

        flash = st.session_state.pop("license_entry_flash", None)
        if flash is not None:
            kind, message = flash
            # Clear the paste field on any outcome (success or refusal) before
            # the widget is instantiated this run, so reopening "Replace
            # licence" never prefills the previous token.
            st.session_state["license_entry_token"] = ""
            if kind == "success":
                st.sidebar.success(message)
            elif kind == "warning":
                st.sidebar.warning(message)
            else:
                st.sidebar.error(message)

        installed = status.status in (
            LicenseStatus.VALID,
            LicenseStatus.EXPIRED_GRACE,
            LicenseStatus.EXPIRED_BLOCKED,
        )
        open_key = "license_entry_open"
        if st.sidebar.button(
            "Replace licence" if installed else "Enter a licence",
            key="license_entry_button",
            help="Paste the licence token from your email.",
        ):
            st.session_state[open_key] = not st.session_state.get(open_key, False)

        if not st.session_state.get(open_key, False):
            return

        with st.sidebar.form("license_entry_form", clear_on_submit=False):
            token = st.sidebar.text_area(
                "Licence token",
                key="license_entry_token",
                height=80,
                placeholder="Paste the token from your email, then Save.",
            )
            submitted = st.sidebar.form_submit_button("Save")

        if not submitted:
            return

        try:
            result = save_license_key(token)
        except Exception as exc:  # a filesystem/permission error must show a line, not raise
            st.session_state["license_entry_flash"] = ("error", f"Could not save the licence: {exc}")
            st.rerun()
            return

        if result.status == LicenseStatus.INVALID:
            # Refusal is an outcome too: show the reason on the rerun and clear
            # the field there.
            st.session_state["license_entry_flash"] = ("error", f"That licence token was refused: {result.reason}")
            st.rerun()
            return

        deployment = result.deployment_id or "unknown"
        if result.status == LicenseStatus.VALID:
            st.session_state["license_entry_flash"] = (
                "success",
                f"Licence installed. Deployment id: {deployment}.",
            )
        else:
            st.session_state["license_entry_flash"] = (
                "warning",
                f"Licence installed, but it is not active ({result.status}). Deployment id: {deployment}.",
            )
        st.session_state[open_key] = False
        st.rerun()
