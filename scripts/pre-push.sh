#!/bin/bash
#
# Git pre-push hook for svg-text2path
# Runs lint, typecheck, format check, and tests before allowing push.
# To bypass (emergency only): git push --no-verify
#

set -e

echo "============================================"
echo "  Pre-push checks for svg-text2path"
echo "============================================"
echo ""

# Change to repo root
REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

# Activate venv if it exists
if [ -d ".venv" ]; then
    source .venv/bin/activate
fi

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

print_status() {
    echo -e "${YELLOW}[RUNNING]${NC} $1..."
}

print_success() {
    echo -e "${GREEN}[PASSED]${NC} $1"
}

print_error() {
    echo -e "${RED}[FAILED]${NC} $1"
}

# Track overall status
FAILED=0

# 1. Linting with ruff
print_status "Lint check (ruff check)"
if uv run ruff check svg_text2path/ tests/ --quiet; then
    print_success "Lint check"
else
    print_error "Lint check - run 'uv run ruff check svg_text2path/ tests/' to see errors"
    FAILED=1
fi

# 2. Type checking with mypy (practical settings - ignore stubs and unused ignores)
print_status "Type check (mypy)"
if uv run mypy svg_text2path/ \
    --ignore-missing-imports \
    --disable-error-code=unused-ignore \
    --disable-error-code=import-untyped \
    --no-error-summary 2>/dev/null; then
    print_success "Type check"
else
    print_error "Type check - run 'uv run mypy svg_text2path/' to see errors"
    FAILED=1
fi

# 3. Format check with ruff format
print_status "Format check (ruff format --check)"
if uv run ruff format svg_text2path/ tests/ --check --quiet 2>/dev/null; then
    print_success "Format check"
else
    print_error "Format check - run 'uv run ruff format svg_text2path/ tests/' to fix"
    FAILED=1
fi

# 4. Run tests
print_status "Running tests (pytest)"
if uv run pytest tests/ -q --tb=no 2>/dev/null; then
    print_success "Tests"
else
    print_error "Tests - run 'uv run pytest tests/ -v' to see failures"
    FAILED=1
fi

echo ""
echo "============================================"

if [ $FAILED -eq 1 ]; then
    echo -e "${RED}Pre-push checks FAILED!${NC}"
    echo "Fix the issues above before pushing."
    echo "To bypass (emergency only): git push --no-verify"
    echo "============================================"
    exit 1
else
    echo -e "${GREEN}All pre-push checks passed!${NC}"
    echo "============================================"
    exit 0
fi
