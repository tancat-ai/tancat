# `src/agents/pipeline_state.py`

## Purpose

Dataclass definitions for the full-pipeline LangGraph state. Distinct from `src/agents/state.py` (`WorkflowState`) which covers only the skeleton-generation sub-phase.

## Key Classes

### `Criterion`
Single test criterion extracted from user story analysis.

| Field | Type | Description |
|---|---|---|
| `ref` | `str` | Unique ID (e.g. `TC01.03`) |
| `description` | `str` | Human-readable condition text |
| `condition_type` | `str` | `happy_path`, `boundary`, `negative`, `exploratory`, `ambiguity` |
| `priority` | `str` | `high`, `medium`, `low` |
| `needs_clarification` | `bool` | True if tester must review before generation |
| `prerequisite_refs` | `list[str]` | Refs of criteria that must execute first |

### `StoryAnalysis`
Output of the Ingestion Agent.

| Field | Type | Description |
|---|---|---|
| `story_text` | `str` | Original user story |
| `criteria` | `list[Criterion]` | Extracted criteria |
| `domain_terms` | `list[str]` | RAG-retrieved domain vocabulary |
| `assumptions` | `list[str]` | Inferred assumptions |
| `source_format` | `str` | `gherkin`, `jira`, `free-form`, `numbered` |

### `PipelineState`
Typed state flowing through all nodes of the multi-agent graph. Serializable for LangGraph checkpointing.

Key fields:
- **Input:** `user_story`, `base_url`, `additional_urls`, `pom_mode`
- **Intermediate:** `story_analysis`, `test_conditions`, `plan_confirmed`, `scraped_pages`
- **Output:** `test_code`, `pom_classes`, `unresolved_placeholders`, `errors`
- **Control:** `max_retries`, `auto_confirm`

## Dependencies

- `dataclasses` (stdlib)
- `typing.Any`


## Recent API Additions

Symbols present in the source but not covered above (refresh pass, 4 items):

### `DataSchemaChange` (class)

A single data schema modification extracted from a spec document.

### `ChangeDelta` (class)

A single change extracted from a spec document.

### `ImpactMap` (class)

Cross-reference of changes to affected test areas.

### `ConsolidatedReport` (class)

Final output of the document-driven pipeline.
