#!/bin/bash
# Install required tools for the data agent

set -e

echo "Installing data processing tools..."

# JSON processing
brew install jq

# CSV/JSON swiss army knife
brew install miller

# Fast SQL analytics on local files
brew install duckdb

# Document conversion (optional, for exporting)
brew install pandoc

# Python package manager
brew install uv

# Python tools (standalone)
echo "Installing Python CLI tools..."
uv tool install xlsx2csv

# Python project dependencies
echo "Setting up Python project..."
uv sync

echo ""
echo "Tools installed:"
echo "  jq: $(jq --version)"
echo "  miller: $(mlr --version)"
echo "  duckdb: $(duckdb --version)"
echo "  uv: $(uv --version)"
echo "  xlsx2csv: $(xlsx2csv --version 2>&1 | head -1)"
echo ""

# Evidence reports
echo "Setting up Evidence..."
cd evidence-reports
npm install
npm run sources

echo ""
echo "Setup complete!"
echo ""
echo "Commands:"
echo "  uv run python scripts/sedlabanki.py  # Process Central Bank data"
echo "  cd evidence-reports && npm run dev   # Start report server"
