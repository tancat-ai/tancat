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
from typing import Any
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
    heldout_story_ids,
    run_resolver_eval,
    select_story_placeholders,
)
from heldout_split import DEFAULT_SPLIT, describe_split, site_groups, split_files  # noqa: E402

from src.rag_bundled import (  # noqa: E402
    build_bundled_patterns,
    ensure_bundled_seeded,
    golden_site_hash,
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
        assert DEFAULT_SPLIT == (
            "eval-007_banking_mock.json",
            "eval-008_goto_navigation.json",
            "eval-010_ambiguous_mock.json",
        )
        for name in DEFAULT_SPLIT:
            assert (_DATASET_DIR / name).is_file(), name
            assert _keys_from_files((name,)), f"{name} carries no scored placeholders - substitute the next file"

    def test_excluded_files_contribute_no_patterns(self) -> None:
        all_patterns = load_golden_patterns(_DATASET_DIR)
        kept = load_golden_patterns(_DATASET_DIR, exclude=DEFAULT_SPLIT)

        assert len(all_patterns) == 113
        assert len(kept) == 83
        # The exact multiset that left the seed is the three held-out files' own
        # keys - no more, no less. Nothing else was removed, nothing stayed.
        dropped = Counter(_keys(all_patterns)) - Counter(_keys(kept))
        assert dropped == Counter(_keys_from_files(DEFAULT_SPLIT)), (
            "the seed did not drop exactly the held-out files' goldens - the gate can see its own answers"
        )

    def test_exclusion_accepts_a_stem_or_a_file_name(self) -> None:
        by_name = load_golden_patterns(_DATASET_DIR, exclude=DEFAULT_SPLIT)
        by_stem = load_golden_patterns(_DATASET_DIR, exclude=tuple(Path(n).stem for n in DEFAULT_SPLIT))
        assert _keys(by_name) == _keys(by_stem)

    def test_no_exclusion_is_the_shipped_pack(self) -> None:
        """The product path is unchanged: the default seed is the full 113."""
        assert len(build_bundled_patterns()) == 113
        assert len(build_bundled_patterns(exclude=DEFAULT_SPLIT)) == 83

    def test_seeding_threads_the_exclusion_to_the_store(self, tmp_path: Path) -> None:
        store = MagicMock()
        store.is_empty = True
        store.add_patterns.return_value = 83
        store.add_docs.return_value = (0, 0)

        result = ensure_bundled_seeded(
            store=store,
            marker_path=tmp_path / ".rag_bundled_seeded.json",
            exclude=DEFAULT_SPLIT,
        )

        assert result["status"] == "seeded"
        seeded = store.add_patterns.call_args.args[0]
        assert len(seeded) == 83
        dropped = Counter(_keys(load_golden_patterns(_DATASET_DIR))) - Counter(_keys(seeded))
        assert dropped == Counter(_keys_from_files(DEFAULT_SPLIT))


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
            _keys(load_golden_patterns(_DATASET_DIR, exclude=DEFAULT_SPLIT))
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
    """A number without its mode, seed and split cannot be written."""

    _SPLIT = "held-out: eval-007, eval-008, eval-010 (30 of 113 placeholders)"

    def test_a_figure_without_a_mode_is_refused(self) -> None:
        with pytest.raises(ValueError, match="mode"):
            gate_record.make_figure(correct=28, total=30, mode="", seed="full pack", split=self._SPLIT)

    def test_a_figure_without_a_seed_configuration_is_refused(self) -> None:
        with pytest.raises(ValueError, match="seed"):
            gate_record.make_figure(correct=28, total=30, mode="static resolver-only", seed="  ", split=self._SPLIT)

    def test_a_labeled_figure_carries_all_three_labels_and_the_number(self) -> None:
        figure = gate_record.make_figure(
            correct=28,
            total=30,
            mode="static resolver-only (no model)",
            seed="bundled pack minus the 3 held-out story files (83 patterns)",
            split=self._SPLIT,
        )
        assert figure["gate1_correct"] == 28
        assert figure["gate1_total"] == 30
        assert figure["gate1_accuracy_pct"] == 93.3
        assert "mode:" in figure["label"] and "seed:" in figure["label"] and "split:" in figure["label"]

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


class TestRotation:
    """Which story files are held back can rotate, deterministically (j-0244 step 2).

    The owner's decision (2026-10-30): read the 90% gate-1 target against the
    held-out split, and rotate the split so the sample grows instead of the same
    30 placeholders being scored forever. The default stays the fixed three so
    the recorded 2026-10-30 figure keeps reproducing itself.
    """

    def test_the_default_split_is_still_the_three_fixed_files(self) -> None:
        """No selector: eval-007/008/010, exactly as the recorded figure used."""
        assert split_files(_DATASET_DIR) == DEFAULT_SPLIT
        assert split_files(_DATASET_DIR, "default") == DEFAULT_SPLIT
        default = describe_split(_DATASET_DIR, DEFAULT_SPLIT)
        assert default["stories"] == ["eval-007", "eval-008", "eval-010"]
        assert default["placeholders"] == 30

    def test_rotation_is_stable_for_one_seed(self) -> None:
        """Two runs with the same seed pick the same split - same day or not."""
        first = split_files(_DATASET_DIR, "seed:42")
        second = split_files(_DATASET_DIR, "seed:42")
        assert first == second
        # Three whole site groups: three files, or four when the banking pair lands.
        assert len(first) in (3, 4)
        assert len(set(first)) == len(first)

    def test_rotation_differs_for_another_seed(self) -> None:
        assert split_files(_DATASET_DIR, "seed:42") != split_files(_DATASET_DIR, "seed:7")

    def test_rotation_by_date_is_stable_within_a_day_and_moves_between_days(self) -> None:
        assert split_files(_DATASET_DIR, "date:2026-10-30") == split_files(_DATASET_DIR, "date:2026-10-30")
        assert split_files(_DATASET_DIR, "date") == split_files(_DATASET_DIR, "date")
        assert split_files(_DATASET_DIR, "date:2026-10-30") != split_files(_DATASET_DIR, "date:2026-10-31")

    def test_a_rotated_split_is_three_whole_groups_that_carry_scored_keys(self) -> None:
        for selector in ("seed:1", "seed:2", "seed:3", "date:2026-11-01"):
            files = split_files(_DATASET_DIR, selector)
            assert len(files) in (3, 4), selector
            assert len({_site_hash_of(_DATASET_DIR, n) for n in files}) == 3, selector
            for name in files:
                assert (_DATASET_DIR / name).is_file(), (selector, name)
                assert _keys_from_files((name,)), (selector, name)

    def test_an_explicit_list_is_allowed(self) -> None:
        wanted = (
            "eval-001_saucedemo_login_checkout.json",
            "eval-005_lv_insurance_quote.json",
            "eval-006_ecommerce_mock.json",
        )
        assert split_files(_DATASET_DIR, ",".join(wanted)) == wanted
        assert split_files(_DATASET_DIR, ", ".join(wanted)) == wanted
        described = describe_split(_DATASET_DIR, wanted)
        assert described["stories"] == ["eval-001", "eval-005", "eval-006"]
        assert described["placeholders"] == 20 + 24 + 16

    def test_a_bad_explicit_list_is_refused_not_silently_trimmed(self) -> None:
        with pytest.raises(ValueError, match="not a dataset file"):
            split_files(_DATASET_DIR, "eval-999_nope.json")
        with pytest.raises(ValueError, match="share"):
            # eval-007 held out, its banking sibling left seeded.
            split_files(_DATASET_DIR, "eval-007_banking_mock.json,eval-005_lv_insurance_quote.json")
        with pytest.raises(ValueError, match="seed:|date:"):
            split_files(_DATASET_DIR, "42")
        # Any set of WHOLE groups is a legal explicit split, whatever its size.
        two = split_files(_DATASET_DIR, "eval-001_saucedemo_login_checkout.json,eval-005_lv_insurance_quote.json")
        assert two == ("eval-001_saucedemo_login_checkout.json", "eval-005_lv_insurance_quote.json")

    def test_the_flag_reaches_the_scorer_and_the_printed_label(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
    ) -> None:
        """--heldout-split scores the same split it prints (plumbing, no model, no RAG)."""
        import asyncio

        from eval_resolver import heldout_story_ids

        seen: dict[str, tuple[str, ...]] = {}

        monkeypatch.setattr(eval_resolver, "load_scraped_pages", lambda: {"u": [{"selector": "#x"}]})
        monkeypatch.setattr(eval_resolver, "isolate_eval_store", lambda *a, **k: None)
        monkeypatch.setattr(eval_resolver, "rag_enabled_for_eval", lambda: False)
        monkeypatch.setattr(eval_resolver, "HELDOUT_STORE_ROOT", tmp_path / "heldout_store")

        async def _fake_run(
            _pages: object, _rag: object = None, *, stories: Sequence[str] | None = None
        ) -> dict[str, object]:
            seen["stories"] = tuple(stories or ())
            return {"total_placeholders": 0, "correct": 0, "accuracy_pct": 0.0, "per_site": {}, "per_story": {}}

        monkeypatch.setattr(eval_resolver, "run_resolver_eval", _fake_run)

        assert asyncio.run(eval_resolver._cmd_static(split_selector="seed:42")) == 0

        chosen = split_files(_DATASET_DIR, "seed:42")
        expected = describe_split(_DATASET_DIR, chosen)
        assert seen["stories"] == heldout_story_ids(list(chosen))
        assert f"[SPLIT: {expected['label']}]" in capsys.readouterr().out

    def test_the_split_names_itself_in_one_line(self) -> None:
        described = describe_split(_DATASET_DIR, DEFAULT_SPLIT)
        assert described["label"] == "held-out: eval-007, eval-008, eval-010 (30 of 113 placeholders)"
        assert described["key"] == "eval-007|eval-008|eval-010"


class TestSplitIsRecordedOnEveryFigure:
    """No figure without its split, and two splits are never read as comparable."""

    def test_a_figure_without_a_split_is_refused(self) -> None:
        with pytest.raises(ValueError, match="split"):
            gate_record.make_figure(correct=12, total=30, mode="static resolver-only", seed="full pack", split="")

    def test_a_figure_carries_its_split_in_the_label(self) -> None:
        figure = gate_record.make_figure(
            correct=12,
            total=30,
            mode="static resolver-only",
            seed="pack minus the 3 held-out files",
            split="held-out: eval-007, eval-008, eval-010 (30 of 113 placeholders)",
            split_key="eval-007|eval-008|eval-010",
            split_kind="heldout",
        )
        assert "split:" in figure["label"]
        assert figure["split_kind"] == "heldout"

    def test_two_different_splits_are_marked_not_comparable(self) -> None:
        a = gate_record.make_figure(
            correct=12,
            total=30,
            mode="static resolver-only",
            seed="pack minus the held-out files",
            split="held-out: eval-007, eval-008, eval-010 (30 of 113 placeholders)",
            split_key="eval-007|eval-008|eval-010",
            split_kind="heldout",
        )
        b = gate_record.make_figure(
            correct=20,
            total=50,
            mode="static resolver-only",
            seed="pack minus the held-out files",
            split="held-out: eval-001, eval-005, eval-006 (60 of 113 placeholders)",
            split_key="eval-001|eval-005|eval-006",
            split_kind="heldout",
        )

        verdict = gate_record.compare_figures(a, b)

        assert verdict["comparable"] is False
        assert "not comparable" in verdict["why"]
        assert "eval-007" in verdict["why"] and "eval-001" in verdict["why"]

    def test_the_same_split_in_the_same_mode_is_comparable(self) -> None:
        shared: dict[str, Any] = {
            "total": 30,
            "mode": "static resolver-only",
            "split": "held-out: eval-007, eval-008, eval-010 (30 of 113 placeholders)",
            "split_key": "eval-007|eval-008|eval-010",
            "split_kind": "heldout",
        }
        with_pack = gate_record.make_figure(correct=12, seed="pack minus the held-out files", **shared)
        without_pack = gate_record.make_figure(correct=12, seed="none (RAG_ENABLED=0)", **shared)

        verdict = gate_record.compare_figures(with_pack, without_pack)

        assert verdict["comparable"] is True

    def test_every_committed_figure_names_its_split(self) -> None:
        payload = json.loads((_EVAL_DIR / "known_gate_scores.json").read_text(encoding="utf-8"))

        assert gate_record.validate_record(payload) == []
        assert payload["split"] and "eval-007" in payload["split"]
        assert payload["split_placeholders"] == 30
        for name, cell in payload["static_leg_2026_10_30"]["cells"].items():
            assert cell["split"], name
            assert cell["split_key"], name
            assert cell["comparability"], name
            assert isinstance(cell["comparable_with"], list), name
            if cell["split_kind"] == "heldout":
                # Rotation cannot weaken the sample quietly: the per-file
                # breakdown sits beside the number.
                assert cell["per_file"], name

    def test_a_cell_may_not_claim_comparability_across_splits(self) -> None:
        """The validator, not the reader, is what refuses a cross-split claim."""
        payload = json.loads((_EVAL_DIR / "known_gate_scores.json").read_text(encoding="utf-8"))
        cells = payload["static_leg_2026_10_30"]["cells"]
        cells["heldout_with_pack"]["comparable_with"] = ["full_113_with_pack"]

        problems = gate_record.validate_record(payload)

        assert problems, "a cross-split comparability claim was accepted"
        assert any("different split" in p for p in problems), problems


def _site_hash_of(dataset_dir: Path, name: str) -> str:
    """The site identity the bundled seed scopes a dataset file's goldens under."""
    data = json.loads((dataset_dir / name).read_text(encoding="utf-8"))
    return golden_site_hash(str(data.get("site", "")), str(data.get("base_url", "")))


def _files_by_site(dataset_dir: Path) -> dict[str, set[str]]:
    groups: dict[str, set[str]] = {}
    for path in sorted(dataset_dir.glob("eval-*.json")):
        groups.setdefault(_site_hash_of(dataset_dir, path.name), set()).add(path.name)
    return groups


class TestAGroupIsHeldOutWhole:
    """A rotation may never separate two story files that share a site (t-1119).

    The +20 golden bonus gates on the pattern's ``site_hash``, not on the file:
    eval-007_banking_mock and eval-008_goto_navigation both hash to
    ``bebd95a0fea633c3``, so a split that holds one out and leaves the other
    seeded hands the answer back - the defect this whole job exists to close,
    half the rotation space wide.
    """

    def test_every_known_sibling_pair_is_one_group(self) -> None:
        groups = site_groups(_DATASET_DIR)
        banking = [h for h, files in groups.items() if "eval-007_banking_mock.json" in files]
        assert len(banking) == 1
        assert set(groups[banking[0]]) == {"eval-007_banking_mock.json", "eval-008_goto_navigation.json"}
        # A split holds a group whole or not at all: every group is a tuple of files.
        assert all(len(files) >= 1 for files in groups.values())

    def test_no_rotation_separates_two_files_that_share_a_site(self) -> None:
        """The review's sweep: 200 seeds plus 84 dates, no same-site pair split."""
        groups = _files_by_site(_DATASET_DIR)
        selectors = [f"seed:{i}" for i in range(1, 201)]
        selectors += [
            f"date:2026-{month:02d}-{day:02d}"
            for month, day in ((m, d) for m in (1, 2, 3, 4, 5, 6) for d in range(1, 15))
        ]

        seen: set[tuple[str, ...]] = set()
        for selector in selectors:
            held_out = set(split_files(_DATASET_DIR, selector))
            seen.add(tuple(sorted(held_out)))
            for site_hash, group in groups.items():
                inside = group & held_out
                assert not (inside and inside != group), (
                    f"{selector} split site {site_hash}: held out {sorted(inside)} of {sorted(group)} - "
                    "the seed keeps the sibling's goldens"
                )
        assert len(seen) > 20, f"the sweep rotated over only {len(seen)} distinct splits"

    def test_a_rotated_split_can_carry_four_files(self) -> None:
        """Holding a group whole is why a split is three GROUPS, not three files."""
        sizes = {len(split_files(_DATASET_DIR, f"seed:{i}")) for i in range(1, 201)}
        assert sizes <= {3, 4}
        assert 4 in sizes, "the two-file banking group was never selected across 200 seeds"

    def test_an_explicit_list_that_separates_a_site_is_refused(self) -> None:
        with pytest.raises(ValueError, match="share"):
            split_files(
                _DATASET_DIR,
                "eval-007_banking_mock.json,eval-010_ambiguous_mock.json,eval-005_lv_insurance_quote.json",
            )

    def test_the_default_split_is_unchanged_at_30_placeholders(self) -> None:
        """Today's 12/30 must stay reproducible: the default is still 007/008/010."""
        assert split_files(_DATASET_DIR) == DEFAULT_SPLIT
        assert DEFAULT_SPLIT == (
            "eval-007_banking_mock.json",
            "eval-008_goto_navigation.json",
            "eval-010_ambiguous_mock.json",
        )
        described = describe_split(_DATASET_DIR, DEFAULT_SPLIT)
        assert described["placeholders"] == 30
        assert described["stories"] == ["eval-007", "eval-008", "eval-010"]


class TestTheRecordRefusesASeparatingSplit:
    """The splitter is the fix; the validator is what stops it coming back."""

    def test_a_figure_whose_split_separates_same_site_files_is_refused(self) -> None:
        payload = json.loads((_EVAL_DIR / "known_gate_scores.json").read_text(encoding="utf-8"))
        cell = payload["static_leg_2026_10_30"]["cells"]["heldout_with_pack"]
        # Drop eval-008 from the split: eval-007 stays scored, its sibling stays seeded.
        cell["split_files"] = ["eval-007_banking_mock.json", "eval-010_ambiguous_mock.json"]

        problems = gate_record.validate_record(payload)

        assert problems, "a split that separates same-site files was accepted"
        assert any("share" in p and "site_hash" in p for p in problems), problems

    def test_the_committed_record_passes_the_guard(self) -> None:
        payload = json.loads((_EVAL_DIR / "known_gate_scores.json").read_text(encoding="utf-8"))

        assert gate_record.validate_record(payload) == []
        for name, cell in payload["static_leg_2026_10_30"]["cells"].items():
            if cell["split_kind"] == "heldout":
                assert cell["split_files"], name


class TestOneListNotTwo:
    """The seed exclusion and the scored list cannot drift apart."""

    def test_the_seed_exclusion_and_the_scored_list_come_from_one_source(self) -> None:
        import src.rag_bundled as rag_bundled

        # The copy in the product module is gone; the eval module owns the list.
        assert not hasattr(rag_bundled, "HELDOUT_STORY_FILES"), (
            "HELDOUT_STORY_FILES is back in src/ - that is the second copy of the split"
        )
        assert split_files(_DATASET_DIR) == DEFAULT_SPLIT
        assert heldout_story_ids() == ("eval-007", "eval-008", "eval-010")

        # What is excluded from the seed is the split's own file list, not a literal.
        described = describe_split(_DATASET_DIR, DEFAULT_SPLIT)
        assert described["files"] == list(DEFAULT_SPLIT)
        held_out = int(str(described["placeholders"]))
        patterns = build_bundled_patterns(exclude=[str(name) for name in described["files"]])
        assert len(patterns) == 113 - held_out
