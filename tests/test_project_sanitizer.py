"""Unit tests for scripts/maintenance/project_sanitizer.py (t-0824).

The CI "Project Sanitizer" job runs ``project_sanitizer.py --check-only`` and
fails on any junk file.  t-0810 vendored the RapidOCR PP-OCRv6 models under
``src/data/ocr/``; the dictionary (``ppocrv6_dict.txt``) is a plain .txt, so the
"temporary .txt" rule flagged it and the job went red.  These tests pin the
allowlist that keeps shipped assets out of the purge.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest

_SANITIZER_PATH = Path(__file__).resolve().parents[1] / "scripts" / "maintenance" / "project_sanitizer.py"


def _load_sanitizer() -> Any:
    spec = importlib.util.spec_from_file_location("project_sanitizer_under_test", _SANITIZER_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def sanitizer() -> Any:
    return _load_sanitizer()


class TestSanitizerPath:
    """Module resolution works from a test, with the repo as the root."""

    def test_project_root_is_the_repo(self, sanitizer: Any) -> None:
        assert sanitizer.PROJECT_ROOT == Path(__file__).resolve().parents[1]

    def test_allowlist_covers_the_vendored_ocr_dir(self, sanitizer: Any) -> None:
        assert "src/data/ocr" in sanitizer.WHITELISTED_DIRS


class TestIsWhitelistedPath:
    """Path-parts matching, which must work on Windows and POSIX alike."""

    def test_vendored_dictionary_is_whitelisted(self, sanitizer: Any) -> None:
        path = sanitizer.PROJECT_ROOT / "src" / "data" / "ocr" / "ppocrv6_dict.txt"
        assert sanitizer.is_whitelisted_path(path) is True

    def test_a_similarly_named_file_outside_the_dir_is_not(self, sanitizer: Any) -> None:
        """``data-ocr.txt`` must not be covered by a substring-style rule."""
        path = sanitizer.PROJECT_ROOT / "src" / "data-ocr.txt"
        assert sanitizer.is_whitelisted_path(path) is False

    def test_a_plain_txt_elsewhere_is_not_whitelisted(self, sanitizer: Any) -> None:
        path = sanitizer.PROJECT_ROOT / "src" / "notes.txt"
        assert sanitizer.is_whitelisted_path(path) is False

    def test_a_path_outside_the_repo_is_not_whitelisted(self, sanitizer: Any) -> None:
        assert sanitizer.is_whitelisted_path(Path("/tmp/somewhere/else.txt")) is False

    def test_anything_new_under_the_dir_is_covered(self, sanitizer: Any) -> None:
        path = sanitizer.PROJECT_ROOT / "src" / "data" / "ocr" / "extra.log"
        assert sanitizer.is_whitelisted_path(path) is True


class TestJunkCheckSkipsVendoredAssets:
    """End-to-end: the check must not report the shipped model dictionary."""

    def test_check_reports_no_junk_for_the_vendored_txt(self, sanitizer: Any) -> None:
        found = sanitizer.purge_junk_check()
        relative = [p.relative_to(sanitizer.PROJECT_ROOT).as_posix() for p in found]
        assert "src/data/ocr/ppocrv6_dict.txt" not in relative

    def test_purge_keeps_the_vendored_files(self, sanitizer: Any, tmp_path: Path) -> None:
        """Deleting here must remove only what is outside the allowlist."""
        ocr_dir = tmp_path / "src" / "data" / "ocr"
        ocr_dir.mkdir(parents=True)
        (ocr_dir / "ppocrv6_dict.txt").write_text("a\nb\n", encoding="utf-8")
        (tmp_path / "stray.txt").write_text("junk\n", encoding="utf-8")

        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(sanitizer, "PROJECT_ROOT", tmp_path)
            sanitizer.purge_junk()

        assert (ocr_dir / "ppocrv6_dict.txt").is_file(), "a vendored asset must survive the purge"
        assert not (tmp_path / "stray.txt").exists(), "real junk must still be purged"
