"""The gate must not be scored on answers it was handed (j-0244, d-0060).

The bundled RAG seed is built from the same ``eval-*.json`` ``expected_locator``
fields the gate scores, so a with-pack score can be recall rather than
resolution. The fix has two halves, and this module guards both:

1. the seed honours an exclusion, so three whole story files are never seeded;
2. the eval scores only those held-out stories when asked, so the figure it
   prints is computed from stories the pack never contained.

It also guards the record: a number written without its mode and its seed
configuration is the bug (a bare ``78.8%`` cannot say whether the tool was
given the answers), so ``scripts/eval/gate_record.py`` refuses to build a
figure without both labels, and the committed record is validated against it.
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DATASET_DIR = _REPO_ROOT / "scripts" / "eval" / "dataset"
_EVAL_DIR = _REPO_ROOT / "scripts" / "eval"
if str(_EVAL_DIR) not in sys.path:
    sys.path.insert(0, str(_EVAL_DIR))

# Imported the same way the other eval tests do (`eval_resolver`, not
# `scripts.eval.eval_resolver`): a second import path makes mypy see one source
# file under two module names and refuse to check either.
import eval_resolver  # noqa: E402
import gate_record  # noqa: E402
from eval_resolver import (  # noqa: E402
    _load_golden_placeholders,
    run_resolver_eval,
    select_story_placeholders,
)

from src.rag_bundled import (  # noqa: E402
    HELDOUT_STORY_FILES,
    build_bundled_patterns,
    ensure_bundled_seeded,
    load_golden_patterns,
)
from src.rag_store import GoldenPattern  # noqa: E402

_EXPECTED_HELDOUT_IDS = ("eval-007", "eval-008", "eval-010")


def _keys_from_files(files: tuple[str, ...]) -> list[tuple[str, str, str]]:
    """Every (action, description, expected_locator) in the named dataset files.

    A list, not a set: the same golden tuple can legitimately appear in two
    stories, and the point of these tests is the exact multiset the exclusion
    removes.
    """
    out: list[tuple[str, str, str]] = []
    for name in files:
        data = json.loads((_DATASET_DIR / name).read_text(encoding="utf-8"))
        for criterion in data.get("golden_resolutions", []):
            for ph in criterion.get("placeholders", []):
                out.append((ph.get("action", ""), ph.get("description", ""), ph.get("expected_locator", "")))
    return out


def _keys(patterns: Sequence[GoldenPattern]) -> list[tuple[str, str, str]]:
    return [(p.action, p.description, p.expected_locator) for p in patterns]


class TestSeedHonoursTheExclusion:
    """Held-out story files contribute no golden patterns."""

    def test_the_split_is_three_whole_files_that_carry_scored_placeholders(self) -> None:
        """The held-out list names whole dataset files, each with scored keys."""
        assert HELDOUT_STORY_FILES == (
            "eval-007_banking_mock.json",
            "eval-008_goto_navigation.json",
            "eval-010_ambiguous_mock.json",
        )
        for name in HELDOUT_STORY_FILES:
            assert (_DATASET_DIR / name).is_file(), name
            assert _keys_from_files((name,)), f"{name} carries no scored placeholders - substitute the next file"

    def test_excluded_files_contribute_no_patterns(self) -> None:
        all_patterns = load_golden_patterns(_DATASET_DIR)
        kept = load_golden_patterns(_DATASET_DIR, exclude=HELDOUT_STORY_FILES)

        assert len(all_patterns) == 113
        assert len(kept) == 83
        # The exact multiset that left the seed is the three held-out files' own
        # keys - no more, no less. Nothing else was removed, nothing stayed.
        dropped = Counter(_keys(all_patterns)) - Counter(_keys(kept))
        assert dropped == Counter(_keys_from_files(HELDOUT_STORY_FILES)), (
            "the seed did not drop exactly the held-out files' goldens - the gate can see its own answers"
        )

    def test_exclusion_accepts_a_stem_or_a_file_name(self) -> None:
        by_name = load_golden_patterns(_DATASET_DIR, exclude=HELDOUT_STORY_FILES)
        by_stem = load_golden_patterns(_DATASET_DIR, exclude=tuple(Path(n).stem for n in HELDOUT_STORY_FILES))
        assert _keys(by_name) == _keys(by_stem)

    def test_no_exclusion_is_the_shipped_pack(self) -> None:
        """The product path is unchanged: the default seed is the full 113."""
        assert len(build_bundled_patterns()) == 113
        assert len(build_bundled_patterns(exclude=HELDOUT_STORY_FILES)) == 83

    def test_seeding_threads_the_exclusion_to_the_store(self, tmp_path: Path) -> None:
        store = MagicMock()
        store.is_empty = True
        store.add_patterns.return_value = 83
        store.add_docs.return_value = (0, 0)

        result = ensure_bundled_seeded(
            store=store,
            marker_path=tmp_path / ".rag_bundled_seeded.json",
            exclude=HELDOUT_STORY_FILES,
        )

        assert result["status"] == "seeded"
        seeded = store.add_patterns.call_args.args[0]
        assert len(seeded) == 83
        dropped = Counter(_keys(load_golden_patterns(_DATASET_DIR))) - Counter(_keys(seeded))
        assert dropped == Counter(_keys_from_files(HELDOUT_STORY_FILES))


class TestHeldoutScoreIsComputedFromHeldoutStoriesOnly:
    """The held-out figure comes from the held-out stories and nothing else."""

    def test_selection_keeps_only_the_heldout_stories(self) -> None:
        everything = _load_golden_placeholders()
        assert len(everything) == 113

        heldout = select_story_placeholders(everything, _EXPECTED_HELDOUT_IDS)

        assert len(heldout) == 30
        assert {ph["story_id"] for ph in heldout} == set(_EXPECTED_HELDOUT_IDS)

    def test_the_heldout_placeholders_are_the_ones_that_were_not_seeded(self) -> None:
        """The two halves line up: what is scored held-out is what is not seeded.

        A tuple can legitimately appear in a held-out file and in a seeded one,
        so this compares key sets and counts, not raw membership.
        """
        everything = _load_golden_placeholders()
        heldout = select_story_placeholders(everything, _EXPECTED_HELDOUT_IDS)
        heldout_keys = {(ph["action"], ph["description"], ph["expected_locator"]) for ph in heldout}
        dropped = Counter(_keys(load_golden_patterns(_DATASET_DIR))) - Counter(
            _keys(load_golden_patterns(_DATASET_DIR, exclude=HELDOUT_STORY_FILES))
        )

        assert len(heldout) == 30
        assert sum(dropped.values()) == 30
        assert not (heldout_keys - set(dropped)), "a scored held-out golden was seeded"

    @pytest.mark.asyncio
    async def test_the_scored_run_counts_only_the_heldout_split(self) -> None:
        pages = eval_resolver.load_scraped_pages()
        if not pages:
            pytest.skip("frozen scraped_pages/ dumps not present (gitignored)")

        summary = await run_resolver_eval(pages, rag_retriever=None, stories=_EXPECTED_HELDOUT_IDS)

        assert summary["total_placeholders"] == 30
        assert set(summary["per_story"]) == set(_EXPECTED_HELDOUT_IDS)
        assert "banking_mock" in summary["per_site"]
        assert "saucedemo" not in summary["per_site"]


class TestRecordedFigureNeedsItsLabels:
    """A number without its mode and seed configuration cannot be written."""

    def test_a_figure_without_a_mode_is_refused(self) -> None:
        with pytest.raises(ValueError, match="mode"):
            gate_record.make_figure(correct=28, total=30, mode="", seed="full pack")

    def test_a_figure_without_a_seed_configuration_is_refused(self) -> None:
        with pytest.raises(ValueError, match="seed"):
            gate_record.make_figure(correct=28, total=30, mode="static resolver-only", seed="  ")

    def test_a_labeled_figure_carries_both_labels_and_the_number(self) -> None:
        figure = gate_record.make_figure(
            correct=28,
            total=30,
            mode="static resolver-only (no model)",
            seed="bundled pack minus the 3 held-out story files (83 patterns)",
        )
        assert figure["gate1_correct"] == 28
        assert figure["gate1_total"] == 30
        assert figure["gate1_accuracy_pct"] == 93.3
        assert "mode:" in figure["label"] and "seed:" in figure["label"]

    def test_the_committed_record_is_fully_labelled(self) -> None:
        payload = json.loads((_EVAL_DIR / "known_gate_scores.json").read_text(encoding="utf-8"))

        assert gate_record.validate_record(payload) == []
        # The four measured cells, each with its mode and its seed configuration.
        assert set(payload["static_leg_2026_10_30"]["cells"]) == {
            "heldout_with_pack",
            "heldout_without_pack",
            "full_113_with_pack",
            "full_113_without_pack",
        }
        # The 89/113 full-mode record is kept, one level down, not deleted.
        assert payload["previous"]["gate1_correct"] == 89
        assert payload["previous"]["gate1_total"] == 113
