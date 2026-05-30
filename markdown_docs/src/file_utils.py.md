# `src/file_utils.py`

## Purpose
File operation helpers for the Playwright test generator. Handles saving generated tests, filename slugification, newline normalization, and file renaming.

## Metadata
- **Lines:** 145
- **Imports:** os, re, datetime, pathlib.Path, src.code_validator.validate_python_syntax

## Functions
| Function | Description |
|----------|-------------|
| `slugify(text)` | Converts text to filesystem-safe filename segment (lowercase, underscore-separated) |
| `save_generated_test(test_code, story_text, base_url, output_dir)` | Saves test code to `test_YYYYMMDD_HHMMSS_<slug>.py` with header comment |
| `normalise_code_newlines(code)` | Restores missing newlines before `import`/`from` keywords in LLM output |
| `rename_test_file(old_path, new_name)` | Renames test file with collision handling via timestamp |

## Key Logic
- Filename format: `test_YYYYMMDD_HHMMSS_<slug>.py`
- Syntax validation via `validate_python_syntax` before saving — rejects invalid Python
- Newline fix uses regex lookbehind: inserts `\n` before `import ` or `from ` when preceded by non-whitespace
- Rename handles collisions by appending timestamp
- Enforces `test_` prefix and strips `.py` extension