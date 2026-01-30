"""Batch commands - process, compare, and track multiple SVG files."""

from __future__ import annotations

import concurrent.futures
import json
import subprocess
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import click
import yaml
from rich.console import Console
from rich.progress import Progress
from rich.table import Table

from svg_text2path import Text2PathConverter
from svg_text2path.config import Config

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


# -----------------------------------------------------------------------------
# INPUT FILES AND FOLDERS (REQUIRED)
# -----------------------------------------------------------------------------
# You MUST specify at least one input. Remove the example and add your own.
#
# TWO INPUT MODES (auto-detected):
#
# FOLDER MODE
# -----------
# Process all SVGs in a directory that contain text elements.
# Files without <text>, <tspan>, or <textPath> elements are skipped.
#
# Required fields:
#   path:       Source directory (trailing slash recommended for clarity)
#   output_dir: Where converted files go (created automatically)
#   suffix:     Added to filename: icon.svg -> icon_converted.svg
#
# FILE MODE
# ---------
# Process a single file with an explicit output path.
# Use when you need precise control over input/output locations.
#
# Required fields:
#   path:   Source SVG file
#   output: Full output path including filename
#
# TIP: You can mix folder and file entries freely in the same config.

inputs:

  # --- FOLDER MODE EXAMPLE ---------------------------------------------------
  # Delete or modify this example to match your project structure.
  #
  - path: ./input_folder/           # Source folder containing SVGs
    output_dir: ./output_folder/    # Destination folder (created if missing)
    suffix: _converted              # Output: logo.svg -> logo_converted.svg

  # --- FILE MODE EXAMPLES (uncomment to use) ---------------------------------
  #
  # Single file with explicit output path:
  # - path: ./assets/logo.svg
  #   output: ./dist/brand/logo_paths.svg
  #
  # Multiple individual files:
  # - path: ./branding/wordmark.svg
  #   output: ./web/assets/wordmark-paths.svg
  #
  # - path: ./branding/icon.svg
  #   output: ./mobile/resources/icon-paths.svg

  # --- MULTIPLE FOLDERS EXAMPLE (uncomment to use) ---------------------------
  #
  # Process different icon sizes with different suffixes:
  # - path: ./icons/small/
  #   output_dir: ./dist/icons/small/
  #   suffix: _sm
  #
  # - path: ./icons/large/
  #   output_dir: ./dist/icons/large/
  #   suffix: _lg


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


# ---------------------------------------------------------------------------
# Batch Config Schema
# ---------------------------------------------------------------------------


@dataclass
class BatchSettings:
    """Settings that apply to all conversions in the batch."""

    precision: int = 6
    preserve_styles: bool = False
    system_fonts_only: bool = False
    font_dirs: list[str] = field(default_factory=list)
    no_remote_fonts: bool = False
    no_size_limit: bool = False
    auto_download: bool = False
    validate: bool = False
    verify: bool = False
    verify_pixel_threshold: int = 10
    verify_image_threshold: float = 5.0
    jobs: int = 4
    continue_on_error: bool = True


@dataclass
class InputEntry:
    """A single input entry - either a file or folder."""

    path: Path
    is_folder: bool
    # For folders: output_dir + suffix
    output_dir: Path | None = None
    suffix: str = "_text2path"
    # For files: full output path
    output: Path | None = None


@dataclass
class BatchConfig:
    """Complete batch configuration from YAML."""

    settings: BatchSettings
    inputs: list[InputEntry]
    log_file: Path


@dataclass
class ConversionLogEntry:
    """Log entry for a single file conversion."""

    input_path: str
    output_path: str
    status: str  # "success", "skipped", "error"
    reason: str = ""
    text_elements: int = 0
    path_elements: int = 0
    diff_percent: float | None = None
    verify_passed: bool | None = None


class BatchConfigError(ValueError):
    """Raised when batch configuration validation fails."""

    pass


def _validate_settings(settings_data: dict[str, Any]) -> list[str]:
    """Validate settings section and return list of errors.

    Validates types, value ranges, and semantic constraints.
    """
    errors: list[str] = []

    # Type validators for each field
    validators: dict[str, tuple[type | tuple[type, ...], str]] = {
        "precision": (int, "integer"),
        "preserve_styles": (bool, "boolean"),
        "system_fonts_only": (bool, "boolean"),
        "font_dirs": (list, "list"),
        "no_remote_fonts": (bool, "boolean"),
        "no_size_limit": (bool, "boolean"),
        "auto_download": (bool, "boolean"),
        "validate": (bool, "boolean"),
        "verify": (bool, "boolean"),
        "verify_pixel_threshold": (int, "integer"),
        "verify_image_threshold": ((int, float), "number"),
        "jobs": (int, "integer"),
        "continue_on_error": (bool, "boolean"),
    }

    # Validate types
    for key, value in settings_data.items():
        if key not in validators:
            errors.append(f"settings.{key}: unknown setting (will be ignored)")
            continue

        expected_type, type_name = validators[key]
        if not isinstance(value, expected_type):
            # Handle special case: YAML parses 1/0 as ints, allow for bools
            if expected_type is bool and isinstance(value, int):
                continue
            errors.append(
                f"settings.{key}: expected {type_name}, got {type(value).__name__}"
            )

    # Validate value ranges
    if "precision" in settings_data:
        precision = settings_data["precision"]
        if isinstance(precision, int) and not (1 <= precision <= 10):
            errors.append("settings.precision: must be between 1 and 10")

    if "verify_pixel_threshold" in settings_data:
        threshold = settings_data["verify_pixel_threshold"]
        if isinstance(threshold, int) and not (1 <= threshold <= 255):
            errors.append("settings.verify_pixel_threshold: must be between 1 and 255")

    if "verify_image_threshold" in settings_data:
        threshold = settings_data["verify_image_threshold"]
        if isinstance(threshold, (int, float)) and not (0.0 <= threshold <= 100.0):
            errors.append(
                "settings.verify_image_threshold: must be between 0.0 and 100.0"
            )

    if "jobs" in settings_data:
        jobs = settings_data["jobs"]
        if isinstance(jobs, int) and jobs < 1:
            errors.append("settings.jobs: must be at least 1")

    # Validate font_dirs is a list of strings
    if "font_dirs" in settings_data:
        font_dirs = settings_data["font_dirs"]
        if isinstance(font_dirs, list):
            for i, d in enumerate(font_dirs):
                if not isinstance(d, str):
                    errors.append(
                        f"settings.font_dirs[{i}]: expected string path, "
                        f"got {type(d).__name__}"
                    )

    return errors


def _validate_input_entry(i: int, entry: dict[str, Any]) -> list[str]:
    """Validate a single input entry and return list of errors."""
    errors: list[str] = []

    # Check required path field
    if "path" not in entry:
        errors.append(f"inputs[{i}]: missing required 'path' field")
        return errors  # Can't validate further without path

    path_value = entry["path"]
    if not isinstance(path_value, str):
        errors.append(
            f"inputs[{i}].path: expected string, got {type(path_value).__name__}"
        )
        return errors

    path = Path(path_value)

    # Determine if folder or file
    if path.exists():
        is_folder = path.is_dir()
    else:
        # Infer from trailing slash or extension
        is_folder = path_value.endswith("/") or not path.suffix

    if is_folder:
        # Folder mode validation
        if "output_dir" not in entry:
            errors.append(
                f"inputs[{i}]: folder mode requires 'output_dir' field "
                f"(path '{path_value}' is a directory)"
            )
        elif not isinstance(entry["output_dir"], str):
            errors.append(
                f"inputs[{i}].output_dir: expected string, "
                f"got {type(entry['output_dir']).__name__}"
            )

        if "suffix" in entry and not isinstance(entry["suffix"], str):
            suffix_type = type(entry["suffix"]).__name__
            errors.append(f"inputs[{i}].suffix: expected string, got {suffix_type}")

        # Warn about file-mode fields in folder mode
        if "output" in entry:
            errors.append(
                f"inputs[{i}]: 'output' field ignored in folder mode "
                "(use 'output_dir' + 'suffix' instead)"
            )
    else:
        # File mode validation
        if "output" not in entry:
            errors.append(
                f"inputs[{i}]: file mode requires 'output' field "
                f"(path '{path_value}' is a file)"
            )
        elif not isinstance(entry["output"], str):
            errors.append(
                f"inputs[{i}].output: expected string, "
                f"got {type(entry['output']).__name__}"
            )

        # Warn about folder-mode fields in file mode
        if "output_dir" in entry:
            errors.append(
                f"inputs[{i}]: 'output_dir' field ignored in file mode "
                "(use 'output' for explicit output path)"
            )

    return errors


def load_batch_config(config_path: Path) -> BatchConfig:
    """Load and validate batch configuration from YAML file.

    Performs comprehensive validation:
    - Type checking for all fields
    - Value range validation (precision, thresholds, etc.)
    - Required field validation for inputs
    - Mode-specific validation (folder vs file mode)

    Raises:
        BatchConfigError: If validation fails, with detailed error messages.
        FileNotFoundError: If config file doesn't exist.
        yaml.YAMLError: If YAML parsing fails.
    """
    # Check file exists
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    # Parse YAML
    with open(config_path) as f:
        try:
            data = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise BatchConfigError(f"Invalid YAML syntax: {e}") from e

    if not data:
        raise BatchConfigError("Empty YAML config file")

    if not isinstance(data, dict):
        raise BatchConfigError(
            f"Config file must contain a YAML mapping, not {type(data).__name__}"
        )

    # Collect all validation errors
    all_errors: list[str] = []

    # Validate settings section
    settings_data = data.get("settings", {})
    if settings_data is None:
        settings_data = {}
    if not isinstance(settings_data, dict):
        all_errors.append(
            f"settings: expected mapping, got {type(settings_data).__name__}"
        )
        settings_data = {}
    else:
        all_errors.extend(_validate_settings(settings_data))

    # Validate inputs section
    inputs_data = data.get("inputs")
    if inputs_data is None:
        all_errors.append("inputs: required field is missing")
        inputs_data = []
    elif not isinstance(inputs_data, list):
        all_errors.append(f"inputs: expected list, got {type(inputs_data).__name__}")
        inputs_data = []
    elif len(inputs_data) == 0:
        all_errors.append("inputs: at least one input entry is required")

    # Validate each input entry
    for i, entry in enumerate(inputs_data):
        if not isinstance(entry, dict):
            all_errors.append(
                f"inputs[{i}]: expected mapping, got {type(entry).__name__}"
            )
            continue
        all_errors.extend(_validate_input_entry(i, entry))

    # Validate log_file
    log_file_value = data.get("log_file")
    if log_file_value is not None and not isinstance(log_file_value, str):
        all_errors.append(
            f"log_file: expected string, got {type(log_file_value).__name__}"
        )

    # If there are errors, raise with all of them
    if all_errors:
        error_msg = "Batch config validation failed:\n" + "\n".join(
            f"  - {e}" for e in all_errors
        )
        raise BatchConfigError(error_msg)

    # Build validated config objects
    settings = BatchSettings(
        precision=settings_data.get("precision", 6),
        preserve_styles=bool(settings_data.get("preserve_styles", False)),
        system_fonts_only=bool(settings_data.get("system_fonts_only", False)),
        font_dirs=settings_data.get("font_dirs", []),
        no_remote_fonts=bool(settings_data.get("no_remote_fonts", False)),
        no_size_limit=bool(settings_data.get("no_size_limit", False)),
        auto_download=bool(settings_data.get("auto_download", False)),
        validate=bool(settings_data.get("validate", False)),
        verify=bool(settings_data.get("verify", False)),
        verify_pixel_threshold=settings_data.get("verify_pixel_threshold", 10),
        verify_image_threshold=float(settings_data.get("verify_image_threshold", 5.0)),
        jobs=settings_data.get("jobs", 4),
        continue_on_error=bool(settings_data.get("continue_on_error", True)),
    )

    # Build input entries (already validated above)
    inputs: list[InputEntry] = []
    for entry in inputs_data:
        if not isinstance(entry, dict) or "path" not in entry:
            continue

        path = Path(entry["path"])

        # Determine if folder or file
        if path.exists():
            is_folder = path.is_dir()
        else:
            is_folder = str(entry["path"]).endswith("/") or not path.suffix

        if is_folder:
            inputs.append(
                InputEntry(
                    path=path,
                    is_folder=True,
                    output_dir=Path(entry["output_dir"]),
                    suffix=entry.get("suffix", "_text2path"),
                )
            )
        else:
            inputs.append(
                InputEntry(
                    path=path,
                    is_folder=False,
                    output=Path(entry["output"]),
                )
            )

    # Log file path
    log_file = Path(data.get("log_file", "batch_conversion_log.json"))

    return BatchConfig(settings=settings, inputs=inputs, log_file=log_file)


def find_svg_files_with_text(folder: Path) -> list[Path]:
    """Find all SVG files in folder that contain text elements."""
    from svg_text2path.svg.parser import find_text_elements, parse_svg

    svg_files = []
    for svg_path in folder.glob("*.svg"):
        try:
            tree = parse_svg(svg_path)
            root = tree.getroot()
            if root is not None:
                text_elements = find_text_elements(root)
                if text_elements:
                    svg_files.append(svg_path)
        except Exception:
            # Skip files that can't be parsed
            pass
    return sorted(svg_files)


def run_verification(
    original: Path,
    converted: Path,
    pixel_threshold: int,
    image_threshold: float,
) -> tuple[float | None, bool | None]:
    """Run sbb-compare verification and return (diff_percent, passed)."""
    import shutil

    bun_path = shutil.which("bun")
    if not bun_path:
        return None, None

    # Use original's parent as CWD
    cwd = original.parent
    orig_rel = original.name
    try:
        conv_rel = converted.relative_to(cwd)
    except ValueError:
        conv_rel = converted

    cmd = [
        "bunx",
        "sbb-compare",
        "--quiet",
        "--headless",
        "--threshold",
        str(pixel_threshold),
        str(orig_rel),
        str(conv_rel),
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            cwd=cwd,
        )
        output = result.stdout.strip()
        clean_output = output.replace("%", "").strip()
        if clean_output:
            diff_pct = float(clean_output)
            passed = diff_pct <= image_threshold
            return diff_pct, passed
    except Exception:
        pass

    return None, None


# ---------------------------------------------------------------------------
# Batch Commands
# ---------------------------------------------------------------------------


@click.group()
def batch() -> None:
    """Batch processing commands for multiple SVG files."""
    pass


@batch.command("template")
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


@batch.command("convert")
@click.argument("config_file", type=click.Path(exists=True, path_type=Path))
@click.pass_context
def batch_convert(
    ctx: click.Context,
    config_file: Path,
) -> None:
    """Convert multiple SVG files using YAML configuration.

    CONFIG_FILE: Path to YAML configuration file.

    \b
    YAML config structure:
      settings:           # Conversion settings (all optional)
        precision: 6
        preserve_styles: false
        system_fonts_only: false
        font_dirs: []
        no_remote_fonts: false
        no_size_limit: false
        auto_download: false
        validate: false
        verify: false
        verify_pixel_threshold: 10
        verify_image_threshold: 5.0
        jobs: 4
        continue_on_error: true

      inputs:             # List of files or folders to convert
        # Folder mode (auto-detected when path is a directory)
        - path: samples/icons/
          output_dir: converted/icons/
          suffix: _converted

        # File mode (auto-detected when path is a file)
        - path: samples/logo.svg
          output: converted/brand/company_logo.svg

      log_file: batch_log.json  # Optional, defaults to batch_conversion_log.json

    \b
    Example:
      text2path batch convert batch_config.yaml
    """
    app_config = ctx.obj.get("config", Config.load())
    log_level = ctx.obj.get("log_level", "WARNING")

    # Load batch config
    try:
        batch_cfg = load_batch_config(config_file)
    except Exception as e:
        console.print(f"[red]Error loading config:[/red] {e}")
        raise SystemExit(1) from None

    settings = batch_cfg.settings

    # Apply config settings to app config
    if settings.system_fonts_only:
        app_config.fonts.system_only = True
    if settings.font_dirs:
        app_config.fonts.custom_dirs = [Path(d) for d in settings.font_dirs]
    if settings.no_remote_fonts:
        app_config.fonts.remote = False
    if settings.no_size_limit:
        app_config.security.ignore_size_limits = True

    # Create converter
    converter = Text2PathConverter(
        precision=settings.precision,
        preserve_styles=settings.preserve_styles,
        log_level=log_level,
        config=app_config,
        auto_download_fonts=settings.auto_download,
        validate_svg=settings.validate,
    )

    # Collect all file pairs (input, output)
    file_pairs: list[tuple[Path, Path]] = []

    console.print("[bold]Collecting input files...[/bold]")

    for entry in batch_cfg.inputs:
        if entry.is_folder:
            if not entry.path.exists():
                console.print(
                    f"[yellow]Warning:[/yellow] Folder not found: {entry.path}"
                )
                continue

            # Find SVG files with text elements
            svg_files = find_svg_files_with_text(entry.path)
            console.print(
                f"  [dim]{entry.path}[/dim]: {len(svg_files)} SVG files with text"
            )

            # Ensure output dir exists
            if entry.output_dir:
                entry.output_dir.mkdir(parents=True, exist_ok=True)

            for svg_file in svg_files:
                out_name = f"{svg_file.stem}{entry.suffix}.svg"
                out_path = entry.output_dir / out_name if entry.output_dir else None
                if out_path:
                    file_pairs.append((svg_file, out_path))
        else:
            # Single file
            if not entry.path.exists():
                console.print(f"[yellow]Warning:[/yellow] File not found: {entry.path}")
                continue

            if entry.output:
                # Ensure output directory exists
                entry.output.parent.mkdir(parents=True, exist_ok=True)
                file_pairs.append((entry.path, entry.output))

    if not file_pairs:
        console.print("[red]Error:[/red] No valid input files found")
        raise SystemExit(1)

    console.print(f"\n[bold]Converting {len(file_pairs)} files...[/bold]")

    # Process files
    log_entries: list[ConversionLogEntry] = []
    success_count = 0
    skipped_count = 0
    error_count = 0
    verify_pass_count = 0
    verify_fail_count = 0

    def process_file(pair: tuple[Path, Path]) -> ConversionLogEntry:
        input_path, output_path = pair

        try:
            result = converter.convert_file(input_path, output_path)

            if result.success:
                # Check if any text was converted
                if result.text_count == 0:
                    return ConversionLogEntry(
                        input_path=str(input_path),
                        output_path=str(output_path),
                        status="skipped",
                        reason="No text elements found",
                    )

                log_entry = ConversionLogEntry(
                    input_path=str(input_path),
                    output_path=str(output_path),
                    status="success",
                    text_elements=result.text_count,
                    path_elements=result.path_count,
                )

                # Run verification if enabled
                if settings.verify:
                    diff_pct, passed = run_verification(
                        input_path,
                        output_path,
                        settings.verify_pixel_threshold,
                        settings.verify_image_threshold,
                    )
                    log_entry.diff_percent = diff_pct
                    log_entry.verify_passed = passed

                return log_entry
            else:
                return ConversionLogEntry(
                    input_path=str(input_path),
                    output_path=str(output_path),
                    status="error",
                    reason=str(result.errors),
                )
        except PermissionError as e:
            return ConversionLogEntry(
                input_path=str(input_path),
                output_path=str(output_path),
                status="error",
                reason=f"Permission denied: {e}",
            )
        except OSError as e:
            return ConversionLogEntry(
                input_path=str(input_path),
                output_path=str(output_path),
                status="error",
                reason=f"I/O error: {e}",
            )
        except Exception as e:
            return ConversionLogEntry(
                input_path=str(input_path),
                output_path=str(output_path),
                status="error",
                reason=str(e),
            )

    with Progress(console=console) as progress:
        task = progress.add_task("[green]Converting...", total=len(file_pairs))

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=settings.jobs
        ) as executor:
            future_to_pair = {
                executor.submit(process_file, pair): pair for pair in file_pairs
            }

            for future in concurrent.futures.as_completed(future_to_pair):
                pair = future_to_pair[future]
                try:
                    log_entry = future.result()
                    log_entries.append(log_entry)

                    if log_entry.status == "success":
                        success_count += 1
                        if log_entry.verify_passed is True:
                            verify_pass_count += 1
                        elif log_entry.verify_passed is False:
                            verify_fail_count += 1
                    elif log_entry.status == "skipped":
                        skipped_count += 1
                    else:
                        error_count += 1
                        if not settings.continue_on_error:
                            console.print(
                                f"[red]Error in {pair[0]}:[/red] {log_entry.reason}"
                            )
                            raise SystemExit(1)
                except Exception as e:
                    error_count += 1
                    log_entries.append(
                        ConversionLogEntry(
                            input_path=str(pair[0]),
                            output_path=str(pair[1]),
                            status="error",
                            reason=str(e),
                        )
                    )
                    if not settings.continue_on_error:
                        console.print(f"[red]Error processing {pair[0]}:[/red] {e}")
                        raise SystemExit(1) from None
                finally:
                    progress.advance(task)

    # Write log file
    log_data = {
        "timestamp": datetime.now(UTC).isoformat(),
        "config_file": str(config_file),
        "settings": {
            "precision": settings.precision,
            "preserve_styles": settings.preserve_styles,
            "auto_download": settings.auto_download,
            "validate": settings.validate,
            "verify": settings.verify,
            "verify_pixel_threshold": settings.verify_pixel_threshold,
            "verify_image_threshold": settings.verify_image_threshold,
        },
        "summary": {
            "total": len(file_pairs),
            "success": success_count,
            "skipped": skipped_count,
            "errors": error_count,
            "verify_passed": verify_pass_count if settings.verify else None,
            "verify_failed": verify_fail_count if settings.verify else None,
        },
        "files": [
            {
                "input": e.input_path,
                "output": e.output_path,
                "status": e.status,
                "reason": e.reason if e.reason else None,
                "text_elements": e.text_elements if e.text_elements else None,
                "path_elements": e.path_elements if e.path_elements else None,
                "diff_percent": e.diff_percent,
                "verify_passed": e.verify_passed,
            }
            for e in log_entries
        ],
    }

    batch_cfg.log_file.write_text(json.dumps(log_data, indent=2))

    # Summary table
    console.print()
    table = Table(title="Batch Conversion Summary")
    table.add_column("Metric", style="cyan")
    table.add_column("Count", justify="right")

    table.add_row("Total files", str(len(file_pairs)))
    table.add_row("[green]Converted[/green]", str(success_count))
    table.add_row("[yellow]Skipped (no text)[/yellow]", str(skipped_count))
    table.add_row("[red]Errors[/red]", str(error_count))

    if settings.verify:
        table.add_row("", "")
        table.add_row("[green]Verify passed[/green]", str(verify_pass_count))
        table.add_row("[red]Verify failed[/red]", str(verify_fail_count))

    console.print(table)
    console.print()
    console.print(f"[blue]Log file:[/blue] {batch_cfg.log_file}")

    if error_count > 0:
        console.print(
            f"\n[yellow]Warning:[/yellow] {error_count} files had errors. "
            f"Check {batch_cfg.log_file} for details."
        )

    if error_count > 0 and not settings.continue_on_error:
        raise SystemExit(1)


@batch.command("compare")
@click.option(
    "--samples-dir",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Directory with text*.svg samples (default: samples/reference_objects)",
)
@click.option(
    "--output-dir",
    "-o",
    type=click.Path(path_type=Path),
    default=None,
    help="Output directory (default: tmp/batch_compare)",
)
@click.option(
    "--skip",
    multiple=True,
    default=["text4.svg"],
    help="Files to skip (can be specified multiple times)",
)
@click.option(
    "--threshold",
    type=float,
    default=3.0,
    help="Diff percentage threshold for pass/fail",
)
@click.option("--scale", type=float, default=1.0, help="Render scale for comparison")
@click.option(
    "--resolution",
    default="nominal",
    type=click.Choice(["nominal", "viewbox", "full", "scale", "stretch", "clip"]),
    help="Resolution mode for sbb-compare",
)
@click.option("-p", "--precision", type=int, default=6, help="Path precision")
@click.option("--timeout", type=int, default=60, help="Per-command timeout (seconds)")
@click.option("--csv", "csv_output", is_flag=True, help="Output CSV format only")
@click.pass_context
def batch_compare(
    ctx: click.Context,
    samples_dir: Path | None,
    output_dir: Path | None,
    skip: tuple[str, ...],
    threshold: float,
    scale: float,
    resolution: str,
    precision: int,
    timeout: int,
    csv_output: bool,
) -> None:
    """Convert and compare text*.svg samples in one step.

    Converts all matching SVG files, then runs visual comparison
    using svg-bbox's sbb-compare batch mode.
    """
    config = ctx.obj.get("config", Config.load())
    log_level = ctx.obj.get("log_level", "WARNING")

    # Find repo root (from cli/commands/batch.py -> project root)
    repo_root = Path(__file__).resolve().parents[3]

    # Set defaults relative to repo root
    if samples_dir is None:
        samples_dir = repo_root / "samples" / "reference_objects"
    if output_dir is None:
        output_dir = repo_root / "tmp" / "batch_compare"

    conv_dir = output_dir / "converted"
    output_dir.mkdir(parents=True, exist_ok=True)
    conv_dir.mkdir(parents=True, exist_ok=True)

    # Find text*.svg files
    skip_set = set(skip)
    svg_files = [
        f for f in sorted(samples_dir.glob("text*.svg")) if f.name not in skip_set
    ]

    if not svg_files:
        console.print(f"[yellow]Warning:[/yellow] No text*.svg in {samples_dir}")
        return

    # Create converter
    converter = Text2PathConverter(
        precision=precision,
        log_level=log_level,
        config=config,
    )

    # Convert files and build pairs
    pairs: list[dict[str, str]] = []
    conversion_errors: list[tuple[str, str]] = []

    if not csv_output:
        console.print(f"[bold]Converting {len(svg_files)} files...[/bold]")

    for svg in svg_files:
        out_svg = conv_dir / f"{svg.stem}_conv.svg"
        try:
            result = converter.convert_file(svg, out_svg)
            if result.success:
                pairs.append({"a": str(svg), "b": str(out_svg)})
                if not csv_output:
                    console.print(f"  [green]OK[/green] {svg.name}")
            else:
                conversion_errors.append((svg.name, str(result.errors)))
                if not csv_output:
                    console.print(f"  [red]FAIL[/red] {svg.name}: {result.errors}")
        except Exception as e:
            conversion_errors.append((svg.name, str(e)))
            if not csv_output:
                console.print(f"  [red]ERROR[/red] {svg.name}: {e}")

    if not pairs:
        console.print("[red]Error:[/red] No files converted successfully")
        raise SystemExit(1)

    # Write pairs JSON for sbb-compare batch mode
    pairs_path = output_dir / "pairs.json"
    pairs_path.write_text(json.dumps(pairs))

    # Run sbb-compare in batch mode
    summary_path = output_dir / "summary.json"
    cmd = [
        "npx",
        "sbb-compare",
        "--batch",
        str(pairs_path),
        "--threshold",
        str(int(threshold * 10)),  # sbb-compare uses integer threshold
        "--scale",
        str(scale),
        "--resolution",
        resolution,
        "--json",
    ]

    if not csv_output:
        console.print("\n[bold]Running visual comparison...[/bold]")

    try:
        with summary_path.open("w") as f:
            batch_timeout = timeout * max(1, len(pairs))
            subprocess.run(cmd, check=True, timeout=batch_timeout, stdout=f)
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Error:[/red] sbb-compare failed: {e}")
        raise SystemExit(1) from None
    except FileNotFoundError:
        console.print("[red]Error:[/red] sbb-compare not found. npm install svg-bbox")
        raise SystemExit(1) from None

    # Parse and display results
    summary = json.loads(summary_path.read_text())
    results = summary.get("results", [])

    pass_count = 0
    fail_count = 0

    if csv_output:
        # CSV output mode
        print("file,diff_percent,status")
        for r in results:
            diff = float(r.get("diffPercent") or r.get("diff") or 0)
            name = Path(r.get("a", "")).name
            status = "pass" if diff < threshold else "FAIL"
            print(f"{name},{diff:.2f},{status}")
            if status == "pass":
                pass_count += 1
            else:
                fail_count += 1
    else:
        # Rich table output
        table = Table(title="Comparison Results")
        table.add_column("File", style="cyan")
        table.add_column("Diff %", justify="right")
        table.add_column("Status", justify="center")

        for r in results:
            diff = float(r.get("diffPercent") or r.get("diff") or 0)
            name = Path(r.get("a", "")).name
            if diff < threshold:
                status = "[green]PASS[/green]"
                pass_count += 1
            else:
                status = "[red]FAIL[/red]"
                fail_count += 1
            table.add_row(name, f"{diff:.2f}", status)

        console.print(table)
        console.print()
        console.print(f"[bold]Summary:[/bold] {pass_count} passed, {fail_count} failed")
        console.print(f"[blue]Results:[/blue] {summary_path}")

    if fail_count > 0:
        raise SystemExit(1)


@batch.command("regression")
@click.option(
    "--samples-dir",
    type=click.Path(exists=True, path_type=Path),
    default=None,
    help="Directory with text*.svg samples",
)
@click.option(
    "--output-dir",
    "-o",
    type=click.Path(path_type=Path),
    default=None,
    help="Output directory (default: tmp/regression_check)",
)
@click.option(
    "--registry",
    type=click.Path(path_type=Path),
    default=None,
    help="Path to regression registry JSON (default: tmp/regression_history.json)",
)
@click.option(
    "--skip",
    multiple=True,
    default=[],
    help="Files to skip",
)
@click.option(
    "--threshold",
    type=int,
    default=20,
    help="Threshold for sbb-compare",
)
@click.option("--scale", type=float, default=4.0, help="Render scale")
@click.option(
    "--resolution",
    default="viewbox",
    type=click.Choice(["nominal", "viewbox", "full", "scale", "stretch", "clip"]),
    help="Resolution mode",
)
@click.option("-p", "--precision", type=int, default=3, help="Path precision")
@click.option("--timeout", type=int, default=300, help="Comparer timeout (seconds)")
@click.pass_context
def batch_regression(
    ctx: click.Context,
    samples_dir: Path | None,
    output_dir: Path | None,
    registry: Path | None,
    skip: tuple[str, ...],
    threshold: int,
    scale: float,
    resolution: str,
    precision: int,
    timeout: int,
) -> None:
    """Run batch compare and track results for regression detection.

    Converts samples, compares against originals, saves results to
    a timestamped registry, and warns if any diff percentage increased
    compared to the previous run with matching settings.
    """
    config = ctx.obj.get("config", Config.load())
    log_level = ctx.obj.get("log_level", "WARNING")

    # Find repo root
    repo_root = Path(__file__).resolve().parents[3]

    # Set defaults
    if samples_dir is None:
        samples_dir = repo_root / "samples" / "reference_objects"
    if output_dir is None:
        output_dir = repo_root / "tmp" / "regression_check"
    if registry is None:
        registry = repo_root / "tmp" / "regression_history.json"

    # Create timestamped run directory
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    run_dir = output_dir / timestamp
    conv_dir = run_dir / "converted"
    run_dir.mkdir(parents=True, exist_ok=True)
    conv_dir.mkdir(parents=True, exist_ok=True)

    # Find text*.svg files
    skip_set = set(skip)
    svg_files = [
        f
        for f in sorted(samples_dir.glob("text*.svg"))
        if f.name not in skip_set and "-paths" not in f.name
    ]

    if not svg_files:
        console.print("[yellow]Warning:[/yellow] No text*.svg files found")
        return

    # Create converter
    converter = Text2PathConverter(
        precision=precision,
        log_level=log_level,
        config=config,
    )

    # Convert files
    pairs: list[tuple[str, str]] = []
    failures: list[tuple[str, str]] = []

    console.print(f"[bold]Converting {len(svg_files)} files...[/bold]")

    for svg in svg_files:
        out_svg = conv_dir / f"{svg.stem}_conv.svg"
        try:
            result = converter.convert_file(svg, out_svg)
            if result.success:
                pairs.append((str(svg), str(out_svg)))
                console.print(f"  [green]OK[/green] {svg.name}")
            else:
                failures.append((svg.name, str(result.errors)))
                console.print(f"  [red]FAIL[/red] {svg.name}")
        except Exception as e:
            failures.append((svg.name, str(e)))
            console.print(f"  [red]ERROR[/red] {svg.name}: {e}")

    if not pairs:
        console.print("[red]Error:[/red] No files converted successfully")
        raise SystemExit(1)

    # Write pairs file for sbb-compare (tab-separated for compatibility)
    pairs_path = run_dir / "pairs.txt"
    pairs_path.write_text("\n".join("\t".join(p) for p in pairs))

    # Run comparison (try sbb-comparer.cjs first, fall back to npx sbb-compare)
    summary_path = run_dir / "summary.json"
    sbb_comparer = repo_root / "SVG-BBOX" / "sbb-comparer.cjs"

    if sbb_comparer.exists():
        cmd = [
            "node",
            str(sbb_comparer),
            "--batch",
            str(pairs_path),
            "--threshold",
            str(threshold),
            "--scale",
            str(scale),
            "--resolution",
            resolution,
            "--json",
        ]
    else:
        # Fall back to npx sbb-compare with JSON pairs
        pairs_json_path = run_dir / "pairs.json"
        pairs_json = [{"a": a, "b": b} for a, b in pairs]
        pairs_json_path.write_text(json.dumps(pairs_json))
        cmd = [
            "npx",
            "sbb-compare",
            "--batch",
            str(pairs_json_path),
            "--threshold",
            str(threshold),
            "--scale",
            str(scale),
            "--resolution",
            resolution,
            "--json",
        ]

    console.print("\n[bold]Running comparison...[/bold]")

    try:
        with summary_path.open("w") as f:
            subprocess.run(cmd, check=True, timeout=timeout, stdout=f)
    except subprocess.CalledProcessError as e:
        console.print(f"[red]Error:[/red] Comparer failed: {e}")
        raise SystemExit(1) from None
    except FileNotFoundError:
        console.print("[red]Error:[/red] Comparer not found")
        raise SystemExit(1) from None

    # Parse results
    summary = json.loads(summary_path.read_text())
    result_map: dict[str, float] = {}

    for r in summary.get("results", []):
        diff = r.get("diffPercent") or r.get("diffPercentage") or r.get("diff")
        svg_path = r.get("a") or r.get("svg1") or ""
        name = Path(svg_path).name
        if diff is not None:
            result_map[name] = float(diff)

    # Load existing registry
    registry_data: list[dict[str, Any]] = []
    if registry.exists():
        try:
            registry_data = json.loads(registry.read_text())
        except Exception:
            registry_data = []

    # Find previous entry with matching settings for regression comparison
    prev_entry = None
    for entry in reversed(registry_data):
        if (
            entry.get("threshold") == threshold
            and entry.get("scale") == scale
            and entry.get("resolution") == resolution
            and entry.get("precision") == precision
        ):
            prev_entry = entry
            break

    # Detect regressions
    regressions: list[tuple[str, float, float]] = []
    if prev_entry and "results" in prev_entry:
        prev_results = prev_entry["results"]
        for name, diff in result_map.items():
            if name in prev_results and diff > prev_results[name]:
                regressions.append((name, prev_results[name], diff))

    # Append current run to registry
    registry_data.append(
        {
            "timestamp": timestamp,
            "threshold": threshold,
            "scale": scale,
            "resolution": resolution,
            "precision": precision,
            "results": result_map,
            "failures": failures,
        }
    )
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text(json.dumps(registry_data, indent=2))

    # Display results
    console.print()
    table = Table(title="Regression Check Results")
    table.add_column("File", style="cyan")
    table.add_column("Diff %", justify="right")
    table.add_column("Change", justify="right")

    for name, diff in sorted(result_map.items()):
        change = ""
        if prev_entry and "results" in prev_entry and name in prev_entry["results"]:
            prev_diff = prev_entry["results"][name]
            delta = diff - prev_diff
            if delta > 0:
                change = f"[red]+{delta:.2f}[/red]"
            elif delta < 0:
                change = f"[green]{delta:.2f}[/green]"
            else:
                change = "[dim]0.00[/dim]"
        table.add_row(name, f"{diff:.2f}", change)

    console.print(table)
    console.print()

    if regressions:
        console.print("[bold red]WARNING: Regression detected![/bold red]")
        for name, old_diff, new_diff in regressions:
            console.print(f"  {name}: {old_diff:.2f}% -> {new_diff:.2f}%")
        console.print()
        console.print("[yellow]Consider reverting recent changes.[/yellow]")
    else:
        console.print("[green]No regression detected.[/green]")

    console.print(f"\n[blue]Registry:[/blue] {registry}")
    console.print(f"[blue]Run output:[/blue] {run_dir}")
