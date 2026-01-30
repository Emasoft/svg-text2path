# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.4.9] - 2026-01-30

### Added

- **Compact YAML input format**: Semicolon-delimited input entries for batch config
  - File mode: `input_path;output_path`
  - Folder mode: `input_folder/;output_folder/;suffix`
  - Escaping: `\;` or `%3B` for literal semicolons, `%20` for spaces
  - YAML quoted strings supported: `"path;with;semicolons;out.svg"`
  - Both compact strings and dict format can be mixed in same config

- **Remote path support**: Batch inputs can now reference remote files
  - SSH paths: `user@host:/path/to/file.svg`
  - URLs: `https://example.com/icon.svg`, `ftp://...`
  - Local-to-remote and remote-to-local file transfers

- **In-place conversion**: `allow_overwrite` setting enables same input/output path
  - Creates `.bak` backup of original file before conversion
  - Default: false (requires explicit opt-in)

- **Path format validation**: Input and output paths are now validated
  - Local paths: relative, absolute, home (~/) paths
  - SSH paths: validates user, host (hostname/IP), and remote path
  - URLs: validates scheme (http/https/ftp/sftp) and host
  - Windows paths: drive letters and UNC paths supported
  - Descriptive error messages for invalid paths

- **Preflight accessibility checks**: `preflight_check` setting (default: true)
  - Verifies all paths are accessible before processing begins
  - Checks: file permissions, SSH authentication, network connectivity
  - Detects: stale NFS mounts, unreachable hosts, disk space issues
  - Provides actionable suggestions for each error type:
    - Authentication: SSH key, password, host key issues
    - Network: DNS resolution, connection timeouts, NAT/firewall
    - Permission: read/write access, file ownership
    - Disk: low disk space warnings
  - Groups errors by type for clear diagnostics
  - Can be disabled with `preflight_check: false` in settings
  - All errors saved to JSON log report (`preflight_errors` array)

## [0.4.8] - 2026-01-30

### Changed

- **Format selection defaults**: SVG format now enabled by default (`svg: true`)
  - `formats` section is now optional - omitting it defaults to SVG only
  - Other formats still require explicit opt-in
  - Existing v0.4.7 configs continue to work unchanged

## [0.4.7] - 2026-01-30

### Added

- **Explicit format selection for batch mode**: New `formats` YAML section for file type selection
  - All 12 formats configurable: svg, svgz, html, css, json, csv, markdown, python, javascript, rst, plaintext, epub
  - Validation enforces at least one format must be enabled
  - Format handlers now used for all file types (not just SVG)

### Fixed

- **Click deprecation warning**: Prefer `importlib.metadata.version()` over `__version__` attribute

## [0.4.6] - 2026-01-30

### Fixed

- **Windows compatibility**: Replace Unicode box-drawing characters in YAML template with ASCII equivalents to fix `UnicodeEncodeError` on Windows

## [0.4.5] - 2026-01-30

### Added

- **YAML config validation**: Comprehensive validation for batch config files
  - Type checking for all settings fields
  - Value range validation (precision 1-10, thresholds, jobs ≥1)
  - Required field enforcement with detailed error messages
  - `BatchConfigError` exception with all validation errors listed

- **Template generation**: `text2path batch template [output.yaml]`
  - Generates extensively-commented YAML configuration template
  - Quick-start guide with 3-step workflow
  - All settings documented with defaults and examples
  - `--force` flag to overwrite existing files

### Changed

- Improved batch processing documentation in README
- Enhanced YAML template with ASCII diagrams and tips section

## [0.4.4] - 2026-01-30

### Added

- **Conversion verification**: `--verify` CLI flag verifies conversion faithfulness using sbb-compare
  - Visual diff comparison between original and converted SVG
  - `--verify-pixel-threshold` sets pixel color difference sensitivity (1-255, default: 10)
  - `--verify-image-threshold` sets max acceptable diff percentage (default: 5.0%)
  - Uses `bunx sbb-compare` for pixel-accurate visual comparison

- **YAML batch configuration**: `text2path batch convert config.yaml`
  - Full YAML config file for batch conversions
  - All CLI settings configurable in YAML (precision, verify, auto_download, etc.)
  - Mixed input modes: folders and individual files
  - Folder mode: auto-detects directories, processes all SVGs with text elements
  - File mode: specify exact input/output paths
  - JSON log report with conversion details (success, skipped, errors, verification)
  - Comprehensive YAML validation with detailed error messages
  - Type checking, value range validation, and required field enforcement
  - See `samples/batch_config_example.yaml` for full configuration reference

- **YAML template generation**: `text2path batch template [output.yaml]`
  - Generates a fully-commented YAML configuration template
  - All settings documented with defaults and examples
  - `--force` flag to overwrite existing files

## [0.4.3] - 2026-01-30

### Added

- **SVG validation**: `--validate` CLI flag validates input/output SVG using svg-matrix via Bun
  - New `svg_text2path/tools/svg_validator.py` module
  - `validate_svg` parameter on `Text2PathConverter`
  - `input_valid`, `output_valid`, `validation_issues` fields on `ConversionResult`
- **Auto font download**: `--auto-download` CLI flag downloads missing fonts automatically
  - New `svg_text2path/fonts/downloader.py` module
  - Uses fontget (primary) or fnt (fallback) tools
  - `auto_download_fonts` parameter on `Text2PathConverter`
  - `auto_download` parameter on `FontCache.get_font()`
- **Offline mode support**: Network-dependent features gracefully degrade when offline
  - Font auto-download skips with "no network (offline)" message
  - SVG validation skips with "Validation skipped (offline mode)" message
  - `is_network_available()` utility function in validator and downloader modules

### Fixed

- **Font style fallback**: Fixed italic/oblique font matching when weight != 400
  - fontconfig patterns now include slant suffix for proper style resolution

## [0.4.2] - 2026-01-26

### Added

- **Security configuration**: New `SecurityConfig` dataclass for file size limits
  - `--no-size-limit` CLI flag to bypass file size limits for large files
  - `security.ignore_size_limits` YAML config option
  - `security.max_file_size_mb` - configurable max file size (default: 50MB)
  - `security.max_decompressed_size_mb` - configurable max decompressed size (default: 100MB)
  - `TEXT2PATH_IGNORE_SIZE_LIMITS`, `TEXT2PATH_MAX_FILE_SIZE_MB`, `TEXT2PATH_MAX_DECOMPRESSED_SIZE_MB` environment variables
- **Config property on handlers**: All format handlers now receive config via `handler.config` property

### Security

- **Decompression bomb protection**: All handlers that process compressed files (.svgz, .epub) and remote URLs now enforce configurable size limits
- Size limits can be overridden for trusted large files using `--no-size-limit` flag

## [0.4.1] - 2026-01-25

### Changed

- **Documentation improvements**: Added comprehensive beginner-friendly comments to examples
- **Type safety improvements**: Enhanced type annotations throughout codebase

### Added

- New SVG DOM manipulation examples using `lxml` and `minidom` libraries

## [0.4.0] - 2026-01-25

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
