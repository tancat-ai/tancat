"""Cross-process write lock for the Milvus Lite RAG store.

Phase 6c — team-deployment concurrency.

The RAG store is backed by ``MilvusLiteBackend`` (a local ``.db`` file). Milvus
Lite is **single-writer**: two processes opening ``MilvusClient`` on the same
db and both writing corrupt it / contend on ``manifest.json.tmp`` (a known
milvus-lite race on Windows — the ``upsert`` path deliberately omits
``flush()`` for this reason). The store is already instantiated per call
(orchestrator generation, the ``generated_tests/conftest.py`` auto-learn
teardown, a CI ``learn: true`` run), so the team shape — *N* Streamlit sessions
sharing one workspace, a UI generation, a CI run — opens several concurrent
Milvus clients on one db.

This module serialises **cross-process RAG-store writes** behind a single OS
advisory lock keyed on the store path. ``SQLitePersistence`` already needs no
such guard (WAL + ``busy_timeout``) and ``FlowMemoryStore.save`` is already
atomic (``tmp + os.replace``) — only the Milvus store needs it.

Design constraints (air-gap / no-egress — AI-045):
- **Stdlib only** (``msvcrt`` on Windows, ``fcntl`` elsewhere) — no new
  dependency, no network.
- The lock is **exclusive across processes** (two separate Streamlit / CI
  processes cannot hold it at once) and **re-entrant within the owning process**
  (nested calls from any thread of the same process are cheap no-ops — the OS
  lock is acquired once, on the first acquire, and held until the last release
  drops to zero, so no in-process writer ever contends with its own lock).
- The lock file is a small sidecar (``<rag_path>.lock``); it is never deleted so
  the inode stays stable across processes.
- Readers (``search``) do **not** take the lock — reads never corrupt the store
  and must not be serialised.
"""

from __future__ import annotations

import atexit
import logging
import sys
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import TextIO

logger = logging.getLogger(__name__)

__all__ = ["StoreLock", "store_lock", "StoreLockError", "DEFAULT_LOCK_TIMEOUT_S"]

DEFAULT_LOCK_TIMEOUT_S: float = 60.0

# msvcrt locks a single 1-byte region at file offset 0 (msvcrt.locking has no
# "whole file" mode; one held byte is enough to serialise writers).
_MSVCRT_REGION_SIZE = 1


class StoreLockError(RuntimeError):
    """Raised when the RAG store write lock cannot be acquired in time."""


def lock_path_for(rag_path: str | Path) -> Path:
    """Return the lock-file path for a given RAG store path.

    Whether *rag_path* is a ``.db`` file or a Milvus-Lite directory, every
    writer in the deployment converges on the same sibling ``.lock`` file.
    """
    return Path(str(rag_path) + ".lock")


class _OsLock:
    """The OS advisory lock for one lock file (msvcrt on Windows, fcntl else)."""

    def __init__(self, lock_file: Path) -> None:
        self._lock_file = lock_file
        self._fh: TextIO | None = None

    def acquire(self, timeout: float) -> None:
        """Acquire the lock, blocking up to *timeout* seconds.

        Raises :class:`StoreLockError` if another process still holds it.
        """
        self._lock_file.parent.mkdir(parents=True, exist_ok=True)
        # Create/append — never unlink: unlinking would let a second process
        # open a *different* inode and defeat the lock.
        fh = open(self._lock_file, "a+", encoding="utf-8")
        self._fh = fh
        deadline = time.monotonic() + max(0.0, timeout)
        try:
            if sys.platform == "win32":
                import msvcrt  # type: ignore[import-not-found]

                while True:
                    try:
                        msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, _MSVCRT_REGION_SIZE)
                        return
                    except OSError:
                        if time.monotonic() >= deadline:
                            raise StoreLockError(
                                f"Could not acquire RAG store write lock at {self._lock_file} "
                                f"within {timeout:.0f}s — another process is writing the store."
                            ) from None
                        time.sleep(0.05)
            else:
                import fcntl  # type: ignore[import-not-found]

                while True:
                    try:
                        fcntl.lockf(fh, fcntl.LOCK_EX | fcntl.LOCK_NB, _MSVCRT_REGION_SIZE)
                        return
                    except OSError:
                        if time.monotonic() >= deadline:
                            raise StoreLockError(
                                f"Could not acquire RAG store write lock at {self._lock_file} "
                                f"within {timeout:.0f}s — another process is writing the store."
                            ) from None
                        time.sleep(0.05)
        except BaseException:
            try:
                fh.close()
            finally:
                self._fh = None
            raise

    def release(self) -> None:
        fh = self._fh
        if fh is None:
            return
        try:
            if sys.platform == "win32":
                import msvcrt  # type: ignore[import-not-found]

                msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, _MSVCRT_REGION_SIZE)
            else:
                import fcntl  # type: ignore[import-not-found]

                fcntl.lockf(fh, fcntl.LOCK_UN)
        except OSError:
            pass
        finally:
            try:
                fh.close()
            finally:
                self._fh = None


class StoreLock:
    """Re-entrant (per-process), cross-process advisory write lock.

    Usage::

        with store_lock(rag_path, timeout=60.0):
            backend.upsert(entries)

    The OS lock is acquired on the first ``acquire()`` in the process and held
    until the hold count returns to zero, so any thread of the same process can
    nest/interleave without contending with itself; only a *different* process
    is excluded.
    """

    def __init__(self, rag_path: str | Path, timeout: float = DEFAULT_LOCK_TIMEOUT_S) -> None:
        self._rag_path = str(rag_path)
        self._lock_file = lock_path_for(self._rag_path)
        self._timeout = timeout
        self._mu = threading.Lock()
        self._holds = 0
        self._os_lock: _OsLock | None = None
        atexit.register(self._release_at_exit)

    # -- context manager ----------------------------------------------------
    def __enter__(self) -> StoreLock:
        self.acquire()
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        self.release()

    # -- acquire / release --------------------------------------------------
    def acquire(self) -> None:
        with self._mu:
            if self._os_lock is None:
                os_lock = _OsLock(self._lock_file)
                os_lock.acquire(self._timeout)  # blocks only the *first* holder
                self._os_lock = os_lock
            self._holds += 1

    def release(self) -> None:
        with self._mu:
            if self._os_lock is None:
                return
            self._holds -= 1
            if self._holds <= 0:
                self._holds = 0
                self._os_lock.release()
                self._os_lock = None

    def _release_at_exit(self) -> None:
        try:
            with self._mu:
                if self._os_lock is not None:
                    self._os_lock.release()
                    self._os_lock = None
                    self._holds = 0
        except Exception:  # pragma: no cover - best-effort cleanup
            pass

    @property
    def lock_file(self) -> Path:
        return self._lock_file

    @property
    def rag_path(self) -> str:
        return self._rag_path

    @property
    def is_held(self) -> bool:
        with self._mu:
            return self._os_lock is not None


class _Registry:
    """Process-local cache: one :class:`StoreLock` (and thus one OS lock) per
    distinct rag_path, shared across all callers/threads in the process."""

    def __init__(self) -> None:
        self._by_path: dict[str, StoreLock] = {}
        self._mu = threading.Lock()

    def get(self, rag_path: str | Path, timeout: float) -> StoreLock:
        key = str(rag_path)
        with self._mu:
            lock = self._by_path.get(key)
            if lock is None:
                lock = StoreLock(key, timeout=timeout)
                self._by_path[key] = lock
            return lock


_REGISTRY = _Registry()


@contextmanager
def store_lock(
    rag_path: str | Path,
    timeout: float = DEFAULT_LOCK_TIMEOUT_S,
) -> Iterator[StoreLock]:
    """Acquire the cross-process write lock for the RAG store at *rag_path*.

    This is the seam Phase 6c wraps every Milvus-store **write** with. Reads
    are intentionally not serialised.
    """
    lock = _REGISTRY.get(rag_path, timeout)
    lock.acquire()
    try:
        yield lock
    finally:
        lock.release()
