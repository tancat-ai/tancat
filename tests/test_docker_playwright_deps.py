"""The images install what Playwright 1.65's bundled Node needs, in the right order.

Playwright 1.65 links the driver's Node against libatomic.so.1. `install-deps` lists
`libatomic1` from that version, but it starts the bundled Node before it installs
anything, so on a bare base image it dies before it can install the library it needs
(t-1533, reproduced: exit 127 on python:3.14.7-slim).

These tests hold the order in both images: the explicit `libatomic1` install must come
*after* the venv is in place and *before* `playwright install-deps`.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
IMAGES = ("Dockerfile", "Dockerfile.action")


@pytest.mark.parametrize("name", IMAGES)
def test_the_image_installs_libatomic1_before_install_deps(name: str) -> None:
    text = (REPO_ROOT / name).read_text(encoding="utf-8")
    lines = text.splitlines()

    install_deps = next(i for i, line in enumerate(lines) if "playwright install-deps" in line)
    libatomic = [i for i, line in enumerate(lines) if "libatomic1" in line and not line.lstrip().startswith("#")]

    assert libatomic, f"{name} does not install libatomic1 - Playwright 1.65's Node needs it"
    assert min(libatomic) < install_deps, (
        f"{name}: libatomic1 must be installed BEFORE `playwright install-deps` "
        "(that command runs the bundled Node before it installs anything)"
    )


@pytest.mark.parametrize("name", IMAGES)
def test_the_reason_is_written_down(name: str) -> None:
    """The comment is the part that stops the next person deleting the line."""
    text = (REPO_ROOT / name).read_text(encoding="utf-8")
    assert "Playwright 1.65" in text and "chicken-and-egg" in text, (
        f"{name}: the libatomic1 line has no comment saying why it is there"
    )


def test_the_dependency_note_records_the_inert_wait() -> None:
    """1.65 changes when an action runs; a generated test may start timing out."""
    note = (REPO_ROOT / "docs" / "implementation" / "dependency-notes.md").read_text(encoding="utf-8")
    for phrase in ("non-inert", "RFC 6265", "Proxy credentials", "get_by_ref", "normalize()"):
        assert phrase in note, f"dependency-notes.md does not record: {phrase}"
