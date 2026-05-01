#!/usr/bin/env bash
# launch_cli.sh — Start the AI Test Generator interactive CLI.
#
# Usage: bash launch_cli.sh

set -e

echo ""
echo "🎭  AI Playwright Test Generator — CLI Launcher"
echo "================================================"
echo ""

# Check Python
if ! command -v python &>/dev/null; then
  echo "❌  Python not found."
  exit 1
fi
echo "✅  Python: $(python --version)"

# Check uv
if ! command -v uv &>/dev/null; then
  echo "❌  uv not found. Install it with: pip install uv"
  exit 1
fi
echo "✅  uv: $(uv --version)"

# Sync dependencies
echo "📦  Syncing dependencies…"
uv sync

# Activate venv if not already active
if [[ "$VIRTUAL_ENV" == "" ]]; then
  source .venv/Scripts/activate 2>/dev/null || source .venv/bin/activate 2>/dev/null
fi

echo ""
echo "🚀  Starting Interactive CLI"
echo "    Press Ctrl+C to stop"
echo ""

uv run python -m cli.main