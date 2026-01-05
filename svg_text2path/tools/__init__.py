"""External tools integration for svg-text2path.

This subpackage provides:
- Auto-installer for font tools (FontGet, fnt, nerdconvert)
- svg-bbox wrapper for visual comparison
- External tool invocation utilities
"""

from svg_text2path.tools.svg_bbox import compare_svgs, get_bounding_boxes
from svg_text2path.tools.installer import ensure_tool_installed

__all__ = [
    "compare_svgs",
    "get_bounding_boxes",
    "ensure_tool_installed",
]
