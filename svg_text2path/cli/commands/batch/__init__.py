"""Batch commands - process, compare, and track multiple SVG files."""

from __future__ import annotations

import click

# Import commands
from .compare import batch_compare

# Import config classes and functions for public API
from .config import (
    FORMAT_EXTENSIONS,
    BatchConfig,
    BatchConfigError,
    BatchSettings,
    ConversionLogEntry,
    FormatSelection,
    InputEntry,
    find_files_for_conversion,
    get_enabled_extensions,
    load_batch_config,
    run_verification,
)
from .convert import batch_convert
from .regression import batch_regression
from .template import BATCH_CONFIG_TEMPLATE, batch_template

# Import validation functions for public API
from .validation import (
    PathAccessResult,
    _check_path_accessibility,
    _is_remote_path,
    _parse_compact_entry,
    _validate_path_format,
)

# ---------------------------------------------------------------------------
# Batch Command Group
# ---------------------------------------------------------------------------


@click.group()
def batch() -> None:
    """Batch processing commands for multiple SVG files."""
    pass


# Register subcommands
batch.add_command(batch_template, name="template")
batch.add_command(batch_convert, name="convert")
batch.add_command(batch_compare, name="compare")
batch.add_command(batch_regression, name="regression")


# Public API exports
__all__ = [
    # Command group
    "batch",
    # Config classes
    "BatchConfig",
    "BatchConfigError",
    "BatchSettings",
    "ConversionLogEntry",
    "FormatSelection",
    "FORMAT_EXTENSIONS",
    "InputEntry",
    # Config functions
    "load_batch_config",
    "get_enabled_extensions",
    "find_files_for_conversion",
    "run_verification",
    # Validation classes
    "PathAccessResult",
    # Validation functions
    "_check_path_accessibility",
    "_is_remote_path",
    "_parse_compact_entry",
    "_validate_path_format",
    # Template
    "BATCH_CONFIG_TEMPLATE",
]
