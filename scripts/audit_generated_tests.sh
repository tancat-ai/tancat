#!/usr/bin/env bash
# audit_generated_tests.sh — Read-only safety audit for generated_tests/.
#
# Created per Recovery Protocol (session 2026-08-21) after an agent
# suggested `rm -rf generated_tests/` without verifying git depth, .gitignore
# rules, or evidence state. This script performs ONLY read operations — it
# never deletes, moves, or modifies anything.
#
# Safety Statement compliance (AGENTS.md §12):
#   1. Git depth check      -> git log --all -- <path>
#   2. .gitignore validation -> git check-ignore --verbose
#   3. Evidence snapshot     -> SHA-256 of every untracked-unignored artifact
#
# Usage:
#   bash scripts/audit_generated_tests.sh           # full audit + summary
#   bash scripts/audit_generated_tests.sh --json    # machine-readable summary
#
# Exit codes:
#   0  PASS     — everything under generated_tests/ is tracked or gitignored
#   1  UNKNOWN  — git-irrelevant (running outside a repo) or usage error
#   2  DANGER   — untracked + unignored artifacts found (potential evidence loss)

set -u
set -o pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT" || exit 1

if ! git rev-parse --git-dir >/dev/null 2>&1; then
  echo "ERROR: not inside a git repository ($ROOT)" >&2
  exit 1
fi

JSON=0
if [ "${1:-}" = "--json" ]; then
  JSON=1
fi

BRANCH="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo 'detached')"
TARGET="generated_tests"

echo "=== Audit: $TARGET/ @ $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
echo "  repo : $ROOT"
echo "  branch: $BRANCH"
echo ""

# ---------------------------------------------------------------- 1. Inventory
echo "[1] Enumerate everything under $TARGET/ ..."

# TRACKED: committed to git (recoverable).
tracked="$(git ls-files "$TARGET/")"

# IGNORED: matched by .gitignore (will never be committed).
ignored_count="$(git ls-files --others --ignored --exclude-standard -- "$TARGET/" | grep -c . || true)"

# Untracked but NOT ignored = the danger zone.
danger_count=0
tracked_count=0

if [[ -n "$tracked" ]]; then
  tracked_count="$(printf '%s\n' "$tracked" | grep -c .)"
fi

echo ""
echo "[1.1] TRACKED (recoverable via git) — $tracked_count file(s):"
if [[ -n "$tracked" ]]; then
  printf '%s\n' "$tracked" | sed 's/^/      tracked: /'
else
  echo "    (none)"
fi

echo ""
echo "[1.2] Untracked top-level entries + classification:"

# List generated_tests content 1 level deep (files + dirs). Use git ls-files
# --others --exclude-standard to rely on .gitignore exactly as the index does.
while IFS= read -r entry; do
  [ -z "$entry" ] && continue
  # Only consider entries directly under generated_tests/
  if [[ "$entry" == */* ]]; then
    dir="${entry%%/*}"
    [ "$dir" = "generated_tests" ] || continue
  fi
  git check-ignore -q -- "$entry" && status="IGNORED" || {
    status="UNTRACKED-UNIGNORED"
    danger_count=$((danger_count + 1))
  }
  echo "    [$status] $entry"
done < <(git ls-files --others --exclude-standard -- "$TARGET/")

echo ""
echo "[3] == GIT DEPTH CHECK (recoverability of the danger zone) =="
# For every untracked-unignored artifact, does any commit in history contain it?
while IFS= read -r entry; do
  [ -z "$entry" ] && continue
  case "$entry" in
    generated_tests/*) ;;
    *) continue ;;
  esac
  if ! git ls-files --error-unmatch --quiet -- "$entry" 2>/dev/null; then
    dep="$(git log --all --oneline -- "$entry" 2>/dev/null | grep -c . || true)"
    if [ "${dep:-0}" -gt 0 ]; then
      echo "    [git-history: YES - $dep commit(s)] $entry"
    else
      echo "    [git-history: NO  - NOT RECOVERABLE if deleted] $entry"
    fi
  fi
done < <(git ls-files --others --exclude-standard -- "$TARGET/")

echo ""
echo "[4] == EVIDENCE SNAPSHOT (sha256 of untracked-unignored artifacts) =="
while IFS= read -r entry; do
  [ -z "$entry" ] && continue
  if [[ -f "$entry" ]]; then
    hash="$(sha256sum "$entry" 2>/dev/null | awk '{print $1}')"
    echo "    $hash  $entry"
  else
    echo "    (dir)          $entry"
  fi
done < <(git ls-files --others --exclude-standard -- "$TARGET/")

# The only tracked files that MUST survive any cleanup:
echo ""
echo "[5] == PROTECTED (committed, required for the tool to run) =="
git ls-tree -r HEAD --name-only -- "$TARGET/" | sed 's/^/    keep: /'

echo ""
echo "==== SUMMARY ===="
if [ "$JSON" -eq 1 ]; then
  printf '{"repo":"%s","branch":"%s","tracked":%d,"ignored":%d,"danger":%d,"verdict":"%s"}\n' \
    "$ROOT" "$BRANCH" "$tracked_count" "$ignored_count" "$danger_count" \
    "$([ "$danger_count" -eq 0 ] && echo PASS || echo DANGER)"
else
  echo "  tracked            : $tracked_count"
  echo "  ignored (gitignore): $ignored_count"
  echo "  untracked+unignored: $danger_count"
  if [ "$danger_count" -eq 0 ]; then
    echo "  verdict: PASS — nothing in generated_tests/ is at risk."
  else
    echo "  verdict: DANGER — $danger_count untracked artifact(s) exist."
    echo "  Action: do NOT delete; preserve evidence; add gitignore rules first."
  fi
fi

# Never delete here. Positive exit only if the tree is safe.
if [ "$danger_count" -gt 0 ]; then
  exit 2
fi
exit 0