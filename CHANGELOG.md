# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2026-01-25

### Added

- **Pixel-perfect comparison**: New `--pixel-perfect` flag for compare command using native ImageComparator
- **Visual diff generation**: `--generate-diff` and `--grayscale-diff` flags for comparison images
- **Batch comparison**: `text2path batch compare` for comparing multiple SVG files at once
- **Regression tracking**: `text2path batch regression` with JSON registry for tracking diff changes over time
- **Enhanced font reporting**: `text2path fonts report --detailed` shows resolved font files and inheritance
- **Font variation settings**: Support for variable fonts in font reports
- **SSRF protection**: Remote SVG fetching blocks private IP ranges (10.x, 172.16.x, 192.168.x, 127.x)
- **XXE protection**: All XML parsing uses defusedxml library
- **Visual comparison tools**: New `svg_text2path/tools/visual_comparison.py` module
- **fc-match caching**: Font resolution subprocess results are cached for performance
- **HarfBuzz font caching**: Reuse HarfBuzz font objects across glyphs
- **BiDi skip for ASCII**: Skip bidirectional processing for ASCII-only text

### Changed

- **Batch command restructured**: `batch` is now a command group with subcommands:
  - `text2path batch convert` (was: `text2path batch`)
  - `text2path batch compare` (new)
  - `text2path batch regression` (new)
- **svg-bbox updated**: 1.1.7 → 1.1.11
- **Performance**: `getGlyphSet()` moved outside glyph loop (significant speedup)

### Deprecated

- **Legacy CLI commands**: `t2p_convert`, `t2p_compare`, `t2p_font_report`, `t2p_font_report_html`, `t2p_analyze_path`, `t2p_text_flow_test` are deprecated. Use `text2path` CLI instead.
- **Legacy package**: `text2path/` package is deprecated in favor of `svg_text2path/`

### Removed

- **requirements.txt**: Redundant with pyproject.toml (had incorrect package names)

### Fixed

- **Type safety**: Added null checks for optional XML attributes throughout
- **Line length**: All files comply with 88-character limit

### Security

- **CVE prevention**: XXE vulnerabilities fixed by replacing `xml.etree.ElementTree` with `defusedxml.ElementTree`
- **SSRF prevention**: Remote SVG handler validates hostnames against private IP blocklist

## [0.2.0] - 2026-01-20

### Added

- Initial unified CLI with Click framework
- Font cache with cross-platform support
- HarfBuzz text shaping integration
- Unicode BiDi support
- Visual comparison via svg-bbox
- 20+ input format handlers

## [0.1.0] - 2025-12-15

### Added

- Initial release with basic text-to-path conversion
- FontCache with fontconfig integration
- Basic CLI tools
