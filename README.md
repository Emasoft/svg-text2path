# Text-to-Path Converter V3

A robust Python tool to convert SVG text elements into vector paths, preserving visual fidelity.

## Features
- **Unicode BiDi Support**: Correctly handles Right-to-Left languages like Arabic and Hebrew.
- **HarfBuzz Shaping**: Uses the industry-standard shaping engine for proper ligatures and contextual forms.
- **Font Fallback**: Matches fonts using system configuration (fontconfig), similar to browsers.
- **Visual Fidelity**: Replicates the visual output of the Rust implementation.

## Installation

```bash
cd text2path
uv pip install -r requirements.txt
```

## Usage

```bash
# Convert an SVG file
python src/main.py input.svg [output.svg]
```

If output path is not specified, it defaults to `input_rust_paths.svg`.

## Requirements
- `fonttools`
- `python-bidi`
- `uharfbuzz`
- System fonts (uses `fc-match` from fontconfig)
- `magick` (ImageMagick) for generating comparison JPEGs (optional)
