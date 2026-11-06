"""t-1346: the committed capture wins, and a differing local one is reported.

The resolver used to layer the gitignored ``scripts/eval/scraped_pages/`` *on
top of* the committed captures, so a stale local copy of a banking page silently
overrode the repository's own - and a developer could measure a different number
from CI with nothing saying so. That is "works on my machine" inverted.

These tests pin the rule: the committed capture is what a number is measured
against, a local capture only adds URLs the repository does not hold, and any
difference is said out loud. An override exists but must be asked for.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

_EVAL_DIR = Path(__file__).resolve().parent.parent / "scripts" / "eval"
sys.path.insert(0, str(_EVAL_DIR))

import pytest  # noqa: E402
from eval_resolver import _resolve_placeholder, load_scraped_pages  # noqa: E402

DASHBOARD = "http://localhost:8781/dashboard.html"
COMMITTED_LINK = {"selector": "#transfer-link", "tag": "a", "id": "transfer-link", "text": "Transfer Money"}
COMMITTED_BALANCE = {"selector": ".account_balance", "tag": "span", "id": "", "text": "$1,000"}
STALE_LINK = {"selector": "#transfer-link-old", "tag": "a", "id": "transfer-link-old", "text": "Move money"}


class _Matcher:
    """Text matcher stub: returns the element whose text contains the description."""

    def pass0_exact_text_match(self, action: str, description: str, pages: dict[str, list[dict[str, Any]]]) -> Any:
        return None

    def pass1_text_match(self, action: str, description: str, pages: dict[str, list[dict[str, Any]]]) -> Any:
        for elements in pages.values():
            for element in elements:
                if description.lower() in str(element.get("text") or "").lower():
                    return element
        return None


def _write(directory: Path, name: str, url: str, elements: list[dict[str, Any]]) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(json.dumps({"url": url, "elements": elements}), encoding="utf-8")


def _dirs(tmp_path: Path) -> tuple[Path, Path]:
    committed, local = tmp_path / "committed", tmp_path / "local"
    _write(committed, "dashboard.json", DASHBOARD, [COMMITTED_LINK, COMMITTED_BALANCE])
    _write(local, "http_localhost_8781_dashboard.html.json", DASHBOARD, [STALE_LINK])
    return committed, local


def _resolve(pages: dict[str, list[dict[str, Any]]]) -> Any:
    return _resolve_placeholder(
        action="CLICK",
        description="Transfer Money",
        pages_data=pages,
        target_page=DASHBOARD,
        element_matcher=_Matcher(),
        flow_store=None,
    )


def test_a_stale_local_capture_does_not_replace_the_committed_one(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    committed, local = _dirs(tmp_path)

    with caplog.at_level("WARNING", logger="eval_resolver"):
        pages = load_scraped_pages(committed_dir=committed, local_dir=local, allow_local_override=False)

    ids = [element["id"] for element in pages[DASHBOARD]]
    assert ids == ["transfer-link", ""], ids  # the committed pair, not the stale local one

    text = caplog.text
    assert "differs from the committed capture" in text, text
    assert "http_localhost_8781_dashboard.html.json" in text, text  # the local file is named
    assert "the COMMITTED one wins" in text, text


def test_the_resolution_is_the_one_the_committed_capture_gives(tmp_path: Path) -> None:
    """A stale local copy must not change what the resolver answers."""
    committed, local = _dirs(tmp_path)

    with_stale_local = _resolve(
        load_scraped_pages(committed_dir=committed, local_dir=local, allow_local_override=False)
    )
    committed_only = _resolve(
        load_scraped_pages(committed_dir=committed, local_dir=tmp_path / "nothing", allow_local_override=False)
    )

    assert with_stale_local == committed_only == "#transfer-link"


def test_a_local_capture_for_an_uncommitted_url_is_still_used(tmp_path: Path) -> None:
    """A developer's third-party captures keep working - they only cannot override."""
    committed, local = _dirs(tmp_path)
    other = "https://www.saucedemo.com/inventory.html"
    _write(local, "https_www_saucedemo.com_inventory.html.json", other, [COMMITTED_BALANCE])

    pages = load_scraped_pages(committed_dir=committed, local_dir=local, allow_local_override=False)

    assert other in pages
    assert len(pages[DASHBOARD]) == 2


def test_an_explicit_override_is_honoured_and_says_so(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    committed, local = _dirs(tmp_path)

    with caplog.at_level("WARNING", logger="eval_resolver"):
        pages = load_scraped_pages(committed_dir=committed, local_dir=local, allow_local_override=True)

    assert [element["id"] for element in pages[DASHBOARD]] == ["transfer-link-old"]
    assert "is being USED because" in caplog.text, caplog.text


def test_the_committed_captures_are_read_before_a_local_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The default directories come from the repository, not the working tree."""
    import eval_resolver

    committed, local = _dirs(tmp_path)
    monkeypatch.setattr(eval_resolver, "_COMMITTED_CAPTURES_DIR", committed)
    monkeypatch.setattr(eval_resolver, "_SCRAPED_DIR", local)
    monkeypatch.delenv("AITEST_ALLOW_LOCAL_CAPTURES", raising=False)

    pages = load_scraped_pages()

    assert [element["id"] for element in pages[DASHBOARD]] == ["transfer-link", ""]


def test_two_local_captures_for_one_page_are_reported_not_silently_resolved(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """The working directory can hold two files for one URL; say which one won."""
    committed = tmp_path / "committed"
    committed.mkdir()
    local = tmp_path / "local"
    first = "https://demoqa.com/automation-practice-form"
    _write(local, "a_first.json", first, [COMMITTED_BALANCE])
    _write(local, "b_second.json", first, [STALE_LINK])

    with caplog.at_level("WARNING", logger="eval_resolver"):
        pages = load_scraped_pages(committed_dir=committed, local_dir=local, allow_local_override=False)

    assert [element["id"] for element in pages[first]] == [""]  # a_first kept
    assert "two local captures claim" in caplog.text, caplog.text
    assert "b_second.json" in caplog.text, caplog.text
    assert "committed" in caplog.text and "nothing in the repository is affected" in caplog.text
