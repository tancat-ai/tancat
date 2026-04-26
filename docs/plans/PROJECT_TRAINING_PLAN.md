# Project Training Plan

This plan is designed to help you move through the project in a practical order:

1. Understand what the project does
2. Explain how it works
3. Modify it safely
4. Rebuild smaller versions of it
5. Eventually rewrite the whole project with confidence

Use this as a working checklist. Tick items off as you complete them.

## Contents

1. [How To Use This Plan](#how-to-use-this-plan)
2. [Learning Goals](#learning-goals)
3. [Project Map](#project-map)
4. [If You Get Stuck On X](#if-you-get-stuck-on-x)
5. [Phase 0 - Setup And Orientation](#phase-0---setup-and-orientation)
6. [Phase 1 - Python And Tooling Foundations](#phase-1---python-and-tooling-foundations)
7. [Phase 2 - Playwright And Pytest Foundations](#phase-2---playwright-and-pytest-foundations)
8. [Phase 3 - Understand This Project End To End](#phase-3---understand-this-project-end-to-end)
9. [Phase 4 - UI, CLI, Reporting, And CI-CD](#phase-4---ui-cli-reporting-and-ci-cd)
10. [Phase 5 - Explain The Project Clearly](#phase-5---explain-the-project-clearly)
11. [Phase 6 - Build Smaller Versions From Scratch](#phase-6---build-smaller-versions-from-scratch)
12. [Phase 7 - Rewrite Readiness](#phase-7---rewrite-readiness)
13. [Weekly Cadence](#weekly-cadence)
14. [Progress Scorecard](#progress-scorecard)

## How To Use This Plan

- Work through one phase at a time.
- Do not rush past exercises just because you can read the code.
- Write short notes in your own words as you go.
- If a term or file confuses you, jump to [If You Get Stuck On X](#if-you-get-stuck-on-x).
- If you finish a phase but still cannot explain it simply, repeat the phase before moving on.

## Learning Goals

By the end of this plan, you should be able to:

- Explain the purpose of every major folder in the repository
- Describe the full pipeline from user story to generated Playwright test
- Write Playwright pytest sync tests without AI help
- Understand how scraping, placeholder resolution, and reporting fit together
- Explain how the UI, CLI, tests, and CI/CD support the core pipeline
- Rebuild a smaller version of the project from scratch
- Plan a rewrite of the full project in safe phases

## Project Map

Use this as your first reference when you are unsure where something belongs.

| Area | Main Files | Why It Matters |
|---|---|---|
| High-level docs | `README.md`, `docs/ARCHITECTURE.md`, `AGENTS.md` | Explain the project shape, rules, and architecture |
| Streamlit UI | `streamlit_app.py` | Main user-facing interface |
| CLI | `cli/main.py`, `cli/` | Command-line entry point and automation path |
| Core orchestration | `src/orchestrator.py` | Coordinates the full generation pipeline |
| Story analysis | `src/spec_analyzer.py`, `src/user_story_parser.py` | Turns raw story text into structured test conditions |
| LLM integration | `src/llm_client.py`, `src/llm_errors.py` | Handles LLM calls and related failures |
| Test generation | `src/test_generator.py`, `src/prompt_utils.py` | Produces test skeletons and prompt content |
| Scraping and context | `src/scraper.py`, `src/stateful_scraper.py` | Collects page information used after generation |
| Placeholder resolution | `src/skeleton_parser.py`, `src/placeholder_resolver.py` | Maps placeholders to real locators |
| Test structure output | `src/page_object_builder.py`, `src/pipeline_writer.py` | Creates generated files and page objects |
| Execution and reporting | `src/pipeline_run_service.py`, `src/pipeline_report_service.py`, `src/pytest_output_parser.py` | Runs tests, parses output, builds reports |
| Data models | `src/pipeline_models.py`, `src/test_plan.py` | Defines project data shapes |
| Quality gates | `tests/`, `pyproject.toml`, `.github/workflows/ci.yml` | Protect correctness and maintainability |

## If You Get Stuck On X

Use this as a quick index when you hit something confusing.

| If you do not understand... | Read these first |
|---|---|
| What the project does overall | `README.md`, `docs/ARCHITECTURE.md` |
| Project rules and constraints | `AGENTS.md` |
| How the UI triggers the pipeline | `streamlit_app.py`, `src/orchestrator.py` |
| How the CLI differs from the UI | `cli/main.py`, `cli/`, `src/orchestrator.py` |
| How a user story becomes test conditions | `src/spec_analyzer.py`, `src/user_story_parser.py` |
| How the LLM is used | `src/llm_client.py`, `src/test_generator.py`, `src/prompt_utils.py` |
| Why the project uses placeholders first | `docs/ARCHITECTURE.md`, `src/skeleton_parser.py`, `src/placeholder_resolver.py` |
| How scraping works | `src/scraper.py`, `src/stateful_scraper.py` |
| How generated files are written | `src/pipeline_writer.py`, `generated_tests/` |
| Page Object Model generation | `src/page_object_builder.py`, generated `pages/*.py` examples |
| How reports are built | `src/pipeline_report_service.py`, `src/report_builder.py`, `src/report_formatters.py` |
| How pytest output is parsed | `src/pytest_output_parser.py`, `tests/test_pytest_output_parser.py` |
| How evidence and coverage work | `src/evidence_tracker.py`, `src/coverage_utils.py`, related tests |
| How tests protect the codebase | `tests/`, especially module-matching test files |
| How CI/CD fits in | `.github/workflows/ci.yml`, `pyproject.toml`, `.pre-commit-config.yaml` |

## Phase 0 - Setup And Orientation

Goal: get the project running and know where things are.

### Checklist

- [ ] Read `README.md`
- [ ] Read `docs/ARCHITECTURE.md`
- [ ] Read `AGENTS.md`
- [ ] Run `uv sync`
- [ ] Activate the virtual environment
- [ ] Run `playwright install chromium`
- [ ] Confirm `.env` exists and understand the important variables
- [ ] Run `pytest -v`
- [ ] Start the app once
- [ ] Write a one-paragraph summary of what the project does

### Deliverable

- [ ] A note in your own words answering: "What does this project do, who is it for, and what problem is it solving?"

## Phase 1 - Python And Tooling Foundations

Goal: understand the language and tooling this repo depends on.

### Topics

- Python functions, classes, dataclasses, typing, imports, exceptions
- Reading and writing files
- Virtual environments and dependencies
- `uv`, `pytest`, `ruff`, `mypy`

### Checklist

- [ ] Learn what type hints are and why this repo enforces them
- [ ] Learn how imports work across `src/`, `cli/`, and `tests/`
- [ ] Read `pyproject.toml`
- [ ] Read `.pre-commit-config.yaml`
- [ ] Run `ruff check`
- [ ] Run `mypy`
- [ ] Open 3 test files and match them to the source modules they protect
- [ ] Explain the difference between linting, type checking, and testing

### Exercises

- [ ] Pick one small module in `src/` and explain every function inside it
- [ ] Trace one import chain from `streamlit_app.py` into `src/`
- [ ] Write a short note on why `streamlit_app.py` should not contain testable helper logic

### Milestone Check

- [ ] I can explain what `uv`, `pytest`, `ruff`, and `mypy` each do
- [ ] I can navigate the repo without guessing where things live

## Phase 2 - Playwright And Pytest Foundations

Goal: become comfortable with the kind of tests this project generates.

### Topics

- Playwright sync API for Python
- `pytest` test structure and fixtures
- Locators, assertions, waiting, navigation, forms
- Why this project forbids async Playwright tests in generated output

### Checklist

- [ ] Learn the Playwright sync fixture style used by pytest
- [ ] Learn common locator patterns: role, text, label, id, CSS locator
- [ ] Learn when waiting is needed and when it is a smell
- [ ] Read at least 2 generated test examples under `generated_tests/`
- [ ] Compare generated tests to the project rules in `AGENTS.md`
- [ ] Read `pytest.ini`
- [ ] Read `tests/conftest.py`

### Exercises

- [ ] Hand-write one small Playwright pytest sync test against a simple page
- [ ] Hand-write a second test using better locators than text-only selectors
- [ ] Explain why `async def test_...` is not allowed here
- [ ] Explain why "real selectors from the DOM" matter more than LLM-guessed selectors

### Milestone Check

- [ ] I can write a simple Playwright pytest sync test from scratch
- [ ] I can explain the difference between a fragile locator and a robust locator

## Phase 3 - Understand This Project End To End

Goal: understand the project pipeline in the order it runs.

### Recommended Reading Order

- [ ] `src/pipeline_models.py`
- [ ] `src/orchestrator.py`
- [ ] `src/spec_analyzer.py`
- [ ] `src/test_generator.py`
- [ ] `src/skeleton_parser.py`
- [ ] `src/scraper.py`
- [ ] `src/stateful_scraper.py`
- [ ] `src/placeholder_resolver.py`
- [ ] `src/page_object_builder.py`
- [ ] `src/pipeline_writer.py`
- [ ] `src/pipeline_run_service.py`
- [ ] `src/pipeline_report_service.py`

### Understanding Tasks

- [ ] Identify where raw user story text first enters the system
- [ ] Identify where acceptance criteria become structured data
- [ ] Identify where the LLM is called
- [ ] Identify where placeholders are created
- [ ] Identify where placeholders are resolved into locators
- [ ] Identify where page objects are created
- [ ] Identify where generated test files are written
- [ ] Identify where run results are parsed and reported

### Exercises

- [ ] Draw the pipeline from memory
- [ ] Trace one story through the full system from input to saved generated test
- [ ] Write a plain-English explanation of the "skeleton-first" pipeline
- [ ] Explain why selector data is not injected straight into the LLM prompt

### Milestone Check

- [ ] I can explain the full pipeline in 5 minutes without opening files
- [ ] I know which modules are core to generation versus reporting versus UI

## Phase 4 - UI, CLI, Reporting, And CI-CD

Goal: understand how the project is operated and validated.

### UI And CLI

- [ ] Read `streamlit_app.py`
- [ ] Read `cli/main.py`
- [ ] Read 2-3 related files under `cli/`
- [ ] Explain what logic belongs in the interface versus the core modules
- [ ] Explain how the Streamlit rerun model affects state handling

### Reporting And Evidence

- [ ] Read `src/pytest_output_parser.py`
- [ ] Read `src/pipeline_report_service.py`
- [ ] Read `src/evidence_tracker.py`
- [ ] Read `src/coverage_utils.py`
- [ ] Open their matching tests in `tests/`
- [ ] Explain what evidence, coverage, and reports add beyond test generation

### CI/CD And Project Quality

- [ ] Read `.github/workflows/ci.yml`
- [ ] Read `pyproject.toml` again with CI in mind
- [ ] Explain what should happen on a pull request
- [ ] Explain why CI needs linting, typing, and tests instead of only tests

### Milestone Check

- [ ] I can explain the difference between local validation and CI validation
- [ ] I can explain how UI, CLI, and CI all rely on the same core modules

## Phase 5 - Explain The Project Clearly

Goal: turn understanding into clear communication.

### Exercises

- [ ] Write a 10-sentence summary of the project for a non-technical person
- [ ] Write a 10-sentence summary of the architecture for a developer
- [ ] Explain the project aloud as if teaching a teammate
- [ ] Explain what problem each major folder solves
- [ ] Explain one full generated test run from start to finish using file names

### Explanation Prompts

Use these prompts to test yourself:

- [ ] "Why does this project need both scraping and an LLM?"
- [ ] "Why not ask the LLM to generate the final selectors directly?"
- [ ] "Why are generated tests separated from the tool's own test suite?"
- [ ] "Why is there both a Streamlit app and a CLI?"
- [ ] "Why are `ruff`, `mypy`, and `pytest` all important here?"

### Milestone Check

- [ ] I can explain the project simply to both a beginner and a developer

## Phase 6 - Build Smaller Versions From Scratch

Goal: prove your understanding by rebuilding the ideas in simpler form.

Build these in order. Keep each mini-project small.

### Mini Project 1 - Static Test Writer

- [ ] Build a script that takes a text prompt and writes a fixed pytest file
- [ ] Keep it simple: no scraping, no LLM, no UI
- [ ] Explain what this version is missing

### Mini Project 2 - Story To Skeleton

- [ ] Take a small user story and generate test skeleton functions
- [ ] Use placeholder text instead of real selectors
- [ ] Explain how this mirrors the real project's first phase

### Mini Project 3 - Placeholder Resolver

- [ ] Create a fake set of scraped elements
- [ ] Resolve placeholders against that fake element data
- [ ] Explain how this mirrors the real project's second phase

### Mini Project 4 - Simple CLI

- [ ] Add a command-line wrapper for the mini pipeline
- [ ] Accept input story text and output a test file

### Mini Project 5 - Simple UI

- [ ] Add a tiny Streamlit UI
- [ ] Keep logic outside the UI file where possible

### Mini Project 6 - Reporting

- [ ] Add a basic run summary
- [ ] Parse test output or fake a result model
- [ ] Show pass/fail information in a simple report

### Milestone Check

- [ ] I can rebuild the important ideas without copying this repo line by line

## Phase 7 - Rewrite Readiness

Goal: prepare for a full rewrite without jumping in blindly.

### Analysis Checklist

- [ ] List the modules you would keep as-is
- [ ] List the modules you would simplify
- [ ] List the modules you would redesign
- [ ] Identify technical debt, duplication, and confusing boundaries
- [ ] Identify what the absolute minimum viable rewrite would include
- [ ] Identify what should stay out of version 1 of a rewrite

### Planning Checklist

- [ ] Break the rewrite into phases
- [ ] Decide what can be reused and what should be replaced
- [ ] Decide how to validate correctness during the rewrite
- [ ] Decide what tests must exist before large refactors
- [ ] Write a "rewrite risks" list

### Final Readiness Questions

- [ ] Can I explain the current architecture without notes?
- [ ] Can I build a smaller clone from scratch?
- [ ] Can I say what I would change and why?
- [ ] Can I rewrite one slice safely without breaking the rest?

## Weekly Cadence

Use this pace if you want steady progress without overload.

### Each Week

- [ ] 2 study sessions reading code and docs
- [ ] 2 practical sessions writing code or tests
- [ ] 1 session explaining concepts aloud or in notes
- [ ] 1 session reviewing tests, CI, or tooling
- [ ] 1 recap session: what I now understand, what is still fuzzy, what to revisit next week

### Suggested Rule

- [ ] Do not move on until I can explain the current phase simply

## Progress Scorecard

Use this section to self-assess honestly.

### Level 1 - Orientation

- [ ] I know what the project does
- [ ] I can run it locally
- [ ] I know where the major files are

### Level 2 - Code Reading

- [ ] I can trace behavior across multiple modules
- [ ] I understand the role of the orchestrator
- [ ] I understand the skeleton-first pipeline

### Level 3 - Testing And Tooling

- [ ] I can write Playwright pytest sync tests
- [ ] I can run and interpret `ruff`, `mypy`, and `pytest`
- [ ] I understand why CI/CD is structured the way it is

### Level 4 - Ownership

- [ ] I can explain the system clearly
- [ ] I can make safe changes to it
- [ ] I can debug issues by following the pipeline

### Level 5 - Rewrite Readiness

- [ ] I can build a smaller version of the project myself
- [ ] I can propose a rewrite plan with clear phases
- [ ] I would be comfortable rewriting the project slice by slice
