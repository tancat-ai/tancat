"""The RAG eval must be isolated: distinct mock identities + its own store (t-0515).

Two launch-isolation defects (scout t-0498):

1. ``ambiguous_mock`` and ``lv_insurance`` both hashed to ``localhost:8781``
   because ``_MOCK_SITE_IDENTITY`` omitted ``ambiguous_mock`` — their golden
   patterns shared one identity.
2. ``eval_resolver`` read the production RAG store and generated-test learning
   wrote to it, so an eval run could pollute production learning.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

import pytest

_EVAL_DIR = Path(__file__).resolve().parent.parent / "scripts" / "eval"
sys.path.insert(0, str(_EVAL_DIR))

import eval_resolver  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_storage() -> Any:
    """Reset the storage singleton before *and* after every test."""
    from src.storage import reset_storage

    reset_storage()
    yield
    reset_storage()


def test_mock_datasets_have_distinct_site_identities() -> None:
    """ambiguous_mock must not share lv_insurance's golden identity."""
    from src.rag_bundled import golden_site_hash

    lv = golden_site_hash("lv_insurance", "http://localhost:8781/generated_tests/mock_insurance_site.html")
    ambiguous = golden_site_hash("ambiguous_mock", "http://localhost:8781/index.html")
    assert lv, "lv_insurance has no identity"
    assert ambiguous, "ambiguous_mock has no identity"
    assert lv != ambiguous, "the two mock datasets still share one identity"


def test_ambiguous_mock_port_is_not_shared_with_any_other_mock_or_test() -> None:
    """t-0524: the owner wants nothing sharing a port number.

    ambiguous_mock must not reuse the learning-loop e2e mock's 8784, the
    documented local mock ports (8785/8786), or the other bundled mock ports.
    """
    from src.rag_bundled import golden_site_hash
    from src.rag_learn import site_hash

    ambiguous = golden_site_hash("ambiguous_mock", "http://localhost:8781/index.html")
    assert ambiguous == site_hash("localhost:8787")
    taken = {
        "lv_insurance": site_hash("localhost:8781"),
        "banking_mock": site_hash("localhost:8782"),
        "ecommerce_mock": site_hash("localhost:8783"),
        "learning-loop e2e mock": site_hash("localhost:8784"),
        "documented local ecommerce": site_hash("localhost:8785"),
        "documented local banking": site_hash("localhost:8786"),
    }
    assert ambiguous not in taken.values(), "ambiguous_mock reuses another mock's port"


def test_eval_uses_its_own_store_and_leaves_production_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The eval store is its own path; the production store is not written."""
    from src import storage as storage_mod
    from src.storage import LocalStorageBackend

    # A stand-in production store, so the test never touches the real one.
    production = LocalStorageBackend(root=tmp_path, workspace="default").rag_path()
    production.parent.mkdir(parents=True, exist_ok=True)
    sentinel = b"production-rag-store"
    production.write_bytes(sentinel)

    # Empty == unset, but tracked by monkeypatch so the env is restored after.
    monkeypatch.setenv("AITEST_STORAGE_ROOT", "")
    monkeypatch.setenv("AITEST_WORKSPACE", "")
    storage_mod.reset_storage()

    eval_rag = eval_resolver.isolate_eval_store(root=tmp_path / "eval_store")

    assert eval_rag != production
    assert eval_rag == tmp_path / "eval_store" / "evidence" / "rag_store.db"
    assert production.read_bytes() == sentinel, "production store was touched"
    # The singleton now resolves the eval store, so generated-test learning
    # (build_default_store -> get_storage().rag_path()) writes there too.
    assert storage_mod.get_storage().rag_path() == eval_rag


def test_static_eval_isolates_the_store_before_reading_it(monkeypatch: pytest.MonkeyPatch) -> None:
    """_cmd_static must call isolate_eval_store before any store is built."""
    calls: list[str] = []

    def _record(*_args: Any, **_kwargs: Any) -> Path:
        calls.append("isolated")
        return Path("unused")

    async def _fake_run(_pages: Any, _rag_retriever: Any = None) -> dict[str, Any]:
        return {"total_placeholders": 0, "correct": 0, "accuracy_pct": 0.0, "per_site": {}}

    monkeypatch.setattr(eval_resolver, "load_scraped_pages", lambda: {"u": [{"selector": "#x"}]})
    monkeypatch.setattr(eval_resolver, "rag_enabled_for_eval", lambda: False)
    monkeypatch.setattr(eval_resolver, "isolate_eval_store", _record)
    monkeypatch.setattr(eval_resolver, "run_resolver_eval", _fake_run)

    assert asyncio.run(eval_resolver._cmd_static()) == 0  # noqa: SLF001
    assert calls == ["isolated"]
