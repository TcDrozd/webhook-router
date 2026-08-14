#!/bin/bash
# Run the edge and router test suites.
#
# They run as separate pytest processes on purpose: both services define
# top-level `config`, `services`, and `http_handlers` modules, so only one can
# own those names in a given interpreter. Separate processes make that
# isolation structural rather than dependent on collection order.

set -e

cd "$(dirname "$0")"

PYTEST="${PYTEST:-python3 -m pytest}"

echo "=== edge ==="
$PYTEST tests/edge "$@"

echo ""
echo "=== router ==="
$PYTEST tests/router "$@"

echo ""
echo "All suites passed."
