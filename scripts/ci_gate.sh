#!/usr/bin/env bash
set -euo pipefail

echo "=== ruff check ==="
ruff check csv_reconcile tests

echo "=== mypy ==="
mypy csv_reconcile

echo "=== pytest ==="
pytest -v

echo "=== ALL GATES PASSED ==="
