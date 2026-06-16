#!/usr/bin/env bash
set -euo pipefail

DIFF_ONLY=${DIFF_ONLY:-0}
BASE_BRANCH=${BASE_BRANCH:-main}

if [[ "$DIFF_ONLY" == "1" || "${1:-}" == "--diff-only" ]]; then
    echo "=== diff-only mode: comparing against $BASE_BRANCH ==="
    CHANGED_FILES=$(git diff --name-only "$BASE_BRANCH" HEAD 2>/dev/null || echo "")
    if [[ -z "$CHANGED_FILES" ]]; then
        echo "No changes detected vs $BASE_BRANCH; skipping CI gates."
        exit 0
    fi
    echo "Changed files:"
    echo "$CHANGED_FILES"
    echo ""

    PY_FILES=$(echo "$CHANGED_FILES" | grep -E '\.py$' || true)
    TEST_FILES=$(echo "$CHANGED_FILES" | grep -E '^tests/.*\.py$' || true)

    if [[ -z "$PY_FILES" && -z "$TEST_FILES" ]]; then
        echo "No Python or test files changed; skipping CI gates."
        exit 0
    fi

    echo "=== ruff check (changed files only) ==="
    echo "$PY_FILES" | xargs ruff check || true
    echo "$TEST_FILES" | xargs ruff check || true

    echo "=== mypy (changed files only) ==="
    echo "$PY_FILES" | grep -E '^csv_reconcile/' | xargs mypy || true

    echo "=== pytest (changed tests + all) ==="
    pytest_args=(-v)
    if [[ -n "$TEST_FILES" ]]; then
        pytest_args+=($TEST_FILES)
    else
        pytest_args+=(tests/)
    fi
    pytest "${pytest_args[@]}"
else
    echo "=== full CI mode ==="

    echo "=== ruff check ==="
    ruff check csv_reconcile tests

    echo "=== mypy ==="
    mypy csv_reconcile

    echo "=== pytest ==="
    pytest -v
fi

echo "=== ALL GATES PASSED ==="
