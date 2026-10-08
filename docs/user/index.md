# TanCat user documentation

TanCat generates executable Playwright pytest tests from a user story. You paste
a story, point it at your own LLM, and it writes tests whose selectors come from
the real page, not from the model's imagination.

These are the user docs. The launch set takes you from a fresh checkout to a
passing test you can read and trust.

## Get started

- [What TanCat is](getting-started/what-is-tancat.md) - the one-screen summary.
- [Install](getting-started/install.md) - requirements, `uv sync`, Chromium, Docker.
- [Configure your LLM](getting-started/configure-llm.md) - llama.cpp, Ollama, LM Studio, cloud.
- [Your first run](getting-started/first-run.md) - one story end to end, with expected output.

## Guides

- [How the pipeline works](guides/pipeline.md) - the stages, in plain words.
- [Placeholders, resolution and skips](guides/skips.md) - why an unresolved criterion skips instead of passing.
- [Evidence and reports](guides/evidence.md) - sidecars, screenshots, heat maps, Gantt, HTML.

## Reference

- [Licensing and tiers](reference/licensing.md) - free caps, installing a key, what Pro adds.

!!! note "Where the rest lives"
    Internal engineering material - architecture, specs, session logs, the
    roadmap - is not part of these docs. It stays in the repository for
    maintainers.
