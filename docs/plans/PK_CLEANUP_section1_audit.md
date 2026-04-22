# Project Knowledge Cleanup Section 1: Audit & Conflict Detection

## Objective
Perform a comprehensive comparison between `PROJECT_KNOWLEDGE.md`, `AGENTS.md`, `.clinerules`, and the actual codebase to identify discrepancies, outdated information, and conflicting rules.

## Tasks
- [ ] Compare "Non-Negotiable Rules" in `AGENTS.md` with instructions in `PROJECT_KNOWLEDGE.md`.
- [ ] Verify if the project structure listed in `PROJECT_KNOWLEDGE.md` matches the actual current directory tree.
- [ ] Check for conflicting guidance on:
    - Test formats (Sync vs Async).
    - Package management (`uv` vs others).
    - LLM model defaults and timeout settings.
- [ ] Identify "stale" information that is no longer relevant to the current state of the project.

## Success Criteria
- A detailed list of all conflicting or outdated entries in `PROJECT_KNOWLEDGE.md`.
- Identification of missing critical knowledge that exists in `AGENTS.md` but not in `PROJECT_KNOWLEDGE.md`.