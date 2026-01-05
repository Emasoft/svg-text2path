"""Text shaping for svg-text2path.

This subpackage provides:
- HarfBuzz text shaping wrapper
- BiDi (bidirectional) text handling
- Visual run processing
"""

from svg_text2path.shaping.harfbuzz import (
    shape_text,
    shape_run,
    create_hb_font,
    ShapedGlyph,
    ShapingResult,
)
from svg_text2path.shaping.bidi import (
    apply_bidi_algorithm,
    get_bidi_runs,
    get_visual_runs,
    is_rtl_script,
    detect_base_direction,
    BiDiRun,
)

__all__ = [
    "shape_text",
    "shape_run",
    "create_hb_font",
    "ShapedGlyph",
    "ShapingResult",
    "apply_bidi_algorithm",
    "get_bidi_runs",
    "get_visual_runs",
    "is_rtl_script",
    "detect_base_direction",
    "BiDiRun",
]
