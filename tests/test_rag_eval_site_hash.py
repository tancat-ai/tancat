"""The resolver eval must resolve under the golden store's site identity (t-0490).

The eval called ``PlaceholderScorer.compute_element_score`` without a site_hash,
so ``_golden_pattern_bonus`` skipped every pattern (all carry a non-empty
site_hash) and the RAG on/off A/B measured the same number both ways. These
tests pin the fix: the loader computes the seeded identity, and the resolver
threads it to the scorer.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

_EVAL_DIR = Path(__file__).resolve().parent.parent / "scripts" / "eval"
sys.path.insert(0, str(_EVAL_DIR))

import eval_resolver  # noqa: E402


def test_golden_placeholders_carry_the_seeded_site_hash() -> None:
    """Every placeholder carries the identity its goldens were seeded under."""
    from src.rag_bundled import golden_site_hash

    placeholders = eval_resolver._load_golden_placeholders()  # noqa: SLF001
    assert placeholders
    for ph in placeholders:
        assert ph["site_hash"], f"{ph['site']} placeholder has no site_hash"

    saucedemo = next(ph for ph in placeholders if ph["site"] == "saucedemo")
    assert saucedemo["site_hash"] == golden_site_hash("saucedemo", "https://www.saucedemo.com")


def test_resolver_threads_the_site_hash_into_the_scorer(monkeypatch: pytest.MonkeyPatch) -> None:
    """_resolve_placeholder must pass site_hash to compute_element_score."""
    from src.placeholder_scorers import PlaceholderScorer

    captured: dict[str, Any] = {}
    real = PlaceholderScorer.compute_element_score

    def spy(*args: Any, **kwargs: Any) -> Any:
        captured.update(kwargs)
        return real(*args, **kwargs)

    monkeypatch.setattr(PlaceholderScorer, "compute_element_score", staticmethod(spy))

    class _Matcher:
        def pass0_exact_text_match(self, *args: Any, **kwargs: Any) -> None:
            return None

        def pass1_text_match(self, *args: Any, **kwargs: Any) -> None:
            return None

    element = {"selector": "#add-cart", "text": "Add to cart", "role": "button", "tag": "button"}
    resolved = eval_resolver._resolve_placeholder(  # noqa: SLF001
        action="CLICK",
        description="Add to cart",
        pages_data={"https://www.saucedemo.com/inventory.html": [element]},
        expected_page="",
        element_matcher=_Matcher(),
        site_hash="site-a",
    )

    assert resolved is not None
    assert captured.get("site_hash") == "site-a"
