# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Text2Path is a Python CLI suite that converts SVG text elements (`<text>`, `<tspan>`, `<textPath>`) into vector outline paths. It uses HarfBuzz for accurate text shaping (ligatures, RTL/BiDi support, complex scripts) and provides visual comparison tools against reference renders.

**Current status**: Advanced sample diff ~7.99% vs original (target ~0.2% matching Inkscape reference at 0.1977%).

## Commands

### Setup
```bash
# Create and activate virtual environment
uv venv --python 3.11
source .venv/bin/activate
uv init --python 3.11

# Install dependencies
uv pip install -r requirements.txt
# Or: uv pip install fonttools python-bidi uharfbuzz svg-path pillow numpy

# Install dev dependencies
uv pip install pytest
```

### CLI Tools (Entry Points)
```bash
# Main conversion - convert text to paths
uv run text2path convert input.svg -o output.svg --precision 6

# Visual comparison via Chrome + SVG-BBOX
uv run text2path compare ref.svg converted.svg --threshold 0.5

# Pixel-perfect comparison (native, no svg-bbox)
uv run text2path compare ref.svg converted.svg --pixel-perfect --generate-diff

# Font management
uv run text2path fonts list
uv run text2path fonts find "Noto Sans"
uv run text2path fonts report input.svg --detailed

# Dependency checking
uv run text2path deps
# Note: svg-bbox is installed via npm separately (npm install svg-bbox)
```

### Batch Processing
```bash
# Batch convert multiple SVGs
uv run text2path batch convert *.svg --output-dir ./converted/

# Batch compare with threshold
uv run text2path batch compare --samples-dir ./samples --threshold 0.5

# Regression tracking
uv run text2path batch regression --registry ./regression_history.json
```

### Code Quality
```bash
# Format Python files
uv run ruff format svg_text2path/

# Run tests
uv run pytest tests/
```

## Architecture

### Core Pipeline (`svg_text2path/api.py`)

The `Text2PathConverter` class implements a multi-stage text-to-path pipeline:

1. **Font Resolution** (`svg_text2path/fonts/cache.py`)
   - Cross-platform font discovery (macOS, Linux, Windows)
   - Persistent font cache at `~/.cache/svg-text2path/font_cache.json`
   - Strict font matching (fails on missing fonts, no silent fallbacks)
   - Support for fontconfig (`fc-match`, `fc-list`)

2. **Text Shaping** (`svg_text2path/shaping/`)
   - `harfbuzz.py` - HarfBuzz shaping for proper ligatures and contextual forms
   - `bidi.py` - Unicode BiDi algorithm for RTL text (Arabic, Hebrew)
   - Visual run processing matching browser behavior

3. **Path Generation** (`svg_text2path/paths/`)
   - `generator.py` - Glyph outline extraction via fonttools `TTFont`
   - `transform.py` - Transform matrix handling (scale, rotate, skew)
   - SVG path pen for `d` attribute generation

4. **SVG Manipulation** (`svg_text2path/svg/`)
   - `parser.py` - SVG parsing and writing
   - `elements.py` - Text element replacement with path groups
   - Namespace-aware element handling

### Key Components

| File | Purpose |
|------|---------|
| `svg_text2path/api.py` | Main `Text2PathConverter` class |
| `svg_text2path/fonts/cache.py` | `FontCache` with cross-platform resolution |
| `svg_text2path/shaping/harfbuzz.py` | HarfBuzz text shaping |
| `svg_text2path/shaping/bidi.py` | BiDi algorithm for RTL text |
| `svg_text2path/tools/visual_comparison.py` | Visual diff via Chrome rendering |
| `svg_text2path/cli/commands/` | CLI command implementations |

### npm Dependencies (Visual Comparison)

**svg-bbox** (npm): JavaScript library for accurate SVG bounding box computation via headless Chrome. Used by `text2path compare` for pixel-perfect visual diffs. Provides `sbb-compare` and `sbb-getbbox` CLI tools via npx.

### External Dependencies

**Runtime:**
- `fonttools` - Font parsing, glyph extraction
- `uharfbuzz` - Text shaping engine
- `python-bidi` - BiDi algorithm implementation
- `svg-path` - SVG path parsing
- `pillow` - Image processing for diffs
- `numpy` - Array operations for pixel comparison

**External Tools (must be on PATH):**
- `fontconfig` (`fc-match`, `fc-list`) - Font matching
- `inkscape` - Reference rendering and text-to-path
- `node` - For Chrome-based rendering (puppeteer)
- `magick` (optional) - JPEG preview generation

## Configuration

### Font Cache
Set custom cache location:
```bash
export T2P_FONT_CACHE=/path/to/font_cache.json
```

### Logging
Debug logging can be enabled via CLI:
```bash
text2path -v convert input.svg -o output.svg
```

Or programmatically via the `log_level` parameter on `Text2PathConverter`.

### Security Configuration
File size limits protect against decompression bombs. Configure via:

**CLI flag:**
```bash
text2path convert large_file.svgz -o out.svg --no-size-limit
```

**Environment variables:**
```bash
export TEXT2PATH_IGNORE_SIZE_LIMITS=true     # Bypass all limits
export TEXT2PATH_MAX_FILE_SIZE_MB=100        # Custom file size limit
export TEXT2PATH_MAX_DECOMPRESSED_SIZE_MB=200  # Custom decompressed limit
```

**YAML config (`~/.text2path/config.yaml`):**
```yaml
security:
  ignore_size_limits: false
  max_file_size_mb: 50
  max_decompressed_size_mb: 100
```

Defaults: max 50MB file size, max 100MB decompressed size.

## Project Structure
```
svg-text2path/
├── svg_text2path/       # Main Python package
│   ├── api.py           # Text2PathConverter class
│   ├── config.py        # Configuration dataclass
│   ├── exceptions.py    # Custom exceptions
│   ├── fonts/           # Font resolution and caching
│   ├── shaping/         # HarfBuzz and BiDi text shaping
│   ├── paths/           # Path generation and transforms
│   ├── svg/             # SVG parsing and manipulation
│   ├── formats/         # Input format handlers
│   ├── tools/           # Visual comparison, dependencies
│   └── cli/             # CLI commands (convert, compare, fonts, batch, deps)
├── tests/               # Test suite
├── samples/             # Test SVG files
├── docs_dev/            # Development documentation (gitignored)
├── scripts_dev/         # Development scripts (gitignored)
└── pyproject.toml       # Project configuration
```

## Key Patterns

### Transform Handling
SVG transforms are parsed and applied to path coordinates:
```python
# Parse SVG transform string to 6-tuple affine matrix (a,b,c,d,e,f)
matrix = parse_transform_matrix("translate(10, 20) rotate(45) scale(2)")

# Apply to path data
transformed_path = apply_transform_to_path(path_d, scale_x, scale_y)
```

### Font Matching
Strict matching prevents silent substitution:
```python
cache = FontCache()
cache.prewarm()  # Build/load font cache

# Raises MissingFontError if font not found
font, data, face_idx = cache.get_font("Noto Sans", weight=400, style="normal")
```

### Visual Comparison Workflow
```bash
# 1. Convert SVG text to paths
text2path convert samples/text51.svg -o /tmp/text51_converted.svg

# 2. Compare against original
text2path compare samples/text51.svg /tmp/text51_converted.svg --threshold 0.5

# 3. Pixel-perfect comparison with diff image
text2path compare samples/text51.svg /tmp/text51_converted.svg --pixel-perfect --generate-diff
```

## Known Issues

- RTL/inline-size flow handling needs refinement
- Per-glyph dx/dy offset processing has edge cases
- Variable font instancing pending implementation (see commit 6e7c559)
