"""Guard: the post-run learning hooks stay wired in the scripts.

``scripts/verify_production.py`` and ``scripts/synthesize_stories.py`` both
call ``FlowMemoryStore().learn_suite_flows(<evidence dir>)`` after a real run
— the product-gate and training paths that feed suite-level flows. The
synthesize script additionally runs the B-047 parent-side RAG sweep
(``learn_from_evidence_sidecars``) — the in-process substitute for the
pytest-subprocess learning hook, which is Milvus-lock-blocked while the
resolve-and-learn parent holds the store. These scripts are not exercised by
the unit suite (they need an LLM / live sites), so a deleted or mis-wired
hook would go unnoticed.

Why a static guard: mirrors ``tests/test_no_live_network_in_default_suite.py``.
The hooks are 5-line guarded try/except blocks calling a well-tested method
(``learn_suite_flows`` has its own unit tests); a wiring test would require
heavy patching of the whole script for low marginal value. This guard fails if
the call or its evidence-dir target disappears.
"""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

#: Script → the suite-chaining hook it must keep.
SCRIPT_HOOKS: dict[str, str] = {
    "verify_production.py": "learn_suite_flows(",
    "synthesize_stories.py": "learn_suite_flows(",
}

#: Script → the B-047 parent-side RAG sweep it must keep (the subprocess
#: learning hook is Milvus-lock-blocked in batch resolve-and-learn runs).
SCRIPT_RAG_SWEEPS: dict[str, str] = {
    "synthesize_stories.py": "learn_from_evidence_sidecars(",
}


def test_suite_chaining_hook_present_in_both_scripts() -> None:
    for filename, hook in SCRIPT_HOOKS.items():
        text = (PROJECT_ROOT / "scripts" / filename).read_text(encoding="utf-8")
        assert hook in text, f"scripts/{filename} lost its suite-chaining hook (AI-042-F3)"


def test_suite_chaining_hook_targets_an_evidence_dir() -> None:
    """The hook must be called with an evidence directory (a typo'd path would
    silently learn nothing)."""
    for filename in SCRIPT_HOOKS:
        text = (PROJECT_ROOT / "scripts" / filename).read_text(encoding="utf-8")
        assert "learn_suite_flows(" in text
        assert '/ "evidence")' in text, f"scripts/{filename} hook no longer targets an evidence dir"


def test_rag_sidecar_sweep_present_in_resolve_and_learn() -> None:
    """B-047: the parent-side RAG sweep must stay wired in synthesize_stories.

    Without it, batch ``--resolve-and-learn`` runs learn nothing: the pytest
    subprocess hook raises ``DataDirLockedError`` (Milvus-lite lock held by
    the parent) and the conftest try/except swallows it. The sweep runs in
    the parent, after each site's executions, so batch runs actually grow
    the learned-pattern store.
    """
    for filename, hook in SCRIPT_RAG_SWEEPS.items():
        text = (PROJECT_ROOT / "scripts" / filename).read_text(encoding="utf-8")
        assert hook in text, f"scripts/{filename} lost its parent-side RAG sweep (B-047 follow-up)"
        # The sweep must target the site's evidence dir — a typo'd path would
        # silently learn nothing (same failure mode as the suite-chaining hook).
        assert "evidence'" in text or 'evidence"' in text, (
            f"scripts/{filename} RAG sweep no longer targets an evidence dir"
        )


def test_rag_sidecar_sweep_runs_per_site() -> None:
    """The sweep must run once per site (after the site's test executions),
    not once for the whole run — per-site keeps the learned patterns scoped
    to the site's own sidecars and matches the flow-memory hooks' cadence."""
    text = (PROJECT_ROOT / "scripts" / "synthesize_stories.py").read_text(encoding="utf-8")
    # The sweep call sits inside the per-site loop: the site loop header must
    # precede the sweep call.
    site_loop = text.find("for site in sites:")
    sweep = text.find("learn_from_evidence_sidecars(")
    assert site_loop != -1 and sweep != -1 and sweep > site_loop, (
        "parent-side RAG sweep is no longer inside the per-site loop"
    )
