"""External tools integration for svg-text2path.

This subpackage provides:
- Auto-installer for font tools (FontGet, fnt, nerdconvert)
- svg-bbox wrapper for visual comparison
- svg-matrix SVG validation via Bun
- External tool invocation utilities
"""

from svg_text2path.tools.external import (
    CommandResult,
    check_git_installed,
    check_node_installed,
    check_npm_installed,
    run_command,
    which,
)
from svg_text2path.tools.installer import (
    ensure_tool_installed,
    get_tools_dir,
    is_tool_available,
    list_installed_tools,
)
from svg_text2path.tools.svg_bbox import (
    BoundingBox,
    ComparisonResult,
    compare_svgs,
    get_bounding_boxes,
)
from svg_text2path.tools.svg_validator import (
    SVGValidationResult,
    validate_svg_batch,
    validate_svg_file,
    validate_svg_string,
)

__all__ = [
    # external.py
    "CommandResult",
    "check_git_installed",
    "check_node_installed",
    "check_npm_installed",
    "run_command",
    "which",
    # installer.py
    "ensure_tool_installed",
    "get_tools_dir",
    "is_tool_available",
    "list_installed_tools",
    # svg_bbox.py
    "BoundingBox",
    "ComparisonResult",
    "compare_svgs",
    "get_bounding_boxes",
    # svg_validator.py
    "SVGValidationResult",
    "validate_svg_file",
    "validate_svg_string",
    "validate_svg_batch",
]
