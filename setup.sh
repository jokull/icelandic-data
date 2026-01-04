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

echo ""
echo "Tools installed:"
echo "  jq: $(jq --version)"
echo "  miller: $(mlr --version)"
echo "  duckdb: $(duckdb --version)"
echo ""

# Evidence reports
echo "Setting up Evidence..."
cd evidence-reports
npm install
npm run sources

echo ""
echo "Done! Run 'cd evidence-reports && npm run dev' to start the report server."
