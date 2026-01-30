"""Batch configuration dataclasses and loading logic."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .validation import (
    _is_remote_path,
    _parse_compact_entry,
    _validate_path_format,
)

# ---------------------------------------------------------------------------
# Batch Config Schema
# ---------------------------------------------------------------------------


@dataclass
class FormatSelection:
    """File formats to include in batch conversion.

    Only formats explicitly set to True will be processed.
    SVG is enabled by default; all other formats require explicit opt-in.
    """

    svg: bool = True  # .svg files (enabled by default)
    svgz: bool = False  # .svgz compressed files
    html: bool = False  # .html, .htm, .xhtml files
    css: bool = False  # .css files (data URIs)
    json: bool = False  # .json files (escaped SVG)
    csv: bool = False  # .csv files (escaped SVG)
    markdown: bool = False  # .md, .markdown files
    python: bool = False  # .py files (SVG in strings)
    javascript: bool = False  # .js, .ts, .jsx, .tsx files
    rst: bool = False  # .rst reStructuredText files
    plaintext: bool = False  # .txt files (data URIs)
    epub: bool = False  # .epub ebook files


# Map format flags to file extensions
FORMAT_EXTENSIONS: dict[str, list[str]] = {
    "svg": [".svg"],
    "svgz": [".svgz"],
    "html": [".html", ".htm", ".xhtml"],
    "css": [".css"],
    "json": [".json"],
    "csv": [".csv"],
    "markdown": [".md", ".markdown"],
    "python": [".py"],
    "javascript": [".js", ".ts", ".jsx", ".tsx"],
    "rst": [".rst"],
    "plaintext": [".txt"],
    "epub": [".epub"],
}


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
    allow_overwrite: bool = False  # Allow in-place conversion with .bak backup
    preflight_check: bool = True  # Check path accessibility before processing
    formats: FormatSelection = field(default_factory=FormatSelection)


@dataclass
class InputEntry:
    """A single input entry - either a file or folder."""

    path: Path | str  # Path or remote URL/SSH path
    is_folder: bool
    is_remote_input: bool = False  # True if input is SSH/URL
    is_remote_output: bool = False  # True if output is SSH/URL
    # For folders: output_dir + suffix
    output_dir: Path | str | None = None
    suffix: str = "_text2path"
    # For files: full output path
    output: Path | str | None = None


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


def _validate_formats(formats_data: dict[str, Any]) -> list[str]:
    """Validate formats section and return list of errors."""
    errors: list[str] = []

    valid_formats = {
        "svg",
        "svgz",
        "html",
        "css",
        "json",
        "csv",
        "markdown",
        "python",
        "javascript",
        "rst",
        "plaintext",
        "epub",
    }

    for key, value in formats_data.items():
        if key not in valid_formats:
            valid_list = ", ".join(sorted(valid_formats))
            errors.append(f"formats.{key}: unknown format (valid: {valid_list})")
            continue
        # Allow int for bool (YAML parses 1/0 as ints)
        if not isinstance(value, (bool, int)):
            errors.append(
                f"formats.{key}: expected boolean, got {type(value).__name__}"
            )

    # Check that at least one format is enabled
    any_enabled = any(bool(formats_data.get(fmt, False)) for fmt in valid_formats)
    if not any_enabled:
        errors.append("formats: at least one format must be enabled (set to true)")

    return errors


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
        "allow_overwrite": (bool, "boolean"),
        "preflight_check": (bool, "boolean"),
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


def _validate_input_entry(
    i: int, entry: dict[str, Any] | str, allow_overwrite: bool = False
) -> tuple[list[str], dict[str, Any] | None]:
    """Validate a single input entry and return (errors, parsed_entry).

    Entry can be:
        - dict: Legacy format with path, output/output_dir, suffix fields
        - str: Compact format "input;output" or "input/;output/;suffix"

    Returns:
        Tuple of (list of error messages, parsed dict or None if errors)
    """
    errors: list[str] = []

    # Handle string format (compact semicolon-delimited)
    if isinstance(entry, str):
        try:
            entry = _parse_compact_entry(entry)
        except ValueError as e:
            errors.append(f"inputs[{i}]: {e}")
            return errors, None

    # Check required path field
    if "path" not in entry:
        errors.append(f"inputs[{i}]: missing required 'path' field")
        return errors, None

    path_value = entry["path"]
    if not isinstance(path_value, str):
        errors.append(
            f"inputs[{i}].path: expected string, got {type(path_value).__name__}"
        )
        return errors, None

    # Validate input path format
    path_errors = _validate_path_format(path_value)
    for err in path_errors:
        errors.append(f"inputs[{i}].path: {err}")

    # Check for remote paths
    is_remote_input = _is_remote_path(path_value)

    # Determine if folder or file
    if entry.get("_is_folder") is not None:
        # Already determined by compact parser
        is_folder = entry["_is_folder"]
    elif is_remote_input:
        # Remote paths: infer from trailing slash
        is_folder = path_value.endswith("/")
    else:
        path = Path(path_value)
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
        else:
            # Validate output_dir path format
            output_errors = _validate_path_format(entry["output_dir"])
            for err in output_errors:
                errors.append(f"inputs[{i}].output_dir: {err}")

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
        else:
            output_value = entry["output"]

            # Validate output path format
            output_errors = _validate_path_format(output_value)
            for err in output_errors:
                errors.append(f"inputs[{i}].output: {err}")

            # Check for same input/output (requires allow_overwrite)
            if path_value == output_value and not allow_overwrite:
                errors.append(
                    f"inputs[{i}]: input and output are the same path. "
                    "Set 'allow_overwrite: true' in settings to enable in-place "
                    "conversion with .bak backup."
                )

        # Warn about folder-mode fields in file mode
        if "output_dir" in entry:
            errors.append(
                f"inputs[{i}]: 'output_dir' field ignored in file mode "
                "(use 'output' for explicit output path)"
            )

    return errors, entry if not errors else None


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

    # Validate formats section (optional - defaults to svg only)
    formats_data = data.get("formats", {})
    if formats_data is None:
        formats_data = {}
    if not isinstance(formats_data, dict):
        all_errors.append(
            f"formats: expected mapping, got {type(formats_data).__name__}"
        )
        formats_data = {}
    elif formats_data:  # Only validate if formats section provided
        all_errors.extend(_validate_formats(formats_data))

    # Get allow_overwrite early for input validation
    allow_overwrite = bool(settings_data.get("allow_overwrite", False))

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

    # Validate each input entry (supports both dict and string format)
    validated_entries: list[dict[str, Any]] = []
    for i, entry in enumerate(inputs_data):
        if not isinstance(entry, (dict, str)):
            all_errors.append(
                f"inputs[{i}]: expected string or mapping, got {type(entry).__name__}"
            )
            continue
        errors, parsed = _validate_input_entry(i, entry, allow_overwrite)
        all_errors.extend(errors)
        if parsed is not None:
            validated_entries.append(parsed)

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

    # Build format selection (svg defaults to True, others to False)
    format_selection = FormatSelection(
        svg=bool(formats_data.get("svg", True)),  # Default: enabled
        svgz=bool(formats_data.get("svgz", False)),
        html=bool(formats_data.get("html", False)),
        css=bool(formats_data.get("css", False)),
        json=bool(formats_data.get("json", False)),
        csv=bool(formats_data.get("csv", False)),
        markdown=bool(formats_data.get("markdown", False)),
        python=bool(formats_data.get("python", False)),
        javascript=bool(formats_data.get("javascript", False)),
        rst=bool(formats_data.get("rst", False)),
        plaintext=bool(formats_data.get("plaintext", False)),
        epub=bool(formats_data.get("epub", False)),
    )

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
        allow_overwrite=allow_overwrite,
        preflight_check=bool(settings_data.get("preflight_check", True)),
        formats=format_selection,
    )

    # Build input entries from validated entries
    inputs: list[InputEntry] = []
    for entry in validated_entries:
        path_str = entry["path"]
        is_remote_input = _is_remote_path(path_str)

        # Determine if folder or file
        if entry.get("_is_folder") is not None:
            is_folder = entry["_is_folder"]
        elif is_remote_input:
            is_folder = path_str.endswith("/")
        else:
            path = Path(path_str)
            if path.exists():
                is_folder = path.is_dir()
            else:
                is_folder = path_str.endswith("/") or not path.suffix

        if is_folder:
            output_str = entry["output_dir"]
            is_remote_output = _is_remote_path(output_str)
            inputs.append(
                InputEntry(
                    path=path_str if is_remote_input else Path(path_str),
                    is_folder=True,
                    is_remote_input=is_remote_input,
                    is_remote_output=is_remote_output,
                    output_dir=output_str if is_remote_output else Path(output_str),
                    suffix=entry.get("suffix", "_text2path"),
                )
            )
        else:
            output_str = entry["output"]
            is_remote_output = _is_remote_path(output_str)
            inputs.append(
                InputEntry(
                    path=path_str if is_remote_input else Path(path_str),
                    is_folder=False,
                    is_remote_input=is_remote_input,
                    is_remote_output=is_remote_output,
                    output=output_str if is_remote_output else Path(output_str),
                )
            )

    # Log file path
    log_file = Path(data.get("log_file", "batch_conversion_log.json"))

    return BatchConfig(settings=settings, inputs=inputs, log_file=log_file)


def get_enabled_extensions(formats: FormatSelection) -> list[str]:
    """Get list of file extensions enabled by format selection."""
    extensions: list[str] = []
    if formats.svg:
        extensions.extend(FORMAT_EXTENSIONS["svg"])
    if formats.svgz:
        extensions.extend(FORMAT_EXTENSIONS["svgz"])
    if formats.html:
        extensions.extend(FORMAT_EXTENSIONS["html"])
    if formats.css:
        extensions.extend(FORMAT_EXTENSIONS["css"])
    if formats.json:
        extensions.extend(FORMAT_EXTENSIONS["json"])
    if formats.csv:
        extensions.extend(FORMAT_EXTENSIONS["csv"])
    if formats.markdown:
        extensions.extend(FORMAT_EXTENSIONS["markdown"])
    if formats.python:
        extensions.extend(FORMAT_EXTENSIONS["python"])
    if formats.javascript:
        extensions.extend(FORMAT_EXTENSIONS["javascript"])
    if formats.rst:
        extensions.extend(FORMAT_EXTENSIONS["rst"])
    if formats.plaintext:
        extensions.extend(FORMAT_EXTENSIONS["plaintext"])
    if formats.epub:
        extensions.extend(FORMAT_EXTENSIONS["epub"])
    return extensions


def find_files_for_conversion(folder: Path, formats: FormatSelection) -> list[Path]:
    """Find files in folder matching enabled formats with convertible content.

    For SVG files, checks for text elements.
    For other formats, uses the format handler's can_handle() method.
    """
    from svg_text2path.formats import match_handler
    from svg_text2path.svg.parser import find_text_elements, parse_svg

    enabled_extensions = get_enabled_extensions(formats)
    if not enabled_extensions:
        return []

    found_files: list[Path] = []

    for ext in enabled_extensions:
        for file_path in folder.glob(f"*{ext}"):
            try:
                # For SVG files, check for text elements directly
                if ext in (".svg", ".svgz"):
                    tree = parse_svg(file_path)
                    root = tree.getroot()
                    if root is not None:
                        text_elements = find_text_elements(root)
                        if text_elements:
                            found_files.append(file_path)
                else:
                    # For other formats, use the handler to check
                    match = match_handler(str(file_path))
                    if match.handler.can_handle(str(file_path)):
                        found_files.append(file_path)
            except Exception:
                # Skip files that can't be parsed
                pass

    return sorted(found_files)


def run_verification(
    original: Path,
    converted: Path,
    pixel_threshold: int,
    image_threshold: float,
) -> tuple[float | None, bool | None]:
    """Run sbb-compare verification and return (diff_percent, passed)."""
    import shutil
    import subprocess

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
