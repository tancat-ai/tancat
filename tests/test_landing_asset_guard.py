"""Guard: the committed landing assets match the sources they render from.

The landing share card, previews, icon set and install PDF are generated
artefacts. ``landing/asset-sources.json`` records the git blob hash of every
source (and of the generator), so a copy edit committed without a regeneration
fails CI. These tests pin the committed manifest as current and pin the guard
that catches drift.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parent.parent
GUARD_SCRIPT = PROJECT_ROOT / "scripts" / "maintenance" / "landing_assets_guard.py"


def _load_guard() -> Any:
    spec = importlib.util.spec_from_file_location("landing_assets_guard", GUARD_SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_committed_manifest_matches_sources() -> None:
    """The manifest in the repo must describe the assets in the repo."""
    guard = _load_guard()
    assert guard.check() == []


def test_missing_manifest_is_reported(tmp_path: Path) -> None:
    guard = _load_guard()
    problems = guard.check(tmp_path / "does-not-exist.json", tmp_path)
    assert problems
    assert "missing manifest" in problems[0]


def test_stale_source_is_reported(monkeypatch: Any, tmp_path: Path) -> None:
    guard = _load_guard()
    monkeypatch.setattr(guard, "git_blob_hash", lambda _path: "current")
    (tmp_path / "landing").mkdir()
    (tmp_path / "landing" / "s.html").write_text("x", encoding="utf-8")
    (tmp_path / "landing" / "x.png").write_bytes(b"png")
    (tmp_path / "g.py").write_text("# gen", encoding="utf-8")
    manifest = tmp_path / "asset-sources.json"
    manifest.write_text(
        json.dumps(
            {
                "hash": guard.HASH_ALGO,
                "generator": "g.py",
                "generator_hash": "current",
                "assets": {"landing/x.png": ["landing/s.html"]},
                "sources": {"landing/s.html": "stale"},
            },
        ),
        encoding="utf-8",
    )
    problems = guard.check(manifest, tmp_path)
    assert any("landing/s.html changed" in p for p in problems)
    assert any("landing/x.png" in p for p in problems)


def test_changed_generator_is_reported(monkeypatch: Any, tmp_path: Path) -> None:
    guard = _load_guard()
    monkeypatch.setattr(guard, "git_blob_hash", lambda _path: "current")
    (tmp_path / "landing").mkdir()
    (tmp_path / "landing" / "x.png").write_bytes(b"png")
    (tmp_path / "g.py").write_text("# gen", encoding="utf-8")
    manifest = tmp_path / "asset-sources.json"
    manifest.write_text(
        json.dumps(
            {
                "hash": guard.HASH_ALGO,
                "generator": "g.py",
                "generator_hash": "old",
                "assets": {"landing/x.png": []},
                "sources": {},
            },
        ),
        encoding="utf-8",
    )
    problems = guard.check(manifest, tmp_path)
    assert any("g.py changed" in p for p in problems)


def test_missing_asset_is_reported(monkeypatch: Any, tmp_path: Path) -> None:
    guard = _load_guard()
    monkeypatch.setattr(guard, "git_blob_hash", lambda _path: "current")
    (tmp_path / "g.py").write_text("# gen", encoding="utf-8")
    manifest = tmp_path / "asset-sources.json"
    manifest.write_text(
        json.dumps(
            {
                "hash": guard.HASH_ALGO,
                "generator": "g.py",
                "generator_hash": "current",
                "assets": {"landing/gone.png": []},
                "sources": {},
            },
        ),
        encoding="utf-8",
    )
    problems = guard.check(manifest, tmp_path)
    assert any("landing/gone.png is missing" in p for p in problems)


def test_write_manifest_round_trips(monkeypatch: Any, tmp_path: Path) -> None:
    """The writer and the checker agree on the format."""
    guard = _load_guard()
    monkeypatch.setattr(guard, "git_blob_hash", lambda path: f"h:{Path(path).name}")
    (tmp_path / "landing").mkdir()
    (tmp_path / "landing" / "index.html").write_text("x", encoding="utf-8")
    (tmp_path / "landing" / "og-card.png").write_bytes(b"png")
    generator = tmp_path / "scripts" / "maintenance" / "make_landing_assets.py"
    generator.parent.mkdir(parents=True)
    generator.write_text("# gen", encoding="utf-8")
    manifest = tmp_path / "landing" / "asset-sources.json"

    guard.write_manifest(
        {"og-card.png": ("landing/index.html",)},
        generator_path=generator,
        manifest_path=manifest,
        repo_root=tmp_path,
    )

    assert guard.check(manifest, tmp_path) == []
