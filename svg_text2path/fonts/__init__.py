"""Font handling for svg-text2path.

This subpackage provides:
- FontCache: Cross-platform font discovery and caching
- Font resolution with fallbacks
- Codepoint coverage tracking
"""

from svg_text2path.exceptions import FontNotFoundError
from svg_text2path.fonts.cache import FontCache

# Backward compatibility alias
MissingFontError = FontNotFoundError

__all__ = ["FontCache", "FontNotFoundError", "MissingFontError"]
