#!/usr/bin/env bash
# fetch-annual-report.sh — Cache-aware annual report fetcher
#
# Usage: ./scripts/fetch-annual-report.sh <kennitala> [year]
#
# 1. Checks R2 cache for pre-extracted JSON
# 2. If cached, outputs it to stdout
# 3. If not cached, runs extraction via skatturinn.py + financials.py,
#    caches the result in R2, then outputs it
#
# Requires: AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, R2_ENDPOINT env vars
# (these are set in the Sprite's env.sh during job setup)

set -euo pipefail

KT="${1:?Usage: fetch-annual-report.sh <kennitala> [year]}"
YEAR="${2:-$(date +%Y)}"
BUCKET="adstodarmadur"
R2_KEY="annual-reports/${KT}/${YEAR}.json"
CACHE_FILE="/tmp/ar-cache-${KT}-${YEAR}.json"

# ── Check R2 cache ──────────────────────────────────────────────────

if curl -sf --max-time 5 \
  --aws-sigv4 "aws:amz:auto:s3" \
  --user "${AWS_ACCESS_KEY_ID}:${AWS_SECRET_ACCESS_KEY}" \
  "${R2_ENDPOINT}/${BUCKET}/${R2_KEY}" \
  -o "$CACHE_FILE" 2>/dev/null; then
  echo "CACHE_HIT: ${R2_KEY}" >&2
  cat "$CACHE_FILE"
  exit 0
fi

echo "CACHE_MISS: ${R2_KEY} — extracting from skatturinn.is" >&2

# ── Extract fresh ───────────────────────────────────────────────────

cd /home/sprite/icelandic-data

# Download annual report PDF
uv run python scripts/skatturinn.py download "$KT" --year "$YEAR" 2>&1 >&2 || {
  echo "ERROR: skatturinn.py download failed for ${KT} year ${YEAR}" >&2
  exit 1
}

# Extract financials from PDF
EXTRACT_OUT="/tmp/ar-extract-${KT}-${YEAR}.json"
uv run python scripts/financials.py "$KT" --year "$YEAR" --output "$EXTRACT_OUT" 2>&1 >&2 || {
  echo "ERROR: financials.py extraction failed for ${KT} year ${YEAR}" >&2
  exit 1
}

if [ ! -f "$EXTRACT_OUT" ]; then
  echo "ERROR: extraction produced no output for ${KT} year ${YEAR}" >&2
  exit 1
fi

# ── Cache in R2 ─────────────────────────────────────────────────────

echo "Caching to R2: ${R2_KEY}" >&2
curl -sf --max-time 30 \
  --aws-sigv4 "aws:amz:auto:s3" \
  --user "${AWS_ACCESS_KEY_ID}:${AWS_SECRET_ACCESS_KEY}" \
  -H "Content-Type: application/json" \
  -T "$EXTRACT_OUT" \
  "${R2_ENDPOINT}/${BUCKET}/${R2_KEY}" 2>/dev/null >&2 || {
  echo "WARN: R2 cache write failed (non-fatal)" >&2
}

cat "$EXTRACT_OUT"
