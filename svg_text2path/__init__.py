"""svg-text2path: Convert SVG text elements to path outlines.

This library provides comprehensive SVG text-to-path conversion with:
- HarfBuzz text shaping for accurate glyph placement
- BiDi support for RTL languages (Arabic, Hebrew, etc.)
- Cross-platform font resolution with fallbacks
- Multiple input format support (file, string, tree, embedded)

Example:
    >>> from svg_text2path import Text2PathConverter
    >>> converter = Text2PathConverter()
    >>> converter.convert_file("input.svg", "output.svg")
"""

from svg_text2path.api import ConversionResult, Text2PathConverter
from svg_text2path.config import Config
from svg_text2path.exceptions import (
    ConversionError,
    FontNotFoundError,
    FormatNotSupportedError,
    SVGParseError,
    Text2PathError,
)
from svg_text2path.fonts.cache import FontCache
from svg_text2path.tools.dependencies import (
    DependencyInfo,
    DependencyReport,
    DependencyStatus,
    DependencyType,
    format_dependency_report,
    print_dependency_report,
    verify_all_dependencies,
)

__version__ = "0.4.2"
__author__ = "Emasoft"
__email__ = "713559+Emasoft@users.noreply.github.com"

__all__ = [
    # Main API
    "Text2PathConverter",
    "ConversionResult",
    "Config",
    # Font handling
    "FontCache",
    # Exceptions
    "Text2PathError",
    "FontNotFoundError",
    "SVGParseError",
    "ConversionError",
    "FormatNotSupportedError",
    # Dependency verification
    "verify_all_dependencies",
    "print_dependency_report",
    "format_dependency_report",
    "DependencyReport",
    "DependencyInfo",
    "DependencyStatus",
    "DependencyType",
    # Metadata
    "__version__",
]
