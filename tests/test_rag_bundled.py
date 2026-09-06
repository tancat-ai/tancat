"""Unit tests for ``src/rag_bundled.py`` (B-036 Phase 2 bundled pack + auto-seed + AI-055 ingestion summary)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.rag_bundled import (
    BUNDLED_PACK_VERSION,
    SUPPORTED_FORMATS,
    DocSummary,
    IngestionSummary,
    build_bundled_docs,
    build_bundled_patterns,
    build_summary,
    bundled_marker_path,
    check_supported_formats,
    doc_outcome_from_pages,
    doc_summaries_from_page_report,
    ensure_bundled_seeded,
    prune_learned,
    store_stats,
)
from src.rag_learn import site_hash


class TestBuildBundledPack:
    """The shipped golden pack must load from the repo's own data."""

    def test_bundled_patterns_nonempty_and_wellformed(self) -> None:
        patterns = build_bundled_patterns()
        assert len(patterns) > 0
        for p in patterns:
            assert p.action
            assert p.description
            assert p.expected_locator

    def test_bundled_patterns_cover_all_sites(self) -> None:
        pages = {p.expected_page for p in build_bundled_patterns()}
        assert any("saucedemo" in pg for pg in pages)
        assert any("automationexercise" in pg for pg in pages)
        assert any("demoqa" in pg for pg in pages)
        assert any("the-internet" in pg for pg in pages)
        assert any("localhost:8781" in pg for pg in pages)  # mock sites

    def test_golden_patterns_are_site_scoped(self) -> None:
        """B-047 residual: goldens carry a one-way site_hash from their dataset.

        The +20 golden bonus must be site-scoped like the learned +5. Mock
        datasets whose ``base_url`` predates B-047 (all three mocks on :8781)
        get their canonical concurrent-serve ports instead, so the three mocks
        do not collapse into one bucket.
        """
        patterns = build_bundled_patterns()
        assert patterns
        hashes = {p.site_hash for p in patterns}
        # Real sites hash from their base_url domains.
        assert site_hash("www.saucedemo.com") in hashes
        assert site_hash("automationexercise.com") in hashes
        assert site_hash("demoqa.com") in hashes
        assert site_hash("the-internet.herokuapp.com") in hashes
        # Mock sites: lv_insurance keeps :8781; banking/ecommerce use the
        # canonical concurrent-serve ports (8782/8783) — no collision.
        assert site_hash("localhost:8781") in hashes  # lv_insurance
        assert site_hash("localhost:8782") in hashes  # banking_mock
        assert site_hash("localhost:8783") in hashes  # ecommerce_mock
        assert len(hashes) == 7  # 4 real + 3 mock sites, all distinct
        assert all(p.site_hash for p in patterns)

    def test_bundled_docs_nonempty_and_wellformed(self) -> None:
        chunks = build_bundled_docs()
        assert len(chunks) > 0
        for c in chunks:
            assert c.text
            assert c.source
            assert c.heading_path


class TestBundledMarkerPath:
    def test_marker_lives_in_evidence_dir(self, tmp_path: Path) -> None:
        class _FakeStorage:
            def evidence_dir(self) -> Path:
                return tmp_path / "evidence"

        marker = bundled_marker_path(_FakeStorage())  # type: ignore[arg-type]
        assert marker.name == ".rag_bundled_seeded.json"
        assert marker.parent == tmp_path / "evidence"


class TestEnsureBundledSeeded:
    def test_skips_when_marker_exists(self, tmp_path: Path) -> None:
        marker = tmp_path / ".rag_bundled_seeded.json"
        marker.write_text(json.dumps({"version": 1}))
        store = MagicMock()
        store.counts_by_type.return_value = {"golden": 113, "doc": 101}
        result = ensure_bundled_seeded(store=store, marker_path=marker)
        assert result["status"] == "skipped"
        store.add_patterns.assert_not_called()
        store.add_docs.assert_not_called()

    def test_stale_marker_on_pattern_less_store_reseeds(self, tmp_path: Path) -> None:
        """B-048: the wipe signature — marker survived, golden pack gone.

        The wiped store still held doc chunks ({doc: 66}), so ``is_empty``
        alone cannot detect it; the golden count is the truth signal.
        """
        marker = tmp_path / ".rag_bundled_seeded.json"
        marker.write_text(json.dumps({"version": 1, "seeded_at": "2026-08-20T00:00:00"}))
        store = MagicMock()
        store.is_empty = False  # docs survived the wipe
        store.counts_by_type.return_value = {"golden": 0, "doc": 66}
        store.add_patterns.return_value = 113
        store.add_docs.return_value = (101, 0)
        result = ensure_bundled_seeded(store=store, marker_path=marker)
        assert result["status"] == "reseeded"
        assert result["golden"] == 113
        store.add_patterns.assert_called_once()
        store.add_docs.assert_called_once()
        # The marker is refreshed so the anomaly is not re-reported forever.
        assert marker.exists()

    def test_docs_only_store_without_marker_seeds_golden(self, tmp_path: Path) -> None:
        """B-048 latent variant: no marker + docs-only store must not just 'mark'.

        The old "marked" branch would leave a golden-less store permanent.
        """
        marker = tmp_path / ".rag_bundled_seeded.json"
        store = MagicMock()
        store.is_empty = False
        store.counts_by_type.return_value = {"golden": 0, "doc": 5}
        store.add_patterns.return_value = 113
        store.add_docs.return_value = (27, 0)
        result = ensure_bundled_seeded(store=store, marker_path=marker)
        assert result["status"] == "seeded"
        store.add_patterns.assert_called_once()
        assert marker.exists()

    def test_seeds_empty_store_and_writes_marker(self, tmp_path: Path) -> None:
        marker = tmp_path / ".rag_bundled_seeded.json"
        store = MagicMock()
        store.is_empty = True
        store.add_patterns.return_value = 67
        store.add_docs.return_value = (27, 0)
        result = ensure_bundled_seeded(store=store, marker_path=marker)
        assert result["status"] == "seeded"
        assert result["golden"] == 67
        assert result["docs"] == 27
        store.add_patterns.assert_called_once()
        store.add_docs.assert_called_once()
        assert marker.exists()

    def test_marks_nonempty_store_without_adding(self, tmp_path: Path) -> None:
        marker = tmp_path / ".rag_bundled_seeded.json"
        store = MagicMock()
        store.is_empty = False
        store.counts_by_type.return_value = {"golden": 67, "doc": 27}
        result = ensure_bundled_seeded(store=store, marker_path=marker)
        assert result["status"] == "marked"
        store.add_patterns.assert_not_called()
        store.add_docs.assert_not_called()
        assert marker.exists()

    def test_force_reseeds_despite_marker(self, tmp_path: Path) -> None:
        marker = tmp_path / ".rag_bundled_seeded.json"
        marker.write_text(json.dumps({"version": 1}))
        store = MagicMock()
        store.is_empty = True
        store.add_docs.return_value = (27, 0)
        result = ensure_bundled_seeded(store=store, marker_path=marker, force=True)
        assert result["status"] == "seeded"
        store.add_patterns.assert_called_once()

    def test_force_readds_to_populated_store(self, tmp_path: Path) -> None:
        """--force re-adds the pack even when the store already has entries."""
        marker = tmp_path / ".rag_bundled_seeded.json"
        store = MagicMock()
        store.is_empty = False
        store.add_patterns.return_value = 67
        store.add_docs.return_value = (27, 0)
        result = ensure_bundled_seeded(store=store, marker_path=marker, force=True)
        assert result["status"] == "seeded"
        store.add_patterns.assert_called_once()
        store.add_docs.assert_called_once()

    def test_marker_records_pack_version(self, tmp_path: Path) -> None:
        marker = tmp_path / ".rag_bundled_seeded.json"
        store = MagicMock()
        store.is_empty = True
        store.add_docs.return_value = (27, 0)
        ensure_bundled_seeded(store=store, marker_path=marker)
        data = json.loads(marker.read_text(encoding="utf-8"))
        assert data["version"] == BUNDLED_PACK_VERSION

    def test_failure_propagates_for_caller_to_handle(self, tmp_path: Path) -> None:
        marker = tmp_path / ".rag_bundled_seeded.json"
        store = MagicMock()
        store.is_empty = True
        store.add_patterns.side_effect = RuntimeError("embedder download failed")
        with pytest.raises(RuntimeError):
            ensure_bundled_seeded(store=store, marker_path=marker)
        assert not marker.exists()  # retry on the next run


class TestStoreStatsAndPrune:
    def test_store_stats_adds_total(self) -> None:
        store = MagicMock()
        store.counts_by_type.return_value = {"golden": 67, "doc": 27}
        assert store_stats(store) == {"golden": 67, "doc": 27, "total": 94}

    def test_prune_learned_delegates(self) -> None:
        store = MagicMock()
        store.delete_learned.return_value = 3
        assert prune_learned(store) == 3
        store.delete_learned.assert_called_once()


# ---------------------------------------------------------------------------
# AI-055 ingestion quality summary
# ---------------------------------------------------------------------------


class TestDocOutcomeFromPages:
    """Per-doc outcome derivation from page counts."""

    def test_all_text_is_full(self) -> None:
        assert doc_outcome_from_pages(5, 5, 0, 0) == "full"

    def test_all_ocr_is_full(self) -> None:
        """A fully-OCR'd doc (no native text) is still full — OCR is success."""
        assert doc_outcome_from_pages(5, 0, 5, 0) == "full"

    def test_some_skipped_is_partial(self) -> None:
        assert doc_outcome_from_pages(5, 3, 1, 1) == "partial"

    def test_no_pages_read_is_skipped(self) -> None:
        assert doc_outcome_from_pages(5, 0, 0, 5) == "skipped"
        assert doc_outcome_from_pages(0, 0, 0, 0) == "skipped"


class TestDocSummariesFromPageReport:
    """Build per-doc summaries from the per-page report."""

    def test_single_doc_full(self) -> None:
        report = [
            ("policy.pdf", 1, "text", ""),
            ("policy.pdf", 2, "text", ""),
            ("policy.pdf", 3, "ocr", ""),
        ]
        summaries = doc_summaries_from_page_report(report)
        assert len(summaries) == 1
        s = summaries[0]
        assert s.source == "policy.pdf"
        assert s.outcome == "full"
        assert s.pages_text == 2
        assert s.pages_ocr == 1
        assert s.pages_skipped == 0
        assert s.skipped_pages == []

    def test_multiple_docs_mixed(self) -> None:
        report = [
            ("a.pdf", 1, "text", ""),
            ("a.pdf", 2, "skipped", "no_engine"),
            ("b.pdf", 1, "ocr", ""),
            ("b.pdf", 2, "ocr", ""),
        ]
        summaries = {s.source: s for s in doc_summaries_from_page_report(report)}
        assert summaries["a.pdf"].outcome == "partial"
        assert summaries["a.pdf"].pages_skipped == 1
        assert summaries["a.pdf"].skipped_pages == [(2, "no_engine")]
        assert summaries["b.pdf"].outcome == "full"
        assert summaries["b.pdf"].pages_ocr == 2


class TestCheckSupportedFormats:
    """Format scope: pdf + md in; unknown rejected loudly."""

    def test_supported_pdf_and_md(self) -> None:
        supported, rejected = check_supported_formats(["a.pdf", "b.md"])
        assert [str(p) for p in supported] == ["a.pdf", "b.md"]
        assert rejected == []

    def test_unknown_format_rejected(self) -> None:
        supported, rejected = check_supported_formats(["a.pdf", "report.docx", "notes.txt"])
        assert [str(p) for p in supported] == ["a.pdf"]
        assert sorted(rejected) == ["notes.txt", "report.docx"]

    def test_case_insensitive_extension(self) -> None:
        supported, rejected = check_supported_formats(["A.PDF", "B.MD"])
        assert len(supported) == 2
        assert rejected == []

    def test_supported_formats_constant(self) -> None:
        assert SUPPORTED_FORMATS == (".pdf", ".md")


class TestBuildSummary:
    """Aggregated ingestion summary + actionable suggestion."""

    def test_all_full_no_suggestion(self) -> None:
        report = [("a.pdf", 1, "text", ""), ("a.pdf", 2, "text", "")]
        summary = build_summary(report, chunks_new=3, chunks_present=0)
        assert summary.docs_full == 1
        assert summary.docs_partial == 0
        assert summary.suggestion == ""

    def test_no_engine_skip_gives_install_suggestion(self) -> None:
        # a.pdf: 1 text + 1 skipped (no engine) → partial.  b.pdf: 1 ocr + 1
        # skipped (no engine) → partial.  The suggestion names the install fix.
        report = [
            ("a.pdf", 1, "text", ""),
            ("a.pdf", 2, "skipped", "no_engine"),
            ("b.pdf", 1, "ocr", ""),
            ("b.pdf", 2, "skipped", "no_engine"),
        ]
        summary = build_summary(report, chunks_new=2, chunks_present=0)
        assert summary.docs_partial == 2
        assert "uv sync --extra ocr" in summary.suggestion
        assert "a.pdf" in summary.suggestion

    def test_ocr_no_text_skip_gives_re_run_suggestion(self) -> None:
        # Skipped because OCR ran but couldn't read → suggest a clearer scan / higher tier.
        report = [
            ("a.pdf", 1, "text", ""),
            ("a.pdf", 2, "skipped", "ocr_no_text"),
        ]
        summary = build_summary(report, chunks_new=1, chunks_present=0)
        assert summary.docs_partial == 1
        assert "high-accuracy" in summary.suggestion
        assert "uv sync --extra ocr" not in summary.suggestion

    def test_dedup_transparency(self) -> None:
        report = [("a.pdf", 1, "text", "")]
        summary = build_summary(report, chunks_new=2, chunks_present=10)
        assert summary.chunks_new == 2
        assert summary.chunks_present == 10
        assert summary.chunks_total == 12
        rendered = summary.render()
        assert "already present / deduped" in rendered

    def test_skipped_formats_reported(self) -> None:
        report = [("a.pdf", 1, "text", "")]
        summary = build_summary(report, chunks_new=1, chunks_present=0, skipped_formats=["report.docx"])
        rendered = summary.render()
        assert "unsupported format: report.docx" in rendered

    def test_unreadable_docs_added_as_skipped(self) -> None:
        report = [("a.pdf", 1, "text", "")]
        summary = build_summary(report, chunks_new=1, chunks_present=0, unreadable_docs=["broken.pdf"])
        skipped = [d for d in summary.docs if d.outcome == "skipped"]
        assert any(d.source == "broken.pdf" for d in skipped)

    def test_render_full_summary_no_engine_shows_fix(self) -> None:
        # a.pdf: text + ocr → full.  b.pdf: text + skipped (no engine) → partial.
        # The rendered output must show the [WARN] line AND the install fix.
        report = [
            ("a.pdf", 1, "text", ""),
            ("a.pdf", 2, "ocr", ""),
            ("b.pdf", 1, "text", ""),
            ("b.pdf", 2, "skipped", "no_engine"),
        ]
        summary = build_summary(report, chunks_new=4, chunks_present=0, skipped_formats=["c.docx"])
        rendered = summary.render()
        assert "Ingestion summary (2 docs):" in rendered
        assert "fully ingested" in rendered
        # The skipped doc is surfaced distinctly (must not hide behind a green result)
        assert "[WARN] b.pdf" in rendered
        assert "NOT digested" in rendered
        # The cause is "no_engine" → the install fix is shown
        assert "uv sync --extra ocr" in rendered
        assert "unsupported format: c.docx" in rendered
        assert "Suggested:" in rendered

    def test_render_no_engine_skip_shows_install_fix(self) -> None:
        # A single fully-scanned doc (all pages skipped, no engine) → outcome
        # "skipped" (not "partial").  The [WARN] line + install fix must show so
        # the user knows the doc was NOT digested and how to fix it.
        report = [
            ("scan.pdf", 1, "skipped", "no_engine"),
            ("scan.pdf", 2, "skipped", "no_engine"),
        ]
        summary = build_summary(report, chunks_new=0, chunks_present=0)
        rendered = summary.render()
        assert "[WARN] scan.pdf" in rendered
        assert "OCR engine NOT installed" in rendered
        assert "uv sync --extra ocr" in rendered
        assert "Suggested:" in rendered

    def test_render_ocr_no_text_skip_no_install_fix(self) -> None:
        # Skipped because OCR ran but couldn't read → NOT the "install" cause,
        # so the install fix must NOT be shown (it would be a wrong fix).
        report = [
            ("scan.pdf", 1, "text", ""),
            ("scan.pdf", 2, "skipped", "ocr_no_text"),
        ]
        summary = build_summary(report, chunks_new=1, chunks_present=0)
        rendered = summary.render()
        assert "[WARN] scan.pdf" in rendered
        assert "OCR ran but could not read" in rendered
        assert "uv sync --extra ocr" not in rendered


class TestDocSummaryDataclass:
    def test_default_fields(self) -> None:
        d = DocSummary(source="x.pdf", outcome="full")
        assert d.pages_total == 0
        assert d.pages_text == 0
        assert d.pages_ocr == 0
        assert d.pages_skipped == 0
        assert d.skip_reason == ""

    def test_ingestion_summary_defaults(self) -> None:
        s = IngestionSummary()
        assert s.docs == []
        assert s.chunks_new == 0
        assert s.chunks_present == 0
        assert s.skipped_formats == []
        assert s.suggestion == ""
