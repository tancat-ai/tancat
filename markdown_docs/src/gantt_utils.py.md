# `src/gantt_utils.py`

## Purpose
Builds Gantt-style timelines from EvidenceTracker sidecars (.evidence.json). Visualizes test execution timeline using Plotly horizontal bar charts.

## Metadata
- **Lines:** 194
- **Imports:** json, dataclasses.dataclass, pathlib.Path, typing.Any|Literal, pandas, plotly.express, plotly.graph_objects

## Classes/Dataclasses
| Class | Description |
|-------|-------------|
| `GanttEntry` | Frozen dataclass: test_name, condition_ref, story_ref, status, duration_s |

## Type Aliases
| Type | Values |
|------|--------|
| `GroupingMode` | Literal["condition_type", "sprint", "source"] |

## Functions
| Function | Description |
|----------|-------------|
| `safe_read_sidecar(path)` | Reads JSON sidecar file — returns None if missing or invalid |
| `load_gantt_entries(evidence_dir)` | Loads all *.evidence.json from directory into GanttEntry list |
| `build_gantt_summary_sentences(entries, total_expected)` | Returns (fastest, slowest, coverage) summary tuple |
| `group_gantt_entries(entries, mode, condition_meta)` | Groups entries by condition_type/sprint/source with stable sorting |
| `build_gantt_chart(entries, grouping_mode, condition_meta)` | Builds Plotly horizontal bar chart (go.Figure) from entries |

## Key Logic
- Reads `.evidence.json` sidecars for test metadata (name, condition_ref, story_ref, status, duration_s)
- Summary sentences: fastest/slowest by duration_s, coverage as executed/expected percentage
- Grouping uses optional `condition_meta` dict keyed by condition_ref with type/sprint/source fields
- Sort within groups: status ASC, duration_s DESC, condition_ref ASC
- Chart uses `px.bar` with `base="Start"` for Gantt-style floating bars (avoids px.timeline date-casting issues)
- Color mapping: passed=green, failed=red, skipped=yellow, pending=gray, unknown=cyan
- Dynamic chart height: min(800, 300 + len(entries)*25)