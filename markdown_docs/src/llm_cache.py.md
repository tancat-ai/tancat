---
purpose: >
  LLM-call cache for Phase 6h: disk-backed, TTL'd cache of expensive deterministic LLM calls
  (resolution ranking, skeleton retries) so re-runs of the same prompt are free. Key = sha256(
  provider, model, temperature, enable_thinking, system_prompt, prompt) — a hit is only served
  when every input matches. Local-only, never changes behavior (byte-identical text at temp 0).
lines: ~265
created: "2026-09-05"
---

# `src/llm_cache.py`

## High-Level Purpose

Caches expensive, deterministic LLM calls on disk so repeated resolutions of the same prompt
cost nothing. Same pattern as the Phase 7 package cache — one key function, no new infra.
Constraints (air-gap, spec §7.3): local only (`evidence/cache` by default, `AITEST_LLM_CACHE_DIR`
override), **never changes behavior** (a hit returns byte-identical text to a fresh call at
temp 0), bounded staleness (TTL, default 1h), opt-out (`AITEST_LLM_CACHE=0`).

## Public API

### `llm_cache_key(*, provider, model, prompt, system_prompt="", temperature=None, enable_thinking=None, version=1) -> str`
The one key function: sha256 over the exact inputs that determine output, plus a schema-version
salt. A cached response can never leak across models, temperatures, prompts, or thinking modes.

### `LLMCache(cache_dir=None, *, ttl_s=None, enabled=None)`
Disk-backed, TTL'd cache of completion texts, keyed by call inputs. Thread-safe and
multi-process-safe within a write (atomic tmp+replace).
- `get(key) -> str | None` — miss / corrupt entry / expired → `None` (expired entries swept).
- `put(key, value)` — atomic write (tmp + `os.replace`); lazy sweep when the dir exceeds
  `_MAX_FILES_BEFORE_SWEEP`.
- `clear()` — delete all entries (tests / troubleshooting).
- `stats()` — `{files, bytes}` for the Usage/benchmark surfaces.
- Defaults: `AITEST_LLM_CACHE_TTL_S` (3600), `AITEST_LLM_CACHE` (`"1"` = enabled; `"0"` disables
  reads+writes).

### `CachingGenerator(generator, cache=None)`
Async wrapper implementing the ranker's `AsyncGeneratorLike` protocol: on `generate(...)`,
builds the key (identity pulled from the wrapped generator's `provider_name`/`model` when
present), serves a hit, or calls through and stores the result (non-empty only).

## How It Works (internals)

### `LLMCache.get(key)` — the read path
- `_path_for(key)` → `<cache_dir>/<key>.json`; a missing file or wrong `schema` is a miss.
- Expired entries (`expires_at < now`) are deleted (`_delete`) and reported as a miss.

### `LLMCache.put(key, value)` — the write path
- mkdir the dir, build the entry `{schema, key, created_at, expires_at, value}`, write a `.tmp`
  then `os.replace` (atomic — a concurrent process can never observe a half-written entry).
- `_maybe_sweep()` — when the dir holds ≥ `_MAX_FILES_BEFORE_SWEEP` (500) files, delete every
  expired entry (best-effort; malformed files are removed too).

### `CachingGenerator._identity()` — key inputs from the wrapped generator
Reads `provider_name` / `model` off the generator (LLMClient exposes both); falls back to
`AITEST_LLM_MODEL` / `OLLAMA_MODEL` env when absent (stubs without model identity are never
wrapped — the ranker only wraps generators that expose `.model`).

### Internal utilities
- `default_cache_dir()` — `AITEST_LLM_CACHE_DIR` → `get_storage().evidence_dir() / "cache"`
  (gitignored output dir, naturally per-workspace via AI-029).
- `_temperature_or_none()` — `llm_temperature_default()` (what a caller not passing temperature
  tells the key).