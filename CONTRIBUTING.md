# Contributing to svg-text2path

## Development Setup

```bash
# Clone and setup
git clone https://github.com/Emasoft/svg-text2path.git
cd svg-text2path

# Create virtual environment with uv
uv venv --python 3.12
source .venv/bin/activate

# Install all dependencies including dev
uv sync --all-extras

# Install npm dependencies (for visual comparison)
pnpm install
```

## Running Tests

```bash
# Run all tests
uv run pytest tests/ -v

# Run with coverage
uv run pytest tests/ --cov=svg_text2path --cov-report=html

# Run specific test file
uv run pytest tests/test_svg_parser.py -v

# Skip slow tests
uv run pytest tests/ -m "not slow"
```

## Code Quality

```bash
# Format code
uv run ruff format svg_text2path/ text2path/

# Lint
uv run ruff check svg_text2path/ text2path/

# Type check
uv run mypy svg_text2path/ --ignore-missing-imports
```

## Project Structure

```
svg_text2path/           # Main package (new restructured library)
├── api.py               # Text2PathConverter main class
├── fonts/               # Font resolution and caching
├── svg/                 # SVG parsing and manipulation
├── shaping/             # HarfBuzz + BiDi text shaping
├── paths/               # Path generation and transforms
├── formats/             # Input format handlers
├── cli/                 # CLI commands
└── tools/               # External tool integration

text2path/               # Legacy package (original implementation)
├── main.py              # Core converter with FontCache
└── frame_comparer.py    # Visual comparison

tests/                   # Test suite
├── conftest.py          # Shared fixtures
├── test_*.py            # Test modules
```

## Commit Convention

We use [Conventional Commits](https://www.conventionalcommits.org/):

```
feat: add new feature
fix: bug fix
docs: documentation changes
test: add or update tests
refactor: code refactoring
perf: performance improvements
chore: maintenance tasks
```

## Pull Request Process

1. Fork the repository
2. Create a feature branch: `git checkout -b feat/my-feature`
3. Make changes and add tests
4. Run tests and linting
5. Commit with conventional commit message
6. Push and create PR

## Architecture Notes

### Font Resolution
The `FontCache` class handles cross-platform font discovery with persistent caching at `~/.cache/text2path/font_cache.json`. Fonts are matched strictly - missing fonts cause errors rather than silent fallbacks.

### Text Shaping
Text shaping uses HarfBuzz via `uharfbuzz` for proper ligatures and glyph positioning. The `python-bidi` library handles Unicode BiDi reordering for RTL scripts.

### Security
All XML parsing uses `defusedxml` to prevent XXE attacks. The `svg/parser.py` module provides secure parsing functions.

### Visual Comparison
The `svg-bbox` npm package provides Chrome-based rendering for pixel-perfect visual diffs. The comparison workflow renders both SVGs and computes pixel differences.
