# `scripts/3d map/audit_3d_map.py`

## High-Level Purpose

**Architectural audit of the 3D map** — validates the generated
`docs/nodes.csv` + `docs/links.csv` (produced by `generate_3d_map.py`) against
architectural invariants:

- every node has a label and a resolvable path
- no orphan links (source/target both exist as nodes)
- layer assignments are sane (known layer names only)
- duplicate labels are reported (ambiguous nodes break the visualisation)

Run after regenerating the map:

```
python "scripts/3d map/audit_3d_map.py"
```

## Module Metadata

- **Lines:** ~180
- **Imports:** `csv`, `os`, `collections`
- **Spec:** companion to `generate_3d_map.py` — keeps the Cosmograph dataset
  trustworthy
- **Maintained:** 2026-08-12 (doc added; logic unchanged since 2026-05)

## Public API

No importable API — run as a script. Internally loads `docs/nodes.csv` and
`docs/links.csv` and prints a report of violations; exits non-zero when the
dataset is broken.

## Design Notes

- Pure CSV audit — no browser, no graph library; the 3D map stays
  auditable in CI.
- The map data (`docs/nodes.csv`, `docs/links.csv`,
  `scripts/3d_map_data.json`) is committed, so the audit can run on a clean
  checkout.
