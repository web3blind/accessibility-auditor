#!/bin/sh
set -e

PROJECT_PATH="${1:-.}"
FORMAT="${2:-github-annotations}"
FAIL_THRESHOLD="${3:-60}"
OUTPUT_FILE="${4:-}"
MAX_FILES="${5:-30}"
MAX_FINDINGS="${6:-8}"

CMD="python /app/cli.py audit \"$PROJECT_PATH\" --format \"$FORMAT\" --fail-threshold \"$FAIL_THRESHOLD\" --max-files \"$MAX_FILES\" --max-findings \"$MAX_FINDINGS\""

if [ -n "$OUTPUT_FILE" ]; then
    CMD="$CMD -o \"$OUTPUT_FILE\""
fi

eval $CMD
