# scripts/ Maintenance Guide

> How to keep the scripts folder from becoming a graveyard of stale one-offs.

---

## Rules

### 1. Every script must have a `__main__` entry point

Scripts should be runnable standalone:
```bash
python scripts/smoke.py
python scripts/debug.py text-validation
python scripts/uat.py saucedemo
```

No scripts that only work when imported by another script.

### 2. New scripts go in `scripts/` root, targeted tools in `scripts/debug/`

| Location | Purpose |
|----------|---------|
| `scripts/<name>.py` | General-purpose, used regularly (smoke.py, debug.py, uat.py) |
| `scripts/debug/<name>.py` | Targeted diagnostics for specific scenarios |
| `scripts/maintenance/<name>.py` | CI/project housekeeping tools |
| `scripts/uat/<name>.py` | Site-specific UAT runners |
| `scripts/archive/<name>.py` | Archived one-offs (never executed) |

### 3. Archive, don't delete

After a debugging session, one-off scripts that served their purpose go to `scripts/archive/debug_scripts/`. The README documents why they were archived.

**Trigger:** If a script is only relevant to a resolved bug (e.g. B-017), archive it.

### 4. Update `scripts/README.md` when adding new scripts

Every new script gets a row in the quick reference table and a usage example.

### 5. CI enforces smoke test health

`scripts/smoke.py` runs in CI (Gate 0) on every push. If smoke checks fail, CI fails. This ensures:
- Module imports stay valid
- Resolver text matching doesn't regress
- Skeleton parser works
- POM data model is intact

### 6. Pom-first default

New scripts default to POM mode. Use `--flat` flag for standard mode where applicable.

---

## When to add a new script

| Scenario | Action |
|----------|--------|
| Pipeline debugging | Use `scripts/debug.py` — add subcommand if needed |
| UAT against a new site | Add config to `scripts/uat.py` SITE_CONFIGS |
| Offline resolver test | Add case to `scripts/smoke.py` or `scripts/debug.py text-validation` |
| One-off investigation | Write in `scripts/debug/`, archive when resolved |
| Regression comparison | Use `scripts/uat.py --save/--compare` |

---

## Smoke test maintenance

When `src/` modules are renamed, moved, or have breaking API changes:
1. Run `python scripts/smoke.py` — it will fail on broken imports
2. Update the import list in `check_module_imports()` to match new names
3. If new resolver cases emerge (e.g. new synonym groups), add to `check_text_validation()`
4. If new POM features land, add a data model check

---

## Debug CLI maintenance

When adding a new subcommand to `scripts/debug.py`:
1. Add the subcommand parser in `build_parser()`
2. Add the async function (or sync for offline)
3. Wire it in `main()`
4. Add a usage example to the `--help` epilog
5. Update `scripts/README.md`

---

*Last updated: 2026-06-29*
