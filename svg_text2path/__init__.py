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

__version__ = "0.2.0"
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
    # Metadata
    "__version__",
]
