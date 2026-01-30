# svg-text2path

Convert SVG text elements (`<text>`, `<tspan>`, `<textPath>`) to vector outline paths with HarfBuzz text shaping.

[![CI](https://github.com/Emasoft/svg-text2path/actions/workflows/ci.yml/badge.svg)](https://github.com/Emasoft/svg-text2path/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/svg-text2path)](https://pypi.org/project/svg-text2path/)
[![Python](https://img.shields.io/pypi/pyversions/svg-text2path)](https://pypi.org/project/svg-text2path/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Why svg-text2path?

When you embed text in SVG files, the viewer must have the correct fonts installed to render them properly. This causes problems when:

- Sharing SVGs across different systems with different fonts
- Converting SVGs to other formats (PDF, PNG) where font embedding is unreliable
- Creating SVG icons or logos that must look identical everywhere
- Archiving designs for long-term preservation

**svg-text2path** solves this by converting text to vector paths that render identically on any system, without requiring fonts.

### Before & After

| Before (text elements) | After (vector paths) |
|:----------------------:|:--------------------:|
| ![Before](assets/example_before.svg) | ![After](assets/example_after.svg) |
| *Requires fonts on viewer's system* | *Renders identically everywhere* |

## Features

- **HarfBuzz text shaping** - Proper ligatures, kerning, and complex script support
- **Unicode BiDi** - RTL languages (Arabic, Hebrew) rendered correctly
- **TextPath support** - Text along paths with tangent-based placement
- **Strict font matching** - Fails on missing fonts (no silent fallbacks)
- **Auto font download** - Missing fonts downloaded automatically via fontget/fnt
- **SVG validation** - Input/output validation via svg-matrix
- **Multi-format input** - SVG files, HTML, CSS, URLs, Python/JS code, Markdown, RST, ePub
- **Visual diff tools** - Pixel-perfect comparison via svg-bbox
- **Offline mode** - Graceful degradation when network is unavailable
- **Cross-platform** - Works on macOS, Linux, and Windows

## Installation

**Requires Python 3.11+** and **[uv](https://docs.astral.sh/uv/)** (fast Python package manager).

### Install uv

```bash
# macOS / Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows (PowerShell)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# Or via Homebrew
brew install uv

# Or via pip (if you have Python)
pip install uv
```

After installation, restart your terminal or run `source ~/.bashrc` (Linux) / `source ~/.zshrc` (macOS).

Three methods depending on your use case:

### 1. CLI Tool (End Users)

Install the `text2path` command globally in an isolated environment:

```bash
# Install (with recommended Python version)
uv tool install svg-text2path --python 3.11

# Upgrade to latest version
uv tool install svg-text2path --python 3.11 --upgrade

# Uninstall
uv tool uninstall svg-text2path
```

The command is available system-wide without activating any virtual environment.

### 2. Library Dependency (Your Project)

Add svg-text2path as a dependency in your Python project:

```bash
# Install (adds to pyproject.toml)
uv add svg-text2path

# Uninstall (removes from pyproject.toml)
uv remove svg-text2path
```

Use this when you want to import `svg_text2path` in your code. Make sure your project uses Python 3.11+.

### 3. Direct Install (Virtual Environment)

Install directly into a virtual environment:

```bash
# Create venv with compatible Python version
uv venv --python 3.11
source .venv/bin/activate  # or .venv\Scripts\activate on Windows

# Install
uv pip install svg-text2path

# Uninstall
uv pip uninstall svg-text2path
```

Use this for quick testing or scripts without a `pyproject.toml`.

### Platform-Specific Notes

#### macOS

Fonts are loaded from `/Library/Fonts`, `/System/Library/Fonts`, and `~/Library/Fonts`. No additional setup required.

#### Linux

For best results, install fontconfig:

```bash
# Debian/Ubuntu
sudo apt-get install fontconfig

# Fedora/RHEL
sudo dnf install fontconfig

# Arch
sudo pacman -S fontconfig
```

#### Windows

Fonts are loaded from `C:\Windows\Fonts` and the user font directory. For enhanced font matching, the library uses Windows font APIs automatically.

### Development Setup

```bash
git clone https://github.com/Emasoft/svg-text2path.git
cd svg-text2path

# Install uv if not already installed
curl -LsSf https://astral.sh/uv/install.sh | sh

# Sync dependencies (creates venv and installs all deps)
uv sync --all-extras

# Install pre-push hook (runs lint, typecheck, format, tests before push)
cp scripts/pre-push.sh .git/hooks/pre-push
chmod +x .git/hooks/pre-push

# Run tests
uv run pytest tests/ -v

# Build package
uv build

# Publish to PyPI (requires PyPI token)
uv publish
```

## Quick Start

### Python Library

```python
from svg_text2path import Text2PathConverter

converter = Text2PathConverter()

# Convert a file
result = converter.convert_file("input.svg", "output.svg")
print(f"Converted {result.text_count} text elements to {result.path_count} paths")

# Convert an SVG string
svg_content = '''<svg xmlns="http://www.w3.org/2000/svg" width="200" height="50">
  <text x="10" y="35" font-family="Arial" font-size="24">Hello World</text>
</svg>'''
output = converter.convert_string(svg_content)

# Check for errors
if result.errors:
    for error in result.errors:
        print(f"Error: {error}")
```

### Command Line

```bash
# Basic conversion
text2path convert input.svg -o output.svg

# Convert with higher precision (more decimal places in paths)
text2path convert input.svg -o output.svg --precision 8

# Convert large files that exceed default size limits
text2path convert large_file.svgz -o output.svg --no-size-limit

# Auto-download missing fonts (requires fontget or fnt)
text2path convert input.svg -o output.svg --auto-download

# Validate SVG structure (requires Bun)
text2path convert input.svg -o output.svg --validate

# Combine validation and auto-download
text2path convert input.svg -o output.svg --auto-download --validate
```

#### Supported Input Formats

All formats are auto-detected. Use `--format <type>` to force a specific format.

| Format | Extension | Example Command | Description |
|--------|-----------|-----------------|-------------|
| **SVG** | `.svg` | `text2path convert input.svg -o output.svg` | Standard SVG files |
| **SVGZ** | `.svgz` | `text2path convert compressed.svgz -o out.svgz` | Gzip-compressed SVG |
| **Inkscape** | `.svg` | `text2path convert inkscape.svg -o out.svg` | Preserves sodipodi/inkscape metadata |
| **HTML** | `.html` | `text2path convert page.html -o page_out.html` | Inline SVG, `<object>`, `<img>`, data URIs |
| **CSS** | `.css` | `text2path convert styles.css -o styles_out.css` | SVG in `url()` data URIs |
| **Python** | `.py` | `text2path convert icons.py -o icons_out.py` | SVG strings in Python code |
| **JavaScript** | `.js`, `.ts`, `.jsx`, `.tsx` | `text2path convert app.tsx -o app_out.tsx` | SVG in template literals and strings |
| **Markdown** | `.md` | `text2path convert README.md -o README_out.md` | Embedded SVG (HTML blocks, data URIs) |
| **RST** | `.rst` | `text2path convert docs.rst -o docs_out.rst` | reStructuredText `.. raw::` directives |
| **Plain Text** | `.txt` | `text2path convert base64.txt -o base64_out.txt` | Base64-encoded SVG content |
| **ePub** | `.epub` | `text2path convert book.epub -o book_out.epub` | ePub v3+ ebooks with embedded SVG |
| **Remote URL** | `https://` | `text2path convert "https://example.com/icon.svg" -o icon.svg` | Fetch and convert remote SVG |
| **Data URI** | `data:` | `text2path convert 'data:image/svg+xml;base64,PHN2Zy...' -o out.svg` | Base64 or URL-encoded SVG |
| **CSS URL** | `url()` | `text2path convert 'url("data:image/svg+xml;base64,...")' -o out.txt` | CSS url() wrapped data URI |

#### Additional Commands

```bash
# Force specific input format
text2path convert input --format html -o output.html

# Output as base64 data URI
text2path convert input.svg --base64 -o encoded.txt

# Batch convert multiple files
text2path batch convert *.svg --output-dir ./converted/

# Compare original and converted visually
text2path compare original.svg converted.svg --threshold 0.5

# Pixel-perfect comparison with diff image
text2path compare original.svg converted.svg --pixel-perfect --generate-diff

# List available fonts
text2path fonts list

# Find a specific font
text2path fonts find "Noto Sans"

# Generate font report for an SVG
text2path fonts report input.svg --detailed

# Check external dependencies
text2path deps
```

## Use Cases

### 1. Creating Font-Independent Logos

```python
from svg_text2path import Text2PathConverter

converter = Text2PathConverter(precision=6)
result = converter.convert_file("logo_with_text.svg", "logo_paths.svg")

# The output SVG will render identically on any system
```

### 2. Batch Processing Design Assets

```bash
# Convert all SVGs in a directory
text2path batch convert assets/*.svg --output-dir dist/

# Compare against reference renders
text2path batch compare --samples-dir ./reference --threshold 0.3
```

### 3. Verifying Conversion Quality

```python
from svg_text2path import Text2PathConverter
from svg_text2path.tools.visual_comparison import ImageComparator

# Convert
converter = Text2PathConverter()
converter.convert_file("input.svg", "output.svg")

# Compare pixel-by-pixel
comparator = ImageComparator()
diff_percent = comparator.compare("input.svg", "output.svg")
print(f"Visual difference: {diff_percent:.2f}%")
```

### 4. Working with Complex Scripts

```python
from svg_text2path import Text2PathConverter

converter = Text2PathConverter()

# Arabic text (RTL with complex shaping)
arabic_svg = '''<svg xmlns="http://www.w3.org/2000/svg" width="300" height="50">
  <text x="280" y="35" font-family="Noto Naskh Arabic" font-size="24"
        text-anchor="end" direction="rtl">مرحبا بالعالم</text>
</svg>'''

result = converter.convert_string(arabic_svg)
# HarfBuzz handles proper glyph shaping and BiDi text direction
```

## Configuration

### YAML Config File

Create `~/.text2path/config.yaml` or `./text2path.yaml`:

```yaml
defaults:
  precision: 6          # Decimal places for path coordinates
  preserve_styles: false  # Keep style attributes on converted paths
  output_suffix: "_paths"  # Suffix for output files

fonts:
  system_only: false    # Only use system fonts (ignore custom dirs)
  custom_dirs:
    - ~/.fonts/custom
    - /opt/fonts/brand

# Font family replacements (useful for cross-platform consistency)
replacements:
  "Arial": "Liberation Sans"
  "Helvetica": "Liberation Sans"
  "Times New Roman": "Liberation Serif"

# Security settings for file size limits
security:
  ignore_size_limits: false     # Bypass all size limits (WARNING: security risk)
  max_file_size_mb: 50          # Maximum input file size in MB
  max_decompressed_size_mb: 100 # Maximum decompressed size for .svgz/.epub
```

### Environment Variables

```bash
# Custom font cache location
export T2P_FONT_CACHE=/path/to/font_cache.json

# Verbose logging
export TEXT2PATH_LOG_LEVEL=DEBUG

# Security settings
export TEXT2PATH_IGNORE_SIZE_LIMITS=true   # Bypass file size limits (use with caution)
export TEXT2PATH_MAX_FILE_SIZE_MB=100      # Custom max file size (default: 50)
export TEXT2PATH_MAX_DECOMPRESSED_SIZE_MB=200  # Custom max decompressed size (default: 100)
```

## API Reference

### Text2PathConverter

```python
from svg_text2path import Text2PathConverter

converter = Text2PathConverter(
    font_cache=None,           # Optional: reuse FontCache across calls
    precision=6,               # Path coordinate precision (1-12)
    preserve_styles=False,     # Keep style metadata on paths
    log_level="WARNING",       # Logging level
    auto_download_fonts=False, # Auto-download missing fonts via fontget/fnt
    validate_svg=False,        # Validate input/output SVG via svg-matrix
)

# Methods
result = converter.convert_file(input_path, output_path)
output_svg = converter.convert_string(svg_content)
output_svg, result = converter.convert_string(svg_content, return_result=True)
element = converter.convert_element(text_element)
```

### ConversionResult

```python
from dataclasses import dataclass
from pathlib import Path
from xml.etree.ElementTree import Element

@dataclass
class ConversionResult:
    success: bool              # True if conversion completed
    input_format: str          # Detected input format
    output: Path | str | Element  # Output location or content
    errors: list[str]          # Error messages
    warnings: list[str]        # Warning messages
    text_count: int            # Number of text elements found
    path_count: int            # Number of paths generated
    missing_fonts: list[str]   # Fonts that couldn't be resolved
    input_valid: bool | None   # Input SVG validation result (if --validate)
    output_valid: bool | None  # Output SVG validation result (if --validate)
    validation_issues: list[str]  # SVG validation issues found
```

### FontCache

```python
from svg_text2path import FontCache

cache = FontCache()
cache.prewarm()  # Build font cache (run once)

# Get font for specific parameters
font, data, face_idx = cache.get_font(
    family="Arial",
    weight=400,      # 100-900
    style="normal",  # normal, italic, oblique
    stretch="normal" # condensed, normal, expanded
)
```

## Supported Input Formats

| Format | Interface | Example |
|--------|-----------|---------|
| SVG file | CLI + API | `text2path convert input.svg` |
| SVG string | API only | `converter.convert_string("<svg>...</svg>")` |
| ElementTree | API only | `converter.convert_tree(ET.parse("file.svg"))` |
| Inkscape SVG | CLI + API | Works with sodipodi namespace files |

## Troubleshooting

### "Font not found" Error

```
FontNotFoundError: Font not found: CustomFont (weight=400, style=normal)
```

**Solutions:**

1. Install the missing font using [FontGet](https://github.com/Graphixa/FontGet) or [fnt](https://github.com/alexmyczko/fnt):
   ```bash
   fontget install "Noto Sans"  # or
   fnt install "Noto Sans"
   ```
2. Use a font replacement in config:
   ```yaml
   replacements:
     "CustomFont": "Arial"
   ```
3. Check available fonts: `text2path fonts list`

### Visual Differences After Conversion

Small differences (< 1%) are normal due to:
- Anti-aliasing differences between text and path rendering
- Sub-pixel positioning variations
- Hinting differences

For pixel-perfect comparison:
```bash
text2path compare original.svg converted.svg --pixel-perfect --tolerance 5
```

### Slow Performance with Many Fonts

The first run builds a font cache. Speed up subsequent runs:

```bash
# Pre-warm the cache
text2path fonts cache --refresh

# Or set a custom cache location
export T2P_FONT_CACHE=/fast/disk/font_cache.json
```

### Windows Path Issues

Ensure paths use forward slashes or raw strings:

```python
# Correct
converter.convert_file("C:/Users/name/input.svg", "output.svg")
converter.convert_file(r"C:\Users\name\input.svg", "output.svg")

# Incorrect (escape issues)
converter.convert_file("C:\Users\name\input.svg", "output.svg")
```

### Offline Mode

When running without network connectivity (e.g., in containers or air-gapped environments):

- **Font auto-download**: Skipped with message "Cannot download: no network (offline)"
- **SVG validation**: Skipped with message "Validation skipped (offline mode)"

The conversion itself works fully offline - only the optional features require network.

```python
# Works offline - core conversion doesn't need network
converter = Text2PathConverter()
result = converter.convert_file("input.svg", "output.svg")

# These features gracefully degrade when offline:
converter = Text2PathConverter(
    auto_download_fonts=True,  # Skips download if no network
    validate_svg=True,         # Skips validation if no network
)
```

## Requirements

### Python Dependencies

| Package | Purpose |
|---------|---------|
| `fonttools` | Font parsing, glyph extraction |
| `uharfbuzz` | HarfBuzz text shaping |
| `python-bidi` | Unicode BiDi algorithm |
| `defusedxml` | XXE-safe XML parsing |
| `click` | CLI framework |
| `rich` | Terminal formatting |
| `pillow` | Image processing |
| `numpy` | Array operations |

### External Tools (Optional)

| Tool | Purpose | Install |
|------|---------|---------|
| fontconfig | Enhanced font matching | `apt install fontconfig` |
| Node.js | Chrome-based comparison | `brew install node` |
| Inkscape | Reference rendering | `apt install inkscape` |
| Bun | SVG validation via svg-matrix | `curl -fsSL https://bun.sh/install \| sh` |
| fontget | Auto font download | `curl -fsSL https://raw.githubusercontent.com/Graphixa/FontGet/main/scripts/install.sh \| sh` |
| fnt | Auto font download (fallback) | `brew install fnt` |

### Font Installation Tools (Recommended)

Need more fonts? These tools make installing fonts easy:

| Tool | Description | Link |
|------|-------------|------|
| **FontGet** | Download and install 2700+ Google Fonts with a simple CLI | [github.com/Graphixa/FontGet](https://github.com/Graphixa/FontGet) |
| **fnt** | Lightweight font manager for Linux/macOS, downloads from Google Fonts | [github.com/alexmyczko/fnt](https://github.com/alexmyczko/fnt) |

```bash
# FontGet - install any Google Font
fontget install "Noto Sans"
fontget install "Roboto Mono"

# fnt - browse and install fonts
fnt update                    # Update font list
fnt search noto              # Search for fonts
fnt preview "Noto Sans"      # Preview a font
fnt install "Noto Sans"      # Install a font
```

## Security

- **XXE Protection**: All XML parsing uses `defusedxml`
- **SSRF Protection**: Remote URL fetching blocks private IP ranges (10.x, 172.16.x, 192.168.x, 127.x)
- **Input Validation**: File paths are validated before processing
- **Decompression Bomb Protection**: Size limits on compressed files (.svgz, .epub)
  - Default max file size: 50MB
  - Default max decompressed size: 100MB
  - Can be customized via config or overridden with `--no-size-limit` (use with caution)

## License

MIT

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and guidelines.

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for version history.
