"""Cache-key tests (Phase 7b, spec §7).

Key = sha256(story + url + model + provider + prompt-fingerprint). The
fingerprint constant is the regeneration-sensitive part (AI-042-F4) — bumping
it must change every key.
"""

from __future__ import annotations

import subprocess
import sys

import action.cache_key as cache_key
from action.cache_key import compute_cache_key


def test_key_is_stable_for_same_inputs() -> None:
    a = compute_cache_key("story A", "https://staging.example.com", "gpt-4o", "openai")
    b = compute_cache_key("story A", "https://staging.example.com", "gpt-4o", "openai")
    assert a == b
    assert len(a) == 64


def test_key_changes_with_any_input() -> None:
    base = compute_cache_key("story", "url", "model", "provider")
    assert compute_cache_key("story2", "url", "model", "provider") != base
    assert compute_cache_key("story", "url2", "model", "provider") != base
    assert compute_cache_key("story", "url", "model2", "provider") != base
    assert compute_cache_key("story", "url", "model", "provider2") != base


def test_key_ignores_whitespace_padding() -> None:
    a = compute_cache_key("  story  ", " url ", " model ", " provider ")
    b = compute_cache_key("story", "url", "model", "provider")
    assert a == b


def test_prompt_fingerprint_bump_invalidates_keys() -> None:
    """Bumping PROMPT_FINGERPRINT must invalidate every cached package."""
    import hashlib

    material = "|".join(["story", "url", "model", "provider", cache_key.PROMPT_FINGERPRINT])
    assert (
        compute_cache_key("story", "url", "model", "provider") == hashlib.sha256(material.encode("utf-8")).hexdigest()
    )
    # A future bump of the constant yields a different key:
    alt = "|".join(["story", "url", "model", "provider", "phase7-7b-v2"])
    assert hashlib.sha256(alt.encode("utf-8")).hexdigest() != compute_cache_key("story", "url", "model", "provider")


def test_cli_prints_only_the_key() -> None:
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "action.cache_key",
            "--story",
            "story",
            "--url",
            "url",
            "--model",
            "model",
            "--provider",
            "provider",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    out = proc.stdout.strip().splitlines()
    assert len(out) == 1
    assert out[0] == compute_cache_key("story", "url", "model", "provider")
