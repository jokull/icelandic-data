#!/bin/bash
# Install required tools for the data toolkit

set -e

echo "Installing data processing tools..."

# JSON processing
brew install jq

# Fast SQL analytics on local files
brew install duckdb

# Python package manager
brew install uv

# Python project dependencies
echo "Setting up Python project..."
uv sync

echo ""
echo "Tools installed:"
echo "  jq: $(jq --version)"
echo "  duckdb: $(duckdb --version)"
echo "  uv: $(uv --version)"
echo ""
echo "Setup complete!"
