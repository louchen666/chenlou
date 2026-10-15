#!/bin/bash
# Run all trading-core tests. Uses stock-bot venv since it's already set up.
set -e
PY=~/stock-bot/.venv/bin/python
DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"
for t in test_*.py; do
    echo "=== $t ==="
    $PY "$t"
    echo
done
