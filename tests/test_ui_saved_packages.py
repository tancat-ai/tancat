"""Unit tests for the saved-package dropdown label builder (AI-XXX)."""

from __future__ import annotations

from src.pipeline_artifact_manager import PackageManifest
from src.ui.ui_saved_packages import _format_package_label


def _pkg(**kwargs: object) -> PackageManifest:
    base: dict[str, object] = {
        "package_name": "test_20260805_181339_as_a_shopper_on_automationexercise_com_i_want_to",
        "created_at": "2026-08-05T18:13:39.385538",
        "source_story": (
            "As a shopper on automationexercise.com, I want to browse products by category, "
            "add items to my cart, review the cart contents, and proceed to checkout so that "
            "I can complete a purchase."
        ),
        "starting_url": "https://automationexercise.com/",
        "generated_test_files": ["a.py"],
        "run_results_count": 0,
        "last_run_at": "2026-08-05T18:51:00+00:00",
    }
    base.update(kwargs)
    return PackageManifest(**base)  # type: ignore[arg-type]


def test_label_includes_readable_date_and_site() -> None:
    label = _format_package_label(_pkg())
    assert "📦" in label
    assert "Aug 5, 18:13" in label
    assert "automationexercise.com" in label
    assert "browse product" in label  # story snippet truncated with ellipsis
    assert "…" in label
    assert "1 test" in label
    assert "0 runs" in label
    assert "last run Aug 5, 18:51" in label


def test_label_pluralizes_test_and_run_counts() -> None:
    label = _format_package_label(_pkg(generated_test_files=["a.py", "b.py"], run_results_count=1))
    assert "2 tests" in label
    assert "1 run" in label


def test_label_falls_back_to_name_timestamp_without_created_at() -> None:
    label = _format_package_label(PackageManifest(package_name="test_20260720_132120_legacy_pkg", run_results_count=2))
    assert "Jul 20, 13:21" in label
    assert "2 runs" in label


def test_label_omits_last_run_when_never_run() -> None:
    label = _format_package_label(_pkg(last_run_at=""))
    assert "last run" not in label


def test_label_with_no_metadata_is_safe() -> None:
    label = _format_package_label(PackageManifest(package_name="bare_name"))
    assert label  # no crash, non-empty
