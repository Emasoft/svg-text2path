"""SVG parsing and manipulation for svg-text2path.

This subpackage provides:
- Safe SVG parsing with XXE protection (defusedxml)
- Text element detection (text, tspan, textPath)
- SVG output generation
"""

from svg_text2path.svg.parser import (
    parse_svg,
    parse_svg_string,
    find_text_elements,
    write_svg,
)

__all__ = ["parse_svg", "parse_svg_string", "find_text_elements", "write_svg"]
