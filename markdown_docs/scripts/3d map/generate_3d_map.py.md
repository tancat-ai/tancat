# `scripts/3d map/generate_3d_map.py`

## High-Level Purpose

**3D architecture map generator** — produces the nodes/links dataset the
Cosmograph 3D graph visualizer consumes:

- `docs/nodes.csv` — every tracked project file as a node (label, layer/group,
  path)
- `docs/links.csv` — edges: import links (AST-extracted), proximity links
  (same-directory neighbours), and reference links (markdown_docs ↔ source)
- `scripts/3d_map_data.json` — the merged payload for Cosmograph

The `LAYER_MAP` classifies files into architecture layers (interface /
orchestration / intelligence / context / refinement / output / utility); files
not mapped fall back to their directory convention. Kept current with the
module set — regenerate after adding/removing `src/` modules:

```
python "scripts/3d map/generate_3d_map.py"
```

## Module Metadata

- **Lines:** ~640
- **Imports:** `ast`, `csv`, `json`, `os`, `collections`
- **Spec:** architecture-visualization utility; the interactive alternative is
  `graphify-out/callflow.html` (graphify, Mermaid-based)
- **Maintained:** 2026-08-12 (LAYER_MAP caught up to the current module set —
  intelligence 11→24, refinement 7→21, output 5→15, context 4→15,
  orchestration 5→10)

## Public API

No importable API — run as a script. Key internal structures:

### `LAYER_MAP: dict[str, str]`
Path → layer group for every `src/` / `cli/` module. The groups mirror the
architecture: `interface` (Streamlit + CLI), `orchestration` (pipeline
wiring), `intelligence` (LLM, prompts, RAG, learning — incl. `flow_memory`),
`context` (scraping), `refinement` (resolution), `output` (evidence/reports),
`utility` (storage/settings/persistence).

### `ALL_FILES: set[str]`
Every project file discovered by directory scan (git-tracked, filtered for
artifacts: `.xml`, `.lock`, logs, mock HTML).

### Output writers
- nodes: label, clean label, layer group, path
- links: source → target with `link_type` (`import` | `proximity` |
  `references`)
- `3d_map_data.json`: `{nodes, links}` for Cosmograph

## Design Notes

- **Dynamic import extraction:** each `.py` file is parsed with `ast` to find
  real imports — links only exist where both endpoints are real files (dead
  links filtered).
- **Proximity links:** files in the same directory are linked so the graph
  shows neighbourhoods, not just imports.
- **markdown_docs proximity:** each doc references its source module, so the
  3D map shows the documentation layer connected to the code it documents.
- **Audit companion:** `scripts/3d map/audit_3d_map.py` checks the generated
  CSV for architectural invariants (orphan nodes, layer sanity).
