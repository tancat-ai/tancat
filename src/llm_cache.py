"""LLM-call cache (Phase 6h, spec §5.10).

Caches expensive, deterministic LLM calls (resolution ranking, skeleton
retries) on disk so re-runs of the same prompt are free. Same pattern as the
Phase 7 package cache — one key function, no new infra.

Key = sha256(provider, model, temperature, enable_thinking, system_prompt,
prompt) — the exact inputs that determine output. A hit is only returned when
every input matches, so a cached response can never be served for a different
model, temperature, or prompt.

Design constraints (air-gap / no-egress, spec §7.3):
- **Local only** — the cache lives in the workspace (``evidence/cache`` by
  default, ``AITEST_LLM_CACHE_DIR`` override). No network.
- **Never changes behavior** — a hit returns byte-identical text to a fresh
  call at temp 0; the cache only removes work.
- **Bounded staleness** — each entry expires after ``AITEST_LLM_CACHE_TTL_S``
  (default 3600s). Expired entries are ignored on read and swept on write.
- **Opt-out** — ``AITEST_LLM_CACHE=0`` disables reads and writes.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

__all__ = ["LLMCache", "CachingGenerator", "llm_cache_key", "DEFAULT_CACHE_TTL_S"]

DEFAULT_CACHE_TTL_S = 3600  # 1h — bounds cross-run staleness (model-file swaps)
_SCHEMA_VERSION = 1
_MAX_FILES_BEFORE_SWEEP = 500


def llm_cache_key(
    *,
    provider: str,
    model: str,
    prompt: str,
    system_prompt: str = "",
    temperature: float | None = None,
    enable_thinking: bool | None = None,
    version: int = _SCHEMA_VERSION,
) -> str:
    """Return the stable cache key for one LLM call's inputs."""
    payload = "\x00".join(
        [
            str(version),
            provider or "",
            model or "",
            str(temperature) if temperature is not None else "",
            "none" if enable_thinking is None else ("1" if enable_thinking else "0"),
            system_prompt or "",
            prompt or "",
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def default_cache_dir() -> Path:
    """Workspace cache dir: ``AITEST_LLM_CACHE_DIR`` → ``<storage>/evidence/cache``.

    ``evidence/`` is a gitignored output dir, so the cache never dirties the
    repo and is naturally per-workspace (AI-029).
    """
    env = os.environ.get("AITEST_LLM_CACHE_DIR", "").strip()
    if env:
        return Path(env)
    try:
        from src.storage import get_storage

        return get_storage().evidence_dir() / "cache"
    except Exception:  # pragma: no cover - fallback
        return Path("evidence/cache")


class LLMCache:
    """Disk-backed, TTL'd cache of LLM completion texts, keyed by call inputs.

    Thread-safe and multi-process-safe within a write (atomic tmp+replace). A
    cross-process race would at worst write the same value twice — harmless.
    """

    def __init__(
        self,
        cache_dir: str | Path | None = None,
        *,
        ttl_s: int | None = None,
        enabled: bool | None = None,
    ) -> None:
        self.dir = Path(cache_dir) if cache_dir is not None else default_cache_dir()
        self.ttl_s = ttl_s if ttl_s is not None else int(os.environ.get("AITEST_LLM_CACHE_TTL_S", DEFAULT_CACHE_TTL_S))
        # Enabled by default; AITEST_LLM_CACHE=0 disables reads+writes.
        self.enabled = True if enabled is None else enabled
        if enabled is None:
            self.enabled = os.environ.get("AITEST_LLM_CACHE", "1") != "0"
        self._mu = threading.Lock()

    # -- core ---------------------------------------------------------------
    def get(self, key: str) -> str | None:
        """Return the cached text for *key*, or None on miss/expired."""
        if not self.enabled:
            return None
        path = self._path_for(key)
        try:
            if not path.exists():
                return None
            entry = json.loads(path.read_text(encoding="utf-8"))
            if entry.get("schema") != _SCHEMA_VERSION:
                return None
            expires = float(entry.get("expires_at", 0))
            if expires and time.time() > expires:
                self._delete(path)
                return None
            return entry.get("value")
        except OSError, ValueError, TypeError:  # pragma: no cover - corrupt entry
            return None

    def put(self, key: str, value: str) -> None:
        """Store *value* under *key* with a TTL; sweep expired on growth."""
        if not self.enabled:
            return
        try:
            self.dir.mkdir(parents=True, exist_ok=True)
        except OSError:  # pragma: no cover - read-only FS
            return
        now = time.time()
        entry = {
            "schema": _SCHEMA_VERSION,
            "key": key,
            "created_at": now,
            "expires_at": now + self.ttl_s,
            "value": value,
        }
        path = self._path_for(key)
        tmp = path.with_suffix(path.suffix + ".tmp")
        with self._mu:
            try:
                tmp.write_text(json.dumps(entry), encoding="utf-8")
                os.replace(tmp, path)
            except OSError as exc:  # pragma: no cover - defensive
                logger.debug("LLM cache write failed: %s", exc)
        self._maybe_sweep()

    def clear(self) -> None:
        """Delete all cache entries (for tests / troubleshooting)."""
        with self._mu:
            if not self.dir.exists():
                return
            for p in self.dir.glob("*.json"):
                self._delete(p)

    def stats(self) -> dict[str, Any]:
        """Entry count + total bytes (for the Usage/benchmark surfaces)."""
        if not self.dir.exists():
            return {"files": 0, "bytes": 0}
        files = list(self.dir.glob("*.json"))
        total = sum(p.stat().st_size for p in files)
        return {"files": len(files), "bytes": total}

    # -- internals ------------------------------------------------------------
    def _path_for(self, key: str) -> Path:
        return self.dir / f"{key}.json"

    @staticmethod
    def _delete(path: Path) -> None:
        try:
            path.unlink()
        except OSError:  # pragma: no cover - race
            pass

    def _maybe_sweep(self) -> None:
        if not self.dir.exists():
            return
        try:
            files = list(self.dir.glob("*.json"))
        except OSError:  # pragma: no cover
            return
        if len(files) < _MAX_FILES_BEFORE_SWEEP:
            return
        now = time.time()
        removed = 0
        for p in files:
            try:
                entry = json.loads(p.read_text(encoding="utf-8"))
                if float(entry.get("expires_at", 0)) < now:
                    self._delete(p)
                    removed += 1
            except OSError, ValueError:  # pragma: no cover
                self._delete(p)
                removed += 1
        if removed:
            logger.debug("LLM cache swept %d expired entries", removed)


# ---------------------------------------------------------------------------
# Async wrapper for the ranker's AsyncGeneratorLike protocol
# ---------------------------------------------------------------------------


class CachingGenerator:
    """Wrap any async ``generate`` with the disk cache (ranker integration).

    Implements the same protocol as LLMClient for ``generate(...)``. The cache
    key is built from the wrapped generator's identity (``.provider_name`` /
    ``.model`` when present) plus the call inputs.
    """

    def __init__(self, generator: Any, cache: LLMCache | None = None) -> None:
        self.generator = generator
        self.cache = cache if cache is not None else LLMCache()

    def _identity(self) -> tuple[str, str]:
        provider = getattr(self.generator, "provider_name", "") or ""
        model = getattr(self.generator, "model", "") or ""
        if not model:
            model = os.environ.get("AITEST_LLM_MODEL", "") or os.environ.get("OLLAMA_MODEL", "")
        return provider, model

    async def generate(
        self,
        prompt: str,
        timeout: int = 300,
        system_prompt: str | None = None,
        *,
        enable_thinking: bool | None = None,
    ) -> str:
        provider, model = self._identity()
        key = llm_cache_key(
            provider=provider,
            model=model,
            prompt=prompt,
            system_prompt=system_prompt or "",
            temperature=_temperature_or_none(),
            enable_thinking=enable_thinking,
        )
        hit = self.cache.get(key)
        if hit is not None:
            return hit
        raw = await self.generator.generate(
            prompt,
            timeout=timeout,
            system_prompt=system_prompt,
            enable_thinking=enable_thinking,
        )
        if raw:
            self.cache.put(key, raw)
        return raw


def _temperature_or_none() -> float | None:
    """The pipeline default temperature (what a caller not passing temp gets)."""
    try:
        from src.llm_client import llm_temperature_default

        return llm_temperature_default()
    except Exception:  # pragma: no cover - import-time guard
        return None
