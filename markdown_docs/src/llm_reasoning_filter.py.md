# llm_reasoning_filter.py

## Purpose
Detect and strip LLM reasoning text from generated code. Extracted from `code_postprocessor.py` to separate reasoning detection into its own independently testable module.

## Location
`src/llm_reasoning_filter.py` (142 lines)

## Dependencies
- **Standard library only**: `re`

## Public API

### `strip_llm_reasoning(code: str) -> str`
Removes lines that look like LLM reasoning/thinking text. LLMs sometimes output their internal chain-of-thought as part of the code block. This function detects and removes such lines while preserving valid Python code, comments, and blank lines.

### `_is_llm_reasoning_line(line: str) -> bool` (private)
Returns `True` if the line looks like LLM reasoning text rather than Python code. Uses a multi-stage detection pipeline:

1. **Empty line check** — blank lines are never reasoning
2. **Python keyword whitelist** — lines starting with valid Python constructs are preserved (def, class, import, from, return, if, else, for, while, try, except, assert, page., self., etc.)
3. **Reasoning prefix match** — lines starting with known reasoning prefixes (Wait, Note, Actually, Hmm, Okay, Sure, Let's, I will, Self-Correction, etc.)
4. **Comment-pattern match** — `# Word,` style reasoning comments
5. **Bullet-pattern match** — `- Actually`, `- I will`, numbered reasoning bullets
6. **Heuristic fallback** — short lines (<80 chars) starting with `CapitalizedWord,` that aren't variable assignments

## Detection Patterns
| Pattern Group | Examples |
|---------------|----------|
| `_LLM_REASONING_PREFIXES` | "Wait,", "Note,", "Actually,", "I will ", "Self-Correction" |
| `_LLM_REASONING_PATTERNS` | `# Word,` comments, bare reasoning words |
| `_BULLET_REASONING_PATTERNS` | `- Actually`, `- I need`, numbered reasoning lists |

## Design Notes
- Extracted from `code_postprocessor.py` for independent testing
- Line-by-line processing — no state carried between lines
- Python keyword whitelist includes runtime objects (`page.`, `self.`, `evidence_tracker`) to avoid false positives
- Heuristic for short natural-language lines catches edge cases not covered by prefixes

## Related Files
- `src/code_postprocessor.py` — consumer; calls `strip_llm_reasoning()` as a post-processing step
- `src/code_normalizer.py` — sibling post-processing module (newline normalization)