# svg-text2path

Convert SVG text elements (`<text>`, `<tspan>`, `<textPath>`) to vector outline paths with HarfBuzz text shaping.

[![CI](https://github.com/Emasoft/svg-text2path/actions/workflows/ci.yml/badge.svg)](https://github.com/Emasoft/svg-text2path/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/svg-text2path)](https://pypi.org/project/svg-text2path/)
[![Python](https://img.shields.io/pypi/pyversions/svg-text2path)](https://pypi.org/project/svg-text2path/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Features

- HarfBuzz text shaping (ligatures, kerning, complex scripts)
- Unicode BiDi support (RTL Arabic, Hebrew)
- TextPath support with tangent-based placement
- Strict font matching (fails on missing fonts, no silent fallbacks)
- 20+ input format handlers (file, string, HTML, CSS, JSON, markdown)
- Visual diff via svg-bbox for pixel-perfect comparison
- Cross-platform font resolution with caching

## Installation

### Library

```bash
pip install svg-text2path
# or with uv
uv add svg-text2path
```

### Development

```bash
git clone https://github.com/Emasoft/svg-text2path.git
cd svg-text2path
uv sync --all-extras
```

## Quick Start

### Python Library

```python
from svg_text2path import Text2PathConverter

converter = Text2PathConverter()

# Convert file
result = converter.convert_file("input.svg", "output.svg")

# Convert string
svg_output = converter.convert_string(svg_content)

# Convert element
path_elem = converter.convert_element(text_element)
```

### CLI

```bash
# Basic conversion
text2path input.svg -o output.svg

# Batch processing
text2path *.svg --output-dir ./converted/

# With options
text2path input.svg --precision 6 --preserve-styles

# Font management
text2path fonts list
text2path fonts search "Noto Sans"
```

### Legacy CLI Tools

```bash
# Direct conversion
t2p_convert input.svg [output.svg] [--precision N]

# Visual comparison via Chrome + SVG-BBOX
t2p_compare ref.svg ours.svg [--inkscape-svg ref_paths.svg]

# Diagnostics
t2p_font_report          # Console font report
t2p_font_report_html     # HTML font report
t2p_analyze_path         # Inspect path data
```

## Configuration

### YAML Config

Create `~/.text2path/config.yaml` or `./text2path.yaml`:

```yaml
defaults:
  precision: 6
  preserve_styles: false
  output_suffix: "_text2path"

fonts:
  system_only: false
  custom_dirs:
    - ~/.fonts/custom

replacements:
  "Arial": "Liberation Sans"
  "Helvetica": "Liberation Sans"
```

### Environment Variables

```bash
export T2P_FONT_CACHE=/path/to/font_cache.json
```

## API Reference

### Text2PathConverter

```python
converter = Text2PathConverter(
    font_cache=None,           # Optional: reuse FontCache across calls
    precision=6,               # Path coordinate precision
    preserve_styles=False,     # Keep style metadata on paths
    log_level="WARNING",       # Logging level
)
```

### ConversionResult

```python
@dataclass
class ConversionResult:
    success: bool
    input_format: str
    output: Path | str | Element
    errors: list[str]
    warnings: list[str]
    text_count: int
    path_count: int
```

## Supported Input Formats

| Format | Detection |
|--------|-----------|
| SVG file | `.svg` extension |
| SVGZ (gzip) | `.svgz` extension or gzip magic bytes |
| SVG string | Starts with `<svg` or `<text` |
| ElementTree | `isinstance(input, ET.Element)` |
| HTML with SVG | Contains `<svg` in HTML |
| CSS data URI | Contains `url("data:image/svg+xml` |
| Inkscape SVG | sodipodi namespace detected |

## Requirements

### Python Dependencies

- `fonttools` - Font parsing, glyph extraction
- `uharfbuzz` - HarfBuzz text shaping
- `python-bidi` - Unicode BiDi algorithm
- `defusedxml` - XXE-safe XML parsing
- `click` - CLI framework
- `rich` - CLI output formatting

### External Tools (optional)

- `fontconfig` (`fc-match`, `fc-list`) - Enhanced font matching
- `node` - For Chrome-based visual comparison
- `inkscape` - Reference rendering

## License

MIT

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup and guidelines.
