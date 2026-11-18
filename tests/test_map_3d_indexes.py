"""The 3D map indexes describe the repository, not somebody's working tree (t-1440).

``scripts/map_3d/generate_3d_map.py`` used to walk the filesystem, so whatever
happened to be in the working tree went into files that are committed and published:
1,102 of the 2,457 node paths existed only on the machine that ran it - 1,077 under
``exported_tests/``, 21 captured scrapes under ``scripts/eval/scraped_pages/`` and 4
private research notes under ``docs/private/``. The public map named internal notes,
and nobody else could reproduce the files.

Two invariants now hold, and this test is the one that fails if they stop holding:

1. every path in the indexes is a **tracked** path - so the generator's output
   depends only on the repository;
2. no path under a directory that must never be indexed appears, even if a file in
   it were tracked one day.
"""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAP_DIR = ROOT / "scripts" / "map_3d"
NODES = ROOT / "docs" / "nodes.csv"
LINKS = ROOT / "docs" / "links.csv"
MAP_JSON = ROOT / "scripts" / "3d_map_data.json"

#: Directories that are internal or captured, and must never reach a published map.
NEVER_INDEXED = ("docs/private/", "exported_tests/", "scripts/eval/scraped_pages/", "graphify-out/")


def _tracked() -> set[str]:
    result = subprocess.run(["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True)
    return {name for name in result.stdout.decode("utf-8").split("\0") if name}


def _label(value: str) -> str:
    return value[2:] if value.startswith("./") else value


def _node_labels() -> list[str]:
    with NODES.open(encoding="utf-8", newline="") as handle:
        return [_label(row["label"]) for row in csv.DictReader(handle)]


def _link_rows() -> list[dict[str, str]]:
    with LINKS.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_the_index_matches_the_repository_exactly() -> None:
    """Both directions: nothing indexed that git lacks, nothing tracked that is missing.

    One direction (indexed must be tracked) let a stale index pass: a file added since
    the last regeneration was simply absent, and absence is not a broken reference
    (t-1446). The expectation is the generator's own selection, imported rather than
    re-implemented, so the two cannot drift.
    """
    sys.path.insert(0, str(MAP_DIR))
    from index_selection import select_indexed_files

    expected = {_label(label) for label in select_indexed_files(ROOT)}
    indexed = set(_node_labels())

    extra = sorted(indexed - expected)
    missing = sorted(expected - indexed)

    assert extra == [] and missing == [], (
        "the 3D map is out of date with the repository - regenerate it from a clean checkout. "
        f"indexed but not selectable ({len(extra)}): " + ", ".join(extra[:10]) + " | "
        f"selectable but not indexed ({len(missing)}): " + ", ".join(missing[:10])
    )


def test_every_link_endpoint_is_tracked() -> None:
    tracked = _tracked()
    dangling: list[str] = []
    for row in _link_rows():
        for column in ("source", "target"):
            label = _label(row[column])
            if label not in tracked:
                dangling.append(f"{row['source']} -> {row['target']}")
                break

    assert dangling == [], f"{len(dangling)} link(s) point at paths the repository does not have: " + "; ".join(
        dangling[:10]
    )


def test_no_internal_directory_reaches_the_map() -> None:
    """Private notes and captured data are not architecture, tracked or not."""
    offenders: list[str] = []
    for label in _node_labels():
        if label.startswith(NEVER_INDEXED):
            offenders.append(label)
    for row in _link_rows():
        for column in ("source", "target"):
            label = _label(row[column])
            if label.startswith(NEVER_INDEXED):
                offenders.append(label)

    assert offenders == [], f"{len(offenders)} internal path(s) in the published map: " + ", ".join(
        sorted(set(offenders))[:10]
    )


def test_the_json_and_the_csvs_agree() -> None:
    """Three files, one graph: a refresh that writes only some of them is a lie."""
    data = json.loads(MAP_JSON.read_text(encoding="utf-8"))
    labels = _node_labels()

    assert len(data["nodes"]) == len(labels), f"{len(data['nodes'])} JSON nodes vs {len(labels)} in nodes.csv"
    assert len(data["links"]) == len(_link_rows()), "the JSON and links.csv disagree on the link count"

    json_labels = {_label(node["label"]) for node in data["nodes"]}
    assert json_labels == set(labels), "the JSON and nodes.csv describe different files"
