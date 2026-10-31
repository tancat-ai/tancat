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

import asyncio
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


# ---------------------------------------------------------------------------
# j-0247 (t-1136): a mistyped part switch must stop a measuring run
# ---------------------------------------------------------------------------

#: Sentinel so a spy can prove the research never got as far as measuring.
_MEASURED = "the resolver eval measured a run"


def _measure_was_reached(*_args: object, **_kwargs: object) -> None:
    raise AssertionError(_MEASURED)


async def _measure_was_reached_async(*_args: object, **_kwargs: object) -> None:
    raise AssertionError(_MEASURED)


def _patch_eval_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail loudly if the run reaches the point where a number is produced."""
    monkeypatch.setattr(eval_resolver, "load_scraped_pages", _measure_was_reached)
    monkeypatch.setattr(eval_resolver, "run_resolver_eval", _measure_was_reached_async)


def test_eval_refuses_an_unknown_switch_value(monkeypatch: pytest.MonkeyPatch) -> None:
    """A typo raises out of the eval instead of becoming a "RAG off" figure.

    Before the fix the retriever build caught everything and logged
    "RAG enabled but failed to init - disabling", so the run went on to print a
    no-RAG number that looked real.
    """
    from src.rag_switches import RAGSwitchError

    monkeypatch.delenv("RAG_ENABLED", raising=False)  # product default: RAG on
    monkeypatch.setenv("RAG_GOLDEN", "yes")
    _patch_eval_path(monkeypatch)

    with pytest.raises(RAGSwitchError) as excinfo:
        asyncio.run(eval_resolver._cmd_static())

    assert "RAG_GOLDEN" in str(excinfo.value)
    assert _MEASURED not in str(excinfo.value), "a number was produced from a bad switch"


@pytest.mark.parametrize("raw", ["on", "true", "off", "2"])
def test_eval_refuses_every_unknown_value(monkeypatch: pytest.MonkeyPatch, raw: str) -> None:
    from src.rag_switches import RAGSwitchError

    monkeypatch.delenv("RAG_ENABLED", raising=False)
    monkeypatch.setenv("RAG_LEARNED", raw)
    _patch_eval_path(monkeypatch)

    with pytest.raises(RAGSwitchError):
        asyncio.run(eval_resolver._cmd_static())


def test_eval_with_rag_off_does_not_consult_the_part_switches(monkeypatch: pytest.MonkeyPatch) -> None:
    """RAG_ENABLED=0 is the global gate; the part switches are inside it.

    A stray value there must not stop a deliberately RAG-off comparison run: the
    run reaches its normal "no scraped pages" exit instead.
    """
    monkeypatch.setenv("RAG_ENABLED", "0")
    monkeypatch.setenv("RAG_GOLDEN", "yes")
    monkeypatch.setattr(eval_resolver, "load_scraped_pages", lambda: {})

    assert asyncio.run(eval_resolver._cmd_static()) == 1


def test_eval_accepts_a_valid_switch_value(monkeypatch: pytest.MonkeyPatch) -> None:
    """A switch set to a real value passes the gate and the run proceeds."""
    monkeypatch.delenv("RAG_ENABLED", raising=False)
    monkeypatch.setenv("RAG_GOLDEN", "0")
    _patch_eval_path(monkeypatch)

    with pytest.raises(AssertionError) as excinfo:
        asyncio.run(eval_resolver._cmd_static())

    # It got past the gate: the pages loader is what stopped it, not the switch.
    assert _MEASURED in str(excinfo.value)
