"""The eval's RAG gate must match the product's shared config (t-0488).

The product defaults RAG ON: a missing ``RAG_ENABLED`` means enabled, and only
``RAG_ENABLED=0`` opts out (``src.orchestrator.rag_enabled_by_config``). The
resolver eval used its own ``os.getenv("RAG_ENABLED", "").strip() == "1"`` gate,
so a default run was both labelled and run RAG OFF. These tests pin the eval
gate to the product's gate.

Before the fix the unset case fails (old gate returns False, product True);
after it, all cases pass.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_EVAL_DIR = Path(__file__).resolve().parent.parent / "scripts" / "eval"
sys.path.insert(0, str(_EVAL_DIR))

import eval_resolver  # noqa: E402


@pytest.mark.parametrize(
    ("env_value", "expected"),
    [
        (None, True),  # unset == the product default == RAG on
        ("", True),
        ("0", False),  # the only opt-out
        ("1", True),
    ],
)
def test_eval_rag_gate_matches_the_product(
    monkeypatch: pytest.MonkeyPatch, env_value: str | None, expected: bool
) -> None:
    if env_value is None:
        monkeypatch.delenv("RAG_ENABLED", raising=False)
    else:
        monkeypatch.setenv("RAG_ENABLED", env_value)

    from src.orchestrator import rag_enabled_by_config

    assert rag_enabled_by_config() is expected, "the product contract changed"
    assert eval_resolver.rag_enabled_for_eval() is expected
    assert eval_resolver.rag_enabled_for_eval() is rag_enabled_by_config()
