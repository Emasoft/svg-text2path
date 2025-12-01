# SVG Visual BBox Toolkit - Task Runner
# Usage: just <command>

# Default: show all available commands
default:
  @just --list

# Install all dependencies (pnpm)
install:
  pnpm install

# Install browser binaries for Puppeteer and Playwright
install-browsers:
  pnpm run install-browsers

# Run all tests (unit + integration + e2e)
test:
  pnpm run test

# Run tests in watch mode (for development)
test-watch:
  pnpm run test:watch

# Run only unit tests
test-unit:
  pnpm run test:unit

# Run only integration tests
test-integration:
  pnpm run test:integration

# Run only E2E tests (Playwright)
test-e2e:
  pnpm run test:e2e

# Run tests with coverage report
test-coverage:
  pnpm run test:coverage

# Open Vitest UI (interactive test runner)
test-ui:
  pnpm run test:ui

# Run linting (ESLint + Prettier check)
lint:
  pnpm run lint

# Fix linting issues automatically
lint-fix:
  pnpm run lint:fix

# Format all code with Prettier
format:
  pnpm run format

# Run TypeScript type checking (via JSDoc)
typecheck:
  pnpm run typecheck

# Run full CI suite (lint + typecheck + test + coverage + e2e)
ci:
  pnpm run ci

# Clean test artifacts and coverage
clean:
  rm -rf coverage
  rm -rf test-results
  rm -rf playwright-report
  rm -rf .nyc_output
  find . -name "*-bbox-results.json" -delete
  find . -name "*-bbox-errors.log" -delete
  find . -name "*.objects.html" -delete
  find . -name "*.ids.svg" -delete
  find . -name "*.fixed.svg" -delete
  find . -name "*.rename.json" -delete

# Clean everything (including node_modules)
clean-all: clean
  rm -rf node_modules
  rm -rf pnpm-lock.yaml

# Run a specific test file
test-file FILE:
  pnpm exec vitest run {{FILE}}

# Run tests matching a pattern
test-pattern PATTERN:
  pnpm exec vitest run -t "{{PATTERN}}"

# Debug a specific test file with Node inspector
test-debug FILE:
  pnpm exec vitest run --inspect-brk {{FILE}}

# Show test coverage in browser
coverage-report:
  pnpm run test:coverage
  open coverage/index.html

# Help: Show detailed command information
help:
  @echo "SVG Visual BBox Toolkit - Available Commands:"
  @echo ""
  @echo "Installation:"
  @echo "  just install             - Install all dependencies"
  @echo "  just install-browsers    - Install browser binaries (Playwright + Puppeteer)"
  @echo ""
  @echo "Testing:"
  @echo "  just test                - Run all tests"
  @echo "  just test-watch          - Run tests in watch mode"
  @echo "  just test-unit           - Run only unit tests"
  @echo "  just test-integration    - Run only integration tests"
  @echo "  just test-e2e            - Run only E2E tests"
  @echo "  just test-coverage       - Run tests with coverage"
  @echo "  just test-ui             - Open Vitest UI"
  @echo "  just test-file FILE      - Run specific test file"
  @echo "  just test-pattern PATTERN - Run tests matching pattern"
  @echo "  just test-debug FILE     - Debug specific test with inspector"
  @echo ""
  @echo "Code Quality:"
  @echo "  just lint                - Run linters (ESLint + Prettier)"
  @echo "  just lint-fix            - Auto-fix linting issues"
  @echo "  just format              - Format all code with Prettier"
  @echo "  just typecheck           - Run TypeScript type checking"
  @echo ""
  @echo "CI/CD:"
  @echo "  just ci                  - Run full CI suite"
  @echo ""
  @echo "Utilities:"
  @echo "  just clean               - Clean test artifacts"
  @echo "  just clean-all           - Clean everything (including node_modules)"
  @echo "  just coverage-report     - Show coverage report in browser"
  @echo ""
  @echo "Examples:"
  @echo "  just test-file tests/unit/rasterization.test.js"
  @echo "  just test-pattern 'should handle thick strokes'"
