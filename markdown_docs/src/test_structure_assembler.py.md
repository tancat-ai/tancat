# `src/test_structure_assembler.py`

## High-Level Purpose

`test_structure_assembler.py` rebuilds a generated Playwright test file from its
parsed journey model so that the pipeline — not the LLM — owns the file
structure. LLM skeletons occasionally leak bare executable statements
(`home_page.click(...)`) or dangling decorators OUTSIDE any test function;
those reference fixtures that don't exist at module scope and crash pytest at
COLLECTION time, before any test runs. Sanitizing each leak pattern after the
fact is whack-a-mole; this module instead re-emits only the structural parts
the pipeline controls, making module-level leaks structurally impossible.

The pipeline owns: the header (imports, module constants, module-level helper
`def`/`class` blocks) and, per test, the `@pytest.mark.evidence` decorator plus
the `def` shell. The LLM text only supplies test names, `condition_ref` /
`story_ref` values, and the function body lines (already resolved upstream).

The per-test shell is built with a PEP 750 **t-string** — the decorator and
signature literal text is plain, and the interpolated values are structured
parts, so no `\n` escapes or quote-juggling are needed.

## Module Dependencies

- `re`: extracts `condition_ref` / `story_ref` values from decorator lines.
- `typing.Any`: type hint for the t-string `Template` object in `_render`.
- `.skeleton_parser.SkeletonParser`: parses the generated code into
  `TestJourney` objects (test name, line range, body lines).

## Classes

This module defines no classes.

## Public Functions

### `rebuild_test_structure(code: str) -> str`

Rebuilds the test file from the parsed journey model.

Parameters:

- `code: str`: The fully resolved generated test code (after placeholder
  resolution, evidence-marker injection and normalisation).

Returns:

- `str`: The rebuilt file. Returns the input unchanged when no test functions
  are found (safe fallback — nothing to rebuild).

Key behavior:

- Header (everything before the first test function) is preserved verbatim
  except module-level executable statements and dangling decorators, which are
  dropped by construction.
- Each test function is re-emitted with a canonical t-string shell (decorator +
  `def test_<name>(page: Page, evidence_tracker):`); body lines are taken
  verbatim from the resolved code.
- `condition_ref` / `story_ref` are extracted from the decorator lines directly
  above the `def` (the journey block can extend into the next test's decorator,
  so the whole block is never scanned for refs).
- Decorators and `def` lines written by the LLM inside a block are dropped (the
  assembler re-emits them), while POM instantiation lines, resolved steps,
  `pytest.skip` calls and comments are preserved.

## Private Helpers

### `_render(tpl: Any) -> str`

Interleaves `Template.strings` + `Template.interpolations` into plain text.
PEP 750 t-strings produce a `Template` whose `values` only contains the
evaluated interpolations; the literal text lives in `strings`, so reassembly
must interleave the two.

### `_build_shell(condition_ref: str, story_ref: str, test_name: str) -> str`

Returns the pipeline-owned decorator + `def` shell for one test, built with a
t-string. Interpolation expressions evaluate at the literal site (like
f-strings), so the values are passed as parameters.

### `_is_module_constant(line: str) -> bool`

True when a module-level line is a constant assignment (`NAME = value` with no
call in the left-hand side) — such lines are preserved in the header.

## Architectural Notes

- Wired into `TestOrchestrator.run_pipeline()` as the final structural pass,
  immediately after `normalise_generated_code()`.
- Complements `code_postprocessor._strip_module_level_statements()` (a
  line-based sanitizer) — the assembler makes the same leaks impossible by
  construction rather than by deletion.
- The journey model comes from `SkeletonParser.parse_test_journeys()`, whose
  `test_definition_pattern` matches `def` lines only — hence the walk-up that
  collects decorator lines sitting just above each `def`.
