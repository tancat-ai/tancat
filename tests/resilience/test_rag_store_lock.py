"""Phase 6c — RAG store cross-process write lock.

Offline, CI-able tests for :mod:`src.rag_store_lock` and its wiring into
``MilvusLiteBackend``.

The concurrency risk: Milvus Lite is single-writer. The team shape (*N*
Streamlit sessions + a UI generation + a CI ``learn: true`` run sharing one
workspace) opens several concurrent ``MilvusClient`` processes on one ``.db``.
Without the lock, concurrent writes race on ``manifest.json.tmp`` (a known
milvus-lite Windows race) and corrupt the store.

The lock is **exclusive across processes** and **re-entrant within a process**.
These tests verify both properties:
- re-entrancy / hold-count / path-keying — hermetic, no real Milvus needed;
- cross-process exclusion — ``multiprocessing`` (real separate OS processes),
  using a tiny lock-hold worker; no Milvus, no embedder, no network.
"""

from __future__ import annotations

import multiprocessing as mp
import time
from pathlib import Path

import pytest


def test_lock_path_is_stable_sibling() -> None:
    """The lock file is a deterministic sibling of the store path, regardless
    of whether the store is a .db file or a directory."""
    from src.rag_store_lock import lock_path_for

    assert lock_path_for("/tmp/rag_store.db") == Path("/tmp/rag_store.db.lock")
    assert lock_path_for("/tmp/milvus_dir") == Path("/tmp/milvus_dir.lock")


def test_lock_is_reentrant_within_process(tmp_path: Path) -> None:
    """Nested acquires from the same process are cheap no-ops (no self-deadlock)."""
    from src.rag_store_lock import store_lock

    target = tmp_path / "rag_store.db"
    with store_lock(target, timeout=1.0) as outer:
        assert outer.is_held
        # Nested acquisition must not deadlock — the OS lock is already ours.
        with store_lock(target, timeout=0.5) as inner:
            assert inner.is_held
            assert inner.lock_file == outer.lock_file
    # After the outermost release the lock must be free again.
    with store_lock(target, timeout=0.5):
        pass


def test_lock_is_shared_per_path_within_process(tmp_path: Path) -> None:
    """Two writers in the same process for the same rag_path share one OS lock
    (re-entrant), and a different path gets a different lock file."""
    from src.rag_store_lock import store_lock

    a = tmp_path / "a.db"
    b = tmp_path / "b.db"
    with store_lock(a):
        with store_lock(a):  # same path → re-entrant
            pass
        with store_lock(b):  # different path → independent lock file
            pass
    # Distinct lock files, so a writer on `a` never blocks a writer on `b`.
    with store_lock(a):
        with store_lock(b):
            pass


def _hold_lock(path: str, hold_seconds: float) -> None:
    """Worker: acquire the RAG write lock and hold it for *hold_seconds*."""
    from src.rag_store_lock import store_lock

    with store_lock(path, timeout=1.0):
        time.sleep(hold_seconds)


@pytest.mark.slow
def test_cross_process_exclusion(tmp_path: Path) -> None:
    """Two separate OS processes cannot hold the lock at once — the second must
    time out while the first holds it. This is the 6c guarantee: concurrent
    Milvus writers are serialised, so the store can't be raced into corruption."""
    target = str(tmp_path / "rag_store.db")
    ctx = mp.get_context("spawn")

    holder = ctx.Process(target=_hold_lock, args=(target, 1.5))
    holder.start()
    # Give the holder process time to boot and grab the lock.
    time.sleep(0.8)

    from src.rag_store_lock import StoreLockError, store_lock

    t0 = time.monotonic()
    try:
        # A different process trying to acquire must fail within our short
        # timeout (the holder is still holding for ~1.5s).
        with store_lock(target, timeout=0.6):
            raise AssertionError("lock was acquired but another process holds it")
    except StoreLockError:
        pass
    else:
        holder.join(timeout=5)
        raise AssertionError("expected StoreLockError under cross-process contention")
    elapsed = time.monotonic() - t0
    assert 0.4 < elapsed < 1.4, f"timeout elapsed {elapsed:.2f}s (expected ~0.6s)"

    holder.join(timeout=5)
    assert holder.exitcode == 0


@pytest.mark.slow
def test_lock_is_reacquirable_after_release(tmp_path: Path) -> None:
    """Once the holder process exits and releases, a new acquire succeeds."""
    target = str(tmp_path / "rag_store.db")
    ctx = mp.get_context("spawn")

    holder = ctx.Process(target=_hold_lock, args=(target, 1.0))
    holder.start()
    time.sleep(0.4)

    from src.rag_store_lock import StoreLockError, store_lock

    try:
        with store_lock(target, timeout=0.4):
            raise AssertionError("should be blocked while holder is alive")
    except StoreLockError:
        pass

    # Wait for the holder to finish and release; the lock must become free.
    holder.join(timeout=5)
    assert holder.exitcode == 0
    with store_lock(target, timeout=2.0):
        pass  # success — lock is free again


def test_wired_into_milvus_backend_upsert(monkeypatch: pytest.MonkeyPatch) -> None:
    """The RAG write lock is actually taken by MilvusLiteBackend.upsert (the
    single chokepoint for add_patterns / add_docs / upsert_pattern insert).

    Uses a fake client + real store path — no Milvus, no embedder, offline.
    """
    from src import rag_store_lock
    from src.rag_store import KnowledgeEntry, MilvusLiteBackend

    calls: list[bool] = []

    real_acquire = rag_store_lock.StoreLock.acquire
    real_release = rag_store_lock.StoreLock.release

    def tracking_acquire(self: rag_store_lock.StoreLock) -> None:
        real_acquire(self)
        calls.append(True)

    def tracking_release(self: rag_store_lock.StoreLock) -> None:
        real_release(self)

    monkeypatch.setattr(rag_store_lock.StoreLock, "acquire", tracking_acquire)
    monkeypatch.setattr(rag_store_lock.StoreLock, "release", tracking_release)

    # Isolate the lock registry to a fresh path so the test is hermetic.
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        db_path = str(Path(td) / "rag_store.db")
        backend = MilvusLiteBackend(db_path, dimension=8)
        fake_client = _FakeMilvusClient()
        backend._client = fake_client  # bypass lazy MilvusClient open

        inserted = backend.upsert([KnowledgeEntry(vector=[0.0] * 8, text="t", metadata={"entry_type": "doc"})])

    assert inserted == 1
    # The insert ran while holding the lock (acquire called for this path).
    assert len(calls) >= 1
    # The fake client must have received exactly one insert.
    assert fake_client.insert_calls == 1


class _FakeMilvusClient:
    """Minimal MilvusClient stand-in: records inserts, reports an empty store."""

    def __init__(self) -> None:
        self.insert_calls = 0

    def has_collection(self, name: str) -> bool:
        return True

    def insert(self, name: str, data: list) -> dict:
        self.insert_calls += 1
        return {"insert_count": len(data)}
