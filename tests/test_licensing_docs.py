"""The licensing docs must describe the licence we ship, and cover every module.

t-1505: four `markdown_docs` pages still described the deleted Ed25519 signed-file
mechanism as the live one, and activation, entitlement, window, merchant and pricing
had no page at all. A stale module doc is worse than none: it is where the next person
looks first.

These tests fail on:
- a licensing module with no page;
- a page that names the deleted mechanism as if it were current;
- the sweep index losing an entry (so `document-manager` stops regenerating it).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE = REPO_ROOT / "src" / "licensing"
DOCS = REPO_ROOT / "markdown_docs" / "src" / "licensing"
SWEEP = REPO_ROOT / "markdown_docs" / ".sweep_progress.json"

#: Modules that must have a page, because a person changing licensing reads them.
REQUIRED = (
    "__init__.py",
    "activation.py",
    "entitlement.py",
    "license.py",
    "merchant.py",
    "pricing.py",
    "tiers.py",
    "window.py",
)

#: Words that describe the DELETED mechanism. A page may mention them only while
#: saying they are gone: "deleted", "gone", "removed" or "no longer" in the same
#: sentence is fine; a bare claim that the licence is a signed file is not.
DELETED_WORDS = ("ed25519", "signed licence file", "signed file", "vendored public key")

GONE = re.compile(r"\b(deleted|gone|removed|no longer|replaced|is not|are not)\b", re.IGNORECASE)


def _modules() -> list[str]:
    return sorted(path.name for path in PACKAGE.glob("*.py"))


def _page(module: str) -> Path:
    return DOCS / f"{module}.md"


@pytest.mark.parametrize("module", REQUIRED)
def test_every_licensing_module_has_a_page(module: str) -> None:
    assert _page(module).exists(), f"no markdown_docs page for src/licensing/{module}"


def test_no_licensing_behaviour_is_undocumented() -> None:
    """A module added tomorrow fails here rather than living without a page."""
    undocumented = [module for module in _modules() if not _page(module).exists()]
    assert undocumented == [], f"licensing module(s) with no page: {undocumented}"


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", " ".join(text.split())) if part.strip()]


def test_no_page_claims_the_deleted_mechanism_is_the_live_one() -> None:
    offenders: dict[str, str] = {}
    for path in sorted(DOCS.glob("*.md")):
        for sentence in _sentences(path.read_text(encoding="utf-8")):
            lowered = sentence.lower()
            if any(word in lowered for word in DELETED_WORDS) and not GONE.search(sentence):
                offenders[f"{path.name}: {sentence[:80]}"] = "states the deleted mechanism as current"
                break
    assert offenders == {}, f"docs describe the deleted signed-file mechanism as live: {offenders}"


def test_the_pages_state_the_key_flow() -> None:
    """The three sentences a reader needs, somewhere in the licensing docs."""
    corpus = " ".join(path.read_text(encoding="utf-8").lower() for path in sorted(DOCS.glob("*.md")))
    for phrase in ("activated once", "checked", "offline"):
        assert phrase in corpus, f"the licensing docs never say {phrase!r}"


def test_the_sweep_index_covers_the_package() -> None:
    data = json.loads(SWEEP.read_text(encoding="utf-8"))
    indexed = {entry["source"] for entry in data["files"]}
    missing = [f"src/licensing/{module}" for module in _modules() if f"src/licensing/{module}" not in indexed]
    assert missing == [], f"the documentation sweep index has no entry for: {missing}"
