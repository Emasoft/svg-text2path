"""Batch configuration template generation."""

from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console

console = Console()


# ---------------------------------------------------------------------------
# YAML Template
# ---------------------------------------------------------------------------

BATCH_CONFIG_TEMPLATE = """\
# =============================================================================
# SVG Text2Path - Batch Conversion Configuration
# =============================================================================
#
# Convert multiple SVG files from text elements to vector path outlines in one
# operation. All text is converted to paths that render identically on any
# system without requiring fonts.
#
# QUICK START
# -----------
# 1. Edit the 'inputs' section below (required)
# 2. Optionally adjust settings (all have sensible defaults)
# 3. Run: text2path batch convert <this-file>.yaml
#
# USAGE
# -----
#   text2path batch convert config.yaml
#
# WHAT YOU NEED TO CONFIGURE
# --------------------------
# - 'inputs' section: REQUIRED - specify files/folders to convert
# - 'settings' section: OPTIONAL - all defaults work well for most cases
# - 'log_file': OPTIONAL - where to save the conversion report
#
# =============================================================================

# -----------------------------------------------------------------------------
# CONVERSION SETTINGS
# -----------------------------------------------------------------------------
# These settings apply to ALL conversions in this batch.
# All settings are optional - defaults are shown in comments.

settings:

  # ---------------------------------------------------------------------------
  # Path Generation
  # ---------------------------------------------------------------------------

  # precision: Number of decimal places for path coordinates.
  # Higher values = more accurate but larger file sizes.
  # Range: 1-10
  # Default: 6
  precision: 6

  # preserve_styles: Keep original style attributes on converted path elements.
  # When true, preserves fill, stroke, font-size etc. as attributes.
  # When false, only essential path data is kept.
  # Default: false
  preserve_styles: false

  # ---------------------------------------------------------------------------
  # Font Resolution
  # ---------------------------------------------------------------------------

  # system_fonts_only: Only use fonts installed on the system.
  # When true, ignores embedded fonts and font URLs in SVG.
  # Default: false
  system_fonts_only: false

  # font_dirs: Additional directories to search for font files.
  # Paths can be absolute or relative to this config file.
  # Default: [] (empty list - only system fonts)
  # Example:
  #   font_dirs:
  #     - ./fonts
  #     - /usr/share/fonts/custom
  #     - ~/Library/Fonts
  font_dirs: []

  # no_remote_fonts: Disable fetching fonts from remote URLs.
  # When true, @font-face URLs in SVG will be ignored.
  # Default: false
  no_remote_fonts: false

  # auto_download: Automatically download missing fonts.
  # Uses fontget or fnt tools to find and install missing fonts.
  # Requires: fontget or fnt installed and on PATH.
  # Default: false
  auto_download: false

  # ---------------------------------------------------------------------------
  # Validation & Verification
  # ---------------------------------------------------------------------------

  # validate: Validate SVG structure using svg-matrix.
  # Checks input and output SVG for structural issues.
  # Requires: Bun runtime (bunx @emasoft/svg-matrix)
  # Default: false
  validate: false

  # verify: Verify conversion faithfulness using visual comparison.
  # Compares original vs converted SVG pixel-by-pixel.
  # Requires: Bun runtime (bunx sbb-compare)
  # Default: false
  verify: false

  # verify_pixel_threshold: Pixel color difference sensitivity.
  # How different a pixel must be to count as "different".
  # Lower values = more sensitive (detects smaller differences).
  # Range: 1-255 (where 1 is most sensitive, 255 is least)
  # Default: 10
  verify_pixel_threshold: 10

  # verify_image_threshold: Maximum acceptable difference percentage.
  # Percentage of pixels that can differ before verification fails.
  # Lower values = stricter matching requirement.
  # Range: 0.0-100.0
  # Default: 5.0
  verify_image_threshold: 5.0

  # ---------------------------------------------------------------------------
  # Security
  # ---------------------------------------------------------------------------

  # no_size_limit: Bypass file size limits.
  # WARNING: Disabling size limits may allow decompression bombs.
  # Only use for trusted files that exceed the default 50MB limit.
  # Default: false
  no_size_limit: false

  # ---------------------------------------------------------------------------
  # Processing
  # ---------------------------------------------------------------------------

  # jobs: Number of parallel conversion workers.
  # Higher values = faster batch processing but more memory usage.
  # Set to 1 for sequential processing.
  # Default: 4
  jobs: 4

  # continue_on_error: Continue processing when a file fails.
  # When true, errors are logged but processing continues.
  # When false, batch stops on first error.
  # Default: true
  continue_on_error: true

  # allow_overwrite: Allow output to overwrite input file.
  # When true and input==output, original is renamed to .bak
  # When false, same input/output paths raise an error.
  # Default: false
  allow_overwrite: false

  # preflight_check: Check path accessibility before processing.
  # Verifies: file permissions, network connectivity, SSH auth, disk space.
  # When true, provides detailed diagnostics for any access issues.
  # When false, errors only appear during actual processing.
  # Default: true
  preflight_check: true


# -----------------------------------------------------------------------------
# FILE FORMATS TO CONVERT (REQUIRED)
# -----------------------------------------------------------------------------
# You MUST explicitly enable each format you want to convert.
# All formats default to false for safety - nothing is converted unless enabled.
#
# Enable only the formats you need. Set to true to include, false to exclude.

formats:
  # SVG files - standard SVG and compressed SVGZ
  svg: true                 # .svg files
  svgz: false               # .svgz compressed files

  # Web files - HTML and CSS with embedded/data-URI SVG
  html: false               # .html, .htm, .xhtml files
  css: false                # .css files (SVG in data URIs)

  # Data files - escaped SVG in structured formats
  json: false               # .json files (escaped SVG strings)
  csv: false                # .csv files (escaped SVG strings)

  # Documentation - SVG in documentation formats
  markdown: false           # .md, .markdown files
  rst: false                # .rst reStructuredText files

  # Code files - SVG embedded in source code
  python: false             # .py files (SVG in string literals)
  javascript: false         # .js, .ts, .jsx, .tsx files

  # Other formats
  plaintext: false          # .txt files (data URIs)
  epub: false               # .epub ebook files


# -----------------------------------------------------------------------------
# INPUT FILES AND FOLDERS (REQUIRED)
# -----------------------------------------------------------------------------
# Compact semicolon-delimited format: input;output[;suffix]
#
# FILE MODE:   input_path;output_path
# FOLDER MODE: input_folder/;output_folder/;suffix
#
# Paths support: local, ~/, remote (user@host:path), URLs (https://, ftp://)
#
# ESCAPING SPECIAL CHARACTERS:
#   - Semicolons in paths: use \\; or %3B (URL encoding)
#   - Spaces in paths: use %20 (URL encoding)
#   - Or use YAML quoted strings: "path;with;semicolons;output.svg"

inputs:
  # --- FILE MODE EXAMPLES ---
  - ./assets/logo.svg;./dist/logo_paths.svg
  # - ./art/banner.svg;./output/banner.svg
  # - ~/Documents/icon.svg;./output/icon.svg

  # --- FOLDER MODE EXAMPLES (trailing slash + suffix) ---
  # - ./input/;./output/;_converted
  # - ./icons/;./dist/icons/;_paths

  # --- SAME INPUT/OUTPUT (creates .bak backup, requires allow_overwrite) ---
  # - ./page.html;./page.html

  # --- REMOTE PATHS (SSH) ---
  # - user@192.168.1.10:/home/user/file.svg;./local/file.svg
  # - ./local/file.svg;user@192.168.1.10:/home/user/converted.svg

  # --- URL SOURCES ---
  # - https://example.com/icon.svg;./downloads/icon.svg


# -----------------------------------------------------------------------------
# OUTPUT LOG FILE
# -----------------------------------------------------------------------------
# JSON report generated after batch completion, containing:
#
#   - timestamp: When the batch ran
#   - settings: Configuration used
#   - summary: { total, success, skipped, errors }
#   - files: Array of per-file results:
#       - input/output paths
#       - status: "success" | "skipped" | "error"
#       - text_elements: count found
#       - path_elements: count generated
#       - diff_percent: visual diff (if verify=true)
#       - verify_passed: true/false (if verify=true)
#
# Use this log to audit conversions or integrate with CI/CD pipelines.
#
# Default: batch_conversion_log.json

log_file: batch_conversion_log.json


# =============================================================================
# TIPS
# =============================================================================
#
# 1. TEST WITH ONE FILE FIRST
#    Before running a large batch, test with a single file to verify settings:
#      text2path convert test.svg -o test_out.svg --precision 6
#
# 2. CHECK AVAILABLE FONTS
#    If conversions fail due to missing fonts:
#      text2path fonts list           # See what's available
#      text2path fonts find "Arial"   # Search for a specific font
#
# 3. AUTO-DOWNLOAD MISSING FONTS
#    Enable auto_download in settings to automatically install missing fonts.
#    Requires: fontget (https://github.com/Graphixa/FontGet) or fnt
#
# 4. VERIFY CONVERSION QUALITY
#    Enable verify=true to compare original vs converted visually.
#    The log will show diff percentages for each file.
#
# 5. PARALLEL PROCESSING
#    Increase 'jobs' for faster processing on multi-core systems.
#    Decrease to 1 if you encounter memory issues.
#
# =============================================================================
"""


@click.command("template")
@click.argument(
    "output_file",
    type=click.Path(path_type=Path),
    default="batch_config.yaml",
)
@click.option(
    "--force",
    "-f",
    is_flag=True,
    help="Overwrite existing file without prompting",
)
def batch_template(output_file: Path, force: bool) -> None:
    """Generate a YAML configuration template for batch conversion.

    OUTPUT_FILE: Path for the generated template (default: batch_config.yaml)

    The template includes all available settings with extensive comments
    explaining each option, its default value, and usage examples.

    \b
    Examples:
      text2path batch template                    # Creates batch_config.yaml
      text2path batch template my_batch.yaml      # Creates my_batch.yaml
      text2path batch template config.yaml -f     # Overwrite if exists
    """
    if (
        output_file.exists()
        and not force
        and not click.confirm(f"File '{output_file}' exists. Overwrite?")
    ):
        console.print("[yellow]Aborted.[/yellow]")
        return

    output_file.write_text(BATCH_CONFIG_TEMPLATE)
    console.print(f"[green]Template created:[/green] {output_file}")
    console.print()
    console.print("[dim]Edit the template to configure your batch conversion,[/dim]")
    console.print("[dim]then run:[/dim]")
    console.print(f"  text2path convert --batch {output_file}")
    console.print("[dim]or:[/dim]")
    console.print(f"  text2path batch convert {output_file}")
