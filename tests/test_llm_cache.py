"""Phase 6h — LLM-call cache (src/llm_cache.py) + ranker integration.

Hermetic, no network: disk cache roundtrip, TTL, clear, opt-out env, key
stability/uniqueness, CachingGenerator hit/miss, and a ranker-level test that a
second identical resolve uses the cache (no second generator call).
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pytest

from src.llm_cache import CachingGenerator, LLMCache, default_cache_dir, llm_cache_key

# -- key ----------------------------------------------------------------------


def test_key_stable_and_unique(tmp_path: Path) -> None:
    k1 = llm_cache_key(provider="lm-studio", model="m", prompt="hello")
    k2 = llm_cache_key(provider="lm-studio", model="m", prompt="hello")
    assert k1 == k2
    assert len(k1) == 64  # sha256 hex
    # Different model / temperature / thinking → different key.
    assert k1 != llm_cache_key(provider="lm-studio", model="other", prompt="hello")
    assert k1 != llm_cache_key(provider="lm-studio", model="m", prompt="hello", temperature=0.7)
    assert k1 != llm_cache_key(provider="lm-studio", model="m", prompt="hello", enable_thinking=True)
    assert k1 != llm_cache_key(provider="ollama", model="m", prompt="hello")
    assert k1 != llm_cache_key(provider="lm-studio", model="m", prompt="hello", system_prompt="sys")


# -- disk cache ---------------------------------------------------------------


def test_get_put_roundtrip(tmp_path: Path) -> None:
    cache = LLMCache(cache_dir=tmp_path, ttl_s=60)
    key = "abc123"
    assert cache.get(key) is None
    cache.put(key, "pong")
    assert cache.get(key) == "pong"
    assert (tmp_path / f"{key}.json").exists()


def test_ttl_expiry(tmp_path: Path) -> None:
    cache = LLMCache(cache_dir=tmp_path, ttl_s=1)
    cache.put("k", "v")
    assert cache.get("k") == "v"
    time.sleep(1.1)
    assert cache.get("k") is None  # expired → miss, entry swept


def test_clear(tmp_path: Path) -> None:
    cache = LLMCache(cache_dir=tmp_path, ttl_s=60)
    cache.put("a", "1")
    cache.put("b", "2")
    cache.clear()
    assert cache.get("a") is None
    assert cache.get("b") is None
    assert cache.stats()["files"] == 0


def test_disabled_via_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("AITEST_LLM_CACHE", "0")
    cache = LLMCache(cache_dir=tmp_path, ttl_s=60)
    assert cache.enabled is False
    cache.put("k", "v")  # no write
    assert cache.get("k") is None
    assert not (tmp_path / "k.json").exists()


def test_corrupt_entry_is_miss(tmp_path: Path) -> None:
    cache = LLMCache(cache_dir=tmp_path, ttl_s=60)
    cache.put("k", "v")
    (tmp_path / "k.json").write_text("{not json", encoding="utf-8")
    assert cache.get("k") is None


def test_default_dir_under_evidence() -> None:
    d = default_cache_dir()
    assert "evidence" in d.parts or "cache" in d.parts


# -- CachingGenerator ---------------------------------------------------------


class _FakeGen:
    def __init__(self) -> None:
        self.calls = 0
        self.provider_name = "lm-studio"
        self.model = "qwen-test"

    async def generate(
        self, prompt: str, timeout: int = 300, system_prompt: str | None = None, *, enable_thinking: bool | None = None
    ) -> str:
        self.calls += 1
        return '{"selected_index": 1}'


@pytest.mark.asyncio
async def test_caching_generator_hit_and_miss(tmp_path: Path) -> None:
    gen = _FakeGen()
    cache = LLMCache(cache_dir=tmp_path, ttl_s=60)
    wrapped = CachingGenerator(gen, cache)
    first = await wrapped.generate("same prompt", system_prompt="sys")
    assert gen.calls == 1
    second = await wrapped.generate("same prompt", system_prompt="sys")
    assert gen.calls == 1  # served from cache — no second call
    assert first == second
    # Different prompt → miss → second call.
    await wrapped.generate("other prompt")
    assert gen.calls == 2


@pytest.mark.asyncio
async def test_caching_generator_bypasses_when_disabled(tmp_path: Path) -> None:
    gen = _FakeGen()
    cache = LLMCache(cache_dir=tmp_path, ttl_s=60, enabled=False)
    wrapped = CachingGenerator(gen, cache)
    await wrapped.generate("p")
    await wrapped.generate("p")
    assert gen.calls == 2


# -- ranker integration -------------------------------------------------------


@pytest.mark.asyncio
async def test_ranker_second_resolve_uses_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A second identical resolve must not call the generator again."""
    from src.semantic_candidate_ranker import SemanticCandidateRanker

    gen = _FakeGen()
    cache = LLMCache(cache_dir=tmp_path, ttl_s=60)
    ranker = SemanticCandidateRanker(generator=gen, cache=cache)
    candidates: list[dict[str, Any]] = [{"label": "A", "locator": "#a"}, {"label": "B", "locator": "#b"}]
    r1 = await ranker.choose_best_candidate(
        action="CLICK",
        description="add the fleece jacket to the cart",
        current_url="https://x.example/p",
        candidates=candidates,
    )
    assert r1 is not None
    first_calls = gen.calls
    r2 = await ranker.choose_best_candidate(
        action="CLICK",
        description="add the fleece jacket to the cart",
        current_url="https://x.example/p",
        candidates=candidates,
    )
    assert gen.calls == first_calls  # cache hit — generator untouched
    assert r1 == r2


@pytest.mark.asyncio
async def test_ranker_cache_disabled_still_calls(tmp_path: Path) -> None:
    from src.semantic_candidate_ranker import SemanticCandidateRanker

    gen = _FakeGen()
    cache = LLMCache(cache_dir=tmp_path, ttl_s=60, enabled=False)
    ranker = SemanticCandidateRanker(generator=gen, cache=cache)
    candidates: list[dict[str, Any]] = [{"label": "A", "locator": "#a"}, {"label": "B", "locator": "#b"}]
    await ranker.choose_best_candidate(
        action="CLICK", description="add to cart", current_url="https://x.example/p", candidates=candidates
    )
    await ranker.choose_best_candidate(
        action="CLICK", description="add to cart", current_url="https://x.example/p", candidates=candidates
    )
    assert gen.calls == 2


def test_benchmark_self_test_subprocess() -> None:
    """The benchmark's --self-test must run offline and produce the JSON schema."""
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "scripts/benchmark_latency.py", "--self-test", "--json", "--iterations", "2"],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=Path(__file__).resolve().parent.parent,
    )
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout.strip().splitlines()[-1])
    assert data["self_test"] is True
    assert data["skeleton_median_s"] > 0
    assert "slo_target_s" in data
