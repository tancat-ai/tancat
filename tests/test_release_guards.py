"""j-0313: the release guards refuse what must not reach PyPI.

Each guard is tested for the message it prints and the state it refuses, and the
workflow itself is parsed so the publish job cannot quietly lose its trusted-
publishing identity.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import release_guards as G  # type: ignore[import-not-found]  # noqa: E402

WORKFLOW = ROOT / ".github" / "workflows" / "release.yml"


def _dist(tmp_path: Path, files: dict[str, int]) -> Path:
    dist = tmp_path / "dist"
    dist.mkdir()
    for name, size in files.items():
        path = dist / name
        with path.open("wb") as handle:
            handle.truncate(size)
    return dist


def test_the_tag_must_match_the_packaged_version() -> None:
    ok, message = G.tag_matches_version("v9.9.9", ROOT)
    assert not ok
    assert "does not match the packaged version" in message
    assert "[project].version" in message

    version = G.packaged_version(ROOT)
    assert G.tag_matches_version(f"v{version}", ROOT)[0]


def test_a_file_at_the_limit_is_refused_and_the_sizes_are_printed(tmp_path: Path) -> None:
    dist = _dist(tmp_path, {"ok.whl": 1024, "huge.tar.gz": 101 * 1024 * 1024})

    ok, message = G.files_within_limit(dist)

    assert not ok
    assert "100 MB limit" in message
    assert "huge.tar.gz" in message and "101.00 MB" in message
    assert "ok.whl" in message, "the sizes must be printed whether or not anything fails"


def test_a_dist_with_no_files_is_refused(tmp_path: Path) -> None:
    empty = tmp_path / "dist"
    empty.mkdir()

    ok, message = G.files_within_limit(empty)

    assert not ok
    assert "nothing to publish" in message


def test_the_licence_record_check_passes_on_this_tree() -> None:
    ok, message = G.licence_record_ok(ROOT)

    assert ok, message
    assert "matches uv.lock" in message


def test_a_commit_not_on_main_is_refused() -> None:
    """The guard reads a real git ref; a branch name that is not an ancestor fails."""
    ok, message = G.tag_is_on_main(ROOT, base="refs/heads/definitely-not-a-branch")

    assert not ok
    assert "must be tagged on main" in message


def test_run_guards_stops_at_the_first_refusal(tmp_path: Path) -> None:
    dist = _dist(tmp_path, {"huge.tar.gz": 101 * 1024 * 1024})

    ok, lines = G.run_guards("v9.9.9", dist, ROOT)

    assert not ok
    assert len(lines) == 1, "a refusal must stop the run, not carry on to the next guard"
    assert "REFUSED" in lines[0]


def test_the_workflow_publishes_with_trusted_publishing() -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    publish = workflow["jobs"]["publish"]

    assert publish["environment"]["name"] == "pypi"
    assert publish["permissions"]["id-token"] == "write"
    assert publish["needs"] == "build"
    steps = publish["steps"]
    uses = [step.get("uses", "") for step in steps]
    assert any("pypa/gh-action-pypi-publish" in use for use in uses)
    assert "dist/" in str(steps), "the publish step must name the built files"

    # No token may be stored: the point of trusted publishing.
    text = WORKFLOW.read_text(encoding="utf-8")
    for forbidden in ("PYPI_API_TOKEN", "password:", "TWINE_PASSWORD", "secrets.PYPI"):
        assert forbidden not in text, f"the workflow stores a publishing credential: {forbidden}"


def test_the_workflow_runs_the_guards_before_the_publish() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "scripts/release_guards.py" in text
    assert text.index("release_guards.py") < text.index("gh-action-pypi-publish")


def test_the_tag_trigger_covers_versions_and_excludes_the_floating_tag() -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    tags = workflow[True]["push"]["tags"]  # YAML 1.1 reads the `on:` key as True

    assert "v*" in tags
    assert "!v1" in tags


# -- j-0313 review: the BUILT wheel must carry the identity, not just the config --


@pytest.fixture(scope="module")
def built_wheel(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Build the wheel once and return its path (the artefact, not the config)."""
    out = tmp_path_factory.mktemp("dist")
    result = subprocess.run(
        ["uv", "build", "--wheel", "--out-dir", str(out)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=600,
    )
    if result.returncode != 0:
        pytest.skip(f"could not build a wheel here: {result.stderr[-300:]}")
    wheels = sorted(out.glob("*.whl"))
    assert wheels, "the build produced no wheel"
    return wheels[0]


def _metadata_lines(wheel: Path) -> dict[str, list[str]]:
    import zipfile

    with zipfile.ZipFile(wheel) as archive:
        name = next(name for name in archive.namelist() if name.endswith("METADATA"))
        text = archive.read(name).decode("utf-8")
    fields: dict[str, list[str]] = {}
    for line in text.splitlines():
        if ": " in line and not line.startswith(" "):
            key, value = line.split(": ", 1)
            fields.setdefault(key, []).append(value)
    return fields


def test_the_built_wheel_declares_our_project_urls(built_wheel: Path) -> None:
    """A flat project_urls key inside [project] is not PEP 621, so hatchling drops it."""
    fields = _metadata_lines(built_wheel)
    url_lines = fields.get("Project-URL", [])

    assert "Repository, https://github.com/tancat-ai/tancat" in url_lines, url_lines
    assert "Homepage, https://tancat.dev" in url_lines, url_lines
    assert fields.get("Name") == ["tancat"], fields.get("Name")


def test_the_built_wheel_passes_the_products_own_identity_check(built_wheel: Path) -> None:
    """The update check reads a published answer; ours must not look foreign."""
    from src import version_check

    fields = _metadata_lines(built_wheel)
    urls: dict[str, str] = {}
    for line in fields.get("Project-URL", []):
        label, _, value = line.partition(", ")
        urls[label] = value
    feed = {
        "info": {
            "name": (fields.get("Name") or [""])[0],
            "version": (fields.get("Version") or [""])[0],
            "author_email": (fields.get("Author-email") or [""])[0],
            "project_urls": urls,
        }
    }

    assert version_check.identity_matches(feed), feed
    assert version_check.is_newer((fields.get("Version") or ["0"])[0], "0.9.0")
