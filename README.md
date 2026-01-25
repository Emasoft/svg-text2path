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

## Features

- **HarfBuzz text shaping** - Proper ligatures, kerning, and complex script support
- **Unicode BiDi** - RTL languages (Arabic, Hebrew) rendered correctly
- **TextPath support** - Text along paths with tangent-based placement
- **Strict font matching** - Fails on missing fonts (no silent fallbacks)
- **20+ input formats** - File, string, HTML, CSS, JSON, markdown, remote URLs
- **Visual diff tools** - Pixel-perfect comparison via svg-bbox
- **Cross-platform** - Works on macOS, Linux, and Windows

## Installation

Three installation methods depending on your use case:

### 1. CLI Tool (End Users)

Install the `text2path` command globally in an isolated environment:

```bash
# Install
uv tool install svg-text2path

# Upgrade to latest version
uv tool install svg-text2path --upgrade

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

Use this when you want to import `svg_text2path` in your code.

### 3. Direct Install (Virtual Environment)

Install directly into the current virtual environment:

```bash
# Install
uv pip install svg-text2path

# Uninstall
uv pip uninstall svg-text2path

# Or with pip
pip install svg-text2path
pip uninstall svg-text2path
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
text2path deps check
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

### 5. Processing Remote SVGs

```python
from svg_text2path import Text2PathConverter

converter = Text2PathConverter()

# Fetch and convert remote SVG (with SSRF protection)
result = converter.convert_url(
    "https://example.com/diagram.svg",
    "local_output.svg"
)
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
```

### Environment Variables

```bash
# Custom font cache location
export T2P_FONT_CACHE=/path/to/font_cache.json

# Verbose logging
export T2P_LOG_LEVEL=DEBUG
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
)

# Methods
result = converter.convert_file(input_path, output_path)
result = converter.convert_string(svg_content)
element = converter.convert_element(text_element)
result = converter.convert_url(url, output_path)
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

| Format | Detection | Example |
|--------|-----------|---------|
| SVG file | `.svg` extension | `input.svg` |
| SVGZ (compressed) | `.svgz` or gzip magic | `input.svgz` |
| SVG string | Starts with `<svg` or `<text` | `"<svg>...</svg>"` |
| ElementTree | `isinstance(x, Element)` | `ET.parse("file.svg")` |
| HTML with SVG | Contains `<svg` tag | `"<html>...<svg>...</svg></html>"` |
| CSS data URI | `url("data:image/svg+xml` | CSS background image |
| Inkscape SVG | sodipodi namespace | Inkscape-exported files |
| Remote URL | `http://` or `https://` | `"https://example.com/file.svg"` |

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
text2path fonts cache --rebuild

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

## License

MIT

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and guidelines.

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for version history.
