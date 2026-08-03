"""Unit tests for ``scripts/rag_ingest.py`` (chunking, loading, CLI)."""

from __future__ import annotations

import json
import textwrap
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from scripts.rag_ingest import (
    chunk_markdown_file,
    load_docs,
    load_golden_patterns,
    main,
)

# ---------------------------------------------------------------------------
# Golden pattern loading
# ---------------------------------------------------------------------------


class TestLoadGoldenPatterns:
    def test_loads_placeholder_fields(self, tmp_path: Path) -> None:
        dataset_dir = tmp_path / "dataset"
        dataset_dir.mkdir()
        eval_file = dataset_dir / "eval-001_test.json"
        eval_file.write_text(
            json.dumps(
                {
                    "id": "eval-001",
                    "golden_resolutions": [
                        {
                            "criterion_index": 0,
                            "placeholders": [
                                {
                                    "action": "CLICK",
                                    "description": "login button",
                                    "expected_locator": "#login-btn",
                                    "tolerance_selectors": ["[data-test='login']"],
                                    "expected_page": "/login",
                                }
                            ],
                        }
                    ],
                }
            )
        )

        patterns = load_golden_patterns(dataset_dir)
        assert len(patterns) == 1
        p = patterns[0]
        assert p.action == "CLICK"
        assert p.description == "login button"
        assert p.expected_locator == "#login-btn"
        assert p.tolerance_selectors == ["[data-test='login']"]
        assert p.expected_page == "/login"

    def test_empty_directory(self, tmp_path: Path) -> None:
        dataset_dir = tmp_path / "empty"
        dataset_dir.mkdir()
        patterns = load_golden_patterns(dataset_dir)
        assert patterns == []

    def test_skips_non_eval_files(self, tmp_path: Path) -> None:
        dataset_dir = tmp_path / "dataset"
        dataset_dir.mkdir()
        (dataset_dir / "README.md").write_text("not json")
        patterns = load_golden_patterns(dataset_dir)
        assert patterns == []

    def test_multiple_criteria(self, tmp_path: Path) -> None:
        dataset_dir = tmp_path / "dataset"
        dataset_dir.mkdir()
        (dataset_dir / "eval-001.json").write_text(
            json.dumps(
                {
                    "golden_resolutions": [
                        {
                            "criterion_index": 0,
                            "placeholders": [{"action": "CLICK", "description": "a", "expected_locator": "#a"}],
                        },
                        {
                            "criterion_index": 1,
                            "placeholders": [{"action": "FILL", "description": "b", "expected_locator": "#b"}],
                        },
                    ]
                }
            )
        )
        patterns = load_golden_patterns(dataset_dir)
        assert len(patterns) == 2


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------


SIMPLE_DOC = textwrap.dedent("""\
# Test Doc

Intro paragraph here.

## Section One

This is the content of section one.
It has multiple lines.

## Section Two

Section two content is shorter.
""")


class TestChunkMarkdownFile:
    def test_single_heading_chunks(self, tmp_path: Path) -> None:
        f = tmp_path / "test.md"
        f.write_text("# Title\n\n## Section A\n\nSome content.\n")
        chunks = chunk_markdown_file(f)
        assert len(chunks) == 1
        assert chunks[0].source == "test.md"
        assert chunks[0].heading_path == "Title > Section A"
        assert "Some content" in chunks[0].text

    def test_multiple_sections(self, tmp_path: Path) -> None:
        f = tmp_path / "test.md"
        f.write_text(SIMPLE_DOC)
        chunks = chunk_markdown_file(f)
        assert len(chunks) >= 2
        headings = {c.heading_path for c in chunks}
        assert "Test Doc > Section One" in headings
        assert "Test Doc > Section Two" in headings

    def test_no_headings_uses_filename(self, tmp_path: Path) -> None:
        f = tmp_path / "plain.md"
        f.write_text("Just some text without headings.")
        chunks = chunk_markdown_file(f)
        assert len(chunks) == 1
        assert chunks[0].heading_path == "plain.md"

    def test_heading_path_without_section(self, tmp_path: Path) -> None:
        f = tmp_path / "test.md"
        f.write_text("# Doc Title\n\nContent before any ## heading.")
        chunks = chunk_markdown_file(f)
        assert len(chunks) == 1
        assert chunks[0].heading_path == "Doc Title"

    def test_large_section_split(self, tmp_path: Path) -> None:
        """A section exceeding the chunk target should be split."""
        f = tmp_path / "big.md"
        para = "Paragraph with enough content to force a split. "
        big_content = para * 80
        f.write_text(f"# Big Doc\n\n## Big Section\n\n{big_content}\n")
        chunks = chunk_markdown_file(f)
        assert len(chunks) > 1
        # All chunks should be from the section (title-only preamble is filtered)
        paths = {c.heading_path for c in chunks}
        assert len(paths) == 1
        assert "Big Doc > Big Section" in paths

    def test_empty_file(self, tmp_path: Path) -> None:
        f = tmp_path / "empty.md"
        f.write_text("")
        chunks = chunk_markdown_file(f)
        assert chunks == []


class TestLoadDocs:
    def test_loads_all_md_files(self, tmp_path: Path) -> None:
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "a.md").write_text("# A\n\n## One\n\nContent one.")
        (docs_dir / "b.md").write_text("# B\n\n## Two\n\nContent two.")
        chunks = load_docs(docs_dir)
        sources = {c.source for c in chunks}
        assert "a.md" in sources
        assert "b.md" in sources

    def test_empty_directory(self, tmp_path: Path) -> None:
        docs_dir = tmp_path / "empty_docs"
        docs_dir.mkdir()
        chunks = load_docs(docs_dir)
        assert chunks == []

    def test_chunks_have_required_fields(self, tmp_path: Path) -> None:
        docs_dir = tmp_path / "docs"
        docs_dir.mkdir()
        (docs_dir / "c.md").write_text("# Doc\n\n## Section\n\nContent here.")
        chunks = load_docs(docs_dir)
        for c in chunks:
            assert c.text
            assert c.source
            assert c.heading_path


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


class TestMain:
    def test_no_args_prints_help(self) -> None:
        """No args returns early with a zero-count dict (help printed to stdout)."""
        result = main([])
        assert result == {"golden": 0, "docs": 0, "pdfs": 0}

    def test_bundled_flag_calls_seed(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """B-036 Phase 2: --bundled seeds idempotently (no-op when marked)."""
        fake = MagicMock(return_value={"status": "skipped", "golden": 0, "docs": 0})
        monkeypatch.setattr("scripts.rag_ingest.ensure_bundled_seeded", fake)
        result = main(["--bundled"])
        bundled = result["bundled"]
        assert isinstance(bundled, dict)
        assert bundled["status"] == "skipped"
        fake.assert_called_once_with(force=False)

    def test_bundled_force_flag(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """B-036 Phase 2: --bundled --force re-seeds despite the marker."""
        fake = MagicMock(return_value={"status": "seeded", "golden": 5, "docs": 3})
        monkeypatch.setattr("scripts.rag_ingest.ensure_bundled_seeded", fake)
        result = main(["--bundled", "--force"])
        bundled = result["bundled"]
        assert isinstance(bundled, dict)
        assert bundled["status"] == "seeded"
        fake.assert_called_once_with(force=True)

    def test_stats_flag_reports_counts(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """B-036 Phase 2: --stats shows per-type counts."""
        fake = MagicMock(return_value={"golden": 67, "doc": 27, "total": 94})
        monkeypatch.setattr("scripts.rag_ingest.store_stats", fake)
        result = main(["--stats"])
        stats = result["stats"]
        assert isinstance(stats, dict)
        assert stats["total"] == 94
        fake.assert_called_once()

    def test_prune_learned_flag(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """B-036 Phase 2: --prune-learned removes learned patterns only."""
        fake = MagicMock(return_value=3)
        monkeypatch.setattr("scripts.rag_ingest.prune_learned", fake)
        result = main(["--prune-learned"])
        assert result["pruned"] == 3
        fake.assert_called_once()

    @pytest.mark.slow
    def test_both_flags_accepted(self) -> None:
        """Smoke test: --golden --docs should run without error."""
        result = main(["--golden", "--docs"])
        assert isinstance(result, dict)
        assert "golden" in result
        assert "docs" in result
