#!/usr/bin/env bash
# One-time setup for macOS and Linux. Windows users: run setup.ps1 instead.
#
# The only prerequisite is `uv` (https://docs.astral.sh/uv/). It downloads a
# Python interpreter and every dependency itself — no Homebrew, no system
# Python, no DuckDB binary needed.

set -euo pipefail
cd "$(dirname "$0")"

if ! command -v uv >/dev/null 2>&1; then
  echo "Installing uv (Python package manager)..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  # The installer puts uv in ~/.local/bin; make it visible to this shell.
  export PATH="$HOME/.local/bin:$PATH"
fi
echo "uv $(uv --version | cut -d' ' -f2)"

echo "Installing Python and project dependencies..."
uv sync

echo "Checking the setup..."
uv run python scripts/setup_check.py

cat <<'EOF'

Optional — only needed for browser-driven scrapers (Power BI, Tableau, skatturinn cart):
  uv run playwright install chromium

Now open this folder in Claude Code, Codex, Claude Desktop or ChatGPT Desktop and ask
a question, e.g. "What is the median price per m² of apartments in Reykjavík since 2020?"
EOF
