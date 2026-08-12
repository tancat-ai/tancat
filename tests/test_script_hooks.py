"""Guard: the suite-chaining hooks (AI-042-F3) stay wired in the scripts.

``scripts/verify_production.py`` and ``scripts/synthesize_stories.py`` both
call ``FlowMemoryStore().learn_suite_flows(<evidence dir>)`` after a real run
— the product-gate and training paths that feed suite-level flows. These
scripts are not exercised by the unit suite (they need an LLM / live sites),
so a deleted or mis-wired hook would go unnoticed.

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
