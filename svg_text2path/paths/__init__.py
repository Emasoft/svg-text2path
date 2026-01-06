"""Path generation for svg-text2path.

This subpackage provides:
- Glyph outline to SVG path conversion
- Transform matrix utilities
- Bounding box calculations
"""

from svg_text2path.paths.generator import glyph_to_path, recording_pen_to_svg_path
from svg_text2path.paths.transform import (
    apply_transform_to_path,
    parse_transform_matrix,
)

__all__ = [
    "glyph_to_path",
    "recording_pen_to_svg_path",
    "parse_transform_matrix",
    "apply_transform_to_path",
]
