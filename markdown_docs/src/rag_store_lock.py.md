---
purpose: >
  Cross-process write lock for the Milvus Lite RAG store (Phase 6c, team-deployment concurrency).
  Milvus Lite is single-writer; the team shape (N Streamlit sessions + UI generation + CI
  learn:true run) opens several concurrent Milvus clients on one .db. This module serialises
  RAG-store writes behind one OS advisory lock keyed on the store path. Stdlib only (msvcrt /
  fcntl), re-entrant within a process, exclusive across processes, readers unguarded.
lines: ~256
created: "2026-09-05"
---

# `src/rag_store_lock.py`

## High-Level Purpose

Milvus Lite is **single-writer**: two processes opening `MilvusClient` on the same db and both
writing corrupt it / contend on `manifest.json.tmp` (a known milvus-lite Windows race — the
`upsert` path deliberately omits `flush()` for this reason). The RAG store is instantiated per
call (orchestrator generation, the generated-test conftest auto-learn teardown, a CI
`learn: true` run), so the team shape opens several concurrent Milvus clients on one db.

This module serialises **cross-process RAG-store writes** behind a single OS advisory lock keyed
on the store path. `SQLitePersistence` needs no such guard (WAL + `busy_timeout`) and
`FlowMemoryStore.save` is already atomic (`tmp + os.replace`) — only Milvus needs it.

## Public API

### `store_lock(rag_path, timeout=DEFAULT_LOCK_TIMEOUT_S) -> contextmanager[StoreLock]`
The seam 6c wraps every Milvus-store **write** with. Acquires the per-path lock, yields, releases.
```python
with store_lock(rag_path):
    backend.upsert(entries)
```

### `class StoreLock(rag_path, timeout=DEFAULT_LOCK_TIMEOUT_S)`
Re-entrant (per-process), cross-process advisory write lock.
- `acquire()` — first caller opens the OS lock (blocking up to `timeout`); nested acquisitions
  from any thread of the same process are cheap hold-count increments.
- `release()` — decrement the hold count; the OS lock drops when it returns to zero.
- `lock_file` / `rag_path` / `is_held` — properties for diagnostics/tests.
- The OS lock is acquired once per process and held until the last hold drops, so in-process
  writers never contend with their own lock; only a different process is excluded.

### `StoreLockError(RuntimeError)`
Raised when the lock cannot be acquired within the timeout — another process is writing.

### Wiring (in `src/rag_store.py`)
`MilvusLiteBackend.upsert`, `delete_learned`, and `increment_learned_hit` each wrap their client
call in `with store_lock(self._db_path):`. These are the three write chokepoints — they cover
`add_patterns` / `add_docs` / `upsert_pattern` inserts, learned-hit bumps, and learned deletion.
Reads (`search`, `query`) are intentionally unguarded.

## How It Works (internals)

### `store_lock(...)` / `_Registry`
A process-local registry maps `rag_path` → one `StoreLock` instance, shared across all callers
and threads — so two write paths in the same process for the same store share ONE OS lock
(re-entrant) instead of deadlocking on themselves.

### `class _OsLock(lock_file)` — the platform advisory lock
- `acquire(timeout)` — opens the lock file `a+` (never unlinked: unlinking would let a second
  process open a different inode and defeat the lock), then polls:
  - Windows: `msvcrt.locking(fd, LK_NBLCK, 1)` — one byte region at offset 0, LOCK_NOWAIT, with
    a 50ms sleep loop against the deadline.
  - POSIX: `fcntl.lockf(fh, LOCK_EX | LOCK_NB, 1)` with the same poll loop.
  - On timeout → `StoreLockError` with the store path and a clear "another process is writing"
    message; the fd is closed and never leaked.
- `release()` — `LK_UNLCK` / `LOCK_UN`, then close; no-ops when not held.

### `StoreLock` hold accounting
`_mu` (threading.Lock) guards `_holds` + `_os_lock`. `acquire` creates the `_OsLock` only on the
first hold; `release` drops the OS lock when `_holds` reaches 0. `atexit` releases best-effort
so a process exit never strands the lock file in a held state (the file remains but the OS
advisory lock dies with the process).

### Internal utilities
- `lock_path_for(rag_path)` — `<rag_path>.lock` sibling, whether the store is a `.db` file or a
  Milvus-Lite directory.
- `_REGISTRY` — the module-level `_Registry` backing `store_lock`.