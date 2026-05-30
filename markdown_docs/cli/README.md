# CLI Documentation Summary

This directory documents the `cli/` package for the AI Playwright Test Generator.

## Purpose of the CLI package

The CLI package provides an interactive command-line interface and legacy compatibility layer for:

- configuring LLM providers
- collecting user stories and target URLs
- building living test plans
- running the AI test generation pipeline
- executing generated tests
- generating reports and evidence
- displaying failure diagnostics

## Major modules

- `cli/main.py` — interactive entry point and legacy command parser
- `cli/menu_renderer.py` — retro terminal menu and input collection
- `cli/retro_ui.py` — box-drawing UI rendering primitives
- `cli/session.py` — CLI session state and environment-backed defaults
- `cli/pipeline_runner.py` — pipeline execution, run management, and report lifecycle
- `cli/input_parser.py` — multi-format requirement parsing
- `cli/test_case_orchestrator.py` — legacy test case orchestration
- `cli/evidence_generator.py` — screenshot/evidence capture and packaging
- `cli/report_generator.py` — Jira and markdown report generation
- `cli/color.py` — ANSI styling helpers
- `cli/config.py` — backwards-compatible re-export of shared config values

## Notes

- The CLI shares pipeline behavior with the Streamlit app by invoking core services from `src/`.
- The interactive flow is designed for terminal users, with special handling for Windows Git Bash and ANSI compatibility.
- Legacy CLI commands are retained for backward compatibility while the interactive menu remains the primary experience.
