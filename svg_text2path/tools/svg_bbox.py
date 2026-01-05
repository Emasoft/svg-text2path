"""SVG bounding box and comparison tools using npm svg-bbox package.

This module wraps the svg-bbox npm package for visual SVG comparison and
bounding box computation. It provides Python bindings to sbb-compare and
sbb-getbbox CLI tools.

Why: svg-bbox provides accurate Chrome-based rendering for pixel-perfect
visual comparisons that match browser behavior.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from svg_text2path.tools.external import CommandResult, run_command


@dataclass
class BoundingBox:
    """Visual bounding box of an SVG element.

    Attributes:
        x: Left edge coordinate
        y: Top edge coordinate
        width: Box width
        height: Box height
    """

    x: float
    y: float
    width: float
    height: float


@dataclass
class ComparisonResult:
    """Result of visual SVG comparison.

    Attributes:
        diff_percent: Percentage of differing pixels (0-100)
        html_path: Path to HTML comparison report (if generated)
        diff_image_path: Path to diff PNG image (if generated)
        success: True if comparison completed successfully
        error: Error message if comparison failed
    """

    diff_percent: float
    html_path: Path | None
    diff_image_path: Path | None
    success: bool
    error: str | None


def _find_svg_bbox_bin(tool: str) -> Path | None:
    """Find svg-bbox tool binary in node_modules or via npx.

    Args:
        tool: Tool name (e.g., "sbb-compare", "sbb-getbbox")

    Returns:
        Path to binary if found, None otherwise

    Why: Check local node_modules first for faster execution, fall back to npx
    """
    # Check if we're in a project with node_modules - why: local install is faster
    cwd = Path.cwd()
    possible_paths = [
        cwd / "node_modules" / ".bin" / tool,  # Current directory
        cwd.parent / "node_modules" / ".bin" / tool,  # Parent directory
    ]

    for path in possible_paths:
        if path.exists() and path.is_file():
            return path

    # Binary not found locally - caller should try npx
    return None


def _run_svg_bbox_command(
    tool: str,
    args: list[str],
    timeout: int = 300,
) -> CommandResult:
    """Run an svg-bbox CLI tool with arguments.

    Args:
        tool: Tool name (e.g., "sbb-compare", "sbb-getbbox")
        args: Command line arguments
        timeout: Timeout in seconds (default: 300)

    Returns:
        CommandResult with output and status

    Why: Centralized execution logic with local bin preference
    """
    # Try local node_modules binary first - why: faster than npx
    bin_path = _find_svg_bbox_bin(tool)

    # Use local binary if found, otherwise fall back to npx
    if bin_path:  # noqa: SIM108
        # Use local binary directly - why: avoid npx overhead
        cmd = [str(bin_path)] + args
    else:
        # Fall back to npx - why: will download and run if needed
        cmd = ["npx", tool] + args

    return run_command(cmd, timeout=timeout)


def compare_svgs(
    svg1_path: Path | str,
    svg2_path: Path | str,
    output_dir: Path | str | None = None,
    output_html: bool = True,
) -> ComparisonResult:
    """Compare two SVGs using svg-bbox's sbb-compare.

    Args:
        svg1_path: Path to first SVG (reference)
        svg2_path: Path to second SVG (to compare)
        output_dir: Directory for output files (default: same as svg2)
        output_html: Generate HTML comparison report (default: True)

    Returns:
        ComparisonResult with diff percentage and output paths

    Raises:
        No exceptions - errors returned in ComparisonResult.error

    Why: Provides pixel-perfect visual comparison using Chrome rendering
    """
    # Convert paths to Path objects - why: consistent path handling
    svg1 = Path(svg1_path)
    svg2 = Path(svg2_path)

    # Validate input files exist - why: fail fast with clear error
    if not svg1.exists():
        return ComparisonResult(
            diff_percent=100.0,
            html_path=None,
            diff_image_path=None,
            success=False,
            error=f"Reference SVG not found: {svg1}",
        )

    if not svg2.exists():
        return ComparisonResult(
            diff_percent=100.0,
            html_path=None,
            diff_image_path=None,
            success=False,
            error=f"Comparison SVG not found: {svg2}",
        )

    # Determine output directory - why: default to svg2's directory for convenience
    if output_dir is None:
        out_dir = svg2.parent
    else:
        out_dir = Path(output_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

    # Generate output file paths - why: predictable naming based on input files
    svg1_name = svg1.stem
    svg2_name = svg2.stem
    diff_png = out_dir / f"{svg1_name}_vs_{svg2_name}_diff.png"
    html_report = out_dir / f"{svg1_name}_vs_{svg2_name}_comparison.html"

    # Build command arguments - why: request JSON output for parsing
    args = [
        str(svg1),
        str(svg2),
        "--json",  # Get machine-readable output
        "--out-diff",
        str(diff_png),  # Save diff image
    ]

    if not output_html:
        # Suppress HTML report generation - why: user doesn't want it
        args.append("--no-html")

    # Run comparison - why: execute sbb-compare with timeout protection
    result = _run_svg_bbox_command("sbb-compare", args)

    if not result.success:
        # Command failed - why: return error details
        return ComparisonResult(
            diff_percent=100.0,
            html_path=None,
            diff_image_path=None,
            success=False,
            error=f"sbb-compare failed: {result.stderr}",
        )

    # Parse JSON output - why: extract diff percentage and file paths
    try:
        # sbb-compare outputs JSON to stdout when --json is used
        data = json.loads(result.stdout)

        # Extract diff percentage - why: primary comparison metric
        diff_percent = float(data.get("diffPercent", 0.0))

        # Check if output files were created - why: verify expected outputs exist
        html_path = html_report if output_html and html_report.exists() else None
        diff_path = diff_png if diff_png.exists() else None

        return ComparisonResult(
            diff_percent=diff_percent,
            html_path=html_path,
            diff_image_path=diff_path,
            success=True,
            error=None,
        )

    except (json.JSONDecodeError, KeyError, ValueError) as e:
        # JSON parsing failed - why: malformed output from sbb-compare
        return ComparisonResult(
            diff_percent=100.0,
            html_path=None,
            diff_image_path=None,
            success=False,
            error=f"Failed to parse sbb-compare output: {e}",
        )


def get_bounding_boxes(
    svg_path: Path | str,
) -> dict[str, BoundingBox]:
    """Get bounding boxes of elements using sbb-getbbox.

    Args:
        svg_path: Path to SVG file

    Returns:
        Dictionary mapping element IDs to BoundingBox objects.
        Empty dict if no elements found or on error.

    Raises:
        No exceptions - errors logged, empty dict returned

    Why: Provides accurate visual bounding boxes matching Chrome rendering
    """
    # Convert to Path object - why: consistent path handling
    svg = Path(svg_path)

    # Validate input file exists - why: fail fast with clear error
    if not svg.exists():
        return {}

    # Build command arguments - why: request JSON output to stdout
    args = [
        str(svg),
        "--json",
        "-",  # Output JSON to stdout
    ]

    # Run bounding box computation - why: execute sbb-getbbox
    result = _run_svg_bbox_command("sbb-getbbox", args)

    if not result.success:
        # Command failed - why: return empty dict (no exceptions)
        return {}

    # Parse JSON output - why: extract bounding box data
    try:
        # sbb-getbbox outputs JSON to stdout when --json - is used
        data: dict[str, Any] = json.loads(result.stdout)

        # Convert to BoundingBox objects - why: type-safe API
        boxes: dict[str, BoundingBox] = {}

        # Handle both single-element and multi-element responses
        # Why: sbb-getbbox format varies based on query
        if isinstance(data, dict):
            for elem_id, bbox_data in data.items():
                if isinstance(bbox_data, dict):
                    boxes[elem_id] = BoundingBox(
                        x=float(bbox_data.get("x", 0.0)),
                        y=float(bbox_data.get("y", 0.0)),
                        width=float(bbox_data.get("width", 0.0)),
                        height=float(bbox_data.get("height", 0.0)),
                    )

        return boxes

    except (json.JSONDecodeError, KeyError, ValueError, TypeError):
        # JSON parsing failed - why: malformed output, return empty dict
        return {}
